YLVC local test scripts
=======================

These scripts are local release-check helpers. They are not part of the add-on runtime.

Run from the add-on root:

```powershell
& 'C:\Program Files\Blender Foundation\Blender 4.2\blender.exe' --background --factory-startup --python __ylvc_tests\auto_smoke.py
& 'C:\Program Files\Blender Foundation\Blender5.2\blender.exe' --background --factory-startup --python __ylvc_tests\auto_smoke.py
```

Object-to-object mesh color transfer was removed from the release build for stability.
The old transfer probe scripts are kept as placeholders so the test history remains visible.

Run them only if object transfer is restored in a future version.
