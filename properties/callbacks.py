# -*- coding: utf-8 -*-
"""Scene property callbacks and dynamic property accessors."""

import bpy

from .. import utils
from ..features import adjustments, color, paint
from .state import snapshot_plugin_state


def _sync_preview_to_write_channel(scene):
    if not scene:
        return
    if not getattr(scene, "ylvc_sync_preview_channel", True):
        return
    write_channel = getattr(scene, "ylvc_channel", "RGB")
    if getattr(scene, "ylvc_preview_channel", "RGB") != write_channel:
        scene.ylvc_preview_channel = write_channel


def _cache_holder_rgb(scene, holder):
    fg, bg = utils.get_holder_rgb_colors(holder)
    if fg is None or bg is None:
        return
    scene.ylvc_cached_rgb_fg = fg
    scene.ylvc_cached_rgb_bg = bg
    scene.ylvc_cached_rgb_valid = True


def _sync_previous_pure_channel(scene, holder, channel):
    if not holder or channel not in utils.PURE_VISUAL_CHANNELS:
        return

    index = utils.PURE_VISUAL_CHANNELS[channel]
    pure_fg = list(scene.ylvc_pure_fg_values)
    pure_bg = list(scene.ylvc_pure_bg_values)
    pure_fg[index] = utils.clamp_factor(holder.color[index])
    pure_bg[index] = utils.clamp_factor(holder.secondary_color[index])
    scene.ylvc_pure_fg_values = tuple(pure_fg)
    scene.ylvc_pure_bg_values = tuple(pure_bg)


def _seed_pure_values_from_cached_rgb(scene):
    if not getattr(scene, "ylvc_cached_rgb_valid", False):
        return

    scene.ylvc_pure_fg_values = tuple(float(component) for component in scene.ylvc_cached_rgb_fg)
    scene.ylvc_pure_bg_values = tuple(float(component) for component in scene.ylvc_cached_rgb_bg)


def _apply_pure_channel_visual(scene, holder, channel):
    if not holder or channel not in utils.PURE_VISUAL_CHANNELS:
        return

    index = utils.PURE_VISUAL_CHANNELS[channel]
    fg_value = float(scene.ylvc_pure_fg_values[index])
    bg_value = float(scene.ylvc_pure_bg_values[index])
    holder.color = utils.build_pure_channel_color(channel, fg_value)
    holder.secondary_color = utils.build_pure_channel_color(channel, bg_value)


def _handle_channel_switch(scene, context):
    if getattr(scene, "ylvc_channel_updating", False):
        return

    holder = utils.get_color_holder(context)
    if not holder:
        return

    previous = getattr(scene, "ylvc_previous_channel", "RGB")
    current = getattr(scene, "ylvc_channel", "RGB")

    scene.ylvc_channel_updating = True
    try:
        prev_is_pure = previous in utils.PURE_VISUAL_CHANNELS
        current_is_pure = current in utils.PURE_VISUAL_CHANNELS

        if prev_is_pure:
            _sync_previous_pure_channel(scene, holder, previous)

        if not prev_is_pure and current_is_pure:
            _cache_holder_rgb(scene, holder)
            _seed_pure_values_from_cached_rgb(scene)
            _apply_pure_channel_visual(scene, holder, current)
        elif prev_is_pure and current_is_pure:
            _apply_pure_channel_visual(scene, holder, current)
        elif prev_is_pure and not current_is_pure:
            if getattr(scene, "ylvc_cached_rgb_valid", False):
                utils.set_holder_rgb_colors(holder, scene.ylvc_cached_rgb_fg, scene.ylvc_cached_rgb_bg)
            else:
                _cache_holder_rgb(scene, holder)

        scene.ylvc_previous_channel = current
    finally:
        scene.ylvc_channel_updating = False


def update_write_channel(self, context):
    _sync_preview_to_write_channel(self)
    _handle_channel_switch(self, context)
    color.ops_preview.update_channel_preview(self, context)
    snapshot_plugin_state()


def update_sync_preview_channel(self, context):
    if self.ylvc_sync_preview_channel:
        _sync_preview_to_write_channel(self)
    color.ops_preview.update_channel_preview(self, context)
    snapshot_plugin_state()


def update_preview_channel(self, context):
    color.ops_preview.update_channel_preview(self, context)
    snapshot_plugin_state()


def get_single_fg(self):
    holder = utils.get_color_holder()
    if not holder:
        return 1.0
    channel = self.ylvc_channel
    if channel == "R":
        return holder.color[0]
    if channel == "G":
        return holder.color[1]
    if channel == "B":
        return holder.color[2]
    if channel == "A":
        return self.ylvc_alpha_fg
    return 1.0


def set_single_fg(self, value):
    holder = utils.get_color_holder()
    if not holder:
        return
    channel = self.ylvc_channel
    if channel == "A":
        self.ylvc_alpha_fg = value
    elif channel in utils.PURE_VISUAL_CHANNELS:
        index = utils.PURE_VISUAL_CHANNELS[channel]
        fg = list(self.ylvc_pure_fg_values)
        fg[index] = utils.clamp_factor(value)
        self.ylvc_pure_fg_values = tuple(fg)
        holder.color = utils.build_pure_channel_color(channel, value)
    snapshot_plugin_state()


def get_single_bg(self):
    holder = utils.get_color_holder()
    if not holder:
        return 1.0
    channel = self.ylvc_channel
    if channel == "R":
        return holder.secondary_color[0]
    if channel == "G":
        return holder.secondary_color[1]
    if channel == "B":
        return holder.secondary_color[2]
    if channel == "A":
        return self.ylvc_alpha_bg
    return 1.0


def set_single_bg(self, value):
    holder = utils.get_color_holder()
    if not holder:
        return
    channel = self.ylvc_channel
    if channel == "A":
        self.ylvc_alpha_bg = value
    elif channel in utils.PURE_VISUAL_CHANNELS:
        index = utils.PURE_VISUAL_CHANNELS[channel]
        bg = list(self.ylvc_pure_bg_values)
        bg[index] = utils.clamp_factor(value)
        self.ylvc_pure_bg_values = tuple(bg)
        holder.secondary_color = utils.build_pure_channel_color(channel, value)
    snapshot_plugin_state()


def get_ylvc_layer_items(_self, context):
    obj = context.active_object
    if not obj or obj.type != "MESH" or not obj.data.color_attributes:
        return [("NONE", "No Layer", "")]
    return [(attr.name, attr.name, f"{attr.domain} | {attr.data_type}") for attr in obj.data.color_attributes]


def get_ylvc_layer(_self):
    obj = bpy.context.active_object
    if obj and obj.type == "MESH" and obj.data.color_attributes:
        color_attributes = obj.data.color_attributes
        try:
            idx = color_attributes.active_color_index
            if 0 <= idx < len(color_attributes):
                return idx
        except Exception:
            pass

        try:
            active_attr = color_attributes.active_color
            if active_attr is not None:
                for idx, attr in enumerate(color_attributes):
                    if attr.name == active_attr.name:
                        return idx
        except Exception:
            pass
    return 0


def set_ylvc_layer(_self, value):
    obj = bpy.context.active_object
    if obj and obj.type == "MESH" and obj.data.color_attributes:
        if 0 <= value < len(obj.data.color_attributes):
            color_attr = obj.data.color_attributes[value]
            obj.data.color_attributes.active_color_index = value
            obj.data.color_attributes.render_color_index = value
            try:
                from ..services import display
                display.refresh_after_color_write(
                    bpy.context,
                    obj.data,
                    color_attr.name,
                    obj=obj,
                    ensure_preview=False,
                    force_view_update=True,
                )
            except Exception:
                pass


def update_plugin_state_only(_self, _context):
    try:
        snapshot_plugin_state()
    except Exception:
        pass


def update_ui_section(self, _context):
    if self.ylvc_ui_section != "BRUSH":
        try:
            paint.ops_brush.request_finish_ylvc_paint_session()
        except Exception:
            pass
    if self.ylvc_ui_section != "POST":
        try:
            adjustments.ops_color_adjust.cancel_live_preview_session()
        except Exception:
            pass
    try:
        snapshot_plugin_state()
    except Exception:
        pass
