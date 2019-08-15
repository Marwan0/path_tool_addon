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

bl_info = {
    "name": "Path Tool",
    "author": "Vlad Kuzmin, Ivan Perevala",
    "version": (1, 0, 5),
    "blender": (2, 80, 0),
    "location": "3D View > Tools > Path Tool",
    "description": "An interactive tool for selecting elements of a mesh object by constructing an editable path",
    "category": "3D View"}

import bpy

from .path_tool import VIEW3D_OT_select_path
from .tools import PathSelectionTool

from shutil import copyfile
import os

class PathToolPreferences(bpy.types.AddonPreferences):
    bl_idname = __name__
    # bl_idname = __package__

    color_active: bpy.props.FloatVectorProperty(
        name = "Active endpoint",
        default = (1.0, 0.7, 0.0, 1.0),
        subtype = "COLOR", size = 4, min = 0.0, max = 1.0)
    color_control_point: bpy.props.FloatVectorProperty(
        name = "Control Point",
        default = (1.0, 1.0, 1.0, 1.0),
        subtype = "COLOR", size = 4, min = 0.0, max = 1.0)
    color_fill: bpy.props.FloatVectorProperty(
        name = "Fill",
        default = (0.0, 0.7, 1.0, 0.7),
        subtype = "COLOR", size = 4, min = 0.0, max = 1.0)
    color_face_center: bpy.props.FloatVectorProperty(
        name = "Face Center",
        default = (0.4, 0.4, 0.4, 1.0),
        subtype = "COLOR", size = 4, min = 0.0, max = 1.0)
    vertex_size: bpy.props.FloatProperty(
        name = "Vertex Size",
        default = 4.0,
        min = 1.0, max = 10.0, subtype = 'PIXEL')
    edge_width: bpy.props.FloatProperty(
        name = "Edge Width",
        default = 3.0,
        min = 1.0, max = 10.0, subtype = 'PIXEL')

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False

        col = layout.column(align = True)
        col.prop(self, "color_active")
        col.prop(self, "color_control_point")
        col.prop(self, "color_fill")
        col.prop(self, "color_face_center")

        col = layout.column(align = True)
        col.prop(self, "vertex_size")
        col.prop(self, "edge_width")

def register_keymap():
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.user
    km = kc.keymaps.get("3D View")
    if km:
        kmi = km.keymap_items.new("view3d.select_path", 'LEFTMOUSE', 'PRESS', head = True)

def add_icon():
    frpath = os.path.join(os.path.abspath(os.path.dirname(os.path.dirname(__file__))),
                          "PathTool", "icons", "ops.generic.path_tool.dat")
    path = os.path.split(bpy.app.binary_path)[0]
    pathto = os.path.join(path, "2.80", "datafiles", "icons", "ops.generic.path_tool.dat")

    if os.path.isfile(frpath) and (not os.path.isfile(pathto)):
        try:
            copyfile(frpath, pathto)
        except:
            print("Icon file not copied!")

def remove_icon():
    path = os.path.split(bpy.app.binary_path)[0]
    pathto = os.path.join(path, "2.80", "datafiles", "icons", "ops.generic.path_tool.dat")
    if os.path.isfile(pathto):
        try:
            os.remove(pathto)
        except:
            print("Icon file not deleted!")

def unregister_keymap():
    kc = bpy.context.window_manager.keyconfigs.user
    km = kc.keymaps.get("3D View")
    kmi = km.keymap_items.find_from_operator("view3d.select_path")
    km.keymap_items.remove(kmi)

def register():
    bpy.utils.register_class(PathToolPreferences)
    bpy.utils.register_class(VIEW3D_OT_select_path)
    register_keymap()
    add_icon()
    bpy.utils.register_tool(PathSelectionTool, after = {"builtin.select_lasso"}, separator = False, group = False)

def unregister():
    bpy.utils.unregister_tool(PathSelectionTool)
    bpy.utils.unregister_class(VIEW3D_OT_select_path)
    bpy.utils.unregister_class(PathToolPreferences)
    unregister_keymap()
    remove_icon()
