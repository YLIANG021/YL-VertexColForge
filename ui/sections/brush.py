# -*- coding: utf-8 -*-
"""Paint and fill UI."""

from ...i18n import tr, tr_format
from ...features.paint import brush_ui_policy, ops_brush
from ..common import draw_hint, section_body


def draw_brush_values_content(layout, context):
    brush_ui_policy.mark_brush_panel_draw(context)
    scene = context.scene
    content = section_body(layout)
    is_painting = ops_brush.is_paint_session_active()

    content.label(text=tr("Channel Fill"))
    row_colors = content.row(align=True)
    split_colors = row_colors.split(factor=0.775, align=True)
    row_fg = split_colors.row(align=True)
    row_bg = split_colors.row(align=True)

    if scene.ylvc_channel == "RGB":
        row_fg.prop(scene, "ylvc_fill_rgb_fg", text="")
        row_bg.operator("mesh.ylvc_swap_colors", text="", icon="UV_SYNC_SELECT")
        row_bg.prop(scene, "ylvc_fill_rgb_bg", text="")
    else:
        row_fg.prop(scene, "ylvc_single_fg", text="")
        row_bg.operator("mesh.ylvc_swap_colors", text="", icon="UV_SYNC_SELECT")
        row_bg.prop(scene, "ylvc_single_bg", text="")

    row_actions = content.row(align=True)
    row_actions.scale_y = 1.5
    fill_button = row_actions.row(align=True)
    fill_button.operator(
        "mesh.ylvc_apply_scene_value",
        text=tr_format("Fill {channel_key}", channel_key=scene.ylvc_channel),
    )
    row_actions.operator("mesh.ylvc_brush_eyedropper", text="", icon="EYEDROPPER")

    content.separator(factor=0.65)
    content.label(text=tr("Channel Paint"))

    row_write = content.row(align=True)
    split_write = row_write.split(factor=0.66, align=True)
    split_write.prop(scene, "ylvc_brush_strength", text=tr("Strength"), slider=True)
    split_write.prop(scene, "ylvc_write_blend_mode", text="")

    row_paint = content.row(align=True)
    row_paint.scale_y = 1.5
    row_paint.enabled = not is_painting
    row_paint.operator(
        "mesh.ylvc_local_paint_brush",
        text=tr("Painting...") if is_painting else tr_format("Paint {channel_key}", channel_key=scene.ylvc_channel),
        depress=is_painting,
    )
    if is_painting:
        draw_hint(content, "F: Size, Shift+F: Hardness")
