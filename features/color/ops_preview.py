# -*- coding: utf-8 -*-
import bpy
import re

from ... import utils
from ...core.context import resolve_active_mesh
from ...core.logging import debug
from ...core.operator_poll import has_active_mesh
from ...i18n import tr
from ...paths import preview_blend_path

PREVIEW_MODIFIER_NAME = "YLVC_Preview"
PREVIEW_NODE_GROUP_NAME = "Vertex Color Display"
PREVIEW_AUX_NODE_GROUP_NAMES = ("Switchboard x5",)
PREVIEW_MATERIAL_NAME = "YLVC__Preview_Vertex_RGBA"
LEGACY_PREVIEW_MATERIAL_NAMES = ("Vertex RGBA",)
PREVIEW_MONITOR_INTERVAL = 0.4
_PREVIEW_SOCKET_CACHE = {}
_PREVIEW_MONITOR_ACTIVE = False


def load_preview_node_group():
    if PREVIEW_NODE_GROUP_NAME in bpy.data.node_groups:
        return bpy.data.node_groups[PREVIEW_NODE_GROUP_NAME]

    blend_path = preview_blend_path()
    if not blend_path.exists():
        return None

    with bpy.data.libraries.load(str(blend_path), link=False) as (data_from, data_to):
        if PREVIEW_NODE_GROUP_NAME in data_from.node_groups:
            data_to.node_groups = [PREVIEW_NODE_GROUP_NAME]

    return bpy.data.node_groups.get(PREVIEW_NODE_GROUP_NAME)


def load_preview_material():
    if PREVIEW_MATERIAL_NAME in bpy.data.materials:
        return bpy.data.materials[PREVIEW_MATERIAL_NAME]

    blend_path = preview_blend_path()
    if not blend_path.exists():
        return None

    with bpy.data.libraries.load(str(blend_path), link=False) as (data_from, data_to):
        if PREVIEW_MATERIAL_NAME in data_from.materials:
            data_to.materials = [PREVIEW_MATERIAL_NAME]

    return bpy.data.materials.get(PREVIEW_MATERIAL_NAME)


def _matches_preview_runtime_name(name, base_names):
    for base_name in base_names:
        if name == base_name or re.fullmatch(rf"{re.escape(base_name)}\.\d{{3}}", name):
            return True
    return False


def _remove_runtime_datablock(collection, datablock):
    if datablock is None:
        return False
    try:
        datablock.use_fake_user = False
    except Exception:
        pass
    try:
        collection.remove(datablock, do_unlink=True)
        return True
    except Exception:
        return False


def cleanup_preview_node_groups():
    if any_preview_modifiers_exist():
        return

    node_group_names = (PREVIEW_NODE_GROUP_NAME, *PREVIEW_AUX_NODE_GROUP_NAMES)
    for node_group in list(bpy.data.node_groups):
        name = getattr(node_group, "name", "")
        if not _matches_preview_runtime_name(name, node_group_names):
            continue
        _remove_runtime_datablock(bpy.data.node_groups, node_group)


def cleanup_preview_materials():
    if any_preview_modifiers_exist():
        return

    material_names = (PREVIEW_MATERIAL_NAME, *LEGACY_PREVIEW_MATERIAL_NAMES)
    for material in list(bpy.data.materials):
        name = getattr(material, "name", "")
        if not _matches_preview_runtime_name(name, material_names):
            continue
        _remove_runtime_datablock(bpy.data.materials, material)


def _iter_preview_input_socket_ids(modifier):
    node_group = getattr(modifier, "node_group", None)
    if not node_group or not hasattr(node_group, "interface"):
        return

    cache_key = getattr(node_group, "name_full", "") or getattr(node_group, "name", "")
    cached = _PREVIEW_SOCKET_CACHE.get(cache_key)
    if cached is not None:
        for identifier in cached:
            yield identifier
        return

    candidates = []
    for item in getattr(node_group.interface, "items_tree", []):
        if getattr(item, "item_type", "") != "SOCKET" or getattr(item, "in_out", "") != "INPUT":
            continue

        socket_type = str(getattr(item, "socket_type", "") or "")
        socket_name = f"{getattr(item, 'name', '')} {getattr(item, 'identifier', '')}".lower()
        if "geometry" in socket_type.lower():
            continue

        priority = 100
        if "channel" in socket_name:
            priority -= 80
        if "preview" in socket_name:
            priority -= 25
        if "mode" in socket_name:
            priority -= 10
        if "menu" in socket_type.lower():
            priority -= 35
        if "enum" in socket_type.lower():
            priority -= 20
        if "int" in socket_type.lower():
            priority -= 15
        if "float" in socket_type.lower():
            priority += 10

        candidates.append((priority, item.identifier))

    seen = set()
    resolved = []
    for _priority, identifier in sorted(candidates, key=lambda item: item[0]):
        if not identifier or identifier in seen:
            continue
        seen.add(identifier)
        resolved.append(identifier)

    if cache_key:
        _PREVIEW_SOCKET_CACHE[cache_key] = tuple(resolved)

    for identifier in resolved:
        yield identifier


def _tag_preview_target(modifier, node_group=None, context=None, update_view_layer=False):
    try:
        modifier.update_tag()
    except Exception:
        pass
    try:
        if modifier.id_data:
            modifier.id_data.update_tag()
    except Exception:
        pass
    if update_view_layer:
        try:
            if context and hasattr(context, "view_layer"):
                context.view_layer.update()
        except Exception:
            pass


def _iter_scene_preview_modifiers(scene):
    if scene is None:
        return
    for obj in getattr(scene, "objects", []):
        if getattr(obj, "type", None) != "MESH":
            continue
        modifier = obj.modifiers.get(PREVIEW_MODIFIER_NAME)
        if modifier is not None:
            yield obj, modifier


def _iter_preview_material_color_nodes(material):
    if material is None:
        return
    node_tree = getattr(material, "node_tree", None)
    if node_tree is None:
        return

    for node in getattr(node_tree, "nodes", []):
        if getattr(node, "bl_idname", "") == "ShaderNodeVertexColor":
            yield node


def sync_preview_color_layer(layer_name):
    if not layer_name:
        return False

    material = load_preview_material()
    if material is None:
        return False

    updated = False
    for node in _iter_preview_material_color_nodes(material):
        try:
            if getattr(node, "layer_name", "") != layer_name:
                node.layer_name = layer_name
                updated = True
        except Exception:
            continue

    if updated:
        try:
            material.update_tag()
        except Exception:
            pass
    return updated


def _set_preview_channel_on_node_group(node_group, channel):
    if node_group is None:
        return False

    updated = False
    interface = getattr(node_group, "interface", None)
    if interface is not None:
        for item in getattr(interface, "items_tree", []):
            if getattr(item, "item_type", "") != "SOCKET" or getattr(item, "in_out", "") != "INPUT":
                continue
            socket_name = f"{getattr(item, 'name', '')} {getattr(item, 'identifier', '')}".lower()
            socket_type = str(getattr(item, "socket_type", "") or "").lower()
            if "channel" not in socket_name and "menu" not in socket_type:
                continue
            try:
                item.default_value = channel
                updated = True
                break
            except Exception:
                continue

    menu_node = None
    try:
        menu_node = node_group.nodes.get("Menu Switch")
    except Exception:
        menu_node = None
    if menu_node is not None:
        try:
            menu_input = menu_node.inputs.get("Menu")
        except Exception:
            menu_input = None
        if menu_input is not None:
            try:
                menu_input.default_value = channel
                updated = True
            except Exception:
                pass

    if updated:
        try:
            node_group.interface_update(bpy.context)
        except Exception:
            pass
        try:
            node_group.update_tag()
        except Exception:
            pass
    return updated

def set_preview_channel(modifier, channel, context=None):
    socket_ids = list(_iter_preview_input_socket_ids(modifier))
    preview_index = utils.PREVIEW_CHANNEL_INDEX.get(channel, 4)
    node_group = getattr(modifier, "node_group", None)
    updated = False

    try:
        for socket_id in socket_ids:
            try:
                current_value = modifier.get(socket_id)
                if current_value == preview_index:
                    return False
                modifier[socket_id] = preview_index
                updated = True
            except Exception:
                continue
            break
    except Exception as exc:
        debug(f"YLVC preview update failed: {exc}")

    if updated:
        _tag_preview_target(modifier, node_group=node_group, context=context, update_view_layer=False)
        return True

    updated = _set_preview_channel_on_node_group(node_group, channel)
    if updated:
        _tag_preview_target(modifier, node_group=node_group, context=context, update_view_layer=False)
    return updated


def get_preview_channel(scene):
    if not scene:
        return "RGB"
    if getattr(scene, "ylvc_sync_preview_channel", True):
        return getattr(scene, "ylvc_channel", "RGB")
    return getattr(scene, "ylvc_preview_channel", "RGB")


def clear_other_preview_modifiers(context, active_obj):
    scene = getattr(context, "scene", None)
    if scene is None:
        return

    for obj in scene.objects:
        if obj == active_obj or obj.type != "MESH":
            continue
        modifier = obj.modifiers.get(PREVIEW_MODIFIER_NAME)
        if modifier is not None:
            obj.modifiers.remove(modifier)


def has_any_preview_modifier(scene):
    if scene is None:
        return False

    for obj in scene.objects:
        if obj.type != "MESH":
            continue
        if obj.modifiers.get(PREVIEW_MODIFIER_NAME) is not None:
            return True
    return False


def any_preview_modifiers_exist():
    for scene in getattr(bpy.data, "scenes", []):
        if has_any_preview_modifier(scene):
            return True
    return False


def update_channel_preview(self, context):
    scene = getattr(context, "scene", None)
    if scene is None:
        return
    preview_channel = get_preview_channel(self)
    for _obj, modifier in _iter_scene_preview_modifiers(scene):
        set_preview_channel(modifier, preview_channel, context)


def is_preview_supported(context):
    scene = getattr(context, "scene", None)
    render = getattr(scene, "render", None)
    return getattr(render, "engine", "") != "BLENDER_WORKBENCH"


def _get_view3d_shading(context):
    space = getattr(context, "space_data", None)
    if space and space.type == "VIEW_3D":
        return space.shading

    area = getattr(context, "area", None)
    if area and area.type == "VIEW_3D":
        for item in area.spaces:
            if item.type == "VIEW_3D":
                return item.shading
    return None


def _capture_shading_state(scene, shading):
    if not shading:
        return
    scene.ylvc_prev_shading_type = getattr(shading, "type", "")
    scene.ylvc_prev_shading_light = getattr(shading, "light", "")
    scene.ylvc_prev_shading_color_type = getattr(shading, "color_type", "")
    scene.ylvc_prev_shading_was_saved = True


def _set_shading_type(shading, preferred_types, fallback="SOLID"):
    if not shading:
        return False

    for shading_type in preferred_types:
        try:
            shading.type = shading_type
            return True
        except Exception:
            continue

    try:
        shading.type = fallback
        return True
    except Exception:
        return False


def _restore_shading_state(scene, shading):
    if not shading or not getattr(scene, "ylvc_prev_shading_was_saved", False):
        return False

    prev_type = getattr(scene, "ylvc_prev_shading_type", "")
    prev_light = getattr(scene, "ylvc_prev_shading_light", "")
    prev_color_type = getattr(scene, "ylvc_prev_shading_color_type", "")

    if prev_type:
        try:
            _set_shading_type(shading, [prev_type])
        except Exception:
            pass
    if prev_light:
        try:
            shading.light = prev_light
        except Exception:
            pass
    if prev_color_type:
        try:
            shading.color_type = prev_color_type
        except Exception:
            pass

    scene.ylvc_prev_shading_was_saved = False
    return True


def disable_preview_for_scene(scene, restore_shading=False, shading=None):
    if scene is None:
        return False

    removed_any = False
    for obj, modifier in tuple(_iter_scene_preview_modifiers(scene)):
        try:
            obj.modifiers.remove(modifier)
            removed_any = True
        except Exception:
            pass

    if restore_shading:
        restored = _restore_shading_state(scene, shading)
        if not restored and shading:
            _set_shading_type(shading, ["SOLID"])
    else:
        scene.ylvc_prev_shading_was_saved = False

    cleanup_preview_node_groups()
    cleanup_preview_materials()
    sync_preview_monitor_state(force_scan=False)

    return removed_any


def _iter_view3d_shadings_for_scene(scene):
    window_manager = getattr(bpy.context, "window_manager", None)
    if window_manager is None:
        return

    for window in getattr(window_manager, "windows", []):
        if getattr(window, "scene", None) != scene:
            continue
        screen = getattr(window, "screen", None)
        if screen is None:
            continue
        for area in getattr(screen, "areas", []):
            if getattr(area, "type", None) != "VIEW_3D":
                continue
            for space in getattr(area, "spaces", []):
                if getattr(space, "type", None) == "VIEW_3D" and getattr(space, "shading", None) is not None:
                    yield space.shading


def preview_state_monitor():
    global _PREVIEW_MONITOR_ACTIVE
    try:
        if not any_preview_modifiers_exist():
            _PREVIEW_MONITOR_ACTIVE = False
            return None

        for scene in getattr(bpy.data, "scenes", []):
            if not has_any_preview_modifier(scene):
                continue

            shading_types = [getattr(shading, "type", "") for shading in _iter_view3d_shadings_for_scene(scene)]
            if not shading_types:
                continue

            if any(shading_type in {"MATERIAL", "RENDERED"} for shading_type in shading_types):
                continue

            if any(shading_type in {"SOLID", "WIREFRAME"} for shading_type in shading_types):
                disable_preview_for_scene(scene, restore_shading=False)
    except Exception as exc:
        debug(f"YLVC preview monitor failed: {exc}")

    return PREVIEW_MONITOR_INTERVAL


def _start_preview_monitor():
    global _PREVIEW_MONITOR_ACTIVE
    try:
        if not bpy.app.timers.is_registered(preview_state_monitor):
            bpy.app.timers.register(preview_state_monitor, first_interval=PREVIEW_MONITOR_INTERVAL, persistent=True)
        _PREVIEW_MONITOR_ACTIVE = True
    except Exception:
        pass


def _stop_preview_monitor():
    global _PREVIEW_MONITOR_ACTIVE
    try:
        if bpy.app.timers.is_registered(preview_state_monitor):
            bpy.app.timers.unregister(preview_state_monitor)
    except Exception:
        pass
    _PREVIEW_MONITOR_ACTIVE = False


def sync_preview_monitor_state(force_scan=False):
    has_preview = any_preview_modifiers_exist()
    if has_preview:
        _start_preview_monitor()
    elif force_scan or _PREVIEW_MONITOR_ACTIVE:
        _stop_preview_monitor()
    return has_preview


def register_runtime_helpers():
    sync_preview_monitor_state(force_scan=True)


def unregister_runtime_helpers():
    _stop_preview_monitor()


class MESH_OT_YLVCTogglePreview(bpy.types.Operator):
    bl_idname = "mesh.ylvc_toggle_preview"
    bl_label = "Toggle Viewport Preview"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return has_active_mesh(context)

    def execute(self, context):
        obj, _, error = resolve_active_mesh(context)
        if error:
            self.report({"WARNING"}, error)
            return {"CANCELLED"}

        scene = context.scene
        shading = _get_view3d_shading(context)
        modifier = obj.modifiers.get(PREVIEW_MODIFIER_NAME)

        if modifier is not None:
            disable_preview_for_scene(scene, restore_shading=True, shading=shading)
            self.report({"INFO"}, tr("Preview disabled."))
            return {"FINISHED"}

        if not is_preview_supported(context):
            self.report({"WARNING"}, tr("Viewport preview is unavailable while using Workbench render engine."))
            return {"CANCELLED"}

        preview_was_active = has_any_preview_modifier(scene)
        if not preview_was_active:
            cleanup_preview_node_groups()
            cleanup_preview_materials()

        node_group = load_preview_node_group()
        if not node_group:
            self.report({"ERROR"}, tr("Could not load VertexDisplay.blend."))
            return {"CANCELLED"}

        clear_other_preview_modifiers(context, obj)
        if not preview_was_active:
            _capture_shading_state(scene, shading)

        modifier = obj.modifiers.new(name=PREVIEW_MODIFIER_NAME, type="NODES")
        modifier.node_group = node_group
        modifier.use_pin_to_last = True
        modifier.show_in_editmode = True
        set_preview_channel(modifier, get_preview_channel(scene), context)
        _start_preview_monitor()

        if shading:
            _set_shading_type(shading, ["MATERIAL", "RENDERED", "SOLID"])
        self.report({"INFO"}, tr("Preview enabled."))
        return {"FINISHED"}


CLASSES = (MESH_OT_YLVCTogglePreview,)
