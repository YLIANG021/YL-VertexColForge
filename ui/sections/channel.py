# -*- coding: utf-8 -*-
"""Channel copy UI."""

from ...features.color.ops_channel import can_copy_channels, can_swap_channels
from ...i18n import tr, tr_format
from ..common import section_body


def draw_channel_tools_content(layout, context):
    scene = context.scene
    content = section_body(layout)

    content.label(text=tr("Channel Copy"))
    row_copy = content.row(align=True)
    row_copy.scale_y = 1.2
    split_copy = row_copy.split(factor=0.5, align=True)
    row_source = split_copy.row(align=True)
    row_source.prop(scene, "ylvc_source_channel", text="")
    row_target = split_copy.row(align=True)
    row_target.prop(scene, "ylvc_copy_target_channel", text="")

    row_copy_action = content.row(align=True)
    row_copy_action.scale_y = 1.5
    row_copy_action.enabled = can_copy_channels(scene.ylvc_source_channel, scene.ylvc_copy_target_channel)
    row_copy_action.operator(
        "mesh.ylvc_copy_channel",
        text=tr_format(
            "Copy {source_channel} to {target_channel}",
            source_channel=scene.ylvc_source_channel,
            target_channel=scene.ylvc_copy_target_channel,
        ),
    )

    row_swap = content.row(align=True)
    row_swap.scale_y = 1.5
    row_swap.enabled = can_swap_channels(scene.ylvc_source_channel, scene.ylvc_copy_target_channel)
    row_swap.operator(
        "mesh.ylvc_swap_channel",
        text=tr_format(
            "Swap {source_channel} and {target_channel}",
            source_channel=scene.ylvc_source_channel,
            target_channel=scene.ylvc_copy_target_channel,
        ),
    )

    content.separator()
    content.label(text=tr("Current Channel"))
    row_secondary = content.row(align=True)
    row_secondary.scale_y = 1.3
    row_secondary.operator(
        "mesh.ylvc_invert_channel",
        text=tr_format("Invert {target_channel}", target_channel=scene.ylvc_channel),
    )
    row_secondary.operator(
        "mesh.ylvc_normalize_channel",
        text=tr_format("Normalize {target_channel}", target_channel=scene.ylvc_channel),
    )
