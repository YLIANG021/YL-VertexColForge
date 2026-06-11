# -*- coding: utf-8 -*-
import math

import blf
import bpy
import gpu
import numpy as np
from gpu_extras.batch import batch_for_shader


def _draw_arc(center_x, center_y, radius, start_angle, end_angle, color, thickness=3.0, segments=96):
    if end_angle <= start_angle:
        return

    shader = gpu.shader.from_builtin("UNIFORM_COLOR")
    coords = []
    indices = []

    angle_span = end_angle - start_angle
    arc_segments = max(8, int(segments * (angle_span / (math.pi * 2.0))))
    inner_radius = max(0.0, radius - thickness * 0.5)
    outer_radius = radius + thickness * 0.5

    for segment in range(arc_segments + 1):
        t = segment / arc_segments
        angle = start_angle + angle_span * t
        cos_v = math.cos(angle)
        sin_v = math.sin(angle)
        coords.append((center_x + cos_v * inner_radius, center_y + sin_v * inner_radius))
        coords.append((center_x + cos_v * outer_radius, center_y + sin_v * outer_radius))
        if segment < arc_segments:
            index = segment * 2
            indices.append((index, index + 1, index + 2))
            indices.append((index + 2, index + 1, index + 3))

    batch = batch_for_shader(shader, "TRIS", {"pos": coords}, indices=indices)
    gpu.state.blend_set("ALPHA")
    shader.bind()
    shader.uniform_float("color", color)
    batch.draw(shader)
    gpu.state.blend_set("NONE")


def draw_pick_select_overlay(draw_state):
    if not draw_state or not draw_state.get("visible", False):
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

    center_pos = draw_state.get("center_pos")
    tolerance = float(draw_state.get("tolerance", 0.0))
    swatch = draw_state.get("swatch")
    if center_pos is None:
        return

    cx, cy = center_pos
    base_radius = 39.0
    progress_angle = max(0.0, min(1.0, tolerance)) * math.tau
    ring_color = (1.0, 0.15, 0.15, 1.0)

    _draw_arc(cx, cy, base_radius, -math.pi * 0.5 - progress_angle, -math.pi * 0.5, ring_color, thickness=7.5, segments=128)

    font_id = 0
    blf.size(font_id, 12.0)
    blf.color(font_id, 0.96, 0.96, 0.96, 1.0)
    label = f"{tolerance:.3f}"
    text_width, _ = blf.dimensions(font_id, label)
    blf.position(font_id, cx - text_width * 0.5, cy - base_radius - 18.0, 0.0)
    blf.draw(font_id, label)


def draw_pick_select_surface_overlay(draw_state):
    if not draw_state or not draw_state.get("visible", False):
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

    positions = draw_state.get("positions")
    colors = draw_state.get("colors")
    if positions is None or colors is None:
        return
    if len(positions) == 0 or len(colors) == 0:
        return

    if isinstance(colors, np.ndarray) and np.max(colors[:, 3]) <= 1e-6:
        return

    shader = gpu.shader.from_builtin("SMOOTH_COLOR")
    batch = batch_for_shader(shader, "TRIS", {"pos": positions, "color": colors})
    gpu.state.blend_set("ALPHA")
    try:
        gpu.state.depth_test_set("LESS_EQUAL")
    except Exception:
        pass
    shader.bind()
    batch.draw(shader)
    try:
        gpu.state.depth_test_set("NONE")
    except Exception:
        pass
    gpu.state.blend_set("NONE")
