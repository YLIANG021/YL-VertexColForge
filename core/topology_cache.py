# -*- coding: utf-8 -*-
"""Small mesh topology array cache shared by data-heavy tools."""

from collections import OrderedDict

import numpy as np


_MAX_CACHED_MESHES = 8
_GLOBAL_CACHES = OrderedDict()


def _mesh_key(mesh):
    try:
        return int(mesh.as_pointer())
    except Exception:
        return id(mesh)


def _mesh_signature(mesh):
    return (
        len(mesh.vertices),
        len(mesh.edges),
        len(mesh.loops),
        len(mesh.polygons),
    )


class MeshArrayCache:
    def __init__(self, mesh):
        self.mesh = mesh
        self.signature = _mesh_signature(mesh)
        self._arrays = {}

    def is_valid_for(self, mesh):
        return self.mesh == mesh and self.signature == _mesh_signature(mesh)

    def loop_vertex_indices(self):
        cached = self._arrays.get("loop_vertex_indices")
        if cached is not None:
            return cached

        loop_count = len(self.mesh.loops)
        indices = np.empty(loop_count, dtype=np.int32) if loop_count > 0 else np.zeros(0, dtype=np.int32)
        if loop_count > 0:
            self.mesh.loops.foreach_get("vertex_index", indices)
        self._arrays["loop_vertex_indices"] = indices
        return indices

    def edge_vertex_pairs(self):
        cached = self._arrays.get("edge_vertex_pairs")
        if cached is not None:
            return cached

        edge_count = len(self.mesh.edges)
        edges = np.empty(edge_count * 2, dtype=np.int32) if edge_count > 0 else np.zeros(0, dtype=np.int32)
        if edge_count > 0:
            self.mesh.edges.foreach_get("vertices", edges)
        edges.shape = (-1, 2)
        self._arrays["edge_vertex_pairs"] = edges
        return edges

    def polygon_loop_starts(self):
        cached = self._arrays.get("polygon_loop_starts")
        if cached is not None:
            return cached

        polygon_count = len(self.mesh.polygons)
        starts = np.empty(polygon_count, dtype=np.int32) if polygon_count > 0 else np.zeros(0, dtype=np.int32)
        if polygon_count > 0:
            self.mesh.polygons.foreach_get("loop_start", starts)
        self._arrays["polygon_loop_starts"] = starts
        return starts

    def polygon_loop_totals(self):
        cached = self._arrays.get("polygon_loop_totals")
        if cached is not None:
            return cached

        polygon_count = len(self.mesh.polygons)
        totals = np.empty(polygon_count, dtype=np.int32) if polygon_count > 0 else np.zeros(0, dtype=np.int32)
        if polygon_count > 0:
            self.mesh.polygons.foreach_get("loop_total", totals)
        self._arrays["polygon_loop_totals"] = totals
        return totals

    def polygon_loop_starts_totals(self):
        return self.polygon_loop_starts(), self.polygon_loop_totals()

    def vertex_positions(self):
        cached = self._arrays.get("vertex_positions")
        if cached is not None:
            return cached

        positions = np.empty((len(self.mesh.vertices), 3), dtype=np.float32)
        if len(self.mesh.vertices) > 0:
            self.mesh.vertices.foreach_get("co", positions.ravel())
        self._arrays["vertex_positions"] = positions
        return positions


def get_mesh_array_cache(mesh):
    key = _mesh_key(mesh)
    cache = _GLOBAL_CACHES.get(key)
    if cache is None or not cache.is_valid_for(mesh):
        cache = MeshArrayCache(mesh)
        _GLOBAL_CACHES[key] = cache
    else:
        _GLOBAL_CACHES.move_to_end(key)

    while len(_GLOBAL_CACHES) > _MAX_CACHED_MESHES:
        _GLOBAL_CACHES.popitem(last=False)
    return cache


def clear_mesh_array_cache(mesh=None):
    if mesh is None:
        _GLOBAL_CACHES.clear()
        return
    _GLOBAL_CACHES.pop(_mesh_key(mesh), None)
