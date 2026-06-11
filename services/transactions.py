# -*- coding: utf-8 -*-
"""Small transaction helpers for temporary Blender state changes."""

from __future__ import annotations

from dataclasses import dataclass, field

import bpy

from . import session


def safe_call(callback, *args, **kwargs):
    """Run cleanup code without letting secondary failures mask the main error."""
    try:
        callback(*args, **kwargs)
        return True
    except Exception:
        return False


class CleanupStack:
    """Run registered cleanup callbacks in reverse order."""

    def __init__(self):
        self._callbacks = []

    def add(self, callback, *args, **kwargs):
        self._callbacks.append((callback, args, kwargs))
        return callback

    def push(self, transaction):
        self.add(transaction.restore)
        return transaction

    def push_attributes(self, owner, *attr_names):
        return self.push(AttributeTransaction(owner, *attr_names))

    def push_object_context(self, context):
        return self.push(ObjectContextTransaction(context))

    def push_object_visibility(self, *objects):
        return self.push(ObjectVisibilityTransaction(*objects))

    def push_material_slots(self, obj):
        return self.push(MaterialSlotsTransaction(obj))

    def push_active_color_attribute(self, mesh, layer_name):
        self.add(restore_active_color_attribute, mesh, layer_name)

    def push_color_attribute_removal(self, mesh, attr_name):
        self.add(remove_color_attribute_by_name, mesh, attr_name)

    def push_color_write_refresh(self, context, mesh, layer_name_getter, *, obj=None):
        def refresh():
            layer_name = layer_name_getter() if callable(layer_name_getter) else layer_name_getter
            if not layer_name:
                return
            from . import display

            display.refresh_after_color_write(context, mesh, layer_name, obj=obj)

        self.add(refresh)

    def close(self):
        while self._callbacks:
            callback, args, kwargs = self._callbacks.pop()
            safe_call(callback, *args, **kwargs)

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _tb):
        self.close()
        return False


@dataclass
class ObjectContextTransaction:
    context: object
    state: object = field(init=False)

    def __post_init__(self):
        self.state = session.capture_object_context(self.context)

    def restore(self):
        session.restore_object_context(self.context, self.state)

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _tb):
        self.restore()
        return False


class AttributeTransaction:
    """Snapshot a small list of RNA attributes and restore existing ones later."""

    def __init__(self, owner, *attr_names):
        self.owner = owner
        self._values = []
        for attr_name in attr_names:
            try:
                if hasattr(owner, attr_name):
                    self._values.append((attr_name, getattr(owner, attr_name)))
            except Exception:
                pass

    def restore(self):
        for attr_name, value in self._values:
            safe_call(setattr, self.owner, attr_name, value)

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _tb):
        self.restore()
        return False


class ObjectSelectionTransaction:
    """Restore active object and selected objects for a view layer."""

    def __init__(self, context):
        self.context = context
        self.view_layer = context.view_layer
        self.active_object = getattr(self.view_layer.objects, "active", None)
        self.selected_objects = list(getattr(context, "selected_objects", []))

    def restore(self):
        try:
            for obj in self.view_layer.objects:
                safe_call(obj.select_set, False)
        except Exception:
            pass

        for obj in self.selected_objects:
            try:
                if obj is not None and obj.name in bpy.data.objects:
                    obj.select_set(True)
            except Exception:
                pass

        try:
            if self.active_object is not None and self.active_object.name in bpy.data.objects:
                self.view_layer.objects.active = self.active_object
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _tb):
        self.restore()
        return False


class ObjectVisibilityTransaction:
    """Restore viewport hide flags for one or more objects."""

    def __init__(self, *objects):
        self._states = []
        for obj in objects:
            if obj is None:
                continue
            try:
                self._states.append((obj, obj.hide_viewport, obj.hide_get()))
            except Exception:
                pass

    def restore(self):
        for obj, hide_viewport, hide in self._states:
            try:
                if obj.name not in bpy.data.objects:
                    continue
            except Exception:
                continue
            safe_call(obj.hide_set, hide)
            safe_call(setattr, obj, "hide_viewport", hide_viewport)

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _tb):
        self.restore()
        return False


class MaterialSlotsTransaction:
    """Restore material slot assignments and active material index."""

    def __init__(self, obj):
        self.obj = obj
        self.active_material_index = getattr(obj, "active_material_index", 0)
        self.materials = []
        try:
            self.materials = [slot.material for slot in obj.material_slots]
        except Exception:
            pass

    @property
    def had_no_slots(self):
        return len(self.materials) == 0

    def restore(self):
        obj = self.obj
        if obj is None:
            return
        try:
            if obj.name not in bpy.data.objects:
                return
        except Exception:
            return

        try:
            if self.had_no_slots:
                obj.data.materials.clear()
            else:
                while len(obj.material_slots) < len(self.materials):
                    obj.data.materials.append(None)
                for index, material in enumerate(self.materials):
                    if index < len(obj.material_slots):
                        obj.material_slots[index].material = material
                while len(obj.material_slots) > len(self.materials):
                    obj.data.materials.pop(index=len(obj.material_slots) - 1)
            obj.active_material_index = min(self.active_material_index, max(len(obj.material_slots) - 1, 0))
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _tb):
        self.restore()
        return False


def remove_datablock(collection, datablock, *, do_unlink=False):
    if datablock is None:
        return
    kwargs = {"do_unlink": do_unlink} if do_unlink else {}
    safe_call(collection.remove, datablock, **kwargs)


def remove_datablock_if_unused(collection, datablock, *, do_unlink=False):
    if datablock is None:
        return
    try:
        if datablock.users != 0:
            return
    except Exception:
        return
    remove_datablock(collection, datablock, do_unlink=do_unlink)


def make_single_active_object(context, obj):
    session.make_single_active_object(context, obj)


def make_active_with_selected(context, active_obj, selected_objects):
    session.ensure_object_mode(context)
    try:
        for obj in context.view_layer.objects:
            obj.select_set(False)
    except Exception:
        pass

    for obj in selected_objects:
        safe_call(obj.select_set, True)

    try:
        context.view_layer.objects.active = active_obj
    except Exception:
        pass


def make_objects_visible(*objects):
    for obj in objects:
        if obj is None:
            continue
        safe_call(obj.hide_set, False)
        safe_call(setattr, obj, "hide_viewport", False)


def ensure_object_mode_for(context, obj):
    if obj is None:
        return False
    try:
        if obj.name in bpy.data.objects:
            context.view_layer.objects.active = obj
            return session.ensure_object_mode(context)
    except Exception:
        pass
    return False


def set_mode(context, mode):
    return session.set_object_mode(context, mode)


def set_render_engine(scene, engine):
    safe_call(setattr, scene.render, "engine", engine)


def restore_active_color_attribute(mesh, layer_name):
    if callable(layer_name):
        layer_name = layer_name()
    session.restore_active_layer(mesh, layer_name)


def create_temp_color_attribute(mesh, name, domain, data_type="FLOAT_COLOR"):
    remove_color_attribute_by_name(mesh, name)
    return mesh.color_attributes.new(name=name, domain=domain, type=data_type)


def remove_color_attribute_by_name(mesh, name):
    if mesh is None or not name:
        return
    try:
        color_attr = mesh.color_attributes.get(name)
        if color_attr is not None:
            mesh.color_attributes.remove(color_attr)
    except Exception:
        pass


def remove_color_attribute(context, obj, mesh, color_attr):
    if color_attr is None:
        return

    try:
        if obj is not None and obj.name in bpy.data.objects and obj.mode != "OBJECT":
            ensure_object_mode_for(context, obj)
        remove_color_attribute_by_name(mesh, color_attr.name)
    except Exception:
        pass


def cover_material_slots(obj, material, material_state=None):
    if obj is None or material is None:
        return

    if material_state is None:
        material_state = MaterialSlotsTransaction(obj)

    if material_state.had_no_slots:
        obj.data.materials.append(material)
        return

    for index in range(len(obj.material_slots)):
        obj.material_slots[index].material = material
