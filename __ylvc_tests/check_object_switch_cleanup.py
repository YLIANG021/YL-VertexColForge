import pathlib
import sys


sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import bpy

from common import (
    addon,
    clear_scene,
    create_two_face_object,
    enable_fake_single_channel_preview,
    get_color_attribute_by_name,
    safe_unregister,
    set_active_obj,
)


def main():
    clear_scene()
    addon.register()
    try:
        obj_a = create_two_face_object("A")
        obj_b = create_two_face_object("B", 3.0)
        set_active_obj(obj_a)
        bpy.context.scene.ylvc_channel = "A"
        preview = enable_fake_single_channel_preview(obj_a, "CornerColor", "A", "SWITCH")
        print("PREVIEW_CREATED", preview is not None)
        set_active_obj(obj_b)
        bpy.context.view_layer.update()
        a_residue = get_color_attribute_by_name(obj_a.data, "__YLVC_PREVIEW__", allow_internal=True) is not None
        b_residue = get_color_attribute_by_name(obj_b.data, "__YLVC_PREVIEW__", allow_internal=True) is not None
        print("CHANNEL_AFTER_SWITCH", bpy.context.scene.ylvc_channel)
        print("A_RESIDUE", a_residue)
        print("B_RESIDUE", b_residue)
    finally:
        safe_unregister()


if __name__ == "__main__":
    main()
