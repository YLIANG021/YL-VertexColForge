import bpy
import numpy as np
import pathlib
import sys


sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from common import (
    addon,
    clear_scene,
    create_grid_object,
    data_indices_for_selected_faces,
    disable_fake_preview,
    enable_fake_single_channel_preview,
    get_color_attribute_by_name,
    make_test_image,
    read_color_attribute_colors,
    reset_attr,
    safe_unregister,
    select_first_half_faces,
    set_active_obj,
    set_layer,
    write_color_attribute_colors,
)


RESULTS = []


def log(name, ok=True, detail=""):
    status = "PASS" if ok else "FAIL"
    RESULTS.append((status, name, detail))
    print(f"YLVC_TEST {status}: {name}{' - ' + detail if detail else ''}")


def call_op(op, **kwargs):
    try:
        return op(**kwargs)
    except Exception as exc:
        return exc


def expect_finished(name, result):
    if isinstance(result, Exception):
        log(name, False, f"exception={result}")
        return False
    ok = result == {"FINISHED"} or result == {'FINISHED'}
    log(name, ok, f"result={result}")
    return ok


def assert_selection_only_changed(name, obj, attr, channel_indices, expected, untouched=0.0):
    if expected is None:
        log(name)
        return
    colors = read_color_attribute_colors(obj.data, attr)
    selected = data_indices_for_selected_faces(obj.data, attr)
    mask = np.zeros(len(colors), dtype=bool)
    mask[selected] = True
    ok = True
    for ci in channel_indices:
        ok = ok and np.allclose(colors[mask, ci], expected, atol=1e-4)
        if np.any(~mask):
            ok = ok and np.allclose(colors[~mask, ci], untouched, atol=1e-4)
    log(name, ok)


def test_fill_and_preview(obj, attr):
    scene = bpy.context.scene
    scene.ylvc_affect_selection = True
    set_layer(obj, attr)
    select_first_half_faces(obj)
    reset_attr(attr)

    scene.ylvc_channel = "RGB"
    scene.ylvc_fill_rgb_fg = (0.2, 0.4, 0.6)
    scene.ylvc_alpha_fg = 0.8
    expect_finished(f"fill RGB selected {attr.domain}", bpy.ops.mesh.ylvc_apply_scene_value())
    assert_selection_only_changed(f"fill RGB selection mask {attr.domain}", obj, attr, (0, 1, 2), None)
    colors = read_color_attribute_colors(obj.data, attr)
    selected = data_indices_for_selected_faces(obj.data, attr)
    log(f"fill RGB values {attr.domain}", np.allclose(colors[selected, 0:3], (0.2, 0.4, 0.6), atol=1e-4))

    reset_attr(attr)
    scene.ylvc_channel = "A"
    scene.ylvc_single_fg = 0.35
    expect_finished(f"fill A selected {attr.domain}", bpy.ops.mesh.ylvc_apply_scene_value())
    assert_selection_only_changed(f"fill A selection mask {attr.domain}", obj, attr, (3,), 0.35)

    preview = enable_fake_single_channel_preview(obj, attr, "A", f"SMOKE_{attr.domain}")
    log(f"single-channel preview sync {attr.domain} A", preview is not None)
    scene.ylvc_single_fg = 0.65
    expect_finished(f"fill A while single preview {attr.domain}", bpy.ops.mesh.ylvc_apply_scene_value())
    assert_selection_only_changed(f"fill A while preview mask {attr.domain}", obj, attr, (3,), 0.65)
    disable_fake_preview()
    preview = get_color_attribute_by_name(obj.data, "__YLVC_PREVIEW__", allow_internal=True)
    log(f"preview residue cleared {attr.domain}", preview is None)


def test_channel_ops(obj, attr):
    scene = bpy.context.scene
    scene.ylvc_affect_selection = True
    set_layer(obj, attr)
    select_first_half_faces(obj)
    base = np.zeros((len(attr.data), 4), dtype=np.float32)
    base[:, :] = (0.2, 0.4, 0.6, 0.8)
    write_color_attribute_colors(attr, base)

    scene.ylvc_source_channel = "RGB"
    scene.ylvc_copy_target_channel = "A"
    expect_finished(f"copy RGB to A selected {attr.domain}", bpy.ops.mesh.ylvc_copy_channel())
    colors = read_color_attribute_colors(obj.data, attr)
    selected = data_indices_for_selected_faces(obj.data, attr)
    log(f"copy RGB to A values {attr.domain}", np.all(colors[selected, 3] > 0.35))

    scene.ylvc_source_channel = "R"
    scene.ylvc_copy_target_channel = "B"
    expect_finished(f"swap R B selected {attr.domain}", bpy.ops.mesh.ylvc_swap_channel())
    scene.ylvc_channel = "A"
    expect_finished(f"invert A selected {attr.domain}", bpy.ops.mesh.ylvc_invert_channel())
    colors = read_color_attribute_colors(obj.data, attr)
    selected = data_indices_for_selected_faces(obj.data, attr)
    if len(selected) > 1:
        colors[selected, 0] = np.linspace(0.1, 0.9, len(selected), dtype=np.float32)
        write_color_attribute_colors(attr, colors)
    scene.ylvc_channel = "R"
    expect_finished(f"normalize R selected {attr.domain}", bpy.ops.mesh.ylvc_normalize_channel())


def test_random(obj, attr):
    scene = bpy.context.scene
    scene.ylvc_affect_selection = True
    set_layer(obj, attr)
    select_first_half_faces(obj)
    modes = ("CONNECTED", "MATERIAL", "UV_ISLAND", "SHARP_EDGE", "ANGLE_ISLAND")
    if attr.domain == "POINT":
        modes = ("CONNECTED", "MATERIAL", "SHARP_EDGE")
    for mode in modes:
        scene.ylvc_random_mode = mode
        for channel in ("RGB", "A"):
            scene.ylvc_channel = channel
            expect_finished(f"random {mode} {channel} {attr.domain}", bpy.ops.mesh.ylvc_random_fill())


def test_texture_and_weights(obj, attr):
    scene = bpy.context.scene
    scene.ylvc_affect_selection = True
    set_layer(obj, attr)
    select_first_half_faces(obj)
    reset_attr(attr)
    scene.ylvc_tex_image = make_test_image()
    scene.ylvc_channel = "R"
    scene.ylvc_tex_source = "G"
    expect_finished(f"image G to R selected {attr.domain}", bpy.ops.mesh.ylvc_texture_to_color())
    scene.ylvc_channel = "A"
    scene.ylvc_tex_source = "RGB"
    expect_finished(f"write A to image {attr.domain}", bpy.ops.mesh.ylvc_color_to_texture())
    scene.ylvc_weight_group_name = f"WG_{attr.domain}"
    scene.ylvc_weight_source = "R"
    expect_finished(f"color R to weights {attr.domain}", bpy.ops.mesh.ylvc_color_to_weights())
    scene.ylvc_channel = "A"
    expect_finished(f"weights to A selected {attr.domain}", bpy.ops.mesh.ylvc_weights_to_color())


def test_render_index_not_changed(obj, attr):
    set_layer(obj, attr)
    attrs = obj.data.color_attributes
    attrs.render_color_index = 0
    scene = bpy.context.scene
    scene.ylvc_channel = "A"
    enable_fake_single_channel_preview(obj, attr, "A", "RENDER_INDEX")
    unchanged = attrs.render_color_index == 0
    disable_fake_preview()
    log("render color index unchanged in preview", unchanged)


def main():
    clear_scene()
    addon.register()
    try:
        obj, _corner, _point = create_grid_object("YLVC_A", 0.0)
        set_active_obj(obj)
        for attr_name in ("CornerColor", "VertexColor"):
            attr = obj.data.color_attributes[attr_name]
            test_fill_and_preview(obj, attr)
            test_channel_ops(obj, attr)
            test_random(obj, attr)
            test_texture_and_weights(obj, attr)
        test_render_index_not_changed(obj, obj.data.color_attributes["CornerColor"])
    finally:
        safe_unregister()

    failed = [item for item in RESULTS if item[0] != "PASS"]
    print(f"YLVC_TEST_SUMMARY total={len(RESULTS)} failed={len(failed)}")


if __name__ == "__main__":
    main()
