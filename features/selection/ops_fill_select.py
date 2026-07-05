# -*- coding: utf-8 -*-
"""Shared selection helpers."""

import numpy as np


def build_corner_vertex_match_mask(loop_vert_indices, match_mask, vert_count, require_all=False):
    if loop_vert_indices.size == 0 or match_mask.size == 0 or vert_count <= 0:
        return np.zeros(vert_count, dtype=bool)

    if require_all:
        total_counts = np.bincount(loop_vert_indices, minlength=vert_count)
        matched_counts = np.bincount(loop_vert_indices[match_mask], minlength=vert_count)
        return (total_counts > 0) & (matched_counts == total_counts)

    vertex_mask = np.zeros(vert_count, dtype=bool)
    vertex_mask[loop_vert_indices[match_mask]] = True
    return vertex_mask


CLASSES = ()
