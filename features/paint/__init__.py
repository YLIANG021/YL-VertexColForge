# -*- coding: utf-8 -*-
"""Interactive local paint tools."""

from . import ops_brush, ops_eyedropper

CLASSES = (
    *ops_brush.CLASSES,
    *ops_eyedropper.CLASSES,
)


def register():
    import bpy

    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    ops_brush.request_finish_ylvc_paint_session()

    import bpy

    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
