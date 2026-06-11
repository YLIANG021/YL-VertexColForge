# -*- coding: utf-8 -*-
"""Paint and fill UI."""

from ... import utils
from ...features.color import ops_ui_utils
from ...features.paint import ops_brush
from ...features.paint import brush_ui_policy
from ...i18n import tr, tr_format
from ..common import draw_hint, draw_unavailable, section_body


def draw_brush_values_content(layout, context):
    brush_ui_policy.mark_brush_panel_draw(context)
    scene = context.scene
    content = section_body(layout)
    is_painting = ops_brush.is_paint_session_active()

    color_holder = utils.get_color_holder(context)

    content.label(text=tr("Fill"))
    row_colors = content.row(align=True)
    split_colors = row_colors.split(factor=0.775, align=True)
    row_fg = split_colors.row(align=True)
    row_bg = split_colors.row(align=True)

    if scene.ylvc_channel == "RGB":
        if color_holder:
            row_fg.prop(color_holder, "color", text="")
            row_bg.operator("mesh.ylvc_swap_colors", text="", icon="UV_SYNC_SELECT")
            row_bg.prop(color_holder, "secondary_color", text="")
        else:
            draw_unavailable(row_colors, "vertex paint brush")
    else:
        if color_holder:
            row_fg.prop(scene, "ylvc_single_fg", text="")
            row_bg.operator("mesh.ylvc_swap_colors", text="", icon="UV_SYNC_SELECT")
            row_bg.prop(scene, "ylvc_single_bg", text="")
        else:
            draw_unavailable(row_colors, "vertex paint brush")

    row_actions = content.row(align=True)
    row_actions.scale_y = 1.5
    fill_button = row_actions.row(align=True)
    fill_button.operator(
        "mesh.ylvc_apply_scene_value",
        text=tr_format("Fill {channel_key}", channel_key=scene.ylvc_channel),
    )
    row_actions.operator("mesh.ylvc_brush_eyedropper", text="", icon="EYEDROPPER")

    row_write = content.row(align=True)
    split_write = row_write.split(factor=0.8, align=True)
    split_write.prop(scene, "ylvc_brush_strength", text=tr("Strength"), slider=True)
    split_write.prop(scene, "ylvc_write_blend_mode", text="")

    content.separator(factor=0.6)
    content.label(text=tr("Paint"))
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

    if scene.ylvc_channel == "RGB" and color_holder:
        content.separator()
        palette = ops_ui_utils.get_palette(scene)

        content.label(text=tr("Color Presets"))

        row_palette_actions = content.row(align=True)
        row_palette_actions.scale_y = 1.0
        row_add = row_palette_actions.row(align=True)
        row_add.enabled = palette is None or len(palette.colors) < ops_ui_utils.PALETTE_SLOT_LIMIT
        row_add.operator("mesh.ylvc_add_palette_color", text=tr("Add Preset"))
        row_remove = row_palette_actions.row(align=True)
        row_remove.enabled = palette is not None and len(palette.colors) > 0
        row_remove.operator("mesh.ylvc_remove_palette_color", text=tr("Remove"))

        if palette is None or len(palette.colors) == 0:
            return

        content.template_palette(scene, "ylvc_palette", color=True)
