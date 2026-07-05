# -*- coding: utf-8 -*-
import bpy

from .core_color_engine import find_ramp_node
from ...i18n import tr, tr_format
from ..color import ops_preview
from ...ui.common import draw_hint, draw_missing, draw_requires, get_mesh_context, section_body

PANEL_CATEGORY = "YL VertexColForge"


def _get_mesh_context(context):
    return get_mesh_context(context)


def _has_active_color_attr(context):
    _, _, active_color_attr = _get_mesh_context(context)
    return active_color_attr is not None


def _is_gradient_tool_active(context):
    return getattr(context.scene, "ylvc_ui_section", "") == "GRADIENT"


def _is_viewport_gradient_enabled(context, obj):
    return _is_gradient_tool_active(context) and _has_active_color_attr(context)


def _draw_ramp_controls(layout, context, show_blend=True):
    scene = context.scene
    ramp_node = find_ramp_node()
    if ramp_node is None:
        layout.operator("mesh.ylvc_init_ramp_data", text=tr("Create Ramp"), icon="ADD")
    else:
        layout.template_color_ramp(ramp_node, "color_ramp", expand=True)

    if show_blend:
        layout.prop(scene, "ylvc_blend_mode", text=tr("Blend"))


def draw_viewport_gradient_content(layout, context):
    scene = context.scene
    obj, _, active_color_attr = _get_mesh_context(context)
    content = section_body(layout)

    _draw_ramp_controls(content, context)

    content.separator()
    content.label(text=tr("Gradient"))
    row_gradient = content.row(align=True)
    row_gradient.scale_y = 1.5
    is_tracing = scene.ylvc_is_tracing
    tracing_type = getattr(scene, "ylvc_tracing_type", "")

    op_linear = row_gradient.operator(
        "mesh.ylvc_trace_ramp",
        text=tr_format("Linear {channel_key}", channel_key=scene.ylvc_channel),
        icon="EMPTY_SINGLE_ARROW",
        depress=(is_tracing and tracing_type == "LINEAR"),
    )
    if op_linear:
        op_linear.grad_type = "LINEAR"

    op_radial = row_gradient.operator(
        "mesh.ylvc_trace_ramp",
        text=tr_format("Radial {channel_key}", channel_key=scene.ylvc_channel),
        icon="MESH_CIRCLE",
        depress=(is_tracing and tracing_type == "RADIAL"),
    )
    if op_radial:
        op_radial.grad_type = "RADIAL"


class IMAGE_EDITOR_PT_YLVC_Gradient(bpy.types.Panel):
    bl_space_type = "IMAGE_EDITOR"
    bl_region_type = "UI"
    bl_category = PANEL_CATEGORY
    bl_label = "UV Gradient"

    @classmethod
    def poll(cls, context):
        obj, mesh, active_color_attr = _get_mesh_context(context)
        return context.area is not None and context.area.type == "IMAGE_EDITOR" and obj is not None and mesh is not None and active_color_attr is not None

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        obj, mesh, active_color_attr = _get_mesh_context(context)
        content = section_body(layout)

        if not ops_preview.is_native_preview_enabled(context):
            draw_hint(content, "Enable color attribute preview first.")
            return

        if not _is_gradient_tool_active(context):
            draw_hint(content, "Switch to Gradient mode first.")
            return

        if not mesh.uv_layers.active:
            draw_missing(content, "active UV map")
            return

        if active_color_attr and active_color_attr.domain != "CORNER":
            draw_requires(content, "Face Corner color attribute")
            return

        viewport_gradient_enabled = _is_viewport_gradient_enabled(context, obj)
        _draw_ramp_controls(content, context)

        row_action = content.row(align=True)
        row_action.scale_y = 1.5
        row_action.enabled = viewport_gradient_enabled
        row_action.operator(
            "image.ylvc_draw_uv_gradient",
            text=tr_format("UV -> {channel_key}", channel_key=scene.ylvc_channel),
            icon="COLOR",
            depress=(scene.ylvc_is_tracing and getattr(scene, "ylvc_tracing_type", "") == "UV_LINEAR"),
        )


CLASSES = (
    IMAGE_EDITOR_PT_YLVC_Gradient,
)
