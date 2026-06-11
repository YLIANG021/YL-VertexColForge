import bpy
import numpy as np

from ... import utils
from ...core.channel_sampling import transfer_source_values_for_rgb_target
from ...core.color_attribute import (
    read_color_attribute_colors,
    set_active_color_attribute,
)
from ...core.context import resolve_selection_scope
from ...core.domain_mapping import map_color_array_between_domains, point_to_corner_colors
from ...core.mesh_topology import edge_vertex_pairs, loop_vertex_indices, polygon_loop_totals
from ...core.write_engine import (
    blend_source_values_into_colors,
    restore_color_array_to_attribute,
    write_color_array_to_attribute,
)
from ...i18n import tr, tr_format
from ...services import display, transactions

_TRANSFER_TEMP_ATTR_NAME = "__YLVC_TRANSFER_TEMP__"
_CONVERT_TEMP_ATTR_NAME = "__YLVC_TRANSFER_CONVERTED__"


def _create_temp_color_attribute(mesh, name, domain, data_type="FLOAT_COLOR"):
    return transactions.create_temp_color_attribute(mesh, name, domain, data_type)


def _remove_temp_color_attribute(mesh, name):
    transactions.remove_color_attribute_by_name(mesh, name)


def _colors_match(colors_a, colors_b, atol=1e-6):
    if colors_a is None or colors_b is None:
        return False
    if colors_a.shape != colors_b.shape:
        return False
    return np.allclose(colors_a, colors_b, atol=atol, rtol=0.0)


def _strip_generated_backup_suffix(name):
    base_name = name or ""
    backup_count = 0
    while base_name.endswith("_backup"):
        base_name = base_name[:-7]
        backup_count += 1
    return base_name, backup_count


def _resolve_effective_color_attribute(mesh, color_attr):
    if color_attr is None:
        return None

    base_name, backup_count = _strip_generated_backup_suffix(color_attr.name)
    if backup_count > 0 and base_name and base_name in mesh.color_attributes:
        return mesh.color_attributes[base_name]
    return color_attr


def _capture_color_attribute_backup(mesh, color_attr):
    return {
        "name": color_attr.name,
        "domain": color_attr.domain,
        "colors": read_color_attribute_colors(mesh, color_attr, shaped=False).copy(),
    }


def _restore_color_attribute_backup(mesh, backup):
    if not backup:
        return

    color_attr = mesh.color_attributes.get(backup["name"])
    if color_attr is None or color_attr.domain != backup["domain"]:
        return
    restore_color_array_to_attribute(color_attr, backup["colors"], update_mesh=False)


def _cleanup_stale_transfer_attributes(mesh, base_names=()):
    stale_names = [
        attr.name
        for attr in mesh.color_attributes
        if attr.name.startswith("__YLVC_")
    ]

    for base_name in base_names:
        if not base_name:
            continue
        generated_name = f"{base_name}_backup"
        while generated_name in mesh.color_attributes:
            stale_names.append(generated_name)
            generated_name = f"{generated_name}_backup"

    for name in stale_names:
        _remove_temp_color_attribute(mesh, name)


def _copy_attr_colors_if_compatible(mesh, src_attr, dst_attr):
    if src_attr is None or dst_attr is None:
        return False
    if src_attr.domain != dst_attr.domain:
        return False
    if len(src_attr.data) != len(dst_attr.data):
        return False

    restore_color_array_to_attribute(dst_attr, read_color_attribute_colors(mesh, src_attr, shaped=False), update_mesh=False)
    return True


def _map_point_to_corner_colors(mesh, src_colors):
    return point_to_corner_colors(mesh, src_colors)


def _map_corner_to_point_colors(mesh, src_colors, hard_edge_threshold=0.1):
    return map_color_array_between_domains(
        mesh,
        src_colors,
        "CORNER",
        "POINT",
        hard_edge_threshold=hard_edge_threshold,
    )


def _convert_point_attr_to_corner(mesh, src_attr, dst_attr):
    src_colors = read_color_attribute_colors(mesh, src_attr)
    dst_colors = _map_point_to_corner_colors(mesh, src_colors)
    write_color_array_to_attribute(dst_attr, dst_colors, update_mesh=False)


def _convert_corner_attr_to_point(mesh, src_attr, dst_attr, hard_edge_threshold=0.1):
    src_colors = read_color_attribute_colors(mesh, src_attr)
    avg_colors = _map_corner_to_point_colors(mesh, src_colors, hard_edge_threshold)
    write_color_array_to_attribute(dst_attr, avg_colors, update_mesh=False)


def _set_active_color_attribute(mesh, attr_name):
    if attr_name and attr_name in mesh.color_attributes:
        set_active_color_attribute(mesh, attr_name)


def _merge_transferred_colors(result_attr, target_attr, source_channel, mask=None):
    data_count = len(target_attr.data)
    source_colors = read_color_attribute_colors(None, result_attr)
    target_colors = read_color_attribute_colors(None, target_attr)

    if mask is None:
        mask = np.ones(data_count, dtype=bool)

    if source_channel == "RGB":
        target_colors[mask, :] = source_colors[mask, :]
        write_color_array_to_attribute(target_attr, target_colors, update_mesh=False)
        return

    source_values = transfer_source_values_for_rgb_target(source_colors, source_channel)
    blend_source_values_into_colors(target_colors, source_values, "RGB", "REPLACE", mask)
    write_color_array_to_attribute(target_attr, target_colors, update_mesh=False)


def _merge_transferred_color_array(source_colors, target_attr, source_channel, mask=None):
    source_colors = np.asarray(source_colors, dtype=np.float32)
    source_colors.shape = (-1, 4)
    data_count = len(target_attr.data)
    if len(source_colors) != data_count:
        raise ValueError("Transferred color count does not match the target attribute.")

    if mask is None:
        if source_channel == "RGB":
            write_color_array_to_attribute(target_attr, source_colors, update_mesh=False)
            return
        mask = np.ones(data_count, dtype=bool)

    target_colors = read_color_attribute_colors(None, target_attr)

    if source_channel == "RGB":
        target_colors[mask, :] = source_colors[mask, :]
        write_color_array_to_attribute(target_attr, target_colors, update_mesh=False)
        return

    source_values = transfer_source_values_for_rgb_target(source_colors, source_channel)
    blend_source_values_into_colors(target_colors, source_values, "RGB", "REPLACE", mask)
    write_color_array_to_attribute(target_attr, target_colors, update_mesh=False)


def _topology_layout_matches(src_mesh, tgt_mesh):
    if src_mesh == tgt_mesh:
        return True

    if len(src_mesh.vertices) != len(tgt_mesh.vertices):
        return False
    if len(src_mesh.edges) != len(tgt_mesh.edges):
        return False
    if len(src_mesh.loops) != len(tgt_mesh.loops):
        return False
    if len(src_mesh.polygons) != len(tgt_mesh.polygons):
        return False

    if len(src_mesh.polygons) > 0 and not np.array_equal(polygon_loop_totals(src_mesh), polygon_loop_totals(tgt_mesh)):
        return False
    if len(src_mesh.loops) > 0 and not np.array_equal(loop_vertex_indices(src_mesh), loop_vertex_indices(tgt_mesh)):
        return False
    if len(src_mesh.edges) > 0 and not np.array_equal(edge_vertex_pairs(src_mesh), edge_vertex_pairs(tgt_mesh)):
        return False

    return True


def _transfer_topology_fast(src_mesh, src_attr, tgt_mesh, tgt_attr, source_channel, hard_edge_threshold, mask=None):
    src_colors = read_color_attribute_colors(src_mesh, src_attr, shaped=False)
    src_colors.shape = (-1, 4)

    if src_attr.domain == tgt_attr.domain:
        result_colors = src_colors
    elif src_attr.domain == "POINT" and tgt_attr.domain == "CORNER":
        result_colors = _map_point_to_corner_colors(tgt_mesh, src_colors)
    elif src_attr.domain == "CORNER" and tgt_attr.domain == "POINT":
        result_colors = _map_corner_to_point_colors(tgt_mesh, src_colors, hard_edge_threshold)
    else:
        raise ValueError(f"Unsupported topology transfer domains: {src_attr.domain} -> {tgt_attr.domain}")

    _merge_transferred_color_array(result_colors, tgt_attr, source_channel, mask=mask)
    return int(np.sum(mask)) if mask is not None else int(len(result_colors))


def _source_object_poll(_self, obj):
    return obj is not None and obj.type == "MESH"


def _mapping_items():
    return (
        ("TOPOLOGY", "Topology", "Best for matching topology"),
        ("NEAREST_INTERP", "Nearest Face Interpolated", "Best for similar shapes with different topology"),
        ("PROJECTED", "Projected", "Use projected matching for offset surfaces"),
    )


class YLVC_MeshTransferSettings(bpy.types.PropertyGroup):
    source_channel: bpy.props.EnumProperty(
        name="Source",
        items=(
            ("RGB", "RGB", "Use the full source color"),
            ("R", "R", "Use the red channel only"),
            ("G", "G", "Use the green channel only"),
            ("B", "B", "Use the blue channel only"),
            ("A", "A", "Use the alpha channel only"),
        ),
        default="RGB",
    )
    mapping_mode: bpy.props.EnumProperty(
        name="Mode",
        items=_mapping_items(),
        default="NEAREST_INTERP",
    )
    use_max_distance: bpy.props.BoolProperty(
        name="Use Max Distance",
        description="Skip mismatched surfaces that are too far away",
        default=False,
    )
    max_distance: bpy.props.FloatProperty(
        name="Max Distance",
        default=0.1,
        min=0.0,
    )
    ray_radius: bpy.props.FloatProperty(
        name="Ray Radius",
        default=0.0,
        min=0.0,
    )
    hard_edge_threshold: bpy.props.FloatProperty(
        name="Hard Edge Threshold",
        description="When converting Face Corner to Point, vertices above this variance keep the first loop color",
        default=0.1,
        min=0.0,
        max=1.0,
    )


class MESH_OT_YLVCTransferMeshColors(bpy.types.Operator):
    bl_idname = "mesh.ylvc_transfer_mesh_colors"
    bl_label = "Transfer Mesh Colors"
    bl_options = {"REGISTER", "UNDO"}

    reverse: bpy.props.BoolProperty(default=False, options={"SKIP_SAVE"})

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return (
            obj is not None
            and obj.type == "MESH"
            and getattr(obj, "ylvc_transfer_source_object", None) is not None
        )

    def execute(self, context):
        current_obj = context.active_object
        other_obj = getattr(current_obj, "ylvc_transfer_source_object", None)
        settings = context.scene.ylvc_transfer_settings

        if other_obj is None:
            self.report({"WARNING"}, tr("Please choose the other mesh object first."))
            return {"CANCELLED"}
        if other_obj == current_obj:
            self.report({"WARNING"}, tr("The active object and the other object must be different."))
            return {"CANCELLED"}
        if other_obj.type != "MESH":
            self.report({"WARNING"}, tr("The chosen object must be a mesh."))
            return {"CANCELLED"}

        if self.reverse:
            source_obj = current_obj
            target_obj = other_obj
        else:
            source_obj = other_obj
            target_obj = current_obj

        src_mesh = source_obj.data
        tgt_mesh = target_obj.data
        src_attr = _resolve_effective_color_attribute(src_mesh, utils.get_active_color_attribute_safe(src_mesh))
        tgt_attr = _resolve_effective_color_attribute(tgt_mesh, utils.get_active_color_attribute_safe(tgt_mesh))

        if src_attr is None:
            self.report({"WARNING"}, tr_format("No active color attribute found on '{object_name}'.", object_name=source_obj.name))
            return {"CANCELLED"}
        if tgt_attr is None:
            self.report({"WARNING"}, tr_format("No active color attribute found on '{object_name}'.", object_name=target_obj.name))
            return {"CANCELLED"}

        src_domain = src_attr.domain
        tgt_domain = tgt_attr.domain
        src_attr_name = src_attr.name
        tgt_attr_name = tgt_attr.name
        source_channel = getattr(settings, "source_channel", "RGB")
        selection_scope = None
        if not self.reverse:
            selection_scope = resolve_selection_scope(context, tgt_attr)
        write_mask = selection_scope.data_mask.copy() if selection_scope is not None else None

        if current_obj.mode != "OBJECT":
            try:
                transactions.ensure_object_mode_for(context, current_obj)
            except RuntimeError as exc:
                self.report({"ERROR"}, tr_format("Could not switch to Object Mode: {message}", message=str(exc)))
                return {"CANCELLED"}

        transfer_target_attr = None
        converted_target_attr = None
        transfer_succeeded = False
        target_backup = None
        fast_topology_transfer = settings.mapping_mode == "TOPOLOGY" and _topology_layout_matches(src_mesh, tgt_mesh)

        with transactions.CleanupStack() as cleanup:
            cleanup.add(lambda: transactions.safe_call(context.area.tag_redraw) if context.area else None)
            cleanup.add(tgt_mesh.update)
            cleanup.push_object_context(context)
            cleanup.push_object_visibility(source_obj, target_obj)
            cleanup.push_active_color_attribute(tgt_mesh, tgt_attr_name)
            cleanup.push_active_color_attribute(src_mesh, src_attr_name)
            cleanup.push_color_attribute_removal(tgt_mesh, _CONVERT_TEMP_ATTR_NAME)
            cleanup.push_color_attribute_removal(tgt_mesh, _TRANSFER_TEMP_ATTR_NAME)

            try:
                if fast_topology_transfer:
                    _transfer_topology_fast(
                        src_mesh,
                        src_attr,
                        tgt_mesh,
                        tgt_attr,
                        source_channel,
                        settings.hard_edge_threshold,
                        mask=write_mask,
                    )
                else:
                    _cleanup_stale_transfer_attributes(src_mesh, [src_attr_name])
                    if tgt_mesh != src_mesh:
                        _cleanup_stale_transfer_attributes(tgt_mesh, [tgt_attr_name])

                    target_backup = _capture_color_attribute_backup(tgt_mesh, tgt_attr)
                    tgt_attr = tgt_mesh.color_attributes[tgt_attr_name]

                    transactions.make_objects_visible(source_obj, target_obj)

                    is_cross_domain = src_domain != tgt_domain
                    transfer_target_attr = _create_temp_color_attribute(
                        tgt_mesh,
                        _TRANSFER_TEMP_ATTR_NAME,
                        src_domain,
                        "FLOAT_COLOR",
                    )
                    _copy_attr_colors_if_compatible(tgt_mesh, tgt_attr, transfer_target_attr)

                    transactions.make_active_with_selected(context, source_obj, (source_obj, target_obj))

                    _set_active_color_attribute(src_mesh, src_attr_name)
                    _set_active_color_attribute(tgt_mesh, transfer_target_attr.name)

                    if settings.mapping_mode == "TOPOLOGY":
                        vert_map = loop_map = "TOPOLOGY"
                    elif settings.mapping_mode == "PROJECTED":
                        vert_map = "POLYINTERP_VNORPROJ"
                        loop_map = "POLYINTERP_LNORPROJ"
                    else:
                        vert_map = loop_map = "POLYINTERP_NEAREST"

                    # Blender's color data transfer mapping is exposed through this operator.
                    bpy.ops.object.data_transfer(
                        use_reverse_transfer=False,
                        data_type="COLOR_VERTEX" if src_domain == "POINT" else "COLOR_CORNER",
                        use_create=False,
                        vert_mapping=vert_map,
                        loop_mapping=loop_map,
                        poly_mapping="NEAREST",
                        edge_mapping="NEAREST",
                        layers_select_src="ACTIVE",
                        layers_select_dst="ACTIVE",
                        mix_mode="REPLACE",
                        use_max_distance=settings.use_max_distance,
                        max_distance=settings.max_distance,
                        ray_radius=settings.ray_radius,
                        use_object_transform=True,
                    )

                    # Blender 5.0 writes COLOR_* transfer into the original destination layer
                    # even when a temporary active layer is selected; 5.1+ writes into the
                    # active temporary layer as expected.
                    if src_domain == tgt_domain:
                        transferred_temp_colors = read_color_attribute_colors(tgt_mesh, transfer_target_attr, shaped=False)
                        transferred_target_colors = read_color_attribute_colors(tgt_mesh, tgt_attr, shaped=False)
                        backup_target_colors = target_backup["colors"] if target_backup is not None else None
                        if (
                            backup_target_colors is not None
                            and _colors_match(transferred_temp_colors, backup_target_colors)
                            and not _colors_match(transferred_target_colors, backup_target_colors)
                        ):
                            write_color_array_to_attribute(transfer_target_attr, transferred_target_colors, update_mesh=False)
                            _restore_color_attribute_backup(tgt_mesh, target_backup)

                    result_attr = transfer_target_attr
                    if is_cross_domain:
                        if src_domain == "POINT" and tgt_domain == "CORNER":
                            converted_target_attr = _create_temp_color_attribute(
                                tgt_mesh,
                                _CONVERT_TEMP_ATTR_NAME,
                                tgt_domain,
                                "FLOAT_COLOR",
                            )
                            _convert_point_attr_to_corner(tgt_mesh, transfer_target_attr, converted_target_attr)
                        elif src_domain == "CORNER" and tgt_domain == "POINT":
                            converted_target_attr = _create_temp_color_attribute(
                                tgt_mesh,
                                _CONVERT_TEMP_ATTR_NAME,
                                tgt_domain,
                                "FLOAT_COLOR",
                            )
                            _convert_corner_attr_to_point(
                                tgt_mesh,
                                transfer_target_attr,
                                converted_target_attr,
                                settings.hard_edge_threshold,
                            )
                        result_attr = converted_target_attr if converted_target_attr is not None else transfer_target_attr

                    _merge_transferred_colors(
                        result_attr=result_attr,
                        target_attr=tgt_attr,
                        source_channel=source_channel,
                        mask=write_mask,
                    )

                tgt_mesh.update()
                if target_obj == current_obj:
                    display.refresh_after_color_write(context, tgt_mesh, tgt_attr.name, obj=target_obj)

                transfer_succeeded = True
            except Exception as exc:
                transactions.safe_call(_restore_color_attribute_backup, tgt_mesh, target_backup)
                self.report({"ERROR"}, tr_format("Mesh color transfer failed: {message}", message=str(exc)))
                return {"CANCELLED"}

        if transfer_succeeded:
            direction_label = f"{src_domain} -> {tgt_domain}"
            self.report(
                {"INFO"},
                tr_format(
                    "Transferred '{source_attr}' from '{source_obj}' to '{target_attr}' on '{target_obj}' ({direction}).",
                    source_attr=src_attr_name,
                    source_obj=source_obj.name,
                    target_attr=tgt_attr_name,
                    target_obj=target_obj.name,
                    direction=direction_label,
                ),
            )
            return {"FINISHED"}

        return {"CANCELLED"}


CLASSES = (
    YLVC_MeshTransferSettings,
    MESH_OT_YLVCTransferMeshColors,
)


def register_properties():
    if hasattr(bpy.types.Object, "ylvc_transfer_source_object"):
        del bpy.types.Object.ylvc_transfer_source_object
    if hasattr(bpy.types.Scene, "ylvc_transfer_settings"):
        del bpy.types.Scene.ylvc_transfer_settings

    bpy.types.Object.ylvc_transfer_source_object = bpy.props.PointerProperty(
        name="Transfer Object",
        description="The other mesh used by mesh color transfer",
        type=bpy.types.Object,
        poll=_source_object_poll,
    )
    bpy.types.Scene.ylvc_transfer_settings = bpy.props.PointerProperty(type=YLVC_MeshTransferSettings)


def unregister_properties():
    if hasattr(bpy.types.Scene, "ylvc_transfer_settings"):
        del bpy.types.Scene.ylvc_transfer_settings
    if hasattr(bpy.types.Object, "ylvc_transfer_source_object"):
        del bpy.types.Object.ylvc_transfer_source_object
