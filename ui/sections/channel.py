# -*- coding: utf-8 -*-
"""Channel copy and mirror UI."""

from ...i18n import tr, tr_format
from ..common import section_body


def draw_channel_tools_content(layout, context):
    scene = context.scene
    content = section_body(layout)

    content.label(text=tr("Mirror Colors"))
    col_mirror = content.column(align=True)
    col_mirror.scale_y = 1.5
    col_mirror.operator(
        "view3d.ylvc_mirror_picker",
        text=tr_format("Mirror {channel_key}", channel_key=scene.ylvc_channel),
    )
    content.prop(scene, "ylvc_mirror_tolerance", text=tr("Tolerance"), slider=True)
    content.separator()

    content.label(text=tr("Copy Channels"))
    row_source = content.row(align=True)
    row_source.prop(scene, "ylvc_source_channel", expand=True)
    content.prop(scene, "ylvc_blend_mode", text=tr("Channel Blend"))
    row_copy = content.row(align=True)
    row_copy.scale_y = 1.5
    row_copy.operator(
        "mesh.ylvc_copy_channel",
        text=tr_format(
            "Blend {source_key} -> {target_key}",
            source_key=scene.ylvc_source_channel,
            target_key=scene.ylvc_channel,
        ),
    )
