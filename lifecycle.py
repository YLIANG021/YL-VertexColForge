# -*- coding: utf-8 -*-
"""Top-level add-on register/unregister orchestration."""

import bpy

from . import i18n
from .features import adjustments, color, gradients, paint, transfer
from . import registry
from .core.logging import debug
from .properties import scene as scene_properties
from .properties import state


def _initialize_runtime_data():
    try:
        scene = getattr(bpy.context, "scene", None)
        if scene is not None:
            color.ops_ui_utils.ensure_palette(scene)
    except Exception as exc:
        debug(f"YLVC palette init failed: {exc}")

    try:
        gradients.core_color_engine.ensure_ramp_node()
    except Exception as exc:
        debug(f"YLVC ramp init failed: {exc}")
    try:
        gradients.core_color_engine.ensure_adjust_ramp_node()
    except Exception as exc:
        debug(f"YLVC adjust ramp init failed: {exc}")
    try:
        gradients.core_color_engine.ensure_light_ramp_node()
    except Exception as exc:
        debug(f"YLVC light ramp init failed: {exc}")

    try:
        state.snapshot_plugin_state()
    except Exception as exc:
        debug(f"YLVC session snapshot init failed: {exc}")


def register():
    i18n.register()
    registry.cleanup_stale_panel_classes()
    registry.register_classes()
    transfer.register_properties()
    scene_properties.register_scene_properties()
    _initialize_runtime_data()
    color.ops_preview.register_runtime_helpers()
    state.register_handlers()


def unregister():
    i18n.unregister()
    color.ops_preview.unregister_runtime_helpers()
    try:
        adjustments.ops_color_adjust.clear_ylvc_adjust_cache()
    except Exception:
        pass
    try:
        paint.ops_brush.clear_ylvc_paint_session()
    except Exception:
        pass
    try:
        transfer.unregister_properties()
    except Exception:
        pass

    state.unregister_handlers()
    scene_properties.unregister_scene_properties()
    color.ops_ui_utils.cleanup_previews()
    registry.unregister_classes()
