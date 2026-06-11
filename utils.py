# -*- coding: utf-8 -*-
"""Legacy compatibility layer for shared YLVC helpers.

New code should import focused helpers from core.* modules. This module keeps
existing call sites stable during the staged architecture migration.
"""

import bpy
import numpy as np

from .core.blend import blend_channel_values
from .core.color_attribute import (
    find_color_layer,
    get_active_color_attribute_safe,
    set_active_color_attribute,
)
from .core.color_channels import (
    CHANNEL_COMPONENTS,
    CHANNEL_LABELS,
    PREVIEW_CHANNEL_INDEX,
    PURE_VISUAL_CHANNELS,
    apply_channel_value,
    build_pure_channel_color,
    clamp_factor,
    copy_channel_values,
    ensure_rgba_sequence,
    sample_channel_value,
)

_BRUSH_CACHE_NAME = None


def average_loop_colors(loops, layer):
    total = [0.0, 0.0, 0.0, 0.0]
    count = 0
    for loop in loops:
        rgba = ensure_rgba_sequence(loop[layer])
        for index, value in enumerate(rgba):
            total[index] += value
        count += 1

    if count == 0:
        return (0.0, 0.0, 0.0, 1.0)

    return tuple(value / count for value in total)


def get_color_holder(context=None, assign_brush=False):
    global _BRUSH_CACHE_NAME
    if context is None:
        context = bpy.context

    ts = context.tool_settings
    if hasattr(ts, "vertex_paint") and hasattr(ts.vertex_paint, "unified_paint_settings"):
        ups = ts.vertex_paint.unified_paint_settings
    else:
        ups = getattr(ts, "unified_paint_settings", None)

    if ups and getattr(ups, "use_unified_color", False):
        return ups

    vertex_paint = getattr(ts, "vertex_paint", None)
    if vertex_paint and vertex_paint.brush:
        _BRUSH_CACHE_NAME = vertex_paint.brush.name
        return vertex_paint.brush

    if _BRUSH_CACHE_NAME:
        cached = bpy.data.brushes.get(_BRUSH_CACHE_NAME)
        if cached and (
            getattr(cached, "vertex_tool", "NONE") != "NONE"
            or getattr(cached, "use_paint_vertex", False)
        ):
            if assign_brush and vertex_paint:
                vertex_paint.brush = cached
            return cached

    for brush in bpy.data.brushes:
        if getattr(brush, "vertex_tool", "NONE") != "NONE" or getattr(brush, "use_paint_vertex", False):
            _BRUSH_CACHE_NAME = brush.name
            if assign_brush and vertex_paint:
                vertex_paint.brush = brush
            return brush
    return ups


def get_holder_rgb_colors(holder):
    if not holder:
        return None, None

    color = tuple(clamp_factor(component) for component in holder.color[:3])
    secondary = tuple(clamp_factor(component) for component in holder.secondary_color[:3])
    return color, secondary


def set_holder_rgb_colors(holder, color, secondary=None):
    if not holder:
        return

    if color is not None:
        holder.color = tuple(clamp_factor(component) for component in color[:3])
    if secondary is not None:
        holder.secondary_color = tuple(clamp_factor(component) for component in secondary[:3])


def get_current_fg_rgb(context=None):
    holder = get_color_holder(context)
    if not holder:
        return None
    return tuple(clamp_factor(component) for component in holder.color[:3])


def bm_use_vert_selection(bm):
    return any(v.select for v in bm.verts)


def bm_use_face_selection(bm):
    return any(f.select for f in bm.faces)


def bm_vert_in_auto_scope(vert, use_selection):
    return vert.select if use_selection else True


def bm_face_in_auto_scope(face, use_selection):
    return face.select if use_selection else True


def get_vertex_group_weights(obj, group, vertex_count=None):
    if obj is None or obj.type != "MESH":
        return np.zeros(0, dtype=np.float32)

    if vertex_count is None:
        vertex_count = len(obj.data.vertices)

    weights = np.zeros(vertex_count, dtype=np.float32)
    if group is None or vertex_count <= 0:
        return weights

    group_index = getattr(group, "index", -1)
    if group_index < 0:
        return weights

    for vertex in obj.data.vertices:
        for assignment in vertex.groups:
            if assignment.group == group_index:
                weights[vertex.index] = assignment.weight
                break

    np.clip(weights, 0.0, 1.0, out=weights)
    return weights


def assign_vertex_group_weights(group, indices, weights):
    if group is None:
        return 0

    indices = np.asarray(indices, dtype=np.int32).reshape(-1)
    weights = np.asarray(weights, dtype=np.float32).reshape(-1)
    if indices.size == 0:
        return 0
    if indices.size != weights.size:
        raise ValueError("Vertex group index and weight counts must match.")

    np.clip(weights, 0.0, 1.0, out=weights)

    if indices.size < 1024:
        for index, weight in zip(indices.tolist(), weights.tolist()):
            group.add((int(index),), float(weight), "REPLACE")
        return int(indices.size)

    unique_weights, inverse = np.unique(weights, return_inverse=True)
    if unique_weights.size > (indices.size * 0.75):
        for index, weight in zip(indices.tolist(), weights.tolist()):
            group.add((int(index),), float(weight), "REPLACE")
        return int(indices.size)

    order = np.argsort(inverse, kind="stable")
    sorted_inverse = inverse[order]
    split_points = np.flatnonzero(np.diff(sorted_inverse)) + 1
    grouped_indices = np.split(indices[order], split_points)

    for group_index, vertex_indices in enumerate(grouped_indices):
        group.add(vertex_indices.tolist(), float(unique_weights[group_index]), "REPLACE")

    return int(indices.size)
