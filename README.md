# YL VertexColForge

- **YL VertexColForge** is a channel editing tool for Blender Vertex Color / Color Attribute data. It provides a more direct workflow for previewing, painting, selecting, gradient generation, randomization, conversion, and packing of RGB / R / G / B / A channels, and also makes A-channel editing easier in workflows where it is usually more cumbersome.

- The plugin supports both Face Corner and Vertex / Point color attribute domains. Whether the current target channel is RGB, R, G, B, or A, fill, brush, gradient, random, and conversion operations always write accurately to the target channel without affecting the others.

- It is suitable for game assets, material masks, vertex color weights, channel packing data, and Alpha channel preview. You can complete the full workflow from channel generation, editing, and organization to pre-export checking entirely inside Blender.

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

- Provides channel copy, channel swap, current channel invert, and normalize tools. You can quickly organize R / G / B / A data and pack masks from different sources into the same Vertex Color / Color Attribute.

- Suitable for export to game engines, material systems, or later texture conversion workflows.

<img width="812" height="540" alt="Channel Packing and Channel Operations" src="https://github.com/user-attachments/assets/52e7b3c2-62d6-4203-a828-97732cb836d6" />

### 7. 🎲 Channel Randomization

- Writes random values into the current RGB / R / G / B / A channel, with support for grouping by Connected Mesh, UV Island, Material, Sharp Edge, and Angle Island.

- Useful for quickly generating regional variation, material IDs, mask noise, stylized color changes, or data for later material randomization.

<img width="812" height="540" alt="Random" src="https://github.com/user-attachments/assets/3b4b0e41-2e85-4020-968d-7b2be5b41afd" />

### 8. 🔁 Image / Weight / Channel Conversion

- Convert data bidirectionally between Image, Vertex Group Weights, and Vertex Color channels. You can read or write RGB / R / G / B / A as a data bridge between images, weights, and vertex color channels.

---

## Getting Started

- Install and enable `YL VertexColForge`.
- Select a mesh object in the 3D View and press `N` to open the sidebar.
- Open the `YL VertexColForge` panel and start editing after enabling channel preview.

---

## License

- The plugin is licensed under `GPL-3.0-or-later`.
- Bundled assets follow the respective licenses of their resource files.
