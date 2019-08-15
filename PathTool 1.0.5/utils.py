# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENSE BLOCK #####

# <pep8 compliant>

import bpy
import bmesh
import mathutils
import gpu

from collections import deque
from .draw_utils import (create_batch_control_points, create_batch_path, draw_callback_3d)

class PathUndo:
    def __init__(self):
        self.undo_max_steps = 10
        self.undo_history = deque(maxlen = self.undo_max_steps)  # undo history
        self.redo_history = deque(maxlen = self.undo_max_steps)  # redo history

    def undo(self, context):
        if len(self.undo_history) == 1:
            self.cancel(context)
            return {'CANCELLED'}
        if len(self.undo_history) > 1:
            step = self.undo_history.pop()
            self.redo_history.append(step)
            self.control_elements = self.undo_history[-1].copy()
            self.full_path_update()
        else:
            self.report({'WARNING'}, message = "Can't undo anymore")

        return {"RUNNING_MODAL"}

    def redo(self):
        if len(self.redo_history) > 0:
            step = self.redo_history.pop()
            self.undo_history.append(step)
            self.control_elements = self.undo_history[-1].copy()
            self.full_path_update()
        else:
            self.report({'WARNING'}, message = "Can't redo anymore")

    def register_undo_step(self):
        step = self.control_elements.copy()
        self.undo_history.append(step)
        self.redo_history.clear()

class PathUtils:
    """Utilits for needed for path selection"""

    def mesh_select_mode(self, context):
        """Set 2 modes for select and for view"""
        msm = tuple(context.scene.tool_settings.mesh_select_mode)
        if msm[0] == True or msm[1] == True:
            self.select_mode = (True, False, False)
            self.mesh_mode = (False, True, False)
            self.mesh_elements = "edges"
            if msm != self.mesh_mode:
                self.report({'INFO'}, message = "Select mode changed to Edges only")
        if msm[2] == True:
            self.select_mode = (False, False, True)
            self.mesh_mode = (False, False, True)
            self.mesh_elements = "faces"
            if msm != self.mesh_mode:
                self.report({'INFO'}, message = "Select mode changed to Faces only")
        context.scene.tool_settings.mesh_select_mode = self.mesh_mode

    def chech_first_click(self, context, event):
        """Prevent first click to empty space"""
        elem = self.get_element_by_mouse(context, event)
        if elem:
            return True
        return False

    def set_properties(self, context):
        """Set properties to workspace tool props"""
        tools = bpy.context.workspace.tools
        tool = tools.from_space_view3d_mode('EDIT_MESH', create = False)
        tool_props = tool.operator_properties("view3d.select_path")

        for attr in ("mark_select", "mark_seam", "mark_sharp"):
            setattr(self, attr, getattr(tool_props, attr))

        for attr in ("batch_cp_faces", "batch_cp_verts", "batch_path",
                     "drag_element", "drag_element_index",
                     "mouse_press", "mouse_remove", "drag"):
            setattr(self, attr, None)
        for attr in ("control_elements", "fill_elements",
                     "path_indices", "fill_gap_path"):
            setattr(self, attr, list())

        self.fill_gap = False
        self.original_select = self.selected_elements
        self.shader = gpu.shader.from_builtin('3D_SMOOTH_COLOR')

        addon = "PathTool"
        addons = bpy.context.preferences.addons
        if addon in addons:
            prefs = addons[addon].preferences
            for attr in ("color_active", "color_control_point",
                         "color_fill", "color_face_center",
                         "vertex_size", "edge_width"):
                setattr(self, attr, getattr(prefs, attr))
        else:
            self.color_active = (1.0, 0.7, 0.0, 1.0)
            self.color_control_point = (1.0, 1.0, 1.0, 1.0)
            self.color_fill = (0.0, 0.7, 1.0, 0.7)
            self.color_face_center = (0.4, 0.4, 0.4, 1.0)

            self.vertex_size = 4.0
            self.edge_width = 3.0

    def register_handlers(self, args, context):
        context.window_manager.modal_handler_add(self)
        handle = bpy.types.SpaceView3D.draw_handler_add(draw_callback_3d,
                                                        args, 'WINDOW', 'POST_VIEW')
        self.draw_handle_3d = handle

    def unregister_handlers(self, context):
        bpy.types.SpaceView3D.draw_handler_remove(self.draw_handle_3d, 'WINDOW')
        context.workspace.status_text_set(None)
        self.draw_handle_3d = None

    def create_bmesh(self, context):
        """Create bmesh from object"""
        mesh = context.edit_object.data
        self.bm = bmesh.from_edit_mesh(mesh)
        for n in (self.bm.verts, self.bm.edges, self.bm.faces):
            n.ensure_lookup_table()

    def update_mesh(self, context):
        """Update context editmesh and selection"""
        self.bm.select_flush_mode()
        bmesh.update_edit_mesh(context.active_object.data, False, False)
        context.scene.tool_settings.mesh_select_mode = self.mesh_mode

    def get_element_by_mouse(self, context, event):
        """
        Get element by mouse. First selected element define which
        part of mesh can contain next control points
        Return's: for face mode - face, for edge mode - vertex
        """
        context.scene.tool_settings.mesh_select_mode = self.select_mode
        #
        mloc = (event.mouse_region_x, event.mouse_region_y)
        ret = bpy.ops.view3d.select(location = mloc)
        elem = None
        if 'FINISHED' in ret:
            elem = self.bm.select_history.active
            if len(self.control_elements) == 0:
                bpy.ops.mesh.select_linked(delimit = {'NORMAL'})
                if self.mesh_elements == "faces":
                    self.path_on_indices = [n.index for n
                                            in self.selected_elements]
                elif self.mesh_elements == "edges":
                    self.path_on_indices = [n.index for n
                                            in [v for v in self.bm.verts if v.select == True]]
                self.deselect_all()
            if elem:
                elem.select_set(False)

        context.scene.tool_settings.mesh_select_mode = self.mesh_mode

        if elem != None:
            if elem.index in self.path_on_indices:
                return elem
            else:
                self.report({'INFO'},
                            message = "Can't make path on another part of mesh")

    def switch_direction(self):
        """Reverse direction of lists and redraw"""
        self.control_elements.reverse()
        self.fill_elements.reverse()
        self.create_batches()

    def drag_element_by_mouse(self, elem):
        """Called when drag"""
        if self.drag_element:
            if self.drag_element in self.control_elements:
                ii = self.control_elements.index(self.drag_element)
                if self.drag_element_index != None:
                    self.control_elements[self.drag_element_index] = elem

        if self.drag_element == None:
            self.drag_element = elem
            if self.drag_element in self.control_elements:
                self.drag_element_index = self.control_elements.index(elem)

        elif self.drag_element != elem:
            self.drag_element = elem

        if self.drag_element_index != None:
            self.update_by_element(self.drag_element_index)

    def on_click(self, elem, remove = False):
        """Called when user clicked on mesh"""
        if remove == False:
            if not elem in self.control_elements:
                if elem in self.fill_points:
                    ii = self.get_fillelements_index(elem)
                    self.control_elements.insert(ii + 1, elem)
                    self.fill_elements.insert(ii, [])  # play with ii+/-1
                else:
                    self.control_elements.append(elem)
                    if len(self.control_elements) > 1:
                        self.fill_elements.append([])
                    ii = len(self.control_elements) - 1
                self.update_by_element(ii)
        else:
            self.remove_element(elem)

    def remove_element(self, elem):
        """Removing control point"""
        if elem in self.control_elements:
            self.control_elements.remove(elem)
            self.full_path_update()

    def full_path_update(self):
        """`Update path from every second control point"""
        self.fill_elements = [[] for n in range(len(self.control_elements) - 1)]
        for ii in list(range(len(self.control_elements)))[::2]:
            self.update_by_element(ii)
        self.set_selection(self.original_select)

    def update_by_element(self, elem_ind):
        """Update path from and to element by given index"""
        ll = len(self.control_elements)
        if ((elem_ind > (ll - 1)) or (ll < 2)):
            self.create_batches()
            return
        elem = self.control_elements[elem_ind]

        if elem_ind == 0:
            pairs = [[elem, self.control_elements[1], 0]]
        elif elem_ind == len(self.control_elements) - 1:
            pairs = [[elem, self.control_elements[elem_ind - 1], elem_ind - 1]]
        else:
            pairs = [[elem,
                      self.control_elements[elem_ind - 1],
                      elem_ind - 1],
                     [elem,
                      self.control_elements[elem_ind + 1],
                      elem_ind]]

        for pair in pairs:
            p1, p2, fii = pair
            if p1 == p2:
                self.fill_elements[fii] = list()
                continue

            fill = self.update_path_beetween_two(p1, p2)
            self.fill_elements[fii] = fill
            bpy.context.scene.tool_settings.mesh_select_mode = self.mesh_mode

        self.update_fill_path()

        self.create_batches()

    def update_path_beetween_two(self, p1, p2):
        """Update path by 2 given control points"""
        bpy.context.scene.tool_settings.mesh_select_mode = self.select_mode
        self.deselect_all()
        self.set_selection((p1, p2), True)
        bpy.ops.mesh.shortest_path_select()
        self.set_selection((p1, p2), False)
        fill = self.selected_elements
        self.deselect_all()
        if self.mesh_elements == "edges":
            if fill == []:  # Exception if control points in one edge
                for edge in p1.link_edges:
                    if edge.other_vert(p1) == p2:
                        fill = list([edge])
        return fill

    def update_fill_path(self):
        """Update fill path as separate part"""
        if len(self.control_elements) > 2 and self.fill_gap == True:
            p1 = self.control_elements[0]
            p2 = self.control_elements[-1]
            if p1 != p2:
                fill = self.update_path_beetween_two(p1, p2)
                if len(fill) > 0:
                    self.fill_gap_path = fill
            bpy.context.scene.tool_settings.mesh_select_mode = self.mesh_mode

        else:
            self.fill_gap_path = list()

    def deselect_all(self):
        """Deselect all"""
        bpy.ops.mesh.select_all(action = 'DESELECT')

    def set_selection(self, elements, status = True):
        """Set selection status of elements in given list to given status"""
        for elem in elements:
            elem.select_set(status)

    @property
    def fills(self):
        fills = []
        for n in self.fill_elements:
            for elem in n:
                fills.append(elem)
        fills += self.fill_gap_path
        return fills

    def get_fillelements_index(self, elem):
        """Return's index in fills of given element"""
        if self.mesh_elements == "edges":
            for fill in self.fill_elements:
                for edge in fill:
                    if elem in edge.verts:
                        ind = self.fill_elements.index(fill)
                        return ind
        elif self.mesh_elements in ("verts", "faces"):
            for fill in self.fill_elements:
                for n in fill:
                    if elem == n:
                        ind = self.fill_elements.index(fill)
                        return ind

    @property
    def fill_points(self):
        """List of points in all fills"""
        fills = []
        if self.mesh_elements == "edges":
            for elem in self.fill_elements:
                for edge in elem:
                    for v in edge.verts:
                        fills.append(v)
        elif self.mesh_elements in ("verts", "faces"):
            for n in self.fill_elements:
                for elem in n:
                    fills.append(elem)
        return fills

    @property
    def selected_elements(self):
        """Selected elements"""
        return [n for n in getattr(self.bm, self.mesh_elements) if n.select == True]

    def prepare_for_execute(self, context):
        """Write path elements indices to property"""
        self.confirm_path = False
        final_list = self.control_elements + self.fills + self.fill_gap_path
        path = self.get_path()
        for elem in path:
            ii = elem.index
            if not ii in self.path_indices:
                self.path_indices.append(ii)

        self.set_selection(self.original_select)
        self.update_mesh(context)

    def get_path(self):
        path = []
        pl = self.fill_elements + [self.fill_gap_path]
        if self.mesh_elements == "faces":
            pl.extend([self.control_elements])
        for n in pl:
            for elem in n:
                if not elem in path:
                    path.append(elem)
        return path

    def check_doubles(self, context):
        """Check doubles in control points"""
        for n in range(len(self.control_elements) - 1):
            dou = []
            for ii in range(len(self.control_elements)):
                if self.control_elements[ii] == self.control_elements[n]:
                    dou.append(ii)
            if len(dou) > 1:
                p1, p2 = dou
                ll = len(self.control_elements) - 1

                if (p1 == 0 and p2 == ll) and self.fill_gap == False and ll > 2:
                    self.remove_element(self.control_elements[p2])
                    self.fill_gap = True
                    self.report({'INFO'}, message = "Fill cap")

                elif p2 in (p1 + 1, p1 - 1, p1) or (p1 == 0 and p2 == ll):
                    self.remove_element(self.control_elements[p2])
                    self.report({'INFO'},
                                message = "Merged 2 overlapping control points")
                else:
                    self.undo(context)
                    self.report({'INFO'},
                                message = "You should not duplicate control points, undo")

    def create_batches(self):
        path = self.get_path()
        create_batch_path(self, path)
        create_batch_control_points(self)

    def cancel(self, context):
        """Cancel"""
        self.deselect_all()
        self.set_selection(self.original_select, True)
        self.update_mesh(context)
        self.unregister_handlers(context)
