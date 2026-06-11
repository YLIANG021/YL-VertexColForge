# -*- coding: utf-8 -*-
"""Paint calculations for the local brush operator."""

import numpy as np
from bpy_extras import view3d_utils
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree

from ... import utils
from ...core.blend import blend_colors_np
from ...core.color_attribute import read_color_attribute_colors
from ...core.color_channels import channel_indices, clamp_factor, normalize_write_value
from ...core.mesh_topology import loop_vertex_indices, vertex_positions


SPATIAL_INDEX_MIN_SIZE = 50000


def brush_falloff(values, hardness):
    values = np.asarray(values, dtype=np.float32)
    hardness = clamp_factor(hardness)
    if hardness >= 1.0:
        return np.ones_like(values, dtype=np.float32)

    soft_width = max(1.0 - hardness, 1e-6)
    softened = np.clip(values / soft_width, 0.0, 1.0)
    result = softened * softened * (3.0 - 2.0 * softened)
    if hardness > 0.0:
        result[values >= soft_width] = 1.0
    return result


def mesh_world_positions(obj):
    local_positions = vertex_positions(obj.data)
    if local_positions.size == 0:
        return np.zeros((0, 3), dtype=np.float32)

    matrix = np.array(obj.matrix_world, dtype=np.float32)
    return local_positions @ matrix[:3, :3].T + matrix[:3, 3]


def build_bvh(mesh):
    if len(mesh.vertices) == 0 or len(mesh.polygons) == 0:
        return None

    verts = [vert.co.copy() for vert in mesh.vertices]
    polygons = [tuple(poly.vertices) for poly in mesh.polygons if poly.loop_total >= 3]
    if not polygons:
        return None
    return BVHTree.FromPolygons(verts, polygons)


def current_brush_value(context):
    scene = context.scene
    channel_key = scene.ylvc_channel
    holder = utils.get_color_holder(context)
    if holder is None:
        return None

    if channel_key == "RGB":
        return (holder.color[0], holder.color[1], holder.color[2], scene.ylvc_alpha_fg)
    return scene.ylvc_single_fg


def build_paint_cache(obj, color_attr, domain):
    colors = read_color_attribute_colors(obj.data, color_attr)
    world_positions = mesh_world_positions(obj)
    if domain == "POINT":
        data_positions = world_positions
    else:
        loop_indices = loop_vertex_indices(obj.data)
        data_positions = world_positions[loop_indices] if len(loop_indices) else np.zeros((0, 3), dtype=np.float32)
    return colors, world_positions, data_positions


def paintable_data_subset(data_positions, selection_mask):
    indices = np.flatnonzero(selection_mask)
    if len(indices) == 0:
        empty = np.zeros((0, 3), dtype=np.float32)
        return indices, empty
    return indices, data_positions[indices]


def build_position_spatial_index(positions, min_size=SPATIAL_INDEX_MIN_SIZE):
    if positions is None or len(positions) < int(min_size):
        return None

    tree = KDTree(len(positions))
    for index, position in enumerate(positions):
        tree.insert((float(position[0]), float(position[1]), float(position[2])), index)
    tree.balance()
    return tree


def _surface_tangent(normal):
    normal = Vector(normal).normalized()
    reference = Vector((0.0, 0.0, 1.0))
    if abs(normal.dot(reference)) > 0.96:
        reference = Vector((1.0, 0.0, 0.0))
    return normal.cross(reference).normalized()


def world_radius_for_screen_radius(region, region_data, center, normal, screen_radius):
    if region is None or region_data is None or center is None or normal is None:
        return 0.0
    screen_radius = max(float(screen_radius), 0.0)
    if screen_radius <= 0.0:
        return 0.0

    center = Vector(center)
    tangent = _surface_tangent(normal)
    center_2d = view3d_utils.location_3d_to_region_2d(region, region_data, center)
    unit_edge_2d = view3d_utils.location_3d_to_region_2d(region, region_data, center + tangent)
    if center_2d is None or unit_edge_2d is None:
        return 0.0

    pixels_per_world_unit = (unit_edge_2d - center_2d).length
    if pixels_per_world_unit <= 1e-6:
        return 0.0
    return max(screen_radius / pixels_per_world_unit, 1e-6)


def world_brush_indices(positions, hit_world, radius, spatial_index=None):
    if hit_world is None or positions.size == 0:
        return np.zeros(0, dtype=np.int64), np.zeros(0, dtype=np.float32)

    radius = max(float(radius), 1e-6)
    if spatial_index is not None:
        hits = spatial_index.find_range(hit_world, radius)
        if not hits:
            return np.zeros(0, dtype=np.int64), np.zeros(0, dtype=np.float32)
        local_indices = np.fromiter((item[1] for item in hits), dtype=np.int64, count=len(hits))
        distances = np.fromiter((item[2] for item in hits), dtype=np.float32, count=len(hits))
        return local_indices, distances

    hit = np.array((hit_world.x, hit_world.y, hit_world.z), dtype=np.float32)
    offsets = positions - hit
    distances_sq = np.einsum("ij,ij->i", offsets, offsets)
    active_mask = distances_sq <= radius * radius
    if not np.any(active_mask):
        return np.zeros(0, dtype=np.int64), np.zeros(0, dtype=np.float32)

    local_indices = np.flatnonzero(active_mask)
    distances = np.sqrt(distances_sq[local_indices]).astype(np.float32, copy=False)
    return local_indices, distances


def raycast_surface_hit(region, region_data, mouse_x, mouse_y, *, bvh, world_matrix, world_matrix_inv):
    if bvh is None or region is None or region_data is None:
        return None, None

    coord = (mouse_x, mouse_y)
    origin = view3d_utils.region_2d_to_origin_3d(region, region_data, coord)
    direction = view3d_utils.region_2d_to_vector_3d(region, region_data, coord)
    local_origin = world_matrix_inv @ origin
    local_direction = (world_matrix_inv.to_3x3() @ direction).normalized()
    hit_location, hit_normal, _face_index, _distance = bvh.ray_cast(local_origin, local_direction)
    if hit_location is None:
        return None, None

    hit_world = world_matrix @ hit_location
    hit_normal_world = (world_matrix_inv.transposed().to_3x3() @ hit_normal).normalized()
    return hit_world, hit_normal_world


def paint_at_hit(
    context,
    *,
    hit_world,
    data_indices,
    data_positions,
    spatial_index=None,
    colors,
    channel_key,
    radius=None,
    undo_recorder=None,
):
    if hit_world is None or data_positions.size == 0:
        return 0

    scene = context.scene
    radius = max(float(scene.ylvc_brush_radius if radius is None else radius), 1e-6)
    strength = clamp_factor(scene.ylvc_brush_strength)
    if strength <= 0.0:
        return 0

    brush_value = current_brush_value(context)
    if brush_value is None:
        return 0

    source_values = normalize_write_value(brush_value, channel_key)
    local_indices, distances = world_brush_indices(data_positions, hit_world, radius, spatial_index=spatial_index)
    if len(local_indices) == 0:
        return 0

    active_indices = data_indices[local_indices]

    _capture_undo_colors(colors, active_indices, undo_recorder)
    falloff = 1.0 - np.clip(distances / radius, 0.0, 1.0)
    factors = brush_falloff(falloff, scene.ylvc_brush_softness) * strength
    channels = channel_indices(channel_key)
    blend_mode = getattr(scene, "ylvc_write_blend_mode", "REPLACE")

    if channel_key == "RGB" and blend_mode == "REPLACE":
        target_rgb = np.asarray(source_values[:3], dtype=np.float32)
        current_rgb = colors[active_indices, 0:3]
        current_rgb += (target_rgb - current_rgb) * factors[:, None]
        np.clip(current_rgb, 0.0, 1.0, out=current_rgb)
        colors[active_indices, 0:3] = current_rgb
        return int(active_indices.size)

    source = colors[active_indices].copy()
    for offset, channel in enumerate(channels):
        source[:, channel] = float(source_values[offset])

    blended = colors[active_indices].copy()
    blend_colors_np(blended, source, channel_key, blend_mode)
    result = colors[active_indices] + (blended - colors[active_indices]) * factors[:, None]
    colors[active_indices] = np.clip(result, 0.0, 1.0)

    return int(active_indices.size)


def _capture_undo_colors(colors, active_indices, undo_recorder):
    if undo_recorder is None or len(active_indices) == 0:
        return

    captured_mask = undo_recorder.get("mask")
    if captured_mask is None:
        return

    new_mask = ~captured_mask[active_indices]
    if not np.any(new_mask):
        return

    new_indices = active_indices[new_mask]
    undo_recorder.setdefault("indices", []).append(new_indices.copy())
    undo_recorder.setdefault("colors", []).append(colors[new_indices].copy())
    captured_mask[new_indices] = True
