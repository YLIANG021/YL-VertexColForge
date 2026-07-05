# -*- coding: utf-8 -*-
"""Texture and weight transfer tools."""

from . import ops_texture, ops_weight

CLASSES = (
    *ops_texture.CLASSES,
    *ops_weight.CLASSES,
)


def register():
    import bpy

    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    import bpy

    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
