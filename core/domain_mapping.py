# -*- coding: utf-8 -*-
"""Shared POINT/CORNER color-domain mapping helpers."""

import numpy as np

from .color_attribute import (
    convert_colors_between_domains,
    point_colors_to_corner_colors,
)
from .mesh_topology import average_loop_values_to_vertices, loop_vertex_indices


def corner_colors_to_point_colors_with_hard_edge(mesh, corner_colors, hard_edge_threshold=0.1):
    """Average CORNER colors to POINT, preserving first-loop color on high-variance vertices."""
    corner_colors = np.asarray(corner_colors, dtype=np.float32).reshape(-1, 4)
    vert_indices = loop_vertex_indices(mesh)
    vert_count = len(mesh.vertices)

    avg_colors, valid = average_loop_values_to_vertices(corner_colors, vert_indices, vert_count)
    if corner_colors.size == 0 or vert_indices.size == 0:
        return avg_colors

    avg_per_loop = avg_colors[vert_indices]
    diff_sq = (corner_colors[:, :3] - avg_per_loop[:, :3]) ** 2
    variance_per_loop = diff_sq.sum(axis=1)
    counts = np.bincount(vert_indices, minlength=vert_count)
    counts_safe = np.maximum(counts, 1).astype(np.float32)
    variance_sum = np.bincount(vert_indices, weights=variance_per_loop, minlength=vert_count)
    vert_variance = (variance_sum / counts_safe).astype(np.float32)
    vert_variance[~valid] = 0.0

    hard_edge_mask = vert_variance > hard_edge_threshold
    if np.any(hard_edge_mask):
        unique_verts, first_loop_idx = np.unique(vert_indices, return_index=True)
        first_loop_color = np.zeros((vert_count, 4), dtype=np.float32)
        first_loop_color[unique_verts] = corner_colors[first_loop_idx]
        avg_colors[hard_edge_mask] = first_loop_color[hard_edge_mask]

    return avg_colors


def map_color_array_between_domains(mesh, colors, source_domain, target_domain, *, hard_edge_threshold=None):
    """Map color arrays between POINT and CORNER with optional transfer-specific hard-edge handling."""
    if hard_edge_threshold is not None and source_domain == "CORNER" and target_domain == "POINT":
        return corner_colors_to_point_colors_with_hard_edge(mesh, colors, hard_edge_threshold)
    return convert_colors_between_domains(mesh, colors, source_domain, target_domain)


def point_to_corner_colors(mesh, point_colors):
    return point_colors_to_corner_colors(mesh, point_colors)
