# -*- coding: utf-8 -*-
import bpy
import numpy as np

from ...core.color_attribute import (
    INTERNAL_PREVIEW_ATTRIBUTE_NAME,
    get_color_attribute_by_name,
    read_color_attribute_colors,
    set_scene_selected_color_attribute_name,
)
from ...core.domain_mapping import map_color_array_between_domains
from ...core.operator_poll import active_mesh_has_color_attributes, has_active_mesh
from ...core.write_engine import write_color_array_to_attribute
from ...i18n import tr, tr_format
from ...services import display, transactions


def _read_attribute_colors(mesh, color_attr):
    return read_color_attribute_colors(mesh, color_attr)


def _convert_point_colors_to_corner(mesh, point_colors):
    vert_count = len(mesh.vertices)
    loop_count = len(mesh.loops)
    if vert_count == 0 or loop_count == 0:
        raise ValueError("Mesh needs vertices and loops to convert color domains.")

    return map_color_array_between_domains(mesh, point_colors, "POINT", "CORNER")


def _convert_corner_colors_to_point(mesh, corner_colors):
    vert_count = len(mesh.vertices)
    loop_count = len(mesh.loops)
    if vert_count == 0 or loop_count == 0:
        raise ValueError("Mesh needs vertices and loops to convert color domains.")

    return map_color_array_between_domains(mesh, corner_colors, "CORNER", "POINT")


def _rebuild_color_attribute(mesh, color_attr, target_name, target_type, target_domain):
    colors = _read_attribute_colors(mesh, color_attr)
    old_name = color_attr.name

    if color_attr.domain != target_domain:
        if color_attr.domain == "POINT" and target_domain == "CORNER":
            colors = _convert_point_colors_to_corner(mesh, colors)
        elif color_attr.domain == "CORNER" and target_domain == "POINT":
            colors = _convert_corner_colors_to_point(mesh, colors)
        else:
            raise ValueError(f"Unsupported domain conversion: {color_attr.domain} -> {target_domain}")

    existing_names = set(mesh.color_attributes.keys())
    can_create_with_target_name = target_name != old_name and target_name not in existing_names
    if can_create_with_target_name:
        temp_name = target_name
    else:
        base_name = "__YLVC_REBUILD_TEMP__"
        temp_name = base_name
        suffix = 1
        while temp_name in existing_names:
            temp_name = f"{base_name}_{suffix}"
            suffix += 1

    new_attr = None
    old_removed = False
    try:
        new_attr = mesh.color_attributes.new(name=temp_name, type=target_type, domain=target_domain)
        write_color_array_to_attribute(new_attr, colors, update_mesh=False)
        mesh.color_attributes.remove(color_attr)
        old_removed = True
        if new_attr.name != target_name:
            new_attr.name = target_name
        return new_attr
    except Exception:
        if not old_removed and new_attr is not None:
            try:
                mesh.color_attributes.remove(new_attr)
            except Exception:
                pass
        raise


def _fill_new_attribute_color(color_attr, rgb_color):
    data_count = len(color_attr.data)
    if data_count <= 0:
        return

    colors = np.empty((data_count, 4), dtype=np.float32)
    colors[:, 0:3] = tuple(float(component) for component in rgb_color[:3])
    colors[:, 3] = 1.0
    write_color_array_to_attribute(color_attr, colors, update_mesh=False)


def _active_user_color_attribute_index(context, mesh):
    color_attributes = getattr(mesh, "color_attributes", None)
    if not color_attributes:
        return -1

    keys = list(color_attributes.keys())
    idx = getattr(color_attributes, "active_color_index", -1)
    if 0 <= idx < len(keys) and keys[idx] != INTERNAL_PREVIEW_ATTRIBUTE_NAME:
        return idx

    selected_name = getattr(context.scene, "ylvc_layer_name", "")
    selected_attr = get_color_attribute_by_name(mesh, selected_name)
    if selected_attr is not None and selected_attr.name in keys:
        return keys.index(selected_attr.name)

    for index, name in enumerate(keys):
        if name != INTERNAL_PREVIEW_ATTRIBUTE_NAME:
            return index
    return -1


class MESH_OT_YLVCEnsureColorLayer(bpy.types.Operator):
    bl_idname = "mesh.ylvc_ensure_color_layer"
    bl_label = "Add Attribute"
    bl_options = {"REGISTER", "UNDO"}

    initial_color: bpy.props.FloatVectorProperty(
        name="Color",
        subtype="COLOR",
        size=3,
        min=0.0,
        max=1.0,
        default=(1.0, 1.0, 1.0),
    )

    @classmethod
    def poll(cls, context):
        return has_active_mesh(context)

    def invoke(self, context, _event):
        obj = context.active_object
        if not obj or obj.type != "MESH":
            return {"CANCELLED"}
        return context.window_manager.invoke_props_dialog(self, width=240)

    def draw(self, _context):
        self.layout.prop(self, "initial_color")

    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != "MESH":
            return {"CANCELLED"}
        mesh = obj.data
        transactions.ensure_object_mode_for(context, obj)
        base_name = "Color"
        layer_name = base_name
        suffix = 1
        keys = list(mesh.color_attributes.keys())
        while layer_name in keys:
            layer_name = f"{base_name}_{suffix}"
            suffix += 1

        new_attr = mesh.color_attributes.new(name=layer_name, type="FLOAT_COLOR", domain="CORNER")
        _fill_new_attribute_color(new_attr, self.initial_color)
         
        new_keys = list(mesh.color_attributes.keys())
        idx = new_keys.index(layer_name)
        mesh.color_attributes.active_color_index = idx

        set_scene_selected_color_attribute_name(context.scene, layer_name)
        display.finish_color_write(context, mesh, layer_name, obj=obj)
        self.report({"INFO"}, tr_format('Added "{layer_name}".', layer_name=layer_name))
        return {"FINISHED"}

class MESH_OT_YLVCRemoveColorLayer(bpy.types.Operator):
    bl_idname = "mesh.ylvc_remove_color_layer"
    bl_label = "Remove Attribute"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return active_mesh_has_color_attributes(context)

    def execute(self, context):
        obj = context.active_object
        mesh = obj.data
        layer_name = ""
        transactions.ensure_object_mode_for(context, obj)
        idx = _active_user_color_attribute_index(context, mesh)
        keys = list(mesh.color_attributes.keys())
        
        if 0 <= idx < len(keys):
            attr_name = keys[idx]
            mesh.color_attributes.remove(mesh.color_attributes[idx])
            
            if mesh.color_attributes:
                new_keys = list(mesh.color_attributes.keys())
                user_keys = [name for name in new_keys if name != INTERNAL_PREVIEW_ATTRIBUTE_NAME]
                if user_keys:
                    fallback_name = user_keys[min(idx, len(user_keys) - 1)]
                    new_idx = new_keys.index(fallback_name)
                    mesh.color_attributes.active_color_index = new_idx
                    layer_name = mesh.color_attributes[new_idx].name
                else:
                    layer_name = ""
             
            self.report({"INFO"}, tr_format("Removed '{attr_name}'.", attr_name=attr_name))

        if layer_name and layer_name != INTERNAL_PREVIEW_ATTRIBUTE_NAME:
            set_scene_selected_color_attribute_name(context.scene, layer_name)
            display.finish_color_write(context, mesh, layer_name, obj=obj)
        else:
            try:
                from . import ops_preview
                ops_preview.restore_viewport_display(context)
            except Exception:
                pass
        if not layer_name and context.area:
            context.area.tag_redraw()
        return {"FINISHED"}


class MESH_OT_YLVCRenameColorLayer(bpy.types.Operator):
    bl_idname = "mesh.ylvc_rename_color_layer"
    bl_label = "Edit Attribute"
    bl_options = {"UNDO"}

    new_name: bpy.props.StringProperty(name="Name")
    target_domain: bpy.props.EnumProperty(
        items=(
            ("POINT", "Vertex", ""),
            ("CORNER", "Face Corner", ""),
        ),
        name="Domain",
    )
    target_type: bpy.props.EnumProperty(
        items=(
            ("FLOAT_COLOR", "Float", ""),
            ("BYTE_COLOR", "Byte Color", ""),
        ),
        name="Data Type",
    )

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return active_mesh_has_color_attributes(context)

    def invoke(self, context, event):
        mesh = context.active_object.data
        idx = _active_user_color_attribute_index(context, mesh)
        if idx < 0 or idx >= len(mesh.color_attributes):
            return {"CANCELLED"}

        active_attr = mesh.color_attributes[idx]
        self.new_name = active_attr.name
        self.target_domain = active_attr.domain
        self.target_type = active_attr.data_type
        return context.window_manager.invoke_props_dialog(self, width=300)

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        layout.prop(self, "new_name", text=tr("Name"))
        layout.prop(self, "target_domain", text=tr("Domain"), expand=True)
        layout.prop(self, "target_type", text=tr("Data Type"), expand=True)

    def execute(self, context):
        obj = context.active_object
        mesh = obj.data
        idx = _active_user_color_attribute_index(context, mesh)
        if idx < 0 or idx >= len(mesh.color_attributes):
            self.report({"WARNING"}, tr("No active color attribute to edit."))
            return {"CANCELLED"}

        new_name = self.new_name.strip()
        if not new_name:
            self.report({"WARNING"}, tr("Attribute name cannot be empty."))
            return {"CANCELLED"}

        active_attr = mesh.color_attributes[idx]
        old_name = active_attr.name
        old_domain = active_attr.domain
        old_type = active_attr.data_type
        final_name = old_name
        target_domain = self.target_domain
        target_type = self.target_type

        if (
            new_name == old_name
            and target_domain == old_domain
            and target_type == old_type
        ):
            return {"CANCELLED"}
        if old_name == INTERNAL_PREVIEW_ATTRIBUTE_NAME:
            self.report({"WARNING"}, tr("No active color attribute to edit."))
            return {"CANCELLED"}

        try:
            transactions.ensure_object_mode_for(context, obj)
            active_attr = mesh.color_attributes[idx]
            if target_domain != active_attr.domain or target_type != active_attr.data_type:
                active_attr = _rebuild_color_attribute(
                    mesh,
                    active_attr,
                    new_name,
                    target_type,
                    target_domain,
                )
            else:
                active_attr.name = new_name

            final_name = active_attr.name
            keys = list(mesh.color_attributes.keys())
            if final_name in keys:
                active_index = keys.index(final_name)
                mesh.color_attributes.active_color_index = active_index
        except ValueError as exc:
            self.report({"WARNING"}, str(exc))
            return {"CANCELLED"}

        set_scene_selected_color_attribute_name(context.scene, final_name)
        display.finish_color_write(context, mesh, final_name, obj=obj)
        if new_name != old_name and target_domain == old_domain and target_type == old_type:
            self.report({"INFO"}, tr_format('Renamed "{old_name}" to "{final_name}".', old_name=old_name, final_name=final_name))
        elif target_domain != old_domain and target_type == old_type and new_name == old_name:
            if target_domain == "CORNER":
                self.report({"INFO"}, tr_format('Converted "{layer_name}" to Face Corner.', layer_name=final_name))
            else:
                self.report({"INFO"}, tr_format('Converted "{layer_name}" to Vertex.', layer_name=final_name))
        elif target_type != old_type and target_domain == old_domain and new_name == old_name:
            target_type_label = tr("Color") if target_type == "FLOAT_COLOR" else tr("Byte Color")
            self.report({"INFO"}, tr_format("Converted to {target_type}.", target_type=target_type_label))
        else:
            self.report({"INFO"}, tr_format('Updated "{layer_name}".', layer_name=final_name))
        return {"FINISHED"}


class MESH_OT_YLVCConvertDataType(bpy.types.Operator):
    bl_idname = "mesh.ylvc_convert_data_type"
    bl_label = "Convert Attribute Format"
    bl_options = {"REGISTER", "UNDO"}

    target_type: bpy.props.EnumProperty(
        items=(("BYTE_COLOR", "Byte (8-bit)", ""), ("FLOAT_COLOR", "Float (32-bit)", "")),
        name="Format"
    )
    target_domain: bpy.props.EnumProperty(
        items=(("POINT", "Vertex", ""), ("CORNER", "Face Corner", "")),
        name="Domain",
        options={"SKIP_SAVE"},
    )

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return active_mesh_has_color_attributes(context) and obj is not None

    def execute(self, context):
        obj = context.active_object
        mesh = obj.data
        idx = _active_user_color_attribute_index(context, mesh)
        keys = list(mesh.color_attributes.keys())
         
        if idx < 0 or idx >= len(keys):
            return {"CANCELLED"}
         
        active_attr = mesh.color_attributes[idx]
        if active_attr.name == INTERNAL_PREVIEW_ATTRIBUTE_NAME:
            self.report({"WARNING"}, tr("No active color attribute to convert."))
            return {"CANCELLED"}
        old_domain = active_attr.domain
        old_type = active_attr.data_type
        if active_attr.data_type == self.target_type and active_attr.domain == self.target_domain:
            return {"CANCELLED"}
        layer_name = active_attr.name
        try:
            transactions.ensure_object_mode_for(context, obj)
            active_attr = mesh.color_attributes[idx]
            new_attr = _rebuild_color_attribute(
                mesh,
                active_attr,
                layer_name,
                self.target_type,
                self.target_domain,
            )
        except ValueError as exc:
            self.report({"WARNING"}, str(exc))
            return {"CANCELLED"}

        new_keys = list(mesh.color_attributes.keys())
        new_idx = new_keys.index(new_attr.name)
        mesh.color_attributes.active_color_index = new_idx

        set_scene_selected_color_attribute_name(context.scene, new_attr.name)
        display.finish_color_write(context, mesh, new_attr.name, obj=obj)

        if self.target_domain != old_domain:
            if self.target_domain == "CORNER":
                self.report({"INFO"}, tr_format('Converted "{layer_name}" to Face Corner.', layer_name=new_attr.name))
            else:
                self.report({"INFO"}, tr_format('Converted "{layer_name}" to Vertex.', layer_name=new_attr.name))
        elif self.target_type != old_type:
            target_type_label = tr("Color") if self.target_type == "FLOAT_COLOR" else tr("Byte Color")
            self.report({"INFO"}, tr_format("Converted to {target_type}.", target_type=target_type_label))
        return {"FINISHED"}

CLASSES = (
    MESH_OT_YLVCEnsureColorLayer,
    MESH_OT_YLVCRemoveColorLayer,
    MESH_OT_YLVCRenameColorLayer,
    MESH_OT_YLVCConvertDataType,
)
