# -*- coding: utf-8 -*-
"""Color value selection UI."""

from ...i18n import tr
from ..common import section_body


def draw_selection_content(layout, context):
    scene = context.scene
    content = section_body(layout)

    content.label(text=tr("Select by Channel"))

    row_value = content.row(align=True)
    split_value = row_value.split(factor=0.2, align=True)
    color_part = split_value.row(align=True)
    tolerance_part = split_value.row(align=True)
    if scene.ylvc_channel == "RGB":
        color_part.prop(scene, "ylvc_fill_rgb_fg", text="")
    else:
        color_part.prop(scene, "ylvc_single_fg", text="")
    tolerance_part.prop(scene, "ylvc_select_tolerance", text=tr("Tolerance"), slider=True)

    col_pick = content.column(align=True)
    col_pick.scale_y = 1.5
    col_pick.operator("mesh.ylvc_pick_select_value", text=tr("Pick"))
