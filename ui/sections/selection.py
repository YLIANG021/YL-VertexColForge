# -*- coding: utf-8 -*-
"""Color selection UI."""

from ... import utils
from ...i18n import tr, tr_format
from ..common import draw_unavailable, section_body


def draw_selection_content(layout, context):
    scene = context.scene
    content = section_body(layout)
    color_holder = utils.get_color_holder(context)

    col_pick = content.column(align=True)
    col_pick.scale_y = 1.5
    col_pick.operator("mesh.ylvc_pick_select_value", text=tr("Pick"))

    content.separator(factor=0.4)

    row_settings = content.row(align=True)
    split_settings = row_settings.split(factor=0.1, align=True)
    row_color = split_settings.row(align=True)
    row_tol = split_settings.row(align=True)

    if scene.ylvc_channel == "RGB":
        if color_holder:
            row_color.prop(color_holder, "color", text="")
        else:
            draw_unavailable(row_color, "vertex paint brush")
    else:
        if color_holder:
            row_color.prop(scene, "ylvc_single_fg", text="")
        else:
            draw_unavailable(row_color, "vertex paint brush")

    row_tol.prop(scene, "ylvc_select_tolerance", text=tr("Tolerance"), slider=True)

    row_actions = content.row(align=True)
    row_actions.scale_y = 1.5
    row_actions.operator(
        "mesh.ylvc_select_scene_value",
        text=tr_format("Select by {channel_key} Value", channel_key=scene.ylvc_channel),
    )
