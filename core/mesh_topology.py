# -*- coding: utf-8 -*-
"""Mesh topology array helpers shared by color tools."""

import numpy as np

from .topology_cache import get_mesh_array_cache


def loop_vertex_indices(mesh):
    return get_mesh_array_cache(mesh).loop_vertex_indices()


def edge_vertex_pairs(mesh):
    return get_mesh_array_cache(mesh).edge_vertex_pairs()


def polygon_loop_totals(mesh):
    return get_mesh_array_cache(mesh).polygon_loop_totals()


def polygon_loop_starts(mesh):
    return get_mesh_array_cache(mesh).polygon_loop_starts()


def polygon_loop_starts_totals(mesh):
    return get_mesh_array_cache(mesh).polygon_loop_starts_totals()


def average_loop_values_to_vertices(loop_values, loop_vert_indices, vert_count, loop_mask=None):
    values = np.asarray(loop_values, dtype=np.float32)
    if loop_mask is None:
        active_vertices = loop_vert_indices
        active_values = values
    else:
        active_indices = np.flatnonzero(loop_mask).astype(np.int32, copy=False)
        active_vertices = loop_vert_indices[active_indices]
        active_values = values[active_indices]

    if values.ndim == 1:
        totals = np.zeros(vert_count, dtype=np.float32)
        if len(active_vertices) > 0:
            np.add.at(totals, active_vertices, active_values)
        counts = np.bincount(active_vertices, minlength=vert_count).astype(np.float32)
        valid = counts > 0.0
        averaged = np.zeros(vert_count, dtype=np.float32)
        averaged[valid] = totals[valid] / counts[valid]
        return averaged, valid

    totals = np.zeros((vert_count, values.shape[1]), dtype=np.float32)
    if len(active_vertices) > 0:
        np.add.at(totals, active_vertices, active_values)
    counts = np.bincount(active_vertices, minlength=vert_count).astype(np.float32)
    valid = counts > 0.0
    averaged = np.zeros_like(totals, dtype=np.float32)
    averaged[valid] = totals[valid] / counts[valid, None]
    return averaged, valid


def vertex_positions(mesh):
    return get_mesh_array_cache(mesh).vertex_positions()
