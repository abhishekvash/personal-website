# Quiet, persistent animation for the curiosity house

## Direction

Make the house feel inhabited, not flashy. The gaming room's moving RGB lighting is the focal effect; the workroom's live web preview, cooking, and studio activity provide quieter supporting motion. Preserve the composition, furnishings, portraits, screen content, dark background, sunlight, softened shadows, and optimized assets.

## Confirmed model anchors

The current model already contains:

- A separate gaming keyboard, distinguishable from the study keyboard by its upper-floor position.
- Two workroom screens: a code editor and a “LITTLE WORLDS” web preview with a miniature terrarium.
- Two PC fan rings, two hubs, and fourteen blades: seven blades per fan.
- Two physical VU meter plates on the mixing console.
- A frying pan, a stock pot with a lid, burner rings, and four static steam meshes.

The cookware is not centered over individual burner rings. Effects must follow the cookware rather than blindly following the burners.

## Implementation

### 1. Gaming keyboard backlight

- Add a slow, continuous RGB wave beneath the gaming keycaps.
- Keep the key faces and the study keyboard unchanged.
- Combine the small backlight surfaces into one mesh; animate a shader uniform rather than creating animated textures or updating React state.
- Keep the brightness restrained enough that the sunlight still dominates.

### 2. PC cooling fans

- Group each set of seven blades around its actual hub and rotate the blades continuously.
- Keep the cases, hubs, and outer bezels stationary.
- Slowly cycle the two RGB rings through slightly offset colors.
- Avoid changing shared materials elsewhere in the house.
- Do not regenerate shadow maps for tiny rotating fan blades.

### 3. Kitchen flame and steam

- Add faint blue gas jets beneath the frying pan and stock pot, with small, irregular height variations.
- Use two compact combined meshes and lightweight shaders, not new shadow-casting lights.
- Replace the rigid steam meshes with a few soft, translucent wisps that rise, drift, widen, and fade before repeating.
- Let the stock pot's steam escape near its lid edge. Keep both utensils and the stove in their existing positions.
- Depth-test steam against the room and cookware; avoid opaque smoke or excessive glow.

### 4. Mixing-console VU meters

- Fit animated segmented LED displays to the two existing sloped meter plates.
- Use independently paced, smoothly varying levels with green segments, occasional amber peaks, and restrained brightness.
- Darken the meter backgrounds rather than making the whole console flash.
- Keep the existing DAW screen unchanged. This is illustrative activity, not audio-reactive playback; add no sound.

### 5. Workroom live web preview

- Animate the existing “LITTLE WORLDS” page on the second workroom monitor so it reads as a live development preview rather than a screenshot.
- Give the miniature terrarium gentle leaf sway and a couple of slowly drifting pollen motes within its illustration area.
- Keep the browser chrome, page text, button, pot, and code-editor screen stable. Do not scroll or wobble the whole monitor.
- Confine shader-driven motion to the preview's artwork region; reuse the existing texture rather than uploading a newly painted screen every frame.
- Make the movement noticeable at the scene's normal scale, but quieter than the gaming RGB effects.
- Include this screen animation in the same pause, visibility, and reduced-motion controls as every other effect.

### 6. Animation lifecycle and controls

- Keep the existing demand-rendered canvas rather than enabling unconditional 60 FPS rendering.
- Schedule ambient updates at a maximum of 24 FPS on desktop and 15 FPS on narrow/mobile viewports.
- Stop scheduling when the document is hidden, the canvas is offscreen, or motion is paused. Resume without a large time jump.
- Honor `prefers-reduced-motion` with a composed static state by default.
- Add a small, accessible “Pause motion” / “Play motion” button outside the canvas's `aria-hidden` region. Explicit play can opt into motion.
- Update Three.js transforms and uniforms directly; do not rerender React for each animation frame.
- Keep sunlight and room shadow maps cached. Clean up timers, observers, event listeners, generated geometries, and materials on unmount.

## Files

- Add `src/components/hero/SceneAnimation.ts` for effect construction and time-based updates.
- Add `src/components/hero/SceneMotion.tsx` for scheduling, visibility, and reduced-motion handling.
- Update `src/components/hero/StudioScene.tsx` to install effects, connect their lifecycle, and expose the motion control.
- Update `src/components/hero/ScreenContent.ts` if needed to expose the live preview's animation region while preserving its existing artwork and texture lifecycle.
- Update `src/styles.css` for the restrained motion button and keyboard-focus styling.
- Leave the optimized GLB, Blender source, portrait assets, and unrelated accumulated changes untouched.
- Add no dependencies or tests.

## Validation

After implementation, use Aside browser for the browser validation below, rather than a separate headless Playwright browser. Follow the Aside CLI guide and use its REPL when direct screenshots, DOM inspection, or runtime instrumentation are needed. Perform one batched desktop/mobile inspection in Aside and, if needed, one corrective verification pass:

- Capture the scene at multiple times and verify the keyboard wave, both fan rotations/colors, both flames, steam movement, both VU meters, and the workroom's animated terrarium preview.
- Verify that workroom motion stays inside the web preview's illustration area and does not disturb the page text, browser chrome, or adjacent code editor.
- Check that animation stays subtle at the normal viewing scale and behaves correctly when orbiting.
- Verify pause/resume, reduced motion, hidden/offscreen suspension, and cleanup.
- Check for browser/shader errors, horizontal overflow, material leakage into other rooms, and resource growth.
- Measure added draw calls and runtime behavior against the current approximately 2,977 draw calls per rendered frame. The new effects should add only a small number of draws; the existing scene remains the main rendering cost.
- Run `pnpm exec tsc --noEmit`, `pnpm run lint`, `pnpm run check`, then `pnpm run build`, plus `git diff --check`.
- Report any remaining warnings or performance limits, distinguishing desktop viewport emulation in Aside from measurements on a physical mobile device.
