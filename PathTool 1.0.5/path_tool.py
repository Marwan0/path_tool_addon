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

from .utils import PathUtils, PathUndo
from .draw_utils import (create_batch_control_points, create_batch_path, draw_callback_3d)

class VIEW3D_OT_select_path(bpy.types.Operator, PathUtils, PathUndo):
    bl_idname = "view3d.select_path"
    bl_label = "Select Path"
    bl_description = "An interactive tool for selecting elements of a mesh object by constructing an editable path"

    bl_options = {'REGISTER', 'UNDO'}

    def preperty_update_callback(self, context):
        self.should_update = True

    # (identifier, name, description, icon, number)
    mark_select: bpy.props.EnumProperty(
        items = [("Extend", "Extend", "Extend existing selection", 'SELECT_EXTEND', 1),
                 ("None", "Do nothing", "Do nothing", "X", 2),
                 ("Subtract", "Subtract", "Subtract existing selection", 'SELECT_SUBTRACT', 3),
                 ("Invert", "Invert", "Inverts existing selection", 'SELECT_DIFFERENCE', 4)],
        name = "Select",
        default = "Extend",
        description = "Selection options",
        update = preperty_update_callback)

    mark_seam: bpy.props.EnumProperty(
        items = [("Mark", "Mark", "Mark seam path elements", 'RESTRICT_SELECT_OFF', 1),
                 ("None", "Do nothing", "Do nothing", 'X', 2),
                 ("Clear", "Clear", "Clear seam path elements", 'RESTRICT_SELECT_ON', 3),
                 ("Toogle", "Toogle", "Toogle seams on path", 'ACTION_TWEAK', 4)],
        name = "Seams",
        default = "None",
        description = "Mark seam on path options",
        update = preperty_update_callback)

    mark_sharp: bpy.props.EnumProperty(
        items = [("Mark", "Mark", "Mark sharp path elements", 'RESTRICT_SELECT_OFF', 1),
                 ("None", "Do nothing", "Do nothing", 'X', 2),
                 ("Clear", "Clear", "Clear sharp path elements", 'RESTRICT_SELECT_ON', 3),
                 ("Toogle", "Toogle", "Toogle sharpness on path", 'ACTION_TWEAK', 4)],
        name = "Sharp",
        default = "None",
        description = "Mark sharp on path options",
        update = preperty_update_callback)

    set_to_tool: bpy.props.BoolProperty(
        name = "Apply Tool Settings",
        description = "Apply settings to workspace tool",
        default = True,
        update = preperty_update_callback)

    fill_gap: bpy.props.BoolProperty(
        name = "Fill Gap",
        description = "Fill gap beetween first and last control points",
        default = False,
        update = preperty_update_callback)

    mouse_reverse: bpy.props.BoolProperty(
        name = "Switch Direction",
        description = "Switch path direction",
        default = False)

    undo_one: bpy.props.BoolProperty(name = "Undo", default = False, description = "Undo for one step")
    redo_one: bpy.props.BoolProperty(name = "Redo", default = False, description = "Redo for one step")
    confirm_path: bpy.props.BoolProperty(name = "", default = False, description = "Confirm path")
    should_update: bpy.props.BoolProperty(name = "", default = False)

    @classmethod
    def poll(cls, context):
        if context.area.type != 'VIEW_3D':
            return False
        tool = bpy.context.workspace.tools.from_space_view3d_mode('EDIT_MESH', create = False)
        tool_idname = None
        if tool:
            tool_idname = tool.idname

        if tool_idname != "view3d.path_selection_tool":
            return False
        elif not context.object:
            return False
        elif context.object.type != 'MESH':
            return False
        elif not context.object.data.is_editmode:
            return False

        return True

    def invoke(self, context, event):
        self.create_bmesh(context)
        self.mesh_select_mode(context)
        self.set_properties(context)
        if not self.chech_first_click(context, event):
            return {'CANCELLED'}
        PathUndo.__init__(self)
        self.register_handlers((self, context, event), context)

        context.workspace.status_text_set("Enter/Space: confirm path, Esc: cancel, LMB: add point, " \
                                          "RMB: Open context menu, LMB+Ctrl: remove control point, " \
                                          "Alt: reverse active point to other side, C: toogle fill cap, " \
                                          "Ctrl+Z: undo, Ctrl+Alt+Z: redo")

        self.modal(context, event)

        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if context.area:
            context.area.tag_redraw()

        evkey = (event.alt, event.ctrl, event.shift, event.type, event.value)

        nnume = []
        for n in range(10):
            nnume.append((False, False, False, 'NUMPAD_%d' % n, 'PRESS'))
            nnume.append((False, False, True, 'NUMPAD_%d' % n, 'PRESS'))
            nnume.append((False, True, False, 'NUMPAD_%d' % n, 'PRESS'))
        if evkey in nnume:
            return {'PASS_THROUGH'}
        elif evkey in (
                (False, False, False, 'MIDDLEMOUSE', 'PRESS'),
                (False, True, False, 'MIDDLEMOUSE', 'PRESS'),
                (False, False, True, 'MIDDLEMOUSE', 'PRESS'),
                (False, False, False, 'WHEELDOWNMOUSE', 'PRESS'),
                (False, False, False, 'WHEELUPMOUSE', 'PRESS'),
                (False, False, False, 'NUMPAD_PERIOD', 'PRESS'),
                (False, False, True, 'C', 'PRESS')
        ):
            return {'PASS_THROUGH'}

        elif evkey == (False, False, False, 'ESC', 'PRESS'):
            self.cancel(context)
            return {'CANCELLED'}

        elif evkey in ((False, False, False, 'RET', 'PRESS'),
                       (False, False, False, 'NUMPAD_ENTER', 'PRESS'),
                       (False, False, False, 'SPACE', 'PRESS')) or self.confirm_path:
            self.prepare_for_execute(context)
            self.execute(context)
            self.unregister_handlers(context)
            return {'FINISHED'}

        elif evkey == (False, False, False, 'LEFTMOUSE', 'PRESS'):
            self.mouse_press = True

        elif evkey in ((False, True, False, 'LEFTMOUSE', 'PRESS'),
                       (False, False, False, 'LEFTMOUSE', 'DOUBLE_CLICK')):
            self.mouse_remove = True
            self.mouse_press = False

        elif evkey in ((False, False, False, 'LEFTMOUSE', 'RELEASE'),
                       (False, True, False, 'LEFTMOUSE', 'RELEASE')):
            self.drag = False
            self.mouse_press = False
            self.mouse_remove = False
            self.register_undo_step()
            self.check_doubles(context)
            self.drag_element = None
            self.drag_element_index = None


        elif evkey in ((True, False, False, 'LEFT_ALT', 'PRESS'),
                       (True, False, False, 'RIGHT_ALT', 'PRESS')):
            if self.fill_gap == False:
                self.mouse_reverse = True

        elif evkey == (False, True, False, 'Z', 'PRESS') or self.undo_one:
            self.undo_one = False
            return self.undo(context)

        elif evkey == (True, True, False, 'Z', 'PRESS') or self.redo_one:
            self.redo_one = False
            self.redo()

        elif evkey == (False, False, False, 'C', 'PRESS'):
            self.fill_gap = (not self.fill_gap)
            self.update_fill_path()


        elif evkey == (False, False, False, 'RIGHTMOUSE', 'PRESS'):
            wm = context.window_manager
            wm.popover(self.popover_draw, ui_units_x = 12)

        if self.mouse_reverse == True:
            self.switch_direction()

        if self.mouse_remove == True:
            elem = self.get_element_by_mouse(context, event)
            if elem:
                self.on_click(elem, True)

        if self.mouse_press:
            elem = self.get_element_by_mouse(context, event)
            if elem:
                if evkey == (False, False, False, 'MOUSEMOVE', 'PRESS'):
                    self.drag = True

                if self.drag == True:
                    self.drag_element_by_mouse(elem)
                else:
                    self.on_click(elem, False)

        self.mouse_reverse = False

        if self.should_update:
            self.should_update = False
            tools = bpy.context.workspace.tools
            tool = tools.from_space_view3d_mode('EDIT_MESH', create = False)
            tool_props = tool.operator_properties("view3d.select_path")

            if self.set_to_tool == True:
                for attr in ("mark_select", "mark_seam", "mark_sharp"):
                    setattr(tool_props, attr, getattr(self, attr))

            self.update_fill_path()
            self.create_batches()

        self.set_selection(self.original_select)
        self.bm.select_flush_mode()

        return {'RUNNING_MODAL'}

    def execute(self, context):
        if context.area:
            context.area.tag_redraw()

        self.create_bmesh(context)

        elems = getattr(self.bm, self.mesh_elements)
        path = [elem for elem
                in elems if elem.index in self.path_indices]
        for elem in path:
            if self.mark_select == "Extend":
                elem.select_set(True)
            elif self.mark_select == "Subtract":
                elem.select_set(False)
            elif self.mark_select == "Invert":
                elem.select_set((not elem.select))
        if self.mesh_elements == "edges":
            edges = path
        if self.mesh_elements == "faces":
            edges = []
            for elem in path:
                for edge in elem.edges:
                    if not edge in edges:
                        edges.append(edge)
        for elem in edges:
            if self.mark_seam == "Mark":
                elem.seam = True
            elif self.mark_seam == "Clear":
                elem.seam = False
            elif self.mark_seam == "Toogle":
                elem.seam = (not elem.seam)

            if self.mark_sharp == "Mark":
                elem.smooth = False
            elif self.mark_sharp == "Clear":
                elem.smooth = True
            elif self.mark_sharp == "Toogle":
                elem.smooth = (not elem.smooth)

        tools = bpy.context.workspace.tools
        tool = tools.from_space_view3d_mode('EDIT_MESH', create = False)
        tool_props = tool.operator_properties("view3d.select_path")

        if self.set_to_tool == True:
            if self.set_to_tool == True:
                for attr in ("mark_select", "mark_seam", "mark_sharp"):
                    setattr(tool_props, attr, getattr(self, attr))
        self.update_mesh(context)

        return {'FINISHED'}

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False

        row = layout.row()
        row.prop(self, "mark_select", text = "Select", icon_only = True, expand = True)
        row = layout.row()
        row.prop(self, "mark_seam", text = "Seam", icon_only = True, expand = True)
        row = layout.row()
        row.prop(self, "mark_sharp", text = "Sharp", icon_only = True, expand = True)
        layout.prop(self, "set_to_tool")

    def popover_draw(self, popover, context):
        layout = popover.layout
        layout.label(text = "Path Tool Options:", icon = 'TOOL_SETTINGS')
        col = layout.column(align = True)

        col.prop(self, "fill_gap", toggle = True)
        if not self.fill_gap:
            col.prop(self, "mouse_reverse", toggle = True)

        row = col.row()
        scol = row.column()
        scol.label(text = "Select:")
        scol.row().prop(self, "mark_select", text = "Select", icon_only = True, expand = True)
        scol = row.column()
        scol.label(text = "Seams:")
        scol.row().prop(self, "mark_seam", text = "Seam", icon_only = True, expand = True)
        scol = row.column()
        scol.label(text = "Sharp:")
        scol.row().prop(self, "mark_sharp", text = "Sharp", icon_only = True, expand = True)
        col.prop(self, "set_to_tool")

        row = col.row(align = True)
        srow = row.row()
        srow.enabled = (len(self.undo_history) > 0)
        srow.prop(self, "undo_one", icon = 'LOOP_BACK')
        srow = row.row()
        srow.enabled = (len(self.redo_history) > 0)
        srow.prop(self, "redo_one", icon = 'LOOP_FORWARDS')

        label = "Apply Path"
        row = col.row()
        row.scale_y = 1.5
        row.prop(self, "confirm_path", text = label, toggle = True)
