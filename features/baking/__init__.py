# -*- coding: utf-8 -*-
"""Baking and directional lighting tools."""

from . import ops_gradient_map

CLASSES = (
    *ops_gradient_map.classes,
)


def register():
    import bpy

    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    import bpy

    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
