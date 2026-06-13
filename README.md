# YL VertexColForge

**A comprehensive vertex color / color attribute workstation for Blender 5.x.**

YL VertexColForge is an all-in-one vertex color workstation. More than just a vertex color creation tool, it is a "channel-level" mask and color processing center built specifically for game asset creation, stylized rendering, and technical art.

The add-on supports both Face Corner and Vertex (Point) color attribute domains. Whether you need to independently control any channel, draw gradients, pack RGBA, bake AO and lighting, or transfer data between textures, weights, and objects, everything can be accomplished seamlessly within a single, streamlined panel.

---

## 🌐 Multi-Language Support

Natively supports 13 interface languages: Simplified Chinese, Traditional Chinese, English, Japanese, Korean, German, French, Spanish, Italian, Polish, Portuguese, Russian, and Vietnamese.

---

## ✨ Core Features

### 1. 👁️ WYSIWYG Channel Preview

Break through default viewport limitations and directly view RGB, Alpha, or any individual channel, while easily switching between different color layers. The current preview channel can be synchronized with the write channel, allowing you to truly "write to the channel you are looking at."

<img width="640" height="480" alt="切换图层和预览单通道(1)" src="https://github.com/user-attachments/assets/ef57287b-9bd6-45e2-951e-e02af2bf7774" />

### 2. 🎨 Brush, Fill, Eyedropper, and Color Palette

The brush tool respects your current selection area, supporting quick painting, one-click filling, and picking colors directly from the model. The built-in palette can save up to 40 frequently used colors for quick reuse across multiple tools.

<img width="640" height="480" alt="笔刷" src="https://github.com/user-attachments/assets/99af1292-5419-4632-9d4c-1c97b9b28cb6" />

### 3. 🌈 Viewport Gradients in Any Direction

Supports real-time preview of gradients in any direction and color. Use the ColorRamp to draw linear or radial gradients directly in the 3D viewport by clicking and dragging. Gradient writing also respects the current channel settings, making it useful for both RGB coloring and single-channel mask creation.

<img width="640" height="480" alt="屏幕渐变" src="https://github.com/user-attachments/assets/87efb96a-330d-4f85-a7e9-e84a5891cd96" />

### 4. 🗺️ Real-Time UV Gradients

Create gradients directly in UV space along UV island directions, perfect for texture-space masks, stylized color bands, and workflows requiring precise UV layout alignment. UV gradients also support the current write channel, facilitating the creation of precise control data that can be packed into RGBA.

<img width="640" height="480" alt="uv渐变" src="https://github.com/user-attachments/assets/6ed8c7ff-32fa-438d-8737-fa67096f788b" />

### 5. ⚡ Quick Color Selection

Click on a color on the model and drag your mouse to preview the selection area in real-time, efficiently isolating the color range you need to edit. The selection result can be used for painting, filling, adjustments, and other selection-restricted operations.

<img width="640" height="480" alt="选择" src="https://github.com/user-attachments/assets/6fe8732f-719c-48b5-8797-a84d30c23bcd" />

### 6. 🪞 One-Click Color Mirroring and Channel Blending

Click and drag to complete color mirroring; the system automatically determines the mirror direction, eliminating the need to manually select axes or positive/negative directions. The channel tools allow copying any channel to another and processing channel data using blend modes like Replace, Multiply, Add, and Overlay.

<img width="640" height="480" alt="镜像" src="https://github.com/user-attachments/assets/580ff9fb-9478-440e-8766-c255e15f4991" />

### 7. 💡 AO, Directional Light, and Curvature Masks

Bake Ambient Occlusion, directional lighting, and curvature data with a single click, featuring real-time effect previews. The generated results can be written to the current channel or blended into existing colors, laying the foundation for stylized textures, material masks, and shading levels.

<img width="640" height="480" alt="Light AO" src="https://github.com/user-attachments/assets/52213cf6-275e-438f-a680-ae0900a1dc9b" />

### 8. 🧪 Real-Time Color Adjustments

Supports adjustments like Levels, Gamma, HSV, Invert, Smooth Blur, and Ramp Remap with live previews. The adjustment process also respects the current channel and selection area. Apply the changes once satisfied, or cancel to restore the original colors.

<img width="640" height="480" alt="ADJUST" src="https://github.com/user-attachments/assets/d38cf614-b9d4-4d26-aa1e-e9f7768032d3" />

### 9. 🎲 Structured Color Randomization

Generate random colors by Connected Mesh, UV Island, Material, Sharp Edge, Angle, Vertex Group, Face, or Vertex. It is an efficient way to quickly create ID Maps, differentiate assets, and introduce stylized variations. Randomized results can be written to the current channel, suitable for both RGB color blocking and single-channel mask generation.

<img width="640" height="480" alt="随机" src="https://github.com/user-attachments/assets/576d7a7a-d715-440c-8797-3ea6e5d38c18" />

### 10. 🔁 Texture, Weight, and Object Transfer

Easily convert between textures and vertex colors, weights and vertex colors, and transfer vertex colors between different mesh objects. Object transfer supports data migration across identical topologies, similar models, and varying topologies, making it ideal for reusing color and mask data across High/Low poly models, LODs, remeshed objects, retopologized meshes, or similar assets.

The transfer tool also supports channel-level data processing. It can read RGB or individual R, G, B, and A channels, writing the results to the target color attribute. This facilitates a complete data pipeline between textures, weights, color attributes, and mesh objects.

---

## 📦 Installation Guide

1. Ensure you are using **Blender 5.0** or a higher version.
2. Download the `.zip` extension package, or clone this repository.
3. In Blender, open `Edit > Preferences > Extensions`.
4. Install the add-on from disk and enable `YL VertexColForge`.
5. Select a mesh in the 3D Viewport, press `N` to open the sidebar, and navigate to the `YL VertexColForge` panel to start creating.

## 📄 License

- The add-on Python code is licensed under `GPL-3.0-or-later`.
- The bundled resources in the `assets/` directory are licensed under `CC0-1.0`.
