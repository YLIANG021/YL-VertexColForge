# -*- coding: utf-8 -*-
"""Sample mesh color attributes at surface hit locations."""

from .color_channels import ensure_rgba_sequence


def _compute_barycentric(point, a, b, c):
    v0 = b - a
    v1 = c - a
    v2 = point - a
    d00 = v0.dot(v0)
    d01 = v0.dot(v1)
    d11 = v1.dot(v1)
    d20 = v2.dot(v0)
    d21 = v2.dot(v1)
    denom = d00 * d11 - d01 * d01
    if abs(denom) <= 1e-12:
        return None
    v = (d11 * d20 - d01 * d21) / denom
    w = (d00 * d21 - d01 * d20) / denom
    u = 1.0 - v - w
    return (u, v, w)


def _weighted_color(weights, colors):
    rgba = [0.0, 0.0, 0.0, 0.0]
    for weight, color in zip(weights, colors):
        for idx in range(4):
            rgba[idx] += float(color[idx]) * float(weight)
    return rgba


def _average_colors(colors):
    if not colors:
        return [0.0, 0.0, 0.0, 1.0]
    accum = [0.0, 0.0, 0.0, 0.0]
    for color in colors:
        for idx in range(4):
            accum[idx] += float(color[idx])
    inv = 1.0 / float(len(colors))
    return [value * inv for value in accum]


def _safe_color_data(color_attr, index):
    try:
        data = color_attr.data
        if index < 0 or index >= len(data):
            return None
        return ensure_rgba_sequence(data[index].color)
    except (AttributeError, IndexError, ReferenceError, RuntimeError):
        return None


def sample_hit_color(obj, mesh, color_attr, poly_index, world_location):
    if obj is None or mesh is None or color_attr is None:
        return None
    if poly_index < 0 or poly_index >= len(mesh.polygons):
        return None

    poly = mesh.polygons[poly_index]
    loop_indices = list(range(poly.loop_start, poly.loop_start + poly.loop_total))
    if not loop_indices:
        return None
    if loop_indices[-1] >= len(mesh.loops):
        return None

    local_point = obj.matrix_world.inverted() @ world_location
    source_colors = []
    vertex_coords = []
    use_point_domain = color_attr.domain == "POINT"
    for loop_index in loop_indices:
        try:
            vertex_index = mesh.loops[loop_index].vertex_index
        except (IndexError, ReferenceError, RuntimeError):
            return None
        if vertex_index < 0 or vertex_index >= len(mesh.vertices):
            return None

        color_index = vertex_index if use_point_domain else loop_index
        color = _safe_color_data(color_attr, color_index)
        if color is None:
            return None

        source_colors.append(color)
        vertex_coords.append(mesh.vertices[vertex_index].co.copy())

    if len(loop_indices) == 1:
        return source_colors[0]
    if len(loop_indices) == 2:
        return _average_colors(source_colors[:2])

    for tri_index in range(1, len(loop_indices) - 1):
        coords = (vertex_coords[0], vertex_coords[tri_index], vertex_coords[tri_index + 1])
        weights = _compute_barycentric(local_point, coords[0], coords[1], coords[2])
        if weights is None:
            continue
        if min(weights) >= -1e-5 and max(weights) <= 1.00001:
            tri_colors = (source_colors[0], source_colors[tri_index], source_colors[tri_index + 1])
            return _weighted_color(weights, tri_colors)

    distances = [(coord - local_point).length_squared for coord in vertex_coords]
    nearest_index = distances.index(min(distances))
    return source_colors[nearest_index]
