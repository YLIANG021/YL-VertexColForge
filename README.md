# YL VertexColForge

** Forge vertex colors faster in Blender.**

YL VertexColForge is a focused Blender add-on for artists who want vertex color work to feel fast, visual, and controllable. It brings brush painting, gradients, color selection, channel blending, light/AO baking, color adjustment, randomization, and transfer tools into one practical workspace.

No more jumping between scattered operators just to build a mask, fix a channel, preview alpha, or move color data from one place to another. VertexColForge turns vertex color editing into a direct creative workflow: choose the layer, choose the channel, preview the result, and forge the color data you need.

##  Highlights

🖌️ **Paint, fill, and sample**  
Paint vertex colors, fill selections, swap foreground/background colors, and pick colors directly from the mesh.

🌈 **Screen and UV gradients**  
Draw ColorRamp-driven gradients in the 3D Viewport or UV/Image Editor for masks, stylized ramps, and controlled color transitions.

🎯 **Pick and select by color**  
Sample existing vertex colors and turn matching values back into editable mesh selections.

🎭 **RGBA channel masks**  
Work on the exact channel you need. Copy, blend, mirror, preview, or write into R, G, B, A, or full color data.

💡 **AO, lighting, and curvature bakes**  
Bake ambient occlusion, directional lighting, gradient masks, and curvature-style detail into editable vertex color attributes.

🧪 **Color adjustment lab**  
Refine vertex colors with levels, gamma, HSV, invert, smooth blur, and ColorRamp remapping before applying.

🎲 **Structured random color generation**  
Randomize by connected mesh, UV island, material, sharp edge, face angle, vertex group, face, or vertex.

🔁 **Texture, weight, and mesh transfer**  
Move data between images, vertex colors, vertex groups, and mesh objects for practical production workflows.

👁️ **Live viewport preview**  
Preview color attributes from Object Mode and Edit Mode, including individual RGBA channels and alpha data.

##  Quick Start

1. Install or load the add-on in Blender.
2. Open the 3D Viewport sidebar with `N`.
3. Find the `YL VertexColForge` panel.
4. Pick a color attribute and write channel.
5. Work through the tool tabs from left to right: Brush, Gradient, Select, Channel Blend, Light and AO, Color Adjust, Random, and Color Transfer.

##  Attribute Control And Viewport Preview

VertexColForge starts where every vertex color workflow starts: color attributes and visibility. Create, rename, remove, or convert color layers, then choose exactly which channel you want to write and preview.

The viewport preview is built for fast iteration. Isolate RGB, alpha, or a single channel, inspect masks directly on the model, and stop guessing what your color attribute actually contains.

<!-- GIF: docs/gifs/01-attribute-preview.gif -->

## 🖌️ Brush

Use foreground/background color controls, strength, blend mode, eyedropper sampling, and selection fill tools to paint or block vertex colors quickly. When a color is worth keeping, add it to the shared preset palette and reuse it across tools.

This is the fast lane for broad color blocking, selected-area fills, mask cleanup, and small hand-painted fixes.

<!-- GIF: docs/gifs/02-brush-fill-presets.gif -->

## 🌈 Gradient

Draw gradients directly in the 3D Viewport or in UV space. Because the system is ColorRamp-driven, gradients can be soft, sharp, multi-stop, stylized, or mask-like instead of being limited to a simple two-color fade.

Use screen gradients when the result should follow the model from the current view. Use UV gradients when the result should follow layout space.

<!-- GIF: docs/gifs/03-screen-uv-gradients.gif -->

## 🎯 Select

Pick a color from the mesh, set a tolerance, and select matching elements. This makes existing vertex color data editable again, not just something hidden inside an attribute.

Use it to isolate painted regions, clean up masks, select ID areas, or turn color information back into mesh selections.

<!-- GIF: docs/gifs/04-pick-select-color.gif -->

## 🎭 Channel Blend

Vertex color channels often behave like production masks. VertexColForge lets you mirror a channel across symmetrical geometry, copy channel data, and blend operations instead of overwriting everything blindly.

Repair one side of a model, reuse a mask, push alpha into another channel, or build layered control data without leaving Blender.

<!-- GIF: docs/gifs/05-channel-tools.gif -->

## 💡 Light And AO

Turn useful surface information into editable vertex color data. Bake ambient occlusion for contact depth, directional lighting for light-facing masks, gradient lighting passes, or curvature-style information for edge and cavity emphasis.

Perfect for stylized assets, game-ready meshes, procedural material masks, and hand-painted workflows that need more surface intelligence baked into the color attribute.

<!-- GIF: docs/gifs/06-light-ao-curvature.gif -->

## 🧪 Color Adjust

After the data is written, shape it. Adjust black and white levels, gamma, hue, saturation, value, inversion, smooth blur, and ColorRamp remapping in a preview session before applying the final result.

Use it to tighten masks, rescue bakes, soften noisy colors, push contrast, or recolor a gradient without rebuilding the whole setup.

<!-- GIF: docs/gifs/07-color-adjust-ramp-remap.gif -->

## 🎲 Random

Randomization is useful when it follows the model. VertexColForge can randomize colors by connected geometry, UV island, material slot, sharp-edge island, angle island, vertex group, face, or vertex.

Use it for ID maps, stylized breakup, modular asset variation, material masks, quick look development, or controlled chaos that still respects the mesh.

<!-- GIF: docs/gifs/08-randomize-colors.gif -->

## 🔁 Color Transfer

Move color data where production needs it. Sample an image into vertex colors, bake vertex colors back to an image, convert between vertex colors and vertex groups, or transfer color attributes between mesh objects.

This is the bridge between texture data, weight data, mesh attributes, and Blender's color attribute system.

<!-- GIF: docs/gifs/09-transfer-workflows.gif -->

##  Installation

1. Download the extension package or clone this repository.
2. In Blender, open `Edit > Preferences > Extensions`.
3. Install or load the add-on.
4. Enable `YL VertexColForge`.
5. Open the `YL VertexColForge` panel in the 3D Viewport sidebar.

##  License

The Python add-on code is licensed under `GPL-3.0-or-later`.

Bundled assets under `assets/` are licensed under `CC0-1.0`.
