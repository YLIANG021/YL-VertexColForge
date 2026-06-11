# -*- coding: utf-8 -*-
"""Mesh topology array helpers shared by color tools."""

import numpy as np


def loop_vertex_indices(mesh):
    loop_count = len(mesh.loops)
    indices = np.empty(loop_count, dtype=np.int32) if loop_count > 0 else np.zeros(0, dtype=np.int32)
    if loop_count > 0:
        mesh.loops.foreach_get("vertex_index", indices)
    return indices


def edge_vertex_pairs(mesh):
    edge_count = len(mesh.edges)
    edges = np.empty(edge_count * 2, dtype=np.int32) if edge_count > 0 else np.zeros(0, dtype=np.int32)
    if edge_count > 0:
        mesh.edges.foreach_get("vertices", edges)
    return edges.reshape(-1, 2)


def polygon_loop_totals(mesh):
    polygon_count = len(mesh.polygons)
    totals = np.empty(polygon_count, dtype=np.int32) if polygon_count > 0 else np.zeros(0, dtype=np.int32)
    if polygon_count > 0:
        mesh.polygons.foreach_get("loop_total", totals)
    return totals


def corner_inverse_counts(loop_vert_indices, vert_count):
    counts = np.bincount(loop_vert_indices, minlength=vert_count).astype(np.float32)
    inv_counts = np.zeros_like(counts, dtype=np.float32)
    valid = counts > 0.0
    inv_counts[valid] = 1.0 / counts[valid]
    return inv_counts


def average_loop_values_to_vertices(loop_values, loop_vert_indices, vert_count, loop_mask=None):
    values = np.asarray(loop_values, dtype=np.float32)
    if loop_mask is None:
        active_indices = np.arange(len(loop_vert_indices), dtype=np.int32)
    else:
        active_indices = np.flatnonzero(loop_mask).astype(np.int32, copy=False)

    if values.ndim == 1:
        totals = np.zeros(vert_count, dtype=np.float32)
        if len(active_indices) > 0:
            np.add.at(totals, loop_vert_indices[active_indices], values[active_indices])
        counts = np.bincount(loop_vert_indices[active_indices], minlength=vert_count).astype(np.float32)
        valid = counts > 0.0
        averaged = np.zeros(vert_count, dtype=np.float32)
        averaged[valid] = totals[valid] / counts[valid]
        return averaged, valid

    totals = np.zeros((vert_count, values.shape[1]), dtype=np.float32)
    if len(active_indices) > 0:
        np.add.at(totals, loop_vert_indices[active_indices], values[active_indices])
    counts = np.bincount(loop_vert_indices[active_indices], minlength=vert_count).astype(np.float32)
    valid = counts > 0.0
    averaged = np.zeros_like(totals, dtype=np.float32)
    averaged[valid] = totals[valid] / counts[valid, None]
    return averaged, valid


def vertex_positions(mesh):
    positions = np.empty((len(mesh.vertices), 3), dtype=np.float32)
    if len(mesh.vertices) > 0:
        mesh.vertices.foreach_get("co", positions.ravel())
    return positions


def vertex_normals(mesh):
    normals = np.empty((len(mesh.vertices), 3), dtype=np.float32)
    if len(mesh.vertices) > 0:
        mesh.vertices.foreach_get("normal", normals.ravel())
    return normals


def loop_normals(mesh):
    normals = np.empty((len(mesh.loops), 3), dtype=np.float32)
    if len(mesh.loops) > 0:
        mesh.loops.foreach_get("normal", normals.ravel())
    return normals
