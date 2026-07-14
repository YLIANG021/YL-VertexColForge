# YL VertexColForge

YL VertexColForge makes Color Attribute channel editing simple: preview, paint, fill, select, adjust, pack, and transfer RGB / R / G / B / A channels directly inside Blender.

### ✨ With YL VertexColForge you can:

- 👁️ Preview RGB, R, G, B, or A channels directly in the viewport
- ✍️ Paint and fill a single channel, including Alpha, without affecting the others
- 🎯 Pick a channel value on the mesh, drag to adjust tolerance, and select matching areas
- 🌈 Draw Color Ramp gradients, UV gradients, and Light Masks into the active channel
- 📦 Blend, swap, mirror, invert, normalize, and pack data across RGBA channels
- 🎛️ Adjust channels with Levels, HSV, and Blur with live preview
- 🎨 Store, load, and remove reusable channel color presets
- 🎲 Randomize channels by connected mesh, UV island, material, sharp edge, or angle island
- 🔁 Convert and transfer Color Attribute data between images, vertex groups, and mesh objects
- 🧩 Work with both Face Corner and Vertex color attribute domains

---

## Multilingual Support

- Supports English, 简体中文, 繁體中文, 日本語, 한국어, Deutsch, Français, Español, Italiano, Polski, Português, Русский, and Tiếng Việt.

---

## Core Features

### 1. 👁️ Vertex Color Single-Channel Preview and Editing

- View full RGB in the viewport, or preview any single channel as grayscale: R, G, B, or A. Single-channel preview is powered by Geometry Nodes and is non-destructive. (Before exporting, switch back to **RGB** preview or disable single-channel preview to avoid exporting the temporary preview modifier.)

- The preview channel stays in sync with the write channel: switch to R to view and edit R, switch to A to view and edit A. Fill, brush, gradient, random, and conversion tools all write to the current target channel without affecting the others.

<img width="812" height="540" alt="Channel Preview and Editing" src="https://github.com/user-attachments/assets/d58aa3dc-12b4-4a95-9bc4-ce19ffad3360" />

### 2. 🎨 Vertex Color Channel Fill and Channel Brush

- You can write to the current channel directly in Object Mode or Edit Mode, without switching to Vertex Paint Mode. Both fill and brush support selection limits, so only the needed area is modified.

- The channel brush can paint a single channel directly, including the A channel, which is often cumbersome in the standard vertex painting workflow. With single-channel preview, you can view the Alpha grayscale result while painting the A channel in real time, without affecting the other channels.

<img width="812" height="540" alt="Fill and Brush Tools" src="https://github.com/user-attachments/assets/014e7aec-c834-4df2-9002-ff1433ac1531" />

### 3. ⚡ Interactive Vertex Color Channel Selection

- Click on the model surface to sample the current channel color, then drag the mouse to adjust tolerance in real time and release to complete the selection. The process is direct and fast.

- The selection logic follows the current channel: select by R value in the R channel, or by Alpha value in the A channel, avoiding interference from mixed RGB comparisons.

<img width="812" height="540" alt="Selection" src="https://github.com/user-attachments/assets/f1f657c9-7eab-40a5-bcc4-a78f852f5b72" />

### 4. 🌈 Real-Time Vertex Color Gradients and Light Mask

- Use ColorRamp to control color and transition, and drag in the 3D View to generate linear gradients, radial gradients, or directional Light Masks. Real-time preview is supported, and the result can be written to RGB or any single channel.

- Great for lighting masks, directional masks, gradient weights, or stylized vertex color transitions on characters, environments, and props.

<img width="812" height="540" alt="Real-Time Gradient and Light Mask" src="https://github.com/user-attachments/assets/a0c804c6-2da5-4b68-acf1-1258edd88425" />

### 5. 🗺️ UV Space Gradient

- UV Gradient can draw gradients in UV space inside the UV Editor and write the result to any current channel.

<img width="640" height="480" alt="uv" src="https://github.com/user-attachments/assets/5dc371a9-8540-4443-b899-55428124c664" />

### 6. 📦 Channel Packing and Channel Operations

- Channel Operations provides Blend, Swap, and Mirror modes for organizing and packing data across R / G / B / A channels.

- Blend supports Replace, Multiply, Add, Subtract, and Overlay modes with adjustable strength. Mirror can copy the active channel across the local X, Y, or Z axis with configurable direction and tolerance.

- Suitable for packing masks for game engines, material systems, and texture conversion workflows.

<img width="812" height="540" alt="Channel Packing and Channel Operations" src="https://github.com/user-attachments/assets/52e7b3c2-62d6-4203-a828-97732cb836d6" />

### 7. 🎛️ Channel Adjustments

- Adjust the active channel with Levels, HSV, or Blur while previewing the result in real time.

- Invert and Normalize are also available as quick channel operations. Large meshes use deferred preview updates to keep parameter adjustments responsive.
- <img width="700" height="400" alt="Hsv" src="https://github.com/user-attachments/assets/ff627a53-dfad-4e30-8c17-6058766173e2" />


### 8. 🎲 Channel Randomization

- Writes random values into the current RGB / R / G / B / A channel, with support for grouping by Connected Mesh, UV Island, Material, Sharp Edge, and Angle Island.

- Useful for quickly generating regional variation, material IDs, mask noise, stylized color changes, or data for later material randomization.

<img width="812" height="540" alt="Random" src="https://github.com/user-attachments/assets/3b4b0e41-2e85-4020-968d-7b2be5b41afd" />

### 9. 🔁 Image, Weights, and Object Transfer

- Convert data bidirectionally between images, vertex group weights, and Color Attribute channels.

- Transfer the active channel between the current mesh and another mesh using matching topology or nearest-surface sampling, with an optional maximum distance.

---

## Getting Started

- Install and enable `YL VertexColForge`.
- Select a mesh object in the 3D View and press `N` to open the sidebar.
- Open the `YL VertexColForge` panel and start editing after enabling channel preview.

---

## License

- The plugin is licensed under `GPL-3.0-or-later`.
- Bundled assets follow the respective licenses of their resource files.
