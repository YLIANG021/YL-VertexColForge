# -*- coding: utf-8 -*-
"""UI package for YL VertexColForge."""

from .panel_main import CLASSES

__all__ = (
    "CLASSES",
)


def register():
    import bpy

    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    import bpy

    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
