import pathlib
import sys

import bpy
import numpy as np


TEST_DIR = pathlib.Path(__file__).resolve().parent
ADDON_DIR = TEST_DIR.parent
sys.path.insert(0, str(ADDON_DIR.parent))

import yl_vertexcolforge as addon
from yl_vertexcolforge.core.color_attribute import (
    INTERNAL_PREVIEW_ATTRIBUTE_NAME,
    get_color_attribute_by_name,
    read_color_attribute_colors,
    resolve_target_color_attribute,
    set_active_color_attribute,
    set_scene_selected_color_attribute_name,
    write_color_attribute_colors,
)
from yl_vertexcolforge.features.color import ops_preview


def clear_scene():
    if bpy.ops.object.mode_set.poll():
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    for image in list(bpy.data.images):
        bpy.data.images.remove(image)
    for material in list(bpy.data.materials):
        bpy.data.materials.remove(material)


def set_active_obj(obj):
    if bpy.ops.object.mode_set.poll():
        bpy.ops.object.mode_set(mode="OBJECT")
    for item in bpy.context.scene.objects:
        item.select_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def create_grid_object(name, x_offset=0.0):
    verts = [
        (0 + x_offset, 0, 0),
        (1 + x_offset, 0, 0),
        (2 + x_offset, 0, 0),
        (0 + x_offset, 1, 0),
        (1 + x_offset, 1, 0.25),
        (2 + x_offset, 1, 0),
        (0 + x_offset, 2, 0),
        (1 + x_offset, 2, 0),
        (2 + x_offset, 2, 0.1),
    ]
    faces = [(0, 1, 4, 3), (1, 2, 5, 4), (3, 4, 7, 6), (4, 5, 8, 7)]
    mesh = bpy.data.meshes.new(name + "Mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)

    uv = mesh.uv_layers.new(name="UVMap")
    for poly in mesh.polygons:
        for li in poly.loop_indices:
            vi = mesh.loops[li].vertex_index
            co = mesh.vertices[vi].co
            uv.data[li].uv = (co.x / 2.0, co.y / 2.0)

    mat_a = bpy.data.materials.new(name + "_MatA")
    mat_b = bpy.data.materials.new(name + "_MatB")
    mesh.materials.append(mat_a)
    mesh.materials.append(mat_b)
    for poly in mesh.polygons:
        poly.material_index = poly.index % 2

    for edge in mesh.edges:
        edge.use_seam = True
        edge.use_edge_sharp = edge.index % 2 == 0

    corner = mesh.color_attributes.new(name="CornerColor", type="FLOAT_COLOR", domain="CORNER")
    point = mesh.color_attributes.new(name="VertexColor", type="FLOAT_COLOR", domain="POINT")
    write_color_attribute_colors(corner, np.zeros((len(corner.data), 4), dtype=np.float32))
    write_color_attribute_colors(point, np.zeros((len(point.data), 4), dtype=np.float32))
    return obj, corner, point


def create_two_face_object(name, x_offset=0.0):
    verts = [(0, 0, 0), (1, 0, 0), (1, 1, 0.1), (0, 1, 0), (2, 0, 0), (2, 1, 0)]
    faces = [(0, 1, 2, 3), (1, 4, 5, 2)]
    mesh = bpy.data.meshes.new(name + "Mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.location.x = x_offset
    corner = mesh.color_attributes.new(name="CornerColor", type="FLOAT_COLOR", domain="CORNER")
    point = mesh.color_attributes.new(name="VertexColor", type="FLOAT_COLOR", domain="POINT")
    write_color_attribute_colors(corner, np.zeros((len(corner.data), 4), dtype=np.float32))
    write_color_attribute_colors(point, np.zeros((len(point.data), 4), dtype=np.float32))
    return obj


def copy_mesh_object(src, name, x_offset=0.0):
    mesh = src.data.copy()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.location.x += x_offset
    return obj


def select_first_half_faces(obj):
    set_active_obj(obj)
    bpy.context.tool_settings.mesh_select_mode = (False, False, True)
    for poly in obj.data.polygons:
        poly.select = poly.index in {0, 1}


def select_first_face(obj, enabled=True):
    set_active_obj(obj)
    for poly in obj.data.polygons:
        poly.select = enabled and poly.index == 0


def data_indices_for_selected_faces(mesh, attr):
    selected_faces = [poly for poly in mesh.polygons if poly.select]
    if attr.domain == "CORNER":
        return np.array([li for poly in selected_faces for li in poly.loop_indices], dtype=np.int64)
    verts = sorted({mesh.loops[li].vertex_index for poly in selected_faces for li in poly.loop_indices})
    return np.array(verts, dtype=np.int64)


def set_layer(obj, attr_or_name):
    attr_name = attr_or_name if isinstance(attr_or_name, str) else attr_or_name.name
    scene = bpy.context.scene
    set_active_obj(obj)
    set_scene_selected_color_attribute_name(scene, attr_name)
    scene.ylvc_layer_name = attr_name
    set_active_color_attribute(obj.data, attr_name)
    target, error = resolve_target_color_attribute(bpy.context, activate=False)
    return target is not None and not error and target.layer_name == attr_name


def reset_attr(attr, value=(0.0, 0.0, 0.0, 0.0)):
    colors = np.zeros((len(attr.data), 4), dtype=np.float32)
    colors[:, :] = value
    write_color_attribute_colors(attr, colors)


def make_test_image(name="YLVC_Test_Image"):
    image = bpy.data.images.new(name, width=8, height=8, alpha=True, float_buffer=True)
    pixels = np.zeros((8 * 8, 4), dtype=np.float32)
    for y in range(8):
        for x in range(8):
            idx = y * 8 + x
            pixels[idx] = (x / 7.0, y / 7.0, 0.25, 0.75)
    image.pixels.foreach_set(pixels.ravel())
    return image


def enable_fake_single_channel_preview(obj, attr_or_name, channel="A", tag="TEST"):
    attr_name = attr_or_name if isinstance(attr_or_name, str) else attr_or_name.name
    set_layer(obj, attr_name)
    bpy.context.scene["ylvc_native_color_preview_spaces"] = f'[{{"space_ptr":"{tag}","area_ptr":"{tag}"}}]'
    bpy.context.scene["ylvc_native_color_preview"] = True
    bpy.context.scene.ylvc_channel = channel
    ops_preview.sync_preview_color_layer_for_context(attr_name, context=bpy.context, force=True)
    return get_color_attribute_by_name(obj.data, INTERNAL_PREVIEW_ATTRIBUTE_NAME, allow_internal=True)


def disable_fake_preview():
    ops_preview.clear_deferred_preview_syncs()
    ops_preview.exit_preview_mode(bpy.context, restore_shading=False, clear_flat_state=True)


def safe_register():
    addon.register()


def safe_unregister():
    try:
        addon.unregister()
    except Exception:
        pass

