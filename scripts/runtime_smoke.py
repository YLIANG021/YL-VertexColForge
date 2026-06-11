#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run Blender runtime smoke tests for core extension workflows."""

from __future__ import annotations

import argparse
import importlib
import math
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ID = "yl_vertexcolforge"
BLENDER_EXE = Path(r"C:\Program Files\Blender Foundation\Blender 5.1\blender.exe")


def running_inside_blender() -> bool:
    try:
        import bpy  # noqa: F401
    except Exception:
        return False
    return True


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blender", default=os.environ.get("BLENDER_EXE", str(BLENDER_EXE)))
    parser.add_argument("--package-id", default=PACKAGE_ID)
    parser.add_argument("--package-parent", default=str(ROOT.parent))
    return parser.parse_args(argv)


def run_in_blender(args: argparse.Namespace) -> int:
    blender = Path(args.blender)
    if not blender.exists():
        print(f"ERROR Blender executable not found: {blender}", file=sys.stderr)
        return 1

    command = [
        str(blender),
        "--background",
        "--factory-startup",
        "--python",
        str(Path(__file__).resolve()),
        "--",
        "--package-id",
        args.package_id,
        "--package-parent",
        args.package_parent,
    ]
    result = subprocess.run(command, cwd=ROOT, text=True)
    return result.returncode


def blender_script_args(argv: list[str]) -> list[str]:
    if "--" not in argv:
        return []
    return argv[argv.index("--") + 1:]


def assert_operator(result, op_name: str) -> None:
    if set(result) != {"FINISHED"}:
        raise RuntimeError(f"{op_name} returned {result}, expected FINISHED.")


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def color_array(bpy, attr):
    import numpy as np

    values = np.empty(len(attr.data) * 4, dtype=np.float32)
    if values.size:
        attr.data.foreach_get("color", values)
    values.shape = (-1, 4)
    return values


def set_color_array(attr, values) -> None:
    import numpy as np

    values = np.asarray(values, dtype=np.float32)
    attr.data.foreach_set("color", values.ravel())


def select_only(bpy, obj) -> None:
    for item in bpy.context.scene.objects:
        item.select_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def clear_scene(bpy) -> None:
    for obj in tuple(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)


class RuntimeContext:
    def __init__(self, bpy, active_object, *, region=None, region_data=None):
        self.scene = bpy.context.scene
        self.view_layer = bpy.context.view_layer
        self.window_manager = bpy.context.window_manager
        self.workspace = bpy.context.workspace
        self.active_object = active_object
        self.object = active_object
        self.area = None
        self.region = region
        self.region_data = region_data


class RuntimeRegion:
    width = 100
    height = 100


def make_square_mesh(bpy, name: str, *, domain: str = "CORNER", attr_name: str = "Color", offset=(0.0, 0.0, 0.0)):
    mesh = bpy.data.meshes.new(f"{name}Mesh")
    ox, oy, oz = offset
    vertices = [
        (-1.0 + ox, -1.0 + oy, 0.0 + oz),
        (1.0 + ox, -1.0 + oy, 0.0 + oz),
        (1.0 + ox, 1.0 + oy, 0.0 + oz),
        (-1.0 + ox, 1.0 + oy, 0.0 + oz),
    ]
    mesh.from_pydata(vertices, [], [(0, 1, 2, 3)])
    mesh.update()

    uv_layer = mesh.uv_layers.new(name="UVMap")
    for uv_data, uv in zip(uv_layer.data, ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0))):
        uv_data.uv = uv

    attr = mesh.color_attributes.new(name=attr_name, type="FLOAT_COLOR", domain=domain)
    mesh.color_attributes.active_color_index = 0
    mesh.color_attributes.render_color_index = 0
    set_color_array(attr, [(0.0, 0.0, 0.0, 1.0)] * len(attr.data))

    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    select_only(bpy, obj)
    bpy.context.scene.ylvc_layer_name = attr.name
    return obj, attr


def make_cube_mesh(bpy, name: str, *, domain: str = "POINT"):
    mesh = bpy.data.meshes.new(f"{name}Mesh")
    vertices = [
        (-1.0, -1.0, -1.0),
        (1.0, -1.0, -1.0),
        (1.0, 1.0, -1.0),
        (-1.0, 1.0, -1.0),
        (-1.0, -1.0, 1.0),
        (1.0, -1.0, 1.0),
        (1.0, 1.0, 1.0),
        (-1.0, 1.0, 1.0),
    ]
    faces = [
        (0, 1, 2, 3),
        (4, 7, 6, 5),
        (0, 4, 5, 1),
        (1, 5, 6, 2),
        (2, 6, 7, 3),
        (3, 7, 4, 0),
    ]
    mesh.from_pydata(vertices, [], faces)
    mesh.update()

    attr = mesh.color_attributes.new(name="Color", type="FLOAT_COLOR", domain=domain)
    mesh.color_attributes.active_color_index = 0
    mesh.color_attributes.render_color_index = 0
    set_color_array(attr, [(0.0, 0.0, 0.0, 1.0)] * len(attr.data))

    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    select_only(bpy, obj)
    bpy.context.scene.ylvc_layer_name = attr.name
    return obj, attr


def make_smoke_image(bpy, name="YLVC_RuntimeSmokeImage", size=2):
    image = bpy.data.images.new(name, width=size, height=size, alpha=True, float_buffer=True)
    pixels = [
        1.0, 0.0, 0.0, 1.0,
        0.0, 1.0, 0.0, 1.0,
        0.0, 0.0, 1.0, 1.0,
        1.0, 1.0, 1.0, 1.0,
    ]
    if size != 2:
        pixels = (pixels * (size * size))[: size * size * 4]
    image.pixels.foreach_set(pixels)
    image.update()
    return image


def smoke_random_channel_weight_texture_mirror(bpy, created_images) -> None:
    import numpy as np

    clear_scene(bpy)
    obj, attr = make_square_mesh(bpy, "YLVC_RuntimeTransferObject", domain="CORNER")
    scene = bpy.context.scene
    scene.ylvc_channel = "RGB"
    scene.ylvc_blend_mode = "REPLACE"
    scene.ylvc_random_mode = "CONNECTED"

    assert_operator(bpy.ops.mesh.ylvc_random_fill(), "mesh.ylvc_random_fill")
    assert_true(len(attr.data) == len(obj.data.loops), "Random fill smoke color attribute has an unexpected data count.")
    after_random = color_array(bpy, attr)
    assert_true(float(np.max(after_random[:, :3])) > 0.0, "Random fill did not write visible color data.")

    scene.ylvc_source_channel = "R"
    scene.ylvc_channel = "G"
    scene.ylvc_blend_mode = "REPLACE"
    assert_operator(bpy.ops.mesh.ylvc_copy_channel(), "mesh.ylvc_copy_channel")
    after_copy = color_array(bpy, attr)
    assert_true(np.allclose(after_copy[:, 1], after_copy[:, 0], atol=1e-5), "Channel copy did not copy R into G.")

    group = obj.vertex_groups.new(name="Weights")
    group.add([0, 1, 2, 3], 0.5, "REPLACE")
    scene.ylvc_weight_group_name = "Weights"
    scene.ylvc_channel = "B"
    assert_operator(bpy.ops.mesh.ylvc_weights_to_color(), "mesh.ylvc_weights_to_color")
    after_weights_to_color = color_array(bpy, attr)
    assert_true(np.allclose(after_weights_to_color[:, 2], 0.5, atol=1e-5), "Weights to color did not write B=0.5.")

    scene.ylvc_weight_source = "B"
    scene.ylvc_weight_group_name = "WeightsFromColor"
    assert_operator(bpy.ops.mesh.ylvc_color_to_weights(), "mesh.ylvc_color_to_weights")
    group_from_color = obj.vertex_groups.get("WeightsFromColor")
    assert_true(group_from_color is not None, "Color to weights did not create the target vertex group.")

    from yl_vertexcolforge import utils

    weights = utils.get_vertex_group_weights(obj, group_from_color, vertex_count=len(obj.data.vertices))
    assert_true(np.allclose(weights, 0.5, atol=1e-5), "Color to weights did not write expected vertex weights.")

    image = make_smoke_image(bpy)
    created_images.append(image)
    scene.ylvc_tex_image = image
    scene.ylvc_tex_source = "RGB"
    scene.ylvc_channel = "RGB"
    assert_operator(bpy.ops.mesh.ylvc_texture_to_color(), "mesh.ylvc_texture_to_color")
    after_texture_to_color = color_array(bpy, attr)
    assert_true(float(np.max(after_texture_to_color[:, :3])) > 0.0, "Texture to color did not write RGB data.")

    bake_image = make_smoke_image(bpy, name="YLVC_RuntimeBakeTarget", size=4)
    created_images.append(bake_image)
    scene.ylvc_tex_image = bake_image
    scene.ylvc_tex_source = "RGB"
    scene.ylvc_channel = "RGB"
    scene.ylvc_bake_margin = 0
    assert_operator(bpy.ops.mesh.ylvc_color_to_texture(), "mesh.ylvc_color_to_texture")

    scene.ylvc_channel = "R"
    scene.ylvc_mirror_tolerance = 0.001
    assert_operator(
        bpy.ops.mesh.ylvc_mirror_vertex_colors(axis="X", direction="POS_TO_NEG"),
        "mesh.ylvc_mirror_vertex_colors",
    )


def smoke_mesh_transfer(bpy) -> None:
    import numpy as np

    clear_scene(bpy)
    source_obj, source_attr = make_square_mesh(bpy, "YLVC_RuntimeSource", domain="CORNER")
    target_obj, target_attr = make_square_mesh(bpy, "YLVC_RuntimeTarget", domain="CORNER", offset=(0.0, 0.0, 0.0))

    source_colors = np.array(
        [
            (1.0, 0.0, 0.0, 1.0),
            (0.0, 1.0, 0.0, 1.0),
            (0.0, 0.0, 1.0, 1.0),
            (1.0, 1.0, 1.0, 1.0),
        ],
        dtype=np.float32,
    )
    set_color_array(source_attr, source_colors)
    set_color_array(target_attr, [(0.0, 0.0, 0.0, 1.0)] * len(target_attr.data))

    select_only(bpy, target_obj)
    target_obj.ylvc_transfer_source_object = source_obj
    scene = bpy.context.scene
    scene.ylvc_layer_name = target_attr.name
    scene.ylvc_transfer_settings.mapping_mode = "TOPOLOGY"
    scene.ylvc_transfer_settings.source_channel = "RGB"
    scene.ylvc_channel = "RGB"

    assert_operator(bpy.ops.mesh.ylvc_transfer_mesh_colors(), "mesh.ylvc_transfer_mesh_colors")
    transferred = color_array(bpy, target_attr)
    assert_true(np.allclose(transferred, source_colors, atol=1e-5), "Topology mesh transfer did not copy source colors.")


def smoke_3d_gradient_core(bpy) -> None:
    import numpy as np
    import types
    from yl_vertexcolforge.features.gradients import core_color_engine, ops_gradient_3d

    clear_scene(bpy)
    obj, attr = make_square_mesh(bpy, "YLVC_RuntimeGradient3D", domain="CORNER")
    scene = bpy.context.scene
    scene.ylvc_channel = "RGB"
    scene.ylvc_blend_mode = "REPLACE"
    scene.ylvc_layer_name = attr.name

    ramp_node = core_color_engine.ensure_ramp_node()
    assert_true(ramp_node is not None and ramp_node.color_ramp is not None, "Gradient ramp node was not available.")

    dummy = type("Gradient3DSmoke", (), {})()
    dummy.grad_type = "LINEAR"
    dummy.lut = core_color_engine.build_ramp_lut(ramp_node.color_ramp, 32)
    dummy.start_pos = (0.0, 0.0)
    dummy.mouse_pos = (100.0, 0.0)
    dummy._cached_mode = "OBJECT"
    dummy._cached_obj_name = obj.name
    dummy._cached_layer_name = attr.name
    dummy._cached_domain = attr.domain
    dummy._cached_data_type = attr.data_type
    dummy._cached_data_count = len(attr.data)
    dummy._cached_vert_count = len(obj.data.vertices)
    dummy._cached_region_size = (100, 100)
    dummy._cached_world_matrix_bytes = ops_gradient_3d.MESH_OT_YLVCTraceRamp._matrix_bytes(obj.matrix_world)
    dummy._cached_perspective_matrix_bytes = b""
    dummy._cached_mesh = obj.data
    dummy._cached_attribute = attr
    dummy._cached_colors_np = color_array(bpy, attr)
    dummy._work_colors_np = np.empty_like(dummy._cached_colors_np)
    dummy._target_rgba = np.empty((len(attr.data), 4), dtype=np.float32)
    dummy._cached_pts_2d = np.array([[0.0, 0.0], [100.0, 0.0], [100.0, 100.0], [0.0, 100.0]], dtype=np.float32)
    dummy._valid_mask = np.ones(len(obj.data.vertices), dtype=bool)
    dummy._loop_vert_indices = np.array([loop.vertex_index for loop in obj.data.loops], dtype=np.int32)
    dummy._data_mask = np.ones(len(attr.data), dtype=bool)
    dummy._data_mask_indices = np.arange(len(attr.data), dtype=np.int32)
    dummy._data_mask_count = len(attr.data)
    dummy._tmp_dx_vert = np.empty(len(obj.data.vertices), dtype=np.float32)
    dummy._tmp_dy_vert = np.empty(len(obj.data.vertices), dtype=np.float32)
    dummy._tmp_t_vert = np.empty(len(obj.data.vertices), dtype=np.float32)
    dummy._tmp_t_data = np.empty(len(attr.data), dtype=np.float32)
    dummy._lut_work_t = np.empty(len(attr.data), dtype=np.float32)
    dummy._lut_idx0 = np.empty(len(attr.data), dtype=np.int32)
    dummy._lut_idx1 = np.empty(len(attr.data), dtype=np.int32)
    dummy._lut_sample0 = np.empty((len(attr.data), 4), dtype=np.float32)
    dummy._lut_sample1 = np.empty((len(attr.data), 4), dtype=np.float32)
    dummy._lut_inv_weight = np.empty(len(attr.data), dtype=np.float32)
    dummy._blend_current = np.empty((len(attr.data), 4), dtype=np.float32)
    dummy._blend_gradient = np.empty((len(attr.data), 4), dtype=np.float32)
    dummy._blend_low_mask = np.empty((len(attr.data), 4), dtype=bool)
    dummy.report = lambda _level, _message: None
    dummy._fill_gradient_factors = types.MethodType(ops_gradient_3d.MESH_OT_YLVCTraceRamp._fill_gradient_factors, dummy)
    dummy._execute_object_gradient_fill = types.MethodType(
        ops_gradient_3d.MESH_OT_YLVCTraceRamp._execute_object_gradient_fill,
        dummy,
    )

    def get_valid_object_cache(context):
        return dummy._cached_mesh, dummy._cached_attribute

    dummy._get_valid_object_cache = get_valid_object_cache
    context = RuntimeContext(bpy, obj, region=RuntimeRegion(), region_data=object())
    success = ops_gradient_3d.MESH_OT_YLVCTraceRamp.execute_gradient_fill(dummy, context, is_live=False)
    assert_true(success, "3D gradient core write returned False.")
    written = color_array(bpy, attr)
    assert_true(float(np.max(written[:, :3])) > 0.0, "3D gradient core write did not affect colors.")


def smoke_uv_gradient_core(bpy) -> None:
    import numpy as np
    from yl_vertexcolforge.features.gradients import core_color_engine, ops_gradient_uv

    clear_scene(bpy)
    obj, attr = make_square_mesh(bpy, "YLVC_RuntimeGradientUV", domain="CORNER")
    scene = bpy.context.scene
    scene.ylvc_channel = "RGB"
    scene.ylvc_blend_mode = "REPLACE"
    scene.ylvc_layer_name = attr.name

    ramp_node = core_color_engine.ensure_ramp_node()
    assert_true(ramp_node is not None and ramp_node.color_ramp is not None, "UV gradient ramp node was not available.")

    dummy = type("UVGradientSmoke", (), {})()
    dummy.start_uv = (0.0, 0.0)
    dummy.end_uv = (1.0, 0.0)
    dummy.lut = core_color_engine.build_ramp_lut(ramp_node.color_ramp, 32)
    dummy._color_attr = attr
    dummy.layer_name = attr.name
    dummy.loop_count = len(obj.data.loops)
    dummy.uvs = np.array([tuple(uv.uv) for uv in obj.data.uv_layers.active.data], dtype=np.float32)
    dummy.uv_mask = np.ones(dummy.loop_count, dtype=bool)
    dummy.has_selection = False
    dummy.active_loop_indices = None
    dummy.selected_count = dummy.loop_count
    dummy.initial_colors = color_array(bpy, attr)
    dummy.work_colors = np.empty_like(dummy.initial_colors)
    dummy.target_rgba = np.empty((dummy.loop_count, 4), dtype=np.float32)
    dummy.t_arr_full = np.empty(dummy.loop_count, dtype=np.float32)
    dummy.active_uvs = None
    dummy.target_rgba_active = None
    dummy.t_arr_active = None
    dummy.bm = None
    dummy.bm_color_layer = None
    dummy.active_bm_loops = []
    dummy.active_bm_loop_indices = None
    dummy.cached_loop_colors = {}
    dummy.active_loop_colors = None
    dummy.active_work_colors = None
    dummy.report = lambda _level, _message: None
    success = ops_gradient_uv.IMAGE_EDITOR_OT_YLVCTestGradient.execute_uv_gradient(dummy, bpy.context, is_live=False)
    assert_true(success, "UV gradient core write returned False.")
    written = color_array(bpy, attr)
    assert_true(float(np.max(written[:, :3])) > 0.0, "UV gradient core write did not affect colors.")


def smoke_directional_light_core(bpy) -> None:
    import numpy as np
    from mathutils import Matrix
    from yl_vertexcolforge.features.baking import ops_gradient_map
    from yl_vertexcolforge.features.gradients import core_color_engine

    clear_scene(bpy)
    obj, attr = make_cube_mesh(bpy, "YLVC_RuntimeDirectionalLight", domain="POINT")
    scene = bpy.context.scene
    scene.ylvc_channel = "RGB"
    scene.ylvc_light_blend_mode = "REPLACE"
    scene.ylvc_layer_name = attr.name

    ramp_node = core_color_engine.ensure_light_ramp_node()
    assert_true(ramp_node is not None and ramp_node.color_ramp is not None, "Light ramp node was not available.")

    dummy = type("DirectionalSmoke", (), {})()
    dummy.obj = obj
    dummy.mesh = obj.data
    dummy.color_attr = attr
    dummy.domain = attr.domain
    dummy.world_normals_np = ops_gradient_map.get_world_normals_numpy(obj, obj.data)
    dummy.orig_colors = color_array(bpy, attr)
    dummy.data_mask = np.ones(len(attr.data), dtype=bool)
    dummy.work_colors = np.empty_like(dummy.orig_colors)
    dummy.ramp_colors = np.empty((len(attr.data), 4), dtype=np.float32)
    dummy.tmp_t_vert = np.empty(len(obj.data.vertices), dtype=np.float32)
    dummy.loop_vi = None
    dummy.tmp_t_data = None
    dummy.start_pos = (0.0, 0.0)
    dummy.mouse_pos = (100.0, 20.0)
    dummy.last_direction = None
    dummy.direction_dot_threshold = 0.99995
    dummy.lut = core_color_engine.build_ramp_lut(ramp_node.color_ramp, 32)

    region_data = type("RegionDataSmoke", (), {"view_matrix": Matrix.Identity(4)})()
    context = RuntimeContext(bpy, obj, region_data=region_data)
    success = ops_gradient_map.MESH_OT_VCM_TestDirectionalMask.execute_mask_engine(dummy, context)
    assert_true(success, "Directional lighting core write returned False.")
    written = color_array(bpy, attr)
    assert_true(float(np.max(written[:, :3])) > 0.0, "Directional lighting core write did not affect colors.")


def smoke_curvature_start_cancel(bpy) -> None:
    clear_scene(bpy)
    _obj, attr = make_cube_mesh(bpy, "YLVC_RuntimeCurvature", domain="POINT")
    scene = bpy.context.scene
    scene.ylvc_layer_name = attr.name
    scene.ylvc_channel = "RGB"
    scene.ylvc_light_blend_mode = "REPLACE"
    scene.ylvc_ui_section = "LIGHT"
    scene.ylvc_curvature_props.use_live_preview = True

    assert_operator(bpy.ops.mesh.vcm_start_curvature_live(), "mesh.vcm_start_curvature_live")
    assert_true(scene.ylvc_curvature_props.is_live, "Curvature live session did not start.")
    assert_operator(bpy.ops.mesh.vcm_cancel_curvature_live(), "mesh.vcm_cancel_curvature_live")
    assert_true(not scene.ylvc_curvature_props.is_live, "Curvature live session did not cancel.")


def smoke_ao_bake(bpy) -> None:
    import numpy as np

    clear_scene(bpy)
    _obj, attr = make_cube_mesh(bpy, "YLVC_RuntimeAO", domain="POINT")
    scene = bpy.context.scene
    scene.ylvc_layer_name = attr.name
    scene.ylvc_channel = "RGB"
    scene.ylvc_light_blend_mode = "REPLACE"
    scene.ylvc_ao_props.ao_samples = 8
    scene.ylvc_ao_props.use_ground_plane = False

    assert_operator(bpy.ops.mesh.vcm_bake_ao_gpu(), "mesh.vcm_bake_ao_gpu")
    written = color_array(bpy, attr)
    assert_true(np.all(np.isfinite(written)), "AO bake wrote non-finite color values.")


def run_smoke(package_id: str, package_parent: str) -> None:
    import bpy

    sys.path.insert(0, package_parent)
    module = importlib.import_module(package_id)
    module.register()

    created_images = []
    try:
        smoke_random_channel_weight_texture_mirror(bpy, created_images)
        print("YLVC_SMOKE_TRANSFER_TEXTURE_WEIGHT_MIRROR_OK")

        smoke_mesh_transfer(bpy)
        print("YLVC_SMOKE_MESH_TRANSFER_OK")

        smoke_3d_gradient_core(bpy)
        print("YLVC_SMOKE_GRADIENT_3D_CORE_OK")

        smoke_uv_gradient_core(bpy)
        print("YLVC_SMOKE_GRADIENT_UV_CORE_OK")

        smoke_directional_light_core(bpy)
        print("YLVC_SMOKE_DIRECTIONAL_LIGHT_CORE_OK")

        smoke_curvature_start_cancel(bpy)
        print("YLVC_SMOKE_CURVATURE_START_CANCEL_OK")

        smoke_ao_bake(bpy)
        print("YLVC_SMOKE_AO_BAKE_OK")

        print("YLVC_RUNTIME_SMOKE_OK")
    finally:
        for image in created_images:
            try:
                bpy.data.images.remove(image)
            except Exception:
                pass
        module.unregister()


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if running_inside_blender():
        args = parse_args(blender_script_args(sys.argv))
        run_smoke(args.package_id, args.package_parent)
        return 0

    args = parse_args(argv)
    return run_in_blender(args)


if __name__ == "__main__":
    raise SystemExit(main())
