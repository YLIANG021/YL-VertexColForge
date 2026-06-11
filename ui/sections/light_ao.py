# -*- coding: utf-8 -*-
"""Light, AO, directional lighting, and curvature UI."""

from ...features.baking import ops_curvature_map
from ...features.gradients import ui_panels as gradient_ui
from ...i18n import tr, tr_format
from ..common import section_body


def draw_light_shadow_content(layout, context):
    scene = context.scene
    content = section_body(layout)
    gradient_ui.draw_light_ramp_controls(content, context)
    content.prop(scene, "ylvc_light_blend_mode", text=tr("Bake Blend"))

    ao_props = scene.ylvc_ao_props
    content.separator()
    content.label(text=tr("AO Bake"))
    col_ao = content.column(align=True)
    col_ao.prop(ao_props, "ao_samples")
    row_ao = content.row(align=True)
    row_ao.scale_y = 1.5
    row_ao.operator(
        "mesh.vcm_bake_ao_gpu",
        text=tr_format("AO {channel_key}", channel_key=scene.ylvc_channel),
    )
    row_ao.prop(
        ao_props,
        "use_ground_plane",
        text="",
        icon="VIEW_PERSPECTIVE",
        toggle=True,
    )

    content.separator()
    content.label(text=tr("Directional Lighting"))
    row_light = content.row(align=True)
    row_light.scale_y = 1.5
    is_tracing = scene.ylvc_is_tracing
    tracing_type = getattr(scene, "ylvc_tracing_type", "")
    row_light.operator(
        "mesh.vcm_test_dir_mask",
        text=tr_format("Light {channel_key}", channel_key=scene.ylvc_channel),
        depress=(is_tracing and tracing_type == "LIGHT_DIRECTION"),
    )

    content.separator()
    content.label(text=tr("Curvature"))
    curvature_props = scene.ylvc_curvature_props
    if not curvature_props.is_live:
        row_curvature = content.row(align=True)
        row_curvature.scale_y = 1.5
        row_curvature.operator(
            "mesh.vcm_start_curvature_live",
            text=tr_format("Curvature {channel_key}", channel_key=scene.ylvc_channel),
        )
    else:
        ops_curvature_map.mark_curvature_session_visible(context)
        row_curvature = content.row(align=True)
        row_curvature.scale_y = 1.5
        row_curvature.operator("mesh.vcm_apply_curvature_live", text=tr("Apply"))
        row_curvature.operator("mesh.vcm_cancel_curvature_live", text=tr("Cancel"))
        row_curvature.prop(
            curvature_props,
            "use_live_preview",
            icon="RESTRICT_VIEW_OFF" if curvature_props.use_live_preview else "RESTRICT_VIEW_ON",
            text="",
            toggle=True,
        )
        content.prop(curvature_props, "intensity", slider=True)
        content.prop(curvature_props, "offset", slider=True)
        content.prop(curvature_props, "contrast", slider=True)
