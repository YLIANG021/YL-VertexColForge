import bpy
import mathutils
import gpu
import numpy as np

from gpu_extras.batch import batch_for_shader
from ...i18n import tr, tr_format
from ... import utils
from ...core.color_attribute import (
    read_color_attribute_colors,
    set_active_color_attribute,
)
from ...core.context import resolve_loop_auto_mask_for_object, resolve_target_color_attribute, resolve_vertex_auto_mask_for_object
from ...core.domain_mapping import point_to_corner_colors
from ...core.mesh_topology import loop_vertex_indices
from ...core.operator_poll import active_mesh_has_color_attributes
from ...core.write_engine import (
    blend_source_values_into_colors,
    restore_color_array_to_attribute,
    write_color_array_to_attribute,
)
from ..gradients.core_color_engine import (
    build_ramp_lut,
    ensure_light_ramp_node,
    sample_lut_array_out,
)
from ...services import display, transactions


# ==========================================
# Shared State
# ==========================================

_cached_compute_device_type = None

_draw_state = {
    "start": None,
    "end": None,
}

_draw_cache = {
    "shader": None,
    "shader_type": None,
    "coords_key": None,
    "batch": None,
}


def _snapshot_ao_state():
    try:
        from ... import _snapshot_plugin_state
        _snapshot_plugin_state()
    except Exception:
        pass


# ==========================================
# Safe Attribute Helpers
# ==========================================

def safe_set_attr(owner, attr_name, value):
    try:
        if hasattr(owner, attr_name):
            setattr(owner, attr_name, value)
            return True
    except Exception:
        pass
    return False


def safe_get_attr(owner, attr_name, default=None):
    try:
        return getattr(owner, attr_name, default)
    except Exception:
        return default


# ==========================================
# Cycles Device State Helpers
# ==========================================

def backup_cycles_device_preferences(context):
    """Store the current Cycles device settings so they can be restored later."""
    try:
        cycles_prefs = context.preferences.addons["cycles"].preferences

        state = {
            "compute_device_type": safe_get_attr(cycles_prefs, "compute_device_type", None),
            "devices": [],
        }

        # Refresh the device list before reading flags.
        try:
            cycles_prefs.get_devices()
        except Exception:
            pass

        for device_type in ["OPTIX", "METAL", "CUDA", "HIP", "ONEAPI"]:
            try:
                devices = cycles_prefs.get_devices_for_type(device_type)
            except Exception:
                continue

            for device in devices:
                state["devices"].append({
                    "backend": device_type,
                    "name": safe_get_attr(device, "name", ""),
                    "type": safe_get_attr(device, "type", ""),
                    "use": safe_get_attr(device, "use", False),
                })

        return state

    except Exception:
        return None


def restore_cycles_device_preferences(context, state):
    """Restore the previously saved Cycles device settings."""
    if not state:
        return

    try:
        cycles_prefs = context.preferences.addons["cycles"].preferences

        if state.get("compute_device_type") is not None:
            safe_set_attr(
                cycles_prefs,
                "compute_device_type",
                state["compute_device_type"],
            )

        saved_devices = state.get("devices", [])

        for saved in saved_devices:
            backend = saved.get("backend")
            if not backend:
                continue

            try:
                devices = cycles_prefs.get_devices_for_type(backend)
            except Exception:
                continue

            for device in devices:
                same_name = safe_get_attr(device, "name", "") == saved.get("name", "")
                same_type = safe_get_attr(device, "type", "") == saved.get("type", "")

                if same_name and same_type:
                    safe_set_attr(device, "use", saved.get("use", False))

    except Exception:
        pass


# ==========================================
# Compute Device Selection
# ==========================================

def enable_best_compute_device(context, force_refresh=False):
    """Enable the best available Cycles compute backend for AO baking."""
    global _cached_compute_device_type

    try:
        cycles_prefs = context.preferences.addons["cycles"].preferences

        # Reuse the cached backend when possible.
        if _cached_compute_device_type and not force_refresh:
            try:
                cycles_prefs.compute_device_type = _cached_compute_device_type
                devices = cycles_prefs.get_devices_for_type(_cached_compute_device_type)
                gpu_devices = [
                    device for device in devices
                    if safe_get_attr(device, "type", "") != "CPU"
                ]

                if gpu_devices:
                    for device in gpu_devices:
                        device.use = True
                    return "GPU"

            except Exception:
                _cached_compute_device_type = None

        # Otherwise refresh the available backends.
        try:
            cycles_prefs.get_devices()
        except Exception:
            pass

        # Prefer the usual GPU backends in a practical order.
        device_types = ["OPTIX", "METAL", "CUDA", "HIP", "ONEAPI"]

        for device_type in device_types:
            try:
                devices = cycles_prefs.get_devices_for_type(device_type)
            except Exception:
                continue

            gpu_devices = [
                device for device in devices
                if safe_get_attr(device, "type", "") != "CPU"
            ]

            if gpu_devices:
                cycles_prefs.compute_device_type = device_type

                for device in gpu_devices:
                    device.use = True

                _cached_compute_device_type = device_type
                return "GPU"

        _cached_compute_device_type = None
        return "CPU"

    except Exception:
        _cached_compute_device_type = None
        return "CPU"


# ==========================================
# AO Attribute Helpers
# ==========================================

def ensure_ao_color_attribute(mesh, name="AO"):
    """Get or create a point-domain AO color attribute."""
    color_attr = mesh.color_attributes.get(name)

    if color_attr is None:
        color_attr = mesh.color_attributes.new(
            name=name,
            type="FLOAT_COLOR",
            domain="POINT",
        )

    set_active_color_attribute(mesh, color_attr.name)
    return color_attr


def apply_ramp_to_color_attribute(color_attr, channel_key="RGB", base_colors=None):
    ramp_node = ensure_light_ramp_node()
    if ramp_node is None or not getattr(ramp_node, "color_ramp", None):
        return False

    data_count = len(color_attr.data)
    if data_count <= 0:
        return False

    colors = read_color_attribute_colors(None, color_attr)

    ao_values = np.clip(colors[:, 0], 0.0, 1.0)
    ramp_lut = build_ramp_lut(ramp_node.color_ramp, 512)
    mapped = np.empty((data_count, 4), dtype=np.float32)
    sample_lut_array_out(ramp_lut, ao_values, mapped)

    if base_colors is not None:
        np.copyto(colors, base_colors)

    blend_mode = getattr(bpy.context.scene, "ylvc_light_blend_mode", "REPLACE")
    blend_source_values_into_colors(colors, mapped, channel_key, blend_mode, None)
    write_color_array_to_attribute(color_attr, colors)
    return True


def apply_selection_mask_to_point_attribute(mesh, color_attr, original_colors):
    if color_attr is None or original_colors is None or color_attr.domain != "POINT":
        return False

    vertex_mask = resolve_vertex_auto_mask_for_object(bpy.context.active_object, use_live_edit=False)
    if vertex_mask.size == 0 or np.all(vertex_mask):
        return True

    colors = read_color_attribute_colors(mesh, color_attr)
    colors[~vertex_mask] = original_colors[~vertex_mask]
    restore_color_array_to_attribute(color_attr, colors, update_mesh=False)
    return True


def bake_point_attribute_to_corner_attribute(mesh, source_attr, target_attr, channel_key="RGB"):
    if source_attr is None or target_attr is None:
        return False
    if source_attr.domain != "POINT" or target_attr.domain != "CORNER":
        return False

    point_colors = read_color_attribute_colors(mesh, source_attr)
    loop_vi = loop_vertex_indices(mesh)
    corner_colors = point_to_corner_colors(mesh, point_colors)
    target_colors = read_color_attribute_colors(mesh, target_attr)

    loop_mask = resolve_loop_auto_mask_for_object(bpy.context.active_object, loop_vi, use_live_edit=False)
    blend_source_values_into_colors(target_colors, corner_colors, channel_key, "REPLACE", loop_mask)
    write_color_array_to_attribute(target_attr, target_colors, update_mesh=False)
    return True


# ==========================================
# Temporary Material Helpers
# ==========================================

def get_or_create_ylvc_temp_material():
    """Get or create the shared temporary material used by AO baking."""
    mat = bpy.data.materials.get("YLVC_AO_Temp_Mat")

    if mat is None:
        mat = bpy.data.materials.new("YLVC_AO_Temp_Mat")
        mat.use_nodes = True

        try:
            bsdf = mat.node_tree.nodes.get("Principled BSDF")
            if bsdf:
                # Keep this resilient across Blender input name differences.
                if "Base Color" in bsdf.inputs:
                    bsdf.inputs["Base Color"].default_value = (1.0, 1.0, 1.0, 1.0)
                if "Roughness" in bsdf.inputs:
                    bsdf.inputs["Roughness"].default_value = 0.5
        except Exception:
            pass

    return mat


def ensure_object_has_material(obj):
    """Ensure the object has at least one material slot."""
    if obj.data.materials:
        return False

    mat = get_or_create_ylvc_temp_material()
    obj.data.materials.append(mat)
    return True


def remove_temp_material_from_object_if_added(obj, was_added):
    """Remove the temporary material slot when this bake created it."""
    if not was_added:
        return

    try:
        obj.data.materials.clear()
    except Exception:
        pass


# ==========================================
# Temporary Ground Plane Helpers
# ==========================================

def create_temp_ground_plane(context, target_obj):
    """Create a temporary ground plane without using mesh operators."""
    bbox_corners = [
        target_obj.matrix_world @ mathutils.Vector(corner)
        for corner in target_obj.bound_box
    ]

    min_z = min(v.z for v in bbox_corners)
    center = sum(bbox_corners, mathutils.Vector()) / 8.0

    max_dim = max(target_obj.dimensions)
    size = max_dim * 10.0 if max_dim > 0 else 10.0
    half = size * 0.5

    mesh = bpy.data.meshes.new("YLVC_TEMP_GROUND_MESH")

    mesh.from_pydata(
        [
            (-half, -half, 0.0),
            (half, -half, 0.0),
            (half, half, 0.0),
            (-half, half, 0.0),
        ],
        [],
        [
            (0, 1, 2, 3),
        ],
    )

    mesh.update()

    ground = bpy.data.objects.new("YLVC_TEMP_GROUND", mesh)
    ground.location = (center.x, center.y, min_z - 0.001)
    ground.hide_select = True
    ground["ylvc_temp"] = True

    # Give the plane a simple material to keep bake behavior stable.
    mat = get_or_create_ylvc_temp_material()
    ground.data.materials.append(mat)

    # Link to the current collection when possible.
    try:
        context.collection.objects.link(ground)
    except Exception:
        context.scene.collection.objects.link(ground)

    return ground


def remove_temp_object(obj):
    """Remove a temporary helper object and its mesh when unused."""
    if obj is None:
        return

    try:
        mesh = obj.data
    except Exception:
        mesh = None

    try:
        bpy.data.objects.remove(obj, do_unlink=True)
    except Exception:
        pass

    if mesh is not None:
        try:
            if mesh.users == 0:
                bpy.data.meshes.remove(mesh)
        except Exception:
            pass


# ==========================================
# Bake Scene State Helpers
# ==========================================

def backup_bake_scene_state(scene):
    """Store render and bake settings that AO baking may override."""
    state = {
        "render_engine": safe_get_attr(scene.render, "engine", "BLENDER_EEVEE_NEXT"),
        "cycles_device": None,
        "cycles_samples": None,
        "cycles_bake_type": None,
        "cycles_max_bounces": None,
        "cycles_diffuse_bounces": None,
        "cycles_glossy_bounces": None,
        "cycles_transmission_bounces": None,
        "cycles_volume_bounces": None,
        "cycles_transparent_max_bounces": None,
        "bake_target": None,
        "bake_use_clear": None,
        "bake_margin": None,
    }

    if hasattr(scene, "cycles"):
        state["cycles_device"] = safe_get_attr(scene.cycles, "device", None)
        state["cycles_samples"] = safe_get_attr(scene.cycles, "samples", None)
        state["cycles_bake_type"] = safe_get_attr(scene.cycles, "bake_type", None)
        state["cycles_max_bounces"] = safe_get_attr(scene.cycles, "max_bounces", None)
        state["cycles_diffuse_bounces"] = safe_get_attr(scene.cycles, "diffuse_bounces", None)
        state["cycles_glossy_bounces"] = safe_get_attr(scene.cycles, "glossy_bounces", None)
        state["cycles_transmission_bounces"] = safe_get_attr(scene.cycles, "transmission_bounces", None)
        state["cycles_volume_bounces"] = safe_get_attr(scene.cycles, "volume_bounces", None)
        state["cycles_transparent_max_bounces"] = safe_get_attr(scene.cycles, "transparent_max_bounces", None)

    if hasattr(scene.render, "bake"):
        state["bake_target"] = safe_get_attr(scene.render.bake, "target", None)
        state["bake_use_clear"] = safe_get_attr(scene.render.bake, "use_clear", None)
        state["bake_margin"] = safe_get_attr(scene.render.bake, "margin", None)

    return state


def restore_bake_scene_state(scene, state):
    """Restore render and bake settings after AO baking."""
    if not state:
        return

    safe_set_attr(scene.render, "engine", state.get("render_engine"))

    if hasattr(scene, "cycles"):
        if state.get("cycles_device") is not None:
            safe_set_attr(scene.cycles, "device", state["cycles_device"])

        if state.get("cycles_samples") is not None:
            safe_set_attr(scene.cycles, "samples", state["cycles_samples"])

        if state.get("cycles_bake_type") is not None:
            safe_set_attr(scene.cycles, "bake_type", state["cycles_bake_type"])

        if state.get("cycles_max_bounces") is not None:
            safe_set_attr(scene.cycles, "max_bounces", state["cycles_max_bounces"])

        if state.get("cycles_diffuse_bounces") is not None:
            safe_set_attr(scene.cycles, "diffuse_bounces", state["cycles_diffuse_bounces"])

        if state.get("cycles_glossy_bounces") is not None:
            safe_set_attr(scene.cycles, "glossy_bounces", state["cycles_glossy_bounces"])

        if state.get("cycles_transmission_bounces") is not None:
            safe_set_attr(scene.cycles, "transmission_bounces", state["cycles_transmission_bounces"])

        if state.get("cycles_volume_bounces") is not None:
            safe_set_attr(scene.cycles, "volume_bounces", state["cycles_volume_bounces"])

        if state.get("cycles_transparent_max_bounces") is not None:
            safe_set_attr(scene.cycles, "transparent_max_bounces", state["cycles_transparent_max_bounces"])

    if hasattr(scene.render, "bake"):
        if state.get("bake_target") is not None:
            safe_set_attr(scene.render.bake, "target", state["bake_target"])

        if state.get("bake_use_clear") is not None:
            safe_set_attr(scene.render.bake, "use_clear", state["bake_use_clear"])

        if state.get("bake_margin") is not None:
            safe_set_attr(scene.render.bake, "margin", state["bake_margin"])


def setup_fast_ao_bake_scene(context, samples):
    """Configure Cycles for AO baking."""
    scene = context.scene

    transactions.set_render_engine(scene, "CYCLES")

    best_device = enable_best_compute_device(context)
    safe_set_attr(scene.cycles, "device", best_device)

    safe_set_attr(scene.cycles, "samples", samples)
    safe_set_attr(scene.cycles, "bake_type", "AO")

    if hasattr(scene.render, "bake"):
        safe_set_attr(scene.render.bake, "target", "VERTEX_COLORS")
        safe_set_attr(scene.render.bake, "use_clear", True)

    # AO does not need bounce-heavy lighting, so these can be reduced temporarily.
    if hasattr(scene, "cycles"):
        safe_set_attr(scene.cycles, "max_bounces", 0)
        safe_set_attr(scene.cycles, "diffuse_bounces", 0)
        safe_set_attr(scene.cycles, "glossy_bounces", 0)
        safe_set_attr(scene.cycles, "transmission_bounces", 0)
        safe_set_attr(scene.cycles, "volume_bounces", 0)
        safe_set_attr(scene.cycles, "transparent_max_bounces", 0)

    return best_device


# ==========================================
# Legacy Viewport Line Helpers
# ==========================================

def get_direction_ray_shader():
    """Get and cache the viewport line shader."""
    if _draw_cache["shader"] is not None:
        return _draw_cache["shader"]

    try:
        shader = gpu.shader.from_builtin("3D_POLYLINE_UNIFORM_COLOR")
        _draw_cache["shader"] = shader
        _draw_cache["shader_type"] = "POLYLINE"
        return shader

    except Exception:
        shader = gpu.shader.from_builtin("UNIFORM_COLOR")
        _draw_cache["shader"] = shader
        _draw_cache["shader_type"] = "BASIC"
        return shader


def draw_direction_ray_callback():
    """Draw the cached viewport direction line."""
    start = _draw_state.get("start")
    end = _draw_state.get("end")

    if start is None or end is None:
        return

    coords_key = (
        tuple(start),
        tuple(end),
    )

    shader = get_direction_ray_shader()

    if _draw_cache["batch"] is None or _draw_cache["coords_key"] != coords_key:
        coords = [
            mathutils.Vector(start),
            mathutils.Vector(end),
        ]

        _draw_cache["batch"] = batch_for_shader(
            shader,
            "LINES",
            {
                "pos": coords,
            },
        )

        _draw_cache["coords_key"] = coords_key

    try:
        gpu.state.blend_set("ALPHA")

        try:
            gpu.state.line_width_set(2.0)
        except Exception:
            pass

        shader.bind()

        # Support both modern and fallback built-in shaders.
        if _draw_cache["shader_type"] == "POLYLINE":
            try:
                viewport = bpy.context.region
                shader.uniform_float(
                    "viewportSize",
                    (
                        float(viewport.width),
                        float(viewport.height),
                    ),
                )
            except Exception:
                pass

            try:
                shader.uniform_float("lineWidth", 2.0)
            except Exception:
                pass

        shader.uniform_float("color", (0.2, 0.9, 1.0, 1.0))

        _draw_cache["batch"].draw(shader)

    finally:
        try:
            gpu.state.blend_set("NONE")
        except Exception:
            pass


# ==========================================
# AO Bake Operator
# ==========================================

class MESH_OT_VCM_BakeAO_GPU(bpy.types.Operator):
    bl_idname = "mesh.vcm_bake_ao_gpu"
    bl_label = "AO Bake"
    bl_description = "Bake ambient occlusion to the active color attribute with automatic hardware selection"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return active_mesh_has_color_attributes(context)

    def execute(self, context):
        obj = context.active_object

        if not obj or obj.type != "MESH":
            self.report({"WARNING"}, tr("Select a mesh object first."))
            return {"CANCELLED"}

        scene = context.scene
        props = scene.ylvc_ao_props

        temp_material_added = False
        best_device = "CPU"
        temp_point_attr = None
        original_point_colors = None
        original_attr_name = ""
        mesh = obj.data

        bake_scene_state = backup_bake_scene_state(scene)
        cycles_device_state = backup_cycles_device_preferences(context)

        with transactions.CleanupStack() as cleanup:
            cleanup.push_color_write_refresh(context, mesh, lambda: original_attr_name, obj=obj)
            cleanup.push_object_context(context)
            cleanup.push_active_color_attribute(mesh, lambda: original_attr_name)
            cleanup.add(restore_cycles_device_preferences, context, cycles_device_state)
            cleanup.add(restore_bake_scene_state, scene, bake_scene_state)

            try:
                # Ensure the target object is in Object Mode for baking.
                try:
                    if obj.mode != "OBJECT":
                        transactions.ensure_object_mode_for(context, obj)
                except Exception:
                    pass

                target, error = resolve_target_color_attribute(context)
                if error:
                    self.report({"WARNING"}, error)
                    return {"CANCELLED"}
                color_attr = target.color_attr
                original_attr = color_attr
                original_attr_name = getattr(original_attr, "name", "")
                channel_key = getattr(scene, "ylvc_channel", "RGB")

                if color_attr.domain == "CORNER":
                    temp_point_attr = ensure_ao_color_attribute(mesh, "__YLVC_AO_TEMP_POINT__")
                    cleanup.add(transactions.remove_color_attribute, context, obj, mesh, temp_point_attr)
                    color_attr = temp_point_attr
                elif color_attr.domain != "POINT":
                    self.report({"WARNING"}, tr_format("Unsupported color domain: {domain}", domain=color_attr.domain))
                    return {"CANCELLED"}
                else:
                    original_point_colors = read_color_attribute_colors(mesh, color_attr)

                set_active_color_attribute(mesh, color_attr.name)

                # Add a temporary material if the mesh does not already have one.
                temp_material_added = ensure_object_has_material(obj)
                cleanup.add(remove_temp_material_from_object_if_added, obj, temp_material_added)

                # Optionally add a temporary ground plane for stronger contact AO.
                if props.use_ground_plane:
                    ground = create_temp_ground_plane(context, obj)
                    cleanup.add(remove_temp_object, ground)

                # Configure the bake environment.
                best_device = setup_fast_ao_bake_scene(
                    context=context,
                    samples=props.ao_samples,
                )

                # Make sure the target is the only active selected object.
                transactions.make_single_active_object(context, obj)

                # Bake AO and remap the result through the shared ramp.
                # Blender baking is exposed through operators, not a complete data API.
                bpy.ops.object.bake(type="AO")
                apply_ramp_to_color_attribute(color_attr, channel_key, original_point_colors)
                apply_selection_mask_to_point_attribute(mesh, color_attr, original_point_colors)
                if temp_point_attr is not None:
                    bake_point_attribute_to_corner_attribute(mesh, temp_point_attr, original_attr, channel_key)

            except Exception as e:
                self.report({"ERROR"}, tr_format("AO bake failed: {message}", message=str(e)))
                return {"CANCELLED"}

        hardware_str = "GPU" if best_device == "GPU" else "CPU"

        self.report(
            {"INFO"},
            tr_format(
                "AO bake finished. ({hardware} | {samples} samples)",
                hardware=hardware_str,
                samples=props.ao_samples,
            ),
        )

        return {"FINISHED"}


# ==========================================
# Properties
# ==========================================

class YLVCAOBakeSettings(bpy.types.PropertyGroup):
    ao_samples: bpy.props.IntProperty(
        name="Samples",
        description="Cycles samples used for the AO bake. Values around 16 to 64 are usually enough.",
        default=64,
        min=8,
        max=1024,
        update=lambda self, context: _snapshot_ao_state(),
    )

    use_ground_plane: bpy.props.BoolProperty(
        name="Ground Plane",
        description="Temporarily place a ground plane under the object to strengthen contact occlusion",
        default=True,
        update=lambda self, context: _snapshot_ao_state(),
    )

# ==========================================
# Registration
# ==========================================

classes = (
    MESH_OT_VCM_BakeAO_GPU,
    YLVCAOBakeSettings,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    global _cached_compute_device_type

    _cached_compute_device_type = None

    try:
        pass
    except Exception:
        pass

    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass


if __name__ == "__main__":
    register()
