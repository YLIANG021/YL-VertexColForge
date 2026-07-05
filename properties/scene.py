# -*- coding: utf-8 -*-
"""Scene property registration for YL VertexColForge."""

import bpy

from . import callbacks

SCENE_PROPS = (
    "ylvc_layer_name",
    "ylvc_channel",
    "ylvc_source_channel",
    "ylvc_copy_target_channel",
    "ylvc_previous_channel",
    "ylvc_fill_rgb_fg",
    "ylvc_fill_rgb_bg",
    "ylvc_single_fg",
    "ylvc_single_bg",
    "ylvc_alpha_fg",
    "ylvc_alpha_bg",
    "ylvc_brush_radius",
    "ylvc_brush_strength",
    "ylvc_brush_softness",
    "ylvc_write_blend_mode",
    "ylvc_blend_mode",
    "ylvc_affect_selection",
    "ylvc_select_tolerance",
    "ylvc_is_tracing",
    "ylvc_tracing_type",
    "ylvc_random_mode",
    "ylvc_random_angle_threshold",
    "ylvc_tex_image",
    "ylvc_tex_source",
    "ylvc_image_padding",
    "ylvc_show_texture_advanced",
    "ylvc_weight_source",
    "ylvc_weight_group_name",
    "ylvc_transfer_mode",
    "ylvc_ui_section",
)


def register_scene_properties():
    bpy.types.Scene.ylvc_layer_name = bpy.props.StringProperty(
        name="Attribute",
        get=callbacks.get_ylvc_layer_name,
        set=callbacks.set_ylvc_layer_name,
        translation_context="YLVC_RAW_NAME",
    )
    bpy.types.Scene.ylvc_channel = bpy.props.EnumProperty(
        name="Preview Write",
        items=(("RGB", "RGB", ""), ("R", "R", ""), ("G", "G", ""), ("B", "B", ""), ("A", "A", "")),
        default="RGB",
        translation_context="YLVC_CHANNEL",
        update=callbacks.update_write_channel,
    )
    bpy.types.Scene.ylvc_source_channel = bpy.props.EnumProperty(
        name="Source Channel",
        items=(("RGB", "RGB", ""), ("R", "R", ""), ("G", "G", ""), ("B", "B", ""), ("A", "A", "")),
        default="RGB",
        translation_context="YLVC_CHANNEL",
        update=callbacks.update_plugin_state_only,
    )
    bpy.types.Scene.ylvc_copy_target_channel = bpy.props.EnumProperty(
        name="Target Channel",
        items=(("RGB", "RGB", ""), ("R", "R", ""), ("G", "G", ""), ("B", "B", ""), ("A", "A", "")),
        default="RGB",
        translation_context="YLVC_CHANNEL",
        update=callbacks.update_plugin_state_only,
    )

    bpy.types.Scene.ylvc_fill_rgb_fg = bpy.props.FloatVectorProperty(
        name="FG Color",
        subtype="COLOR",
        size=3,
        min=0.0,
        max=1.0,
        default=(1.0, 1.0, 1.0),
        update=callbacks.update_plugin_state_only,
    )
    bpy.types.Scene.ylvc_fill_rgb_bg = bpy.props.FloatVectorProperty(
        name="BG Color",
        subtype="COLOR",
        size=3,
        min=0.0,
        max=1.0,
        default=(0.0, 0.0, 0.0),
        update=callbacks.update_plugin_state_only,
    )
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
    bpy.types.Scene.ylvc_brush_radius = bpy.props.FloatProperty(
        name="Size",
        description="Screen-space brush size in pixels",
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
        description="Hard center size used by the channel paint brush",
        subtype="FACTOR",
        min=0.0,
        max=1.0,
        default=0.5,
        precision=3,
        update=callbacks.update_plugin_state_only,
    )
    bpy.types.Scene.ylvc_write_blend_mode = bpy.props.EnumProperty(
        name="Paint Blend",
        items=(
            ("REPLACE", "Replace", "Move current values toward the brush value"),
            ("ADD", "Add", "Add the brush value"),
            ("SUBTRACT", "Subtract", "Subtract the brush value"),
            ("MULTIPLY", "Multiply", "Multiply by the brush value"),
            ("OVERLAY", "Overlay", "Apply an overlay blend with the brush value"),
        ),
        default="REPLACE",
        update=callbacks.update_plugin_state_only,
    )
    bpy.types.Scene.ylvc_blend_mode = bpy.props.EnumProperty(
        name="Blend",
        items=(("REPLACE", "Replace", ""), ("MULTIPLY", "Multiply", ""), ("ADD", "Additive", ""), ("OVERLAY", "Overlay", "")),
        default="REPLACE",
        update=callbacks.update_plugin_state_only,
    )
    bpy.types.Scene.ylvc_affect_selection = bpy.props.BoolProperty(
        name="Affect Selection",
        description="When enabled, color operations affect selected mesh elements when a selection exists",
        default=True,
        update=callbacks.update_plugin_state_only,
    )
    bpy.types.Scene.ylvc_select_tolerance = bpy.props.FloatProperty(
        name="Select Tolerance",
        subtype="FACTOR",
        min=0.0,
        max=1.0,
        default=0.2,
        precision=4,
        update=callbacks.update_plugin_state_only,
    )
    bpy.types.Scene.ylvc_is_tracing = bpy.props.BoolProperty(name="Tracing", default=False, options={"SKIP_SAVE"})
    bpy.types.Scene.ylvc_tracing_type = bpy.props.StringProperty(default="", options={"SKIP_SAVE"})
    bpy.types.Scene.ylvc_random_mode = bpy.props.EnumProperty(
        name="Mode",
        items=(
            ("CONNECTED", "By Connected", "Randomize by connected mesh geometry"),
            ("UV_ISLAND", "By UV Island", "Randomize by UV island"),
            ("MATERIAL", "By Material", "Randomize by material slot assignment"),
            ("SHARP_EDGE", "By Sharp Edge", "Randomize by sharp-edge-separated surface island"),
            ("ANGLE_ISLAND", "By Angle Island", "Randomize by surface island separated by face angle"),
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
    bpy.types.Scene.ylvc_tex_image = bpy.props.PointerProperty(
        name="Target Texture",
        type=bpy.types.Image,
        description="The image to sample from or write to",
    )
    bpy.types.Scene.ylvc_tex_source = bpy.props.EnumProperty(
        name="Texture Source",
        items=(
            ("RGB", "RGB", "Read or write RGB from image or attribute"),
            ("R", "R", "Use red channel only"),
            ("G", "G", "Use green channel only"),
            ("B", "B", "Use blue channel only"),
            ("A", "A", "Use alpha channel only"),
        ),
        default="RGB",
        update=callbacks.update_plugin_state_only,
    )
    bpy.types.Scene.ylvc_image_padding = bpy.props.IntProperty(
        name="Image Padding",
        description="Padding in pixels used when writing to image",
        default=2,
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
            ("TEXTURE", "Image <-> Channel", "", 0),
            ("WEIGHT", "Weights <-> Channel", "", 1),
        ),
        default="TEXTURE",
        update=callbacks.update_plugin_state_only,
    )
    bpy.types.Scene.ylvc_ui_section = bpy.props.EnumProperty(
        name="Section",
        items=(
            ("BRUSH", "Fill", "", "BRUSH_DATA", 0),
            ("SELECTION", "Select by Channel", "", "RESTRICT_SELECT_OFF", 1),
            ("GRADIENT", "Mask Generate", "", "COLORSET_03_VEC", 2),
            ("COPY", "Channel Ops", "", "MODIFIER", 3),
            ("RANDOM", "Channel Random", "", "MOD_NOISE", 4),
            ("TRANSFER", "Convert", "", "TEXTURE", 5),
        ),
        default="BRUSH",
        update=callbacks.update_ui_section,
        options={"SKIP_SAVE"},
    )

def unregister_scene_properties():
    for prop_name in SCENE_PROPS:
        if hasattr(bpy.types.Scene, prop_name):
            delattr(bpy.types.Scene, prop_name)
