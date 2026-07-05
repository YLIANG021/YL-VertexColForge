# -*- coding: utf-8 -*-
"""Random color UI."""

from ...i18n import tr, tr_format
from ..common import draw_missing, draw_requires, get_mesh_context, section_body


def draw_random_fill_content(layout, context):
    scene = context.scene
    obj, mesh, active_color_attr = get_mesh_context(context)
    content = section_body(layout)

    content.prop(scene, "ylvc_random_mode", text=tr("Mode"))

    has_uv = bool(mesh.uv_layers.active)
    supports_uv_island = active_color_attr is not None and active_color_attr.domain == "CORNER"
    mode = scene.ylvc_random_mode

    if mode == "ANGLE_ISLAND":
        if active_color_attr is not None and active_color_attr.domain == "POINT":
            draw_requires(content, "Face Corner color attribute")
        content.prop(scene, "ylvc_random_angle_threshold", text=tr("Angle Threshold"))
    elif mode == "UV_ISLAND":
        if not has_uv:
            draw_missing(content, "active UV map")
        if active_color_attr is not None and active_color_attr.domain == "POINT":
            draw_requires(content, "Face Corner color attribute")
    elif mode == "MATERIAL":
        if len(obj.material_slots) == 0:
            draw_missing(content, "material slots")
    elif mode == "SHARP_EDGE":
        pass

    row_action = content.row(align=True)
    row_action.scale_y = 1.5
    row_action.enabled = True
    if mode == "ANGLE_ISLAND":
        row_action.enabled = active_color_attr is not None and active_color_attr.domain == "CORNER"
    elif mode == "UV_ISLAND":
        row_action.enabled = has_uv and supports_uv_island
    elif mode == "MATERIAL":
        row_action.enabled = len(obj.material_slots) > 0
    row_action.operator(
        "mesh.ylvc_random_fill",
        text=tr_format("Randomize {channel_key}", channel_key=scene.ylvc_channel),
    )
