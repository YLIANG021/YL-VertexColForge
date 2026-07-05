# -*- coding: utf-8 -*-
"""Blender extension entry point."""

from . import i18n, properties, ui
from .core.logging import debug
from .features import baking, color, gradients, paint, selection, transfer
from .properties.state import snapshot_plugin_state as _snapshot_plugin_state


modules = (
    color,
    gradients,
    baking,
    paint,
    selection,
    transfer,
    ui,
    properties,
)


def _initialize_runtime_data():
    try:
        _snapshot_plugin_state()
    except Exception as exc:
        debug(f"YLVC session snapshot init failed: {exc}")


def register():
    i18n.register()
    for module in modules:
        module.register()
    _initialize_runtime_data()


def unregister():
    try:
        color.ops_preview.clear_deferred_preview_syncs()
    except Exception:
        pass

    try:
        color.ops_preview.exit_preview_mode(clear_flat_state=True)
    except Exception:
        pass

    for module in reversed(modules):
        module.unregister()
    i18n.unregister()


__all__ = (
    "register",
    "unregister",
    "_snapshot_plugin_state",
)
