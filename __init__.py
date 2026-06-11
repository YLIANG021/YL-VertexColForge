# -*- coding: utf-8 -*-
"""Blender extension entry point."""

from .lifecycle import register, unregister
from .properties.state import snapshot_plugin_state as _snapshot_plugin_state

__all__ = (
    "register",
    "unregister",
    "_snapshot_plugin_state",
)


if __name__ == "__main__":
    register()
