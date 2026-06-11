# -*- coding: utf-8 -*-
import math

import bpy
import gpu
from gpu_extras.batch import batch_for_shader

from .core_color_engine import linear_to_srgb, sample_lut_scalar

_OVERLAY_CACHE = {
    "key": None,
    "coords": None,
    "colors": None,
    "indices": None,
    "shadow_coords": None,
    "shadow_colors": None,
}


def _build_overlay_geometry(start_pos, mouse_pos, lut, grad_type="LINEAR"):
    x1, y1 = start_pos
    x2, y2 = mouse_pos
    dx = x2 - x1
    dy = y2 - y1
    length = math.hypot(dx, dy)
    if length < 5.0:
        return None

    normal_x = -dy / length
    normal_y = dx / length
    line_half_width = 4.0
    arrow_length = 30.0
    arrow_half_width = 15.0
    t_base = max(0.0, (length - arrow_length) / length) if length > arrow_length else 0.0
    segments = max(32, min(192, int(length / 3.0)))

    coords = []
    colors = []
    indices = []

    for segment in range(segments + 1):
        t = segment / segments
        point_x = x1 + dx * t
        point_y = y1 + dy * t

        if t <= t_base or t_base == 0.0:
            width = line_half_width
        else:
            arrow_t = (t - t_base) / (1.0 - t_base)
            width = arrow_half_width * (1.0 - arrow_t)

        coords.append((point_x + normal_x * width, point_y + normal_y * width))
        coords.append((point_x - normal_x * width, point_y - normal_y * width))

        color = sample_lut_scalar(lut, t)
        display_color = (
            linear_to_srgb(color[0]),
            linear_to_srgb(color[1]),
            linear_to_srgb(color[2]),
            1.0,
        )
        colors.extend([display_color, display_color])

        if segment < segments:
            index = segment * 2
            indices.append((index, index + 1, index + 2))
            indices.append((index + 2, index + 1, index + 3))

    if grad_type == "RADIAL":
        end_color = sample_lut_scalar(lut, 1.0)
        end_display = (
            linear_to_srgb(end_color[0]),
            linear_to_srgb(end_color[1]),
            linear_to_srgb(end_color[2]),
            1.0,
        )
        ring_half_width = 2.25
        ring_segments = 48
        base_index = len(coords)

        for segment in range(ring_segments + 1):
            angle = (segment / ring_segments) * 2.0 * math.pi
            cos_v = math.cos(angle)
            sin_v = math.sin(angle)
            inner = (x1 + cos_v * (length - ring_half_width), y1 + sin_v * (length - ring_half_width))
            outer = (x1 + cos_v * (length + ring_half_width), y1 + sin_v * (length + ring_half_width))
            coords.extend([inner, outer])
            colors.extend([end_display, end_display])

            if segment < ring_segments:
                index = base_index + segment * 2
                indices.append((index, index + 1, index + 2))
                indices.append((index + 2, index + 1, index + 3))

    start_color = sample_lut_scalar(lut, 0.0)
    start_display = (
        linear_to_srgb(start_color[0]),
        linear_to_srgb(start_color[1]),
        linear_to_srgb(start_color[2]),
        1.0,
    )

    dot_radius = 7.5
    dot_segments = 24
    base_index = len(coords)
    center_index = base_index
    coords.append((x1, y1))
    colors.append(start_display)

    for segment in range(dot_segments + 1):
        angle = (segment / dot_segments) * 2.0 * math.pi
        coords.append((x1 + math.cos(angle) * dot_radius, y1 + math.sin(angle) * dot_radius))
        colors.append(start_display)
        if segment < dot_segments:
            indices.append((center_index, center_index + segment + 1, center_index + segment + 2))

    shadow_coords = []
    offsets = [(-1.25, 1.25), (1.25, -1.25)]
    for offset_x, offset_y in offsets:
        shadow_coords.extend((x + offset_x, y + offset_y) for x, y in coords)

    shadow_indices = []
    coord_count = len(coords)
    for offset_index in range(len(offsets)):
        base_offset = offset_index * coord_count
        for tri in indices:
            shadow_indices.append((tri[0] + base_offset, tri[1] + base_offset, tri[2] + base_offset))

    shadow_colors = [(0.0, 0.0, 0.0, 0.12)] * len(shadow_coords)
    return coords, colors, indices, shadow_coords, shadow_colors, shadow_indices


def draw_gradient_overlay(start_pos, mouse_pos, lut, grad_type="LINEAR"):
    if not start_pos or not mouse_pos or lut is None:
        return

    cache_key = (
        tuple(start_pos),
        tuple(mouse_pos),
        grad_type,
        len(lut),
        tuple(float(v) for v in lut[0]),
        tuple(float(v) for v in lut[-1]),
    )
    if _OVERLAY_CACHE["key"] != cache_key:
        built = _build_overlay_geometry(start_pos, mouse_pos, lut, grad_type=grad_type)
        if built is None:
            _OVERLAY_CACHE["key"] = None
            return
        coords, colors, indices, shadow_coords, shadow_colors, shadow_indices = built
        _OVERLAY_CACHE["key"] = cache_key
        _OVERLAY_CACHE["coords"] = coords
        _OVERLAY_CACHE["colors"] = colors
        _OVERLAY_CACHE["indices"] = indices
        _OVERLAY_CACHE["shadow_coords"] = shadow_coords
        _OVERLAY_CACHE["shadow_colors"] = shadow_colors
        _OVERLAY_CACHE["shadow_indices"] = shadow_indices

    coords = _OVERLAY_CACHE["coords"]
    colors = _OVERLAY_CACHE["colors"]
    indices = _OVERLAY_CACHE["indices"]
    shadow_coords = _OVERLAY_CACHE["shadow_coords"]
    shadow_colors = _OVERLAY_CACHE["shadow_colors"]
    shadow_indices = _OVERLAY_CACHE["shadow_indices"]
    if not coords or not colors or not indices:
        return

    shader = gpu.shader.from_builtin("SMOOTH_COLOR")
    gpu.state.blend_set("ALPHA")
    shader.bind()
    shadow_batch = batch_for_shader(shader, "TRIS", {"pos": shadow_coords, "color": shadow_colors}, indices=shadow_indices)
    shadow_batch.draw(shader)

    main_batch = batch_for_shader(shader, "TRIS", {"pos": coords, "color": colors}, indices=indices)
    main_batch.draw(shader)
    gpu.state.blend_set("NONE")


def draw_gradient_overlay_callback(draw_state):
    if not draw_state:
        return

    target_area_ptr = draw_state.get("area_ptr")
    target_region_ptr = draw_state.get("region_ptr")
    if target_area_ptr or target_region_ptr:
        area = getattr(bpy.context, "area", None)
        region = getattr(bpy.context, "region", None)
        area_ptr = area.as_pointer() if area is not None else None
        region_ptr = region.as_pointer() if region is not None else None

        if target_area_ptr and area_ptr != target_area_ptr:
            return
        if target_region_ptr and region_ptr != target_region_ptr:
            return

    draw_gradient_overlay(
        draw_state.get("start_pos"),
        draw_state.get("mouse_pos"),
        draw_state.get("lut"),
        draw_state.get("grad_type", "LINEAR"),
    )
