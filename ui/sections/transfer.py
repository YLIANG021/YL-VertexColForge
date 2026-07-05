# -*- coding: utf-8 -*-
"""Texture and weight transfer UI."""

from ...i18n import tr, tr_format
from ..common import draw_hint, draw_missing, draw_requires, get_mesh_context, section_body


def draw_texture_transfer_content(layout, context):
    scene = context.scene
    obj = context.active_object
    content = section_body(layout)

    content.prop(scene, "ylvc_transfer_mode", text=tr("Mode"))
    content.separator()

    transfer_mode = getattr(scene, "ylvc_transfer_mode", "TEXTURE")
    if transfer_mode == "TEXTURE":
        draw_transfer_texture_mode(content, context, obj)
    else:
        draw_transfer_weight_mode(content, context, obj)


def draw_transfer_texture_mode(content, context, obj):
    scene = context.scene
    has_image = bool(scene.ylvc_tex_image)
    has_uv = bool(obj and obj.data.uv_layers.active)

    col_setup = content.column()
    col_setup.prop(scene, "ylvc_tex_image", text=tr("Target Image"))
    col_setup.prop(scene, "ylvc_tex_source", text=tr("Source"))

    if not has_uv:
        draw_missing(content, "active UV map")

    _, _, active_color_attr = get_mesh_context(context)
    if active_color_attr is not None and active_color_attr.domain == "POINT":
        draw_hint(content, "Point domain works, but Face Corner usually gives cleaner UV results.")

    content.separator()

    row_advanced = content.row(align=True)
    row_advanced.alignment = "LEFT"
    row_advanced.prop(
        scene,
        "ylvc_show_texture_advanced",
        text=tr("Advanced"),
        icon="TRIA_DOWN" if scene.ylvc_show_texture_advanced else "TRIA_RIGHT",
        emboss=False,
    )
    if scene.ylvc_show_texture_advanced:
        col_advanced = content.column(align=True)
        col_advanced.prop(scene, "ylvc_image_padding", text=tr("Image Padding"))
        content.separator(factor=0.4)

    if not has_image:
        draw_requires(content, "target image")

    row_actions = content.row(align=True)
    row_actions.scale_y = 1.5
    row_actions.enabled = has_image and has_uv
    row_actions.operator(
        "mesh.ylvc_texture_to_color",
        text=tr_format("Sample to {channel_key}", channel_key=scene.ylvc_channel),
    )
    row_actions.operator(
        "mesh.ylvc_color_to_texture",
        text=tr_format("Write {channel_key} to Image", channel_key=scene.ylvc_channel),
    )


def draw_transfer_weight_mode(content, context, obj):
    scene = context.scene
    col_weight = content.column(align=True)
    col_weight.prop(scene, "ylvc_weight_source", text=tr("Source"))
    if obj and obj.type == "MESH":
        col_weight.prop_search(scene, "ylvc_weight_group_name", obj, "vertex_groups", text=tr("Vertex Group"))
    else:
        col_weight.prop(scene, "ylvc_weight_group_name", text=tr("Vertex Group"))

    row_actions = col_weight.row(align=True)
    row_actions.scale_y = 1.5
    row_actions.operator(
        "mesh.ylvc_color_to_weights",
        text=tr_format("{source_key} -> Weights", source_key=scene.ylvc_weight_source),
    )
    row_actions.operator(
        "mesh.ylvc_weights_to_color",
        text=tr_format("Weights -> {channel_key}", channel_key=scene.ylvc_channel),
    )
