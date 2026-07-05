# -*- coding: utf-8 -*-
"""Vertex group array helpers."""

import numpy as np


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
