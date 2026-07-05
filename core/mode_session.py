# -*- coding: utf-8 -*-
"""Safe object/mode context capture and restoration helpers."""

from dataclasses import dataclass, field

import bpy

from .color_attribute import set_active_color_attribute


@dataclass
class ObjectContextState:
    active_object: object = None
    selected_objects: list = field(default_factory=list)
    mode: str = "OBJECT"


def capture_object_context(context):
    active_obj = getattr(context.view_layer.objects, "active", None)
    selected_objects = list(getattr(context, "selected_objects", []))
    mode = "OBJECT"
    try:
        if active_obj is not None:
            mode = active_obj.mode
    except Exception:
        mode = "OBJECT"
    return ObjectContextState(active_object=active_obj, selected_objects=selected_objects, mode=mode)


def ensure_object_mode(context):
    return set_object_mode(context, "OBJECT")


def set_object_mode(context, mode):
    try:
        active = context.view_layer.objects.active
        if active is not None and active.mode != mode:
            bpy.ops.object.mode_set(mode=mode)
            return True
    except Exception:
        pass
    return False


def restore_object_context(context, state):
    if state is None:
        return

    ensure_object_mode(context)

    try:
        for obj in context.scene.objects:
            obj.select_set(False)
    except Exception:
        pass

    for obj in state.selected_objects:
        try:
            if obj.name in bpy.data.objects:
                obj.select_set(True)
        except Exception:
            pass

    try:
        if state.active_object and state.active_object.name in bpy.data.objects:
            context.view_layer.objects.active = state.active_object
    except Exception:
        pass

    try:
        active = context.view_layer.objects.active
        if active is not None and active.mode != state.mode:
            set_object_mode(context, state.mode)
    except Exception:
        pass


def make_single_active_object(context, obj):
    if obj is None:
        return

    ensure_object_mode(context)

    try:
        for selected in context.selected_objects:
            selected.select_set(False)
    except Exception:
        try:
            bpy.ops.object.select_all(action="DESELECT")
        except Exception:
            pass

    try:
        obj.select_set(True)
        context.view_layer.objects.active = obj
    except Exception:
        pass


def restore_active_layer(mesh, layer_name):
    if layer_name:
        try:
            set_active_color_attribute(mesh, layer_name)
        except Exception:
            pass
