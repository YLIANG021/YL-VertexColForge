# -*- coding: utf-8 -*-
"""Baking, ambient occlusion, curvature, and directional lighting tools."""

from . import ops_bake_ao, ops_curvature_map, ops_gradient_map

CLASSES = (
    *ops_bake_ao.classes,
    *ops_curvature_map.classes,
    *ops_gradient_map.classes,
)
