# -*- coding: utf-8 -*-
"""Color attribute, fill, channel, preview, and randomize operators."""

from . import ops_channel, ops_fill_select, ops_layer, ops_preview, ops_random

CLASSES = (
    *ops_fill_select.CLASSES,
    *ops_layer.CLASSES,
    *ops_channel.CLASSES,
    *ops_preview.CLASSES,
    *ops_random.CLASSES,
)

__all__ = (
    "ops_channel",
    "ops_fill_select",
    "ops_layer",
    "ops_preview",
    "ops_random",
)


def register():
    import bpy

    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    import bpy

    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
