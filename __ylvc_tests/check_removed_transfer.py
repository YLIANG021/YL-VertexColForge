import pathlib
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))

import bpy
import yl_vertexcolforge as addon


addon.register()
try:
    try:
        bpy.ops.mesh.ylvc_transfer_mesh_colors.get_rna_type()
        print("OLD_OP_RNA PRESENT")
    except Exception as exc:
        print("OLD_OP_RNA ABSENT", type(exc).__name__)
    print("HAS_TRANSFER_SETTINGS", hasattr(bpy.types.Scene, "ylvc_transfer_settings"))
    print("HAS_TRANSFER_SOURCE", hasattr(bpy.types.Object, "ylvc_transfer_source_object"))
finally:
    addon.unregister()
