# -*- coding: utf-8 -*-
"""Selection and fill operators."""

from . import ops_fill_select, ops_pick_select

CLASSES = (
    *ops_fill_select.CLASSES,
    *ops_pick_select.CLASSES,
)


def register():
    import bpy

    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    import bpy

    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
