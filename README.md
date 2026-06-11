# YL VertexColForge

**Vertex color work in Blender, sharpened into one forge.**

YL VertexColForge is a Blender add-on for artists who want vertex color tools to feel fast, visual, and production-ready. It gathers painting, gradients, baking, channel edits, color adjustment, randomization, selection, and transfer workflows into one focused panel, so you can build vertex color data without constantly jumping between scattered tools.

Whether you are blocking stylized color, baking masks, preparing game assets, testing material variations, or pushing color attributes into a cleaner pipeline, VertexColForge is designed to keep the work direct: choose the layer, choose the channel, preview the result, and write with control.

## What It Does

- Paint and fill vertex colors with foreground/background color controls.
- Preview color attributes and individual channels directly in the viewport.
- Draw screen-space and UV-space gradients with ColorRamp-driven control.
- Bake ambient occlusion, directional lighting, gradient masks, and curvature-style detail into color attributes.
- Adjust colors with levels, HSV, inversion, ramp remapping, and smooth blur.
- Randomize colors by geometry structure, materials, UV islands, face angle, vertex group, faces, or vertices.
- Mirror and mix color channels for cleaner masks and symmetrical assets.
- Select mesh elements by sampled color values.
- Transfer data between textures, vertex colors, vertex groups, and mesh objects.

## Attribute Control And Viewport Preview

VertexColForge starts with the practical things you touch all the time: color attributes, write channels, and viewport feedback. Create, rename, remove, or convert color layers, then decide exactly which channel you are writing to and which channel you want to preview.

The preview workflow is built for iteration. Instead of guessing what a mask or channel contains, you can isolate RGB, alpha, or a single channel and check it directly in the viewport before committing to the next operation.

<!-- GIF: docs/gifs/01-attribute-preview.gif -->

## Brush, Fill, And Color Presets

The brush tools are made for quick color decisions: pick foreground and background colors, swap them instantly, set strength and blend mode, then paint or fill the active channel. When a color is worth keeping, add it to a preset palette and reuse it across the asset.

It is useful for both broad color blocking and small cleanup passes. Fill selected elements, sample existing colors with the eyedropper, or use blend strength to build masks more gradually.

<!-- GIF: docs/gifs/02-brush-fill-presets.gif -->

## Screen And UV Gradients

VertexColForge includes two gradient workflows: screen-space gradients in the 3D Viewport and UV gradients in the Image Editor. Both are driven by a Blender ColorRamp, so the gradient is not just a two-color fade. You can build sharp masks, soft transitions, stylized ramps, or multi-stop color bands and write them into the selected channel.

Use viewport gradients when the shape should follow what you see on the model. Use UV gradients when the color needs to respect layout space. Both are built for art direction, not guesswork.

<!-- GIF: docs/gifs/03-screen-uv-gradients.gif -->

## Light, AO, Directional Masks, And Curvature

The baking tools turn useful surface information into editable vertex color data. Bake ambient occlusion for contact depth, directional lighting for light-facing masks, gradient-style lighting passes, or curvature information for edge and cavity emphasis.

These tools are especially helpful for stylized assets, hand-painted workflows, masks for procedural materials, or game-ready meshes where vertex color data needs to carry more of the look.

<!-- GIF: docs/gifs/04-light-ao-curvature.gif -->

## Color Adjust And Ramp Remap

Once the color data is in place, VertexColForge gives you a non-destructive-feeling preview session for shaping it. Adjust black and white levels, gamma, hue, saturation, value, invert colors, smooth noisy areas, or remap values through a ColorRamp before applying the result.

This turns vertex color editing into a proper finishing pass. You can tighten masks, push contrast, soften transitions, recolor a gradient, or rescue a bake without leaving the add-on.

<!-- GIF: docs/gifs/05-color-adjust-ramp-remap.gif -->

## Randomize Colors With Structure

Random color does not have to mean messy color. VertexColForge can randomize by connected geometry, UV island, material assignment, sharp-edge island, angle island, vertex group, face, or vertex. That makes it easy to create variation that follows the model instead of fighting it.

Use it for quick ID maps, stylized breakup, material variation masks, modular asset color variation, or any workflow where controlled randomness is faster than manual painting.

<!-- GIF: docs/gifs/06-randomize-colors.gif -->

## Channel Tools: Mirror, Copy, And Blend

Color channels are often masks in disguise. VertexColForge treats them that way. Mirror a channel across symmetrical geometry, copy data from one channel into another, and blend channel operations instead of overwriting everything blindly.

This is built for practical cleanup: repair one side of a model, reuse a mask, push alpha into a color channel, or build layered control data without round-tripping through external tools.

<!-- GIF: docs/gifs/07-channel-tools.gif -->

## Pick And Select By Color

When color data becomes part of the modeling workflow, selection matters. Pick a color value from the mesh, set a tolerance, and select matching elements. It is a fast way to isolate regions, clean up masks, or turn existing vertex colors back into editable selections.

This makes vertex colors feel less like hidden data and more like something you can grab, inspect, and shape.

<!-- GIF: docs/gifs/08-pick-select-color.gif -->

## Texture, Weight, And Mesh Transfer

VertexColForge also helps move color data between the places artists actually need it. Sample an image into vertex colors, bake vertex colors back to an image, convert between vertex colors and vertex groups, or transfer color attributes between mesh objects.

For game and production workflows, this is where the add-on becomes more than a painter. It becomes a bridge between texture data, weight data, mesh attributes, and Blender's color attribute system.

<!-- GIF: docs/gifs/09-transfer-workflows.gif -->

## Built For Everyday Blender Work

The add-on is organized around the way vertex color work usually happens: choose an attribute, choose a channel, make a change, preview it, refine it, and apply it. Tools are grouped into clear modes for brush work, gradients, selection, channel operations, lighting/AO, color adjustment, randomization, and transfer.

It is not trying to replace Blender's material system or texture painting. It is designed to make vertex color workflows faster, clearer, and more expressive when vertex colors are exactly the right tool for the job.

## Installation

1. Download the extension package or clone this repository.
2. In Blender, open `Edit > Preferences > Extensions`.
3. Install or load the add-on.
4. Enable `YL VertexColForge`.
5. Open the `YL VertexColForge` panel in the 3D Viewport sidebar.

## License

The Python add-on code is licensed under `GPL-3.0-or-later`.

Bundled assets under `assets/` are licensed under `CC0-1.0`.
