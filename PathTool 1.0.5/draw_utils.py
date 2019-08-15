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
import bgl
from gpu_extras.batch import batch_for_shader

def create_batch_control_points(self):
    matrix_world = bpy.context.active_object.matrix_world
    control_vertices = [elem for elem in self.control_elements if type(elem) == bmesh.types.BMVert]
    control_faces = [elem for elem in self.control_elements if type(elem) == bmesh.types.BMFace]

    if control_vertices:
        vert_positions = [matrix_world @ v.co for v in control_vertices]
        vert_colors = []
        for vertex in control_vertices:
            if self.fill_gap == False or len(self.control_elements) <= 2:
                if vertex == self.control_elements[-1]:
                    vert_colors.append(self.color_active)
                else:
                    vert_colors.append(self.color_control_point)
            else:
                vert_colors.append(self.color_control_point)

        self.batch_cp_verts = batch_for_shader(self.shader, 'POINTS', {"pos": vert_positions, "color": vert_colors})

    if control_faces:
        temp_bmesh = bmesh.new()
        for face in control_faces:
            temp_bmesh.faces.new((temp_bmesh.verts.new(v.co, v) for v in face.verts), face)
        temp_bmesh.verts.index_update()
        temp_bmesh.faces.ensure_lookup_table()

        vert_positions = [matrix_world @ v.co for v in temp_bmesh.verts]
        face_indices = [(loop.vert.index for loop in looptris) for looptris
                        in temp_bmesh.calc_loop_triangles()]

        face_centers = [matrix_world @ f.calc_center_median() for f in temp_bmesh.faces]
        face_center_colors = [self.color_face_center for f in temp_bmesh.faces]

        vert_colors = []
        for vertex in temp_bmesh.verts:
            if self.fill_gap == False or len(self.control_elements) <= 2:
                if vertex in temp_bmesh.faces[-1].verts:
                    vert_colors.append(self.color_active)
                else:
                    vert_colors.append(self.color_control_point)
            else:
                vert_colors.append(self.color_control_point)

        self.batch_cp_faces = batch_for_shader(self.shader, 'TRIS',
                                               {"pos": vert_positions, "color": vert_colors}, indices = face_indices)

        self.batch_cp_verts = batch_for_shader(self.shader, 'POINTS',
                                               {"pos": face_centers, "color": face_center_colors})

def create_batch_path(self, path):
    matrix_world = bpy.context.active_object.matrix_world

    if self.mesh_elements == "faces":
        temp_bmesh = bmesh.new()
        for face in path:
            temp_bmesh.faces.new((temp_bmesh.verts.new(v.co, v) for v in face.verts), face)
        temp_bmesh.verts.index_update()
        temp_bmesh.faces.ensure_lookup_table()

        vert_positions = [matrix_world @ v.co for v in temp_bmesh.verts]
        face_indices = [(loop.vert.index for loop in looptris) for looptris in temp_bmesh.calc_loop_triangles()]
        vert_colors = [self.color_fill for _ in range(len(temp_bmesh.verts))]

        self.batch_path = batch_for_shader(self.shader, 'TRIS',
                                           {"pos": vert_positions, "color": vert_colors}, indices = face_indices)

    elif self.mesh_elements == "edges":
        vert_positions = []
        vert_colors = []
        for edge in path:
            for vert in edge.verts:
                vert_positions.append(matrix_world @ vert.co)
                vert_colors.append(self.color_fill)
        self.batch_path = batch_for_shader(self.shader, 'LINES',
                                           {"pos": vert_positions, "color": vert_colors})

def draw_callback_3d(self, op, context):
    bgl.glPointSize(self.vertex_size)
    bgl.glLineWidth(self.edge_width)

    bgl.glEnable(bgl.GL_MULTISAMPLE)
    bgl.glEnable(bgl.GL_LINE_SMOOTH)
    bgl.glHint(bgl.GL_LINE_SMOOTH_HINT, bgl.GL_NICEST)

    bgl.glBlendFunc(bgl.GL_SRC_ALPHA, bgl.GL_ONE_MINUS_SRC_ALPHA)
    bgl.glEnable(bgl.GL_BLEND)

    bgl.glEnable(bgl.GL_POLYGON_SMOOTH)
    bgl.glHint(bgl.GL_POLYGON_SMOOTH_HINT, bgl.GL_NICEST)

    bgl.glEnable(bgl.GL_DEPTH_TEST)
    bgl.glDepthFunc(bgl.GL_ALWAYS)

    self.shader.bind()
    if self.batch_path:
        self.batch_path.draw(self.shader)
    if self.batch_cp_faces:
        self.batch_cp_faces.draw(self.shader)
    if self.batch_cp_verts:
        self.batch_cp_verts.draw(self.shader)
