# -*- coding: utf-8 -*-
"""Scene property callbacks and dynamic property accessors."""

import bpy

from ..core.color_attribute import (
    get_active_color_attribute_safe,
    get_color_attribute_by_name,
    get_scene_selected_color_attribute_name,
    set_active_color_attribute,
    set_scene_selected_color_attribute_name,
)
from ..core.color_channels import clamp_factor
from .state import snapshot_plugin_state


def _handle_channel_switch(scene, context):
    scene.ylvc_previous_channel = getattr(scene, "ylvc_channel", "RGB")


def update_write_channel(self, context):
    _handle_channel_switch(self, context)
    try:
        from ..features.color import ops_preview
        ops_preview.update_channel_preview(self, context)
    except Exception:
        pass
    snapshot_plugin_state()
def get_single_fg(self):
    channel = self.ylvc_channel
    if channel == "A":
        return self.ylvc_alpha_fg
    return self.get("ylvc_single_fg", 1.0)


def set_single_fg(self, value):
    channel = self.ylvc_channel
    if channel == "A":
        self.ylvc_alpha_fg = clamp_factor(value)
    else:
        self["ylvc_single_fg"] = clamp_factor(value)
    snapshot_plugin_state()


def get_single_bg(self):
    channel = self.ylvc_channel
    if channel == "A":
        return self.ylvc_alpha_bg
    return self.get("ylvc_single_bg", 0.0)


def set_single_bg(self, value):
    channel = self.ylvc_channel
    if channel == "A":
        self.ylvc_alpha_bg = clamp_factor(value)
    else:
        self["ylvc_single_bg"] = clamp_factor(value)
    snapshot_plugin_state()


def get_ylvc_layer_name(self):
    obj = bpy.context.active_object
    if obj and obj.type == "MESH" and obj.data.color_attributes:
        mesh = obj.data
        selected_name = get_scene_selected_color_attribute_name(self)
        if get_color_attribute_by_name(mesh, selected_name) is not None:
            return selected_name

        active_attr = get_active_color_attribute_safe(mesh)
        if active_attr is not None:
            return active_attr.name
    return ""


def set_ylvc_layer_name(self, value):
    layer_name = value.strip() if isinstance(value, str) else ""
    obj = bpy.context.active_object
    if obj and obj.type == "MESH" and obj.data.color_attributes:
        mesh = obj.data
        color_attr = get_color_attribute_by_name(mesh, layer_name)
        if color_attr is None:
            return

        set_scene_selected_color_attribute_name(self, color_attr.name)
        set_active_color_attribute(mesh, color_attr.name)
        try:
            from ..services import display
            display.finish_color_write(
                bpy.context,
                mesh,
                color_attr.name,
                obj=obj,
                ensure_preview=False,
            )
        except Exception:
            pass


def update_plugin_state_only(_self, _context):
    try:
        snapshot_plugin_state()
    except Exception:
        pass


def update_ui_section(self, _context):
    try:
        snapshot_plugin_state()
    except Exception:
        pass
