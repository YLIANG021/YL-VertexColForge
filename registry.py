# -*- coding: utf-8 -*-
"""Class registry for the add-on lifecycle."""

import bpy

from . import (
    ui,
)
from .features import adjustments, baking, color, gradients, paint, selection, transfer

CLASSES = (
    *color.ops_layer.CLASSES,
    *selection.CLASSES,
    *paint.CLASSES,
    *color.ops_channel.CLASSES,
    *color.ops_ui_utils.CLASSES,
    *color.ops_preview.CLASSES,
    *color.ops_mirror.CLASSES,
    *color.ops_random.CLASSES,
    *transfer.CLASSES,
    *baking.ops_bake_ao.classes,
    *baking.ops_curvature_map.classes,
    *baking.ops_gradient_map.classes,
    *adjustments.ops_color_adjust.classes,
    *adjustments.ops_smooth_blur.classes,
    *ui.CLASSES,
    *gradients.OPERATOR_CLASSES,
    *gradients.UI_CLASSES,
)


def cleanup_stale_panel_classes():
    stale_class_names = (
        "VIEW3D_PT_VCM_AO_Test",
        "VIEW3D_PT_VCM_TestPanel",
        "VIEW3D_PT_VCMC_AdjustPanel",
        "VIEW3D_PT_VCMB_BlurPanel",
    )
    modules = (
        baking.ops_bake_ao,
        baking.ops_gradient_map,
        adjustments.ops_color_adjust,
        adjustments.ops_smooth_blur,
    )

    for module in modules:
        for class_name in stale_class_names:
            cls = getattr(module, class_name, None)
            if cls is None:
                continue
            try:
                bpy.utils.unregister_class(cls)
            except Exception:
                pass


def register_classes():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister_classes():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
