# -*- coding: utf-8 -*-
"""Property registration, callbacks, and runtime state."""

from . import scene, state


def register():
    scene.register_scene_properties()
    state.register_handlers()


def unregister():
    state.unregister_handlers()
    scene.unregister_scene_properties()
