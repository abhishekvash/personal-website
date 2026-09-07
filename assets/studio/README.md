# Illustrated studio reconstruction

The original `landing page.png` is the authority for composition, graphics, palette, and ink texture. The reference frame is **1536 × 1024**. The eight additional September 7 images establish enclosed sides, the stepped shell, roof attachments, and rear surfaces. Two rear images are identical. The views disagree on depth: front/side proportions take precedence over the nearly square top drawing.

## Rebuild

Use Blender and a Python interpreter with Pillow and NumPy. From the repository root:

```sh
rtk proxy python3 scripts/studio/rebuild.py
```

Use `--blender /path/to/blender` to select Blender. Add `--preview` to retain the current landing asset while rebuilding the development preview. Each stage must succeed before the next starts; Blender Python errors fail the pipeline.

The pipeline extracts the source materials, isolates observatory artwork, creates geometry, freezes surface UVs, bakes ownership atlases, renders physical tabletop shadows, and exports the scene. A full rebuild replaces generated assets. Preserve a separate copy before making direct Blender edits.

- Editable scene: `assets/studio/world-studio.blend`
- Browser export: `public/scene/studio-world.glb`
- Published landing asset: `public/scene/studio.glb`
- Camera metadata: `public/scene/scene-world.json` and `scene.json`
- Original and derived surface textures: `public/scene/textures/`

The older `studio.blend`, `build.py`, and non-world comparison files document the earlier image-fitted reconstruction. The world pipeline supersedes that geometry.

## Construction

`world_architecture.py` constructs one stepped solid shell, shared horizontal decks, vertical side walls, bounded room cavities, rounded openings, actual port bores, vents, feet, and a plinth. Floors are divided at room boundaries before assigning interior and exterior paint.

Blender coordinates use **X right, Y back, Z up**. `world.py` defines a separate orthographic reference camera. `world_observatory.py` creates a closed dome, a thick connected aperture, a flat collar, and supported telescope/roof fittings. `world_interiors.py` adapts the detailed furniture into this coordinate system, makes desktops horizontal, and seats supports against floors. `world_tree.py` keeps the source canopy composition while leveling the planter and connecting the woody assembly to the soil.

Source graphics retain their original coordinates in `SourcePosition` before fitting furniture. Per-surface `PaintUV` and `PaintDepth` attributes determine artwork ownership independently of the viewing camera. UVs are then frozen into the exported meshes. Clean source-grain materials extend hidden walls and floors. Separate observatory masks prevent telescope artwork being printed into its starfield or cream rim. Floors use regular divisions in world distance because the original source pixels contain furniture and cannot safely cover newly exposed surfaces.

The saved Blender scene preserves named editable parts. Only the exported copy batches static geometry. Steam, falling petals, and screen glows keep separate names and animation anchors. The tabletop receives a shadow texture rendered from the actual world solids.

## Browser review

Development-only query parameters:

| Query                   | Purpose                                                                                |
| ----------------------- | -------------------------------------------------------------------------------------- |
| `sceneModel=world`      | Inspect the rebuilt asset before promoting it                                          |
| `sceneMotion=off`       | Freeze animation and use device pixel ratio 1                                          |
| `sceneView=clay`        | Inspect depth without painted surfaces                                                 |
| `sceneCapture=on`       | Save the first complete frozen render in the canvas `data-reference-capture` attribute |
| `scenePose=top-left`    | Inspect an orbit boundary                                                              |
| `scenePose=review-left` | Inspect an unrestricted side elevation                                                 |

Orbit poses are `home`, `left`, `right`, `up`, `down`, `top-left`, `top-right`, `bottom-left`, and `bottom-right`. Structural inspection also supports `review-front`, `review-left`, `review-right`, `review-rear`, and `review-top`; these hide the backdrop/table. Normal landing controls remain limited to ±8° horizontally and ±4° vertically, with no pan or zoom.

Use the in-app browser at 1536 × 1024 for final evidence. Compare home crops, all orbit boundaries, and clay views. `audit.py -- --blend assets/studio/world-studio.blend --output assets/studio/world-geometry-audit.json` measures solid topology and selected support contacts; it does not establish visual fidelity or exhaustive collision freedom.

The supplied drawings contain incompatible perspectives. The world reconstruction keeps horizontal roofs and vertical walls, so exact correspondence at every original landmark is not guaranteed. Generated comparison images are evidence for review, not a declaration that the four-pixel fidelity target passed. Mobile layout, full exploration, and deployment remain outside scope.
