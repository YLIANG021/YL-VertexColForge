# -*- coding: utf-8 -*-
"""Viewport gradient UI."""

from ...features.gradients import ui_panels as gradient_ui
from ...i18n import tr, tr_format
from ..common import section_body


def draw_gradient_content(layout, context):
    scene = context.scene
    gradient_ui.draw_viewport_gradient_content(layout, context)

    content = section_body(layout)
    content.separator()
    content.label(text=tr("Light Mask"))
    row_light = content.row(align=True)
    row_light.scale_y = 1.5
    is_tracing = scene.ylvc_is_tracing
    tracing_type = getattr(scene, "ylvc_tracing_type", "")
    row_light.operator(
        "mesh.ylvc_light_mask",
        text=tr_format("Light -> {channel_key}", channel_key=scene.ylvc_channel),
        depress=(is_tracing and tracing_type == "LIGHT_DIRECTION"),
    )
