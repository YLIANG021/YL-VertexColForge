# -*- coding: utf-8 -*-
"""Color attribute and viewport preview UI."""

from ...features.color import ops_preview
from ...i18n import tr
from ..common import draw_point_domain_hint, draw_unavailable, get_mesh_context, section_body


def draw_color_attributes_section(layout, context):
    scene = context.scene
    obj, _, active_color_attr = get_mesh_context(context)
    content = section_body(layout)

    if active_color_attr:
        is_previewing = obj.modifiers.get(ops_preview.PREVIEW_MODIFIER_NAME) is not None
        row_layer_ctrl = content.row(align=True)
        row_layer_ctrl.scale_y = 1.0
        row_layer_ctrl.enabled = not is_previewing
        row_layer_ctrl.prop(scene, "ylvc_layer_name", text="")
        row_layer_ctrl.operator("mesh.ylvc_rename_color_layer", text="", icon="PREFERENCES")
        row_layer_ctrl.operator("mesh.ylvc_ensure_color_layer", text="", icon="ADD")
        row_layer_ctrl.operator("mesh.ylvc_remove_color_layer", text="", icon="REMOVE")

        if active_color_attr.domain == "POINT":
            content.separator(factor=0.35)
            draw_point_domain_hint(content, active_color_attr)

        content.separator(factor=0.5)
        content.label(text=tr("Write Channel"))
        row_channel = content.row(align=True)
        row_channel.scale_y = 1.25
        row_channel.enabled = is_previewing
        row_channel.prop(scene, "ylvc_channel", expand=True)
    else:
        row_layer_ctrl = content.row(align=True)
        draw_unavailable(row_layer_ctrl, "no active color attribute")
        row_layer_ctrl.operator("mesh.ylvc_ensure_color_layer", text=tr("Add Attribute"), icon="ADD")
        return False

    content.separator()
    preview_supported = ops_preview.is_preview_supported(context)
    preview_row = content.row(align=True)
    preview_row.scale_y = 1.75
    preview_row.enabled = is_previewing or preview_supported
    preview_row.operator(
        "mesh.ylvc_toggle_preview",
        text=tr("Disable Viewport Preview") if is_previewing else tr("Enable Viewport Preview"),
        depress=is_previewing,
    )
    sync_toggle = preview_row.row(align=True)
    sync_toggle.enabled = is_previewing
    sync_toggle.prop(
        scene,
        "ylvc_sync_preview_channel",
        text="",
        icon="LINKED" if scene.ylvc_sync_preview_channel else "UNLINKED",
        toggle=True,
    )
    if not preview_supported and not is_previewing:
        draw_unavailable(content, "viewport preview in Workbench")
    preview_settings = content.column()
    preview_settings.enabled = is_previewing
    if not scene.ylvc_sync_preview_channel:
        row_preview_channel = preview_settings.row(align=True)
        row_preview_channel.prop(scene, "ylvc_preview_channel", expand=True)
    return True
