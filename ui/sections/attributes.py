# -*- coding: utf-8 -*-
"""Attribute and viewport preview UI."""

from ...features.color import ops_preview
from ...i18n import tr
from ..common import draw_point_domain_hint, draw_unavailable, get_mesh_context, section_body


def draw_color_attributes_section(layout, context):
    scene = context.scene
    obj, _, active_color_attr = get_mesh_context(context)
    content = section_body(layout)
    preview_enabled = ops_preview.is_native_preview_enabled(context)
    editing_enabled = not preview_enabled

    if active_color_attr:
        row_layer_ctrl = content.row(align=True)
        row_layer_ctrl.scale_y = 1.0
        row_layer_ctrl.prop_search(scene, "ylvc_layer_name", obj.data, "color_attributes", text="")
        row_layer_ctrl.operator("mesh.ylvc_ensure_color_layer", text="", icon="ADD")
        remove_button = row_layer_ctrl.row(align=True)
        remove_button.enabled = editing_enabled
        remove_button.operator("mesh.ylvc_remove_color_layer", text="", icon="REMOVE")
        settings_button = row_layer_ctrl.row(align=True)
        settings_button.enabled = editing_enabled
        settings_button.operator("mesh.ylvc_rename_color_layer", text="", icon="PREFERENCES")

        if active_color_attr.domain == "POINT":
            content.separator(factor=0.35)
            draw_point_domain_hint(content, active_color_attr)

        content.separator(factor=0.5)
        content.label(text=tr("Preview Write"))
        row_channel = content.row(align=True)
        row_channel.scale_y = 1.25
        row_channel.enabled = preview_enabled
        row_channel.prop(scene, "ylvc_channel", expand=True)
    else:
        row_layer_ctrl = content.row(align=True)
        draw_unavailable(row_layer_ctrl, "no active color attribute")
        row_layer_ctrl.operator("mesh.ylvc_ensure_color_layer", text=tr("Add Attribute"), icon="ADD")
        return False

    content.separator()
    preview_row = content.row(align=True)
    preview_row.scale_y = 1.75
    if ops_preview.is_vertex_paint_single_channel(context):
        preview_row.operator("mesh.ylvc_switch_rgb_preview", text=tr("Switch to RGB Preview"))
        content.label(
            text=tr("Single-channel preview is not suitable for native painting. Switch to RGB preview first."),
            icon="KEYTYPE_KEYFRAME_VEC",
        )
    else:
        preview_row.operator(
            "mesh.ylvc_toggle_preview",
            text=tr("Exit Preview") if preview_enabled else tr("Preview Channel"),
            depress=preview_enabled,
        )
        flat_toggle = preview_row.row(align=True)
        flat_toggle.enabled = preview_enabled
        flat_toggle.operator(
            "mesh.ylvc_toggle_preview_flat",
            text="",
            icon="SHADING_SOLID",
            depress=ops_preview.is_flat_preview_enabled(context),
        )

    content.separator(factor=0.35)
    affect_row = content.row(align=True)
    affect_row.scale_y = 1.15
    affect_row.enabled = preview_enabled
    affect_text = "Only Affect Selected Mesh Part" if scene.ylvc_affect_selection else "Affect Whole Mesh"
    affect_row.prop(scene, "ylvc_affect_selection", text=tr(affect_text))
    return True
