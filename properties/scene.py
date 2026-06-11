# -*- coding: utf-8 -*-
"""Scene property registration for YL VertexColForge."""

import bpy

from ..features import adjustments, baking
from . import callbacks

SCENE_PROPS = (
    "ylvc_layer_name",
    "ylvc_preview_channel",
    "ylvc_channel",
    "ylvc_source_channel",
    "ylvc_cached_rgb_fg",
    "ylvc_cached_rgb_bg",
    "ylvc_cached_rgb_valid",
    "ylvc_pure_fg_values",
    "ylvc_pure_bg_values",
    "ylvc_channel_updating",
    "ylvc_previous_channel",
    "ylvc_single_fg",
    "ylvc_single_bg",
    "ylvc_palette",
    "ylvc_alpha_fg",
    "ylvc_alpha_bg",
    "ylvc_brush_radius",
    "ylvc_brush_strength",
    "ylvc_brush_softness",
    "ylvc_write_blend_mode",
    "ylvc_select_tolerance",
    "ylvc_blend_mode",
    "ylvc_light_blend_mode",
    "ylvc_mirror_tolerance",
    "ylvc_is_tracing",
    "ylvc_tracing_type",
    "ylvc_use_live_gradient",
    "ylvc_random_mode",
    "ylvc_random_angle_threshold",
    "ylvc_random_vertex_group",
    "ylvc_sync_preview_channel",
    "ylvc_prev_shading_type",
    "ylvc_prev_shading_light",
    "ylvc_prev_shading_color_type",
    "ylvc_prev_shading_was_saved",
    "ylvc_tex_image",
    "ylvc_tex_source",
    "ylvc_bake_margin",
    "ylvc_show_texture_advanced",
    "ylvc_weight_source",
    "ylvc_weight_group_name",
    "ylvc_transfer_mode",
    "ylvc_show_mesh_advanced",
    "ylvc_ui_section",
    "ylvc_ao_props",
    "ylvc_curvature_props",
    "ylvc_adjust_props",
    "ylvc_blur_props",
)


def register_scene_properties():
    bpy.types.Scene.ylvc_layer_name = bpy.props.EnumProperty(
        name="Color Layer",
        items=callbacks.get_ylvc_layer_items,
        get=callbacks.get_ylvc_layer,
        set=callbacks.set_ylvc_layer,
        translation_context="YLVC_RAW_NAME",
    )
    bpy.types.Scene.ylvc_preview_channel = bpy.props.EnumProperty(
        name="Preview Channel",
        items=(("RGB", "RGB", ""), ("R", "R", ""), ("G", "G", ""), ("B", "B", ""), ("A", "A", "")),
        default="RGB",
        translation_context="YLVC_CHANNEL",
        update=callbacks.update_preview_channel,
    )
    bpy.types.Scene.ylvc_channel = bpy.props.EnumProperty(
        name="Write Channel",
        items=(("RGB", "RGB", ""), ("R", "R", ""), ("G", "G", ""), ("B", "B", ""), ("A", "A", "")),
        default="RGB",
        translation_context="YLVC_CHANNEL",
        update=callbacks.update_write_channel,
    )
    bpy.types.Scene.ylvc_source_channel = bpy.props.EnumProperty(
        name="Source Channel",
        items=(("R", "R", ""), ("G", "G", ""), ("B", "B", ""), ("A", "A", "")),
        default="R",
        translation_context="YLVC_CHANNEL",
        update=callbacks.update_plugin_state_only,
    )

    bpy.types.Scene.ylvc_cached_rgb_fg = bpy.props.FloatVectorProperty(
        name="Cached FG RGB",
        size=3,
        min=0.0,
        max=1.0,
        default=(1.0, 1.0, 1.0),
        options={"SKIP_SAVE"},
    )
    bpy.types.Scene.ylvc_cached_rgb_bg = bpy.props.FloatVectorProperty(
        name="Cached BG RGB",
        size=3,
        min=0.0,
        max=1.0,
        default=(0.0, 0.0, 0.0),
        options={"SKIP_SAVE"},
    )
    bpy.types.Scene.ylvc_cached_rgb_valid = bpy.props.BoolProperty(default=False, options={"SKIP_SAVE"})
    bpy.types.Scene.ylvc_pure_fg_values = bpy.props.FloatVectorProperty(
        name="Pure FG Values",
        size=3,
        min=0.0,
        max=1.0,
        default=(1.0, 1.0, 1.0),
        options={"SKIP_SAVE"},
    )
    bpy.types.Scene.ylvc_pure_bg_values = bpy.props.FloatVectorProperty(
        name="Pure BG Values",
        size=3,
        min=0.0,
        max=1.0,
        default=(0.0, 0.0, 0.0),
        options={"SKIP_SAVE"},
    )
    bpy.types.Scene.ylvc_channel_updating = bpy.props.BoolProperty(default=False, options={"SKIP_SAVE"})
    bpy.types.Scene.ylvc_previous_channel = bpy.props.StringProperty(default="RGB", options={"SKIP_SAVE"})

    bpy.types.Scene.ylvc_alpha_fg = bpy.props.FloatProperty(name="FG Alpha", min=0.0, max=1.0, default=1.0, update=callbacks.update_plugin_state_only)
    bpy.types.Scene.ylvc_alpha_bg = bpy.props.FloatProperty(name="BG Alpha", min=0.0, max=1.0, default=0.0, update=callbacks.update_plugin_state_only)

    bpy.types.Scene.ylvc_single_fg = bpy.props.FloatProperty(
        name="FG",
        subtype="FACTOR",
        min=0.0,
        max=1.0,
        get=callbacks.get_single_fg,
        set=callbacks.set_single_fg,
    )
    bpy.types.Scene.ylvc_single_bg = bpy.props.FloatProperty(
        name="BG",
        subtype="FACTOR",
        min=0.0,
        max=1.0,
        get=callbacks.get_single_bg,
        set=callbacks.set_single_bg,
    )
    bpy.types.Scene.ylvc_palette = bpy.props.PointerProperty(name="Color Preset Palette", type=bpy.types.Palette)

    bpy.types.Scene.ylvc_brush_radius = bpy.props.FloatProperty(
        name="Size",
        description="Screen-space brush size in pixels; painting still uses a 3D world-space radius at the hit point",
        min=2.0,
        soft_min=2.0,
        soft_max=200.0,
        default=48.0,
        precision=1,
        update=callbacks.update_plugin_state_only,
    )
    bpy.types.Scene.ylvc_brush_strength = bpy.props.FloatProperty(
        name="Strength",
        description="Paint strength applied at the center of the brush",
        subtype="FACTOR",
        min=0.0,
        max=1.0,
        default=1.0,
        precision=3,
        update=callbacks.update_plugin_state_only,
    )
    bpy.types.Scene.ylvc_brush_softness = bpy.props.FloatProperty(
        name="Hardness",
        description="Hard center size used by the local paint brush; 0 is soft, 1 is hard",
        subtype="FACTOR",
        min=0.0,
        max=1.0,
        default=0.5,
        precision=3,
        update=callbacks.update_plugin_state_only,
    )
    bpy.types.Scene.ylvc_write_blend_mode = bpy.props.EnumProperty(
        name="Blend",
        items=(
            ("REPLACE", "Replace", "Move current values toward the current brush value"),
            ("ADD", "Additive", "Add the current brush value"),
            ("SUBTRACT", "Subtract", "Subtract the current brush value"),
            ("MULTIPLY", "Multiply", "Multiply by the current brush value"),
            ("OVERLAY", "Overlay", "Apply an overlay blend with the current brush value"),
        ),
        default="REPLACE",
        update=callbacks.update_plugin_state_only,
    )
    bpy.types.Scene.ylvc_select_tolerance = bpy.props.FloatProperty(
        name="Tolerance",
        subtype="FACTOR",
        min=0.0,
        max=1.0,
        default=0.1,
        precision=3,
        update=callbacks.update_plugin_state_only,
    )
    bpy.types.Scene.ylvc_blend_mode = bpy.props.EnumProperty(
        name="Gradient Blend",
        items=(("REPLACE", "Replace", ""), ("MULTIPLY", "Multiply", ""), ("ADD", "Additive", ""), ("OVERLAY", "Overlay", "")),
        default="REPLACE",
        update=callbacks.update_plugin_state_only,
    )
    bpy.types.Scene.ylvc_light_blend_mode = bpy.props.EnumProperty(
        name="Lighting Blend",
        items=(("REPLACE", "Replace", ""), ("MULTIPLY", "Multiply", ""), ("ADD", "Additive", ""), ("OVERLAY", "Overlay", "")),
        default="REPLACE",
        update=callbacks.update_plugin_state_only,
    )
    bpy.types.Scene.ylvc_mirror_tolerance = bpy.props.FloatProperty(
        name="Mirror Tolerance",
        subtype="FACTOR",
        min=0.0,
        max=1.0,
        default=0.01,
        precision=4,
        update=callbacks.update_plugin_state_only,
    )
    bpy.types.Scene.ylvc_is_tracing = bpy.props.BoolProperty(name="Tracing", default=False, options={"SKIP_SAVE"})
    bpy.types.Scene.ylvc_tracing_type = bpy.props.StringProperty(default="", options={"SKIP_SAVE"})
    bpy.types.Scene.ylvc_use_live_gradient = bpy.props.BoolProperty(name="Live Preview", default=True, update=callbacks.update_plugin_state_only)
    bpy.types.Scene.ylvc_sync_preview_channel = bpy.props.BoolProperty(
        name="Sync Preview Channel",
        description="Keep Preview Channel synchronized with Write Channel",
        default=True,
        update=callbacks.update_sync_preview_channel,
        options={"SKIP_SAVE"},
    )

    bpy.types.Scene.ylvc_random_mode = bpy.props.EnumProperty(
        name="Mode",
        items=(
            ("CONNECTED", "By Connected", "Randomize by connected mesh geometry"),
            ("UV_ISLAND", "By UV Island", "Randomize by UV island"),
            ("MATERIAL", "By Material", "Randomize by material slot assignment"),
            ("SHARP_EDGE", "By Sharp Edge", "Randomize by sharp-edge-separated surface island"),
            ("ANGLE_ISLAND", "By Angle Island", "Randomize by surface island separated by face angle"),
            ("VERTEX_GROUP", "By Vertex Group", "Randomize by the chosen vertex group"),
            ("FACE", "By Face", "Randomize by polygon face"),
            ("VERTEX", "By Vertex", "Randomize by mesh vertex"),
        ),
        default="CONNECTED",
        update=callbacks.update_plugin_state_only,
    )
    bpy.types.Scene.ylvc_random_angle_threshold = bpy.props.FloatProperty(
        name="Angle Threshold",
        description="Face angle threshold used to separate angle islands",
        subtype="ANGLE",
        min=0.0,
        max=3.14159265,
        default=0.78539816,
        precision=2,
        update=callbacks.update_plugin_state_only,
    )
    bpy.types.Scene.ylvc_random_vertex_group = bpy.props.StringProperty(
        name="Random Vertex Group",
        description="Vertex group used by Randomize Colors in By Vertex Group mode",
        default="",
        update=callbacks.update_plugin_state_only,
    )

    bpy.types.Scene.ylvc_prev_shading_type = bpy.props.StringProperty(default="")
    bpy.types.Scene.ylvc_prev_shading_light = bpy.props.StringProperty(default="")
    bpy.types.Scene.ylvc_prev_shading_color_type = bpy.props.StringProperty(default="")
    bpy.types.Scene.ylvc_prev_shading_was_saved = bpy.props.BoolProperty(default=False)

    bpy.types.Scene.ylvc_tex_image = bpy.props.PointerProperty(
        name="Target Texture",
        type=bpy.types.Image,
        description="The image to sample from or bake to",
    )
    bpy.types.Scene.ylvc_tex_source = bpy.props.EnumProperty(
        name="Texture Source",
        items=(
            ("RGB", "RGB", "Read or write RGB from texture or vertex color"),
            ("R", "R", "Use red channel only"),
            ("G", "G", "Use green channel only"),
            ("B", "B", "Use blue channel only"),
            ("A", "A", "Use alpha channel only"),
        ),
        default="RGB",
        update=callbacks.update_plugin_state_only,
    )
    bpy.types.Scene.ylvc_bake_margin = bpy.props.IntProperty(
        name="Bake Margin",
        description="Padding in pixels used by bake",
        default=16,
        min=0,
        soft_max=128,
        update=callbacks.update_plugin_state_only,
    )
    bpy.types.Scene.ylvc_show_texture_advanced = bpy.props.BoolProperty(
        name="Advanced",
        default=False,
        options={"SKIP_SAVE"},
        update=callbacks.update_plugin_state_only,
    )
    bpy.types.Scene.ylvc_weight_source = bpy.props.EnumProperty(
        name="Source",
        items=(
            ("RGB", "RGB", "Convert RGB luminance to weight"),
            ("R", "R", "Use red channel only"),
            ("G", "G", "Use green channel only"),
            ("B", "B", "Use blue channel only"),
            ("A", "A", "Use alpha channel only"),
        ),
        default="RGB",
        update=callbacks.update_plugin_state_only,
    )
    bpy.types.Scene.ylvc_weight_group_name = bpy.props.StringProperty(
        name="Vertex Group",
        description="Vertex group to read from or write to",
        default="Weights",
        update=callbacks.update_plugin_state_only,
    )
    bpy.types.Scene.ylvc_transfer_mode = bpy.props.EnumProperty(
        name="Mode",
        items=(
            ("TEXTURE", "Texture <-> Vertex Color", "", 0),
            ("WEIGHT", "Weights <-> Vertex Color", "", 1),
            ("MESH", "Transfer Between Objects", "", 2),
        ),
        default="TEXTURE",
        update=callbacks.update_plugin_state_only,
    )
    bpy.types.Scene.ylvc_show_mesh_advanced = bpy.props.BoolProperty(
        name="Advanced",
        default=False,
        options={"SKIP_SAVE"},
        update=callbacks.update_plugin_state_only,
    )
    bpy.types.Scene.ylvc_ui_section = bpy.props.EnumProperty(
        name="Tool Section",
        items=(
            ("BRUSH", "Brush", "", "BRUSH_DATA", 0),
            ("GRADIENT", "Gradient", "", "COLOR", 1),
            ("SELECT", "Select", "", "RESTRICT_SELECT_OFF", 2),
            ("COPY", "Channel Blend", "", "UV_SYNC_SELECT", 3),
            ("LIGHT", "Light and AO", "", "LIGHT_SUN", 4),
            ("POST", "Color Adjust", "", "IMAGE_RGB", 5),
            ("RANDOM", "Random", "", "MOD_NOISE", 6),
            ("TRANSFER", "Color Transfer", "", "TEXTURE", 7),
        ),
        default="BRUSH",
        update=callbacks.update_ui_section,
        options={"SKIP_SAVE"},
    )

    bpy.types.Scene.ylvc_ao_props = bpy.props.PointerProperty(type=baking.ops_bake_ao.YLVCAOBakeSettings)
    bpy.types.Scene.ylvc_curvature_props = bpy.props.PointerProperty(type=baking.ops_curvature_map.YLVCCurvatureSettings)
    bpy.types.Scene.ylvc_adjust_props = bpy.props.PointerProperty(type=adjustments.ops_color_adjust.YLVCAdjustSettings)
    bpy.types.Scene.ylvc_blur_props = bpy.props.PointerProperty(type=adjustments.ops_smooth_blur.YLVCBlurSettings)


def unregister_scene_properties():
    for prop_name in SCENE_PROPS:
        if hasattr(bpy.types.Scene, prop_name):
            delattr(bpy.types.Scene, prop_name)
