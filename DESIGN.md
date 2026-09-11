---
name: Abhishek's Personal Website
description: A warm, tactile personal world where curiosity becomes an inhabited miniature.
colors:
  blossom-pink: "#ef5c88"
  midnight-paper: "#0b1028"
  cloud-blue: "#c7dcff"
  warm-ivory: "#f3d6b8"
  sunlight-peach: "#ffb080"
  electric-cyan: "#65e3ff"
  soft-lavender: "#c391ff"
  moonlit-rose: "#f0dce9"
typography:
  display:
    fontFamily: "Fraunces, Georgia, serif"
    fontWeight: 500
  body:
    fontFamily: "Figtree, ui-sans-serif, system-ui, sans-serif"
    fontWeight: 400
components:
  scene-viewport:
    backgroundColor: "{colors.midnight-paper}"
    textColor: "{colors.cloud-blue}"
    height: "100svh"
    width: "100%"
  scene-status:
    backgroundColor: "{colors.midnight-paper}"
    textColor: "{colors.moonlit-rose}"
    typography: "{typography.body}"
---

# Design System: Abhishek's Personal Website

## Overview

**Creative North Star: "The Inhabited Sketchbook"**

This world turns personal curiosity into a warm, dimensional place: ideas are not filed into categories but lived in, worked on, cooked with, played through, and observed. Handcrafted miniature detail gives the experience tactility; quiet ambient motion gives it life without turning it into spectacle.

The house is the visual constant. Its ivory shell, saturated rooms, rounded modular construction, and accumulated objects carry identity more strongly than any surrounding interface. The current midnight ground creates cinematic contrast but is framing, not a permanent brand commitment; it may change when another background serves the house better.

Extensions should feel warm, tactile, and quietly magical. Interface elements recede around the artifact, borrowing its material confidence and gentle geometry without imitating a toy dashboard.

**Key Characteristics:**

- Inhabited miniature detail rather than abstract decoration
- Warm light against deep, cool framing
- Rounded, modular architectural forms
- Saturated pink, blue, and amber accents used inside a composed scene
- Quiet motion that implies ongoing creative activity
- Minimal interface chrome around the central artifact

## Colors

Palette balances a deep cool stage with warm architectural material and selective luminous accents. Frontmatter values are the normative current implementation; the background role remains adaptable rather than identity-locked.

### Primary

- **Blossom Pink:** Signature living accent for blossoms, illuminated details, and moments of playful energy.

### Secondary

- **Warm Ivory:** Main architectural shell and tactile frame; gives the house warmth, legibility, and object-like presence.
- **Sunlight Peach:** Environmental warmth for low sunlight and lived-in illumination.

### Tertiary

- **Electric Cyan:** Sparse technological glow in devices and animated details.
- **Soft Lavender:** Secondary electronic accent, used in small luminous moments rather than broad surfaces.

### Neutral

- **Midnight Paper:** Current full-viewport stage. It isolates the house and supports bloom, but may be replaced when a stronger framing context is proven.
- **Cloud Blue:** Default foreground color on the current dark stage.
- **Moonlit Rose:** Human-facing status and failure copy; softer and warmer than default foreground.

### Named Rules

**The House Carries the Color Rule.** Let saturated color live primarily within the house and its authored scene; surrounding UI should not compete with it.

**The Background Is a Stage Rule.** Judge any background by how well it reveals the house. Do not treat the current midnight blue as immutable identity.

## Typography

**Display Font:** Fraunces (with Georgia fallback)  
**Body Font:** Figtree (with system sans-serif fallback)

**Character:** Fraunces offers warm editorial irregularity suited to personal storytelling; Figtree keeps controls and supporting copy clear while adding a softer, more human rhythm. Typography is currently loaded as capability but barely visible because the scene, not text, leads the experience.

### Hierarchy

- **Display** (500 or 700): Reserve for future expressive titles and short moments of authorship.
- **Body** (400–800): Use for interface, descriptions, status text, and utility labels.

### Named Rules

**The Artifact Speaks First Rule.** Type frames and explains the world; it must not become a competing hero treatment over the house.

## Layout

The current surface is a full-viewport experience (`100svh`) with one edge-to-edge artwork layer. The 3D scene fills the stage and is composed toward the right on wider viewports; camera framing adapts at `768px`, reducing and repositioning the artwork rather than rebuilding the scene.

Composition uses controlled asymmetry and large negative space around a dense central artifact. Supporting messages overlay the stage at its vertical center with `1.5rem` horizontal inset. Overflow is clipped so orbit interaction never creates page scroll or horizontal drift.

Future layouts should retain a clear artifact-first reading order. Dense information belongs inside deliberate regions or subsequent surfaces, not scattered over the scene.

## Elevation & Depth

Depth is intrinsic, not simulated by interface cards. The system combines modeled geometry, softened cast shadows, atmospheric sunlight, practical room lights, restrained bloom, and tonal separation. The house should read as a crafted object occupying space; surrounding UI remains flatter so it does not create a second depth hierarchy.

### Named Rules

**The Real Depth Rule.** Prefer scene lighting, material response, overlap, and scale over decorative CSS shadows around the artwork.

**The Quiet Glow Rule.** Bloom marks practical lights and select device accents. Screens and broad surfaces must not glow indiscriminately.

## Shapes

The signature form language is modular and softly engineered: large rounded rectangular room shells, circular portholes, a domed observatory, slim structural seams, and small machined details. Curves soften the technical subject matter without becoming bubbly or childish.

Interface geometry should echo this confidence through restrained rounding and clear silhouettes, not literal miniature-house ornament. No CSS radius scale is established yet; future implementation should derive one from real component work rather than inventing tokens here.

## Components

### Curiosity House Stage

Full-viewport signature component containing the WebGL scene, accessible figure description, loading state, and failure fallback.

- **Composition:** Edge-to-edge stage with house as dominant artifact
- **Background:** Current Midnight Paper; intentionally adaptable
- **Interaction:** Gentle constrained orbit; no pan or zoom
- **Motion:** Demand-rendered ambient activity, capped by viewport class and suspended when hidden or offscreen
- **Accessibility:** Canvas is hidden from assistive technology; equivalent scene title and description remain available
- **Failure:** Human-readable status replaces the unavailable scene without exposing implementation detail

### Scene Status

Supporting copy is centered over the stage, set in Moonlit Rose using Figtree. It remains visually quiet and appears only when the visual experience cannot communicate its own state.

## Do's and Don'ts

### Do:

- **Do** keep the curiosity house as the unmistakable visual protagonist.
- **Do** use light, material, miniature detail, and restrained ambient motion to make spaces feel inhabited.
- **Do** preserve meaningful room distinctions and the objects that communicate Abhishek's range.
- **Do** keep surrounding interface quieter than the scene.
- **Do** treat responsive framing as composition, not simple uniform scaling.
- **Do** provide semantic descriptions and composed static states where motion or WebGL is unavailable.

### Don't:

- **Don't** lock the wider system to Midnight Paper when another background presents the house better.
- **Don't** spread neon accents across broad interface surfaces or let bloom flatten scene hierarchy.
- **Don't** place generic portfolio cards, gradients, or oversized marketing typography over the house.
- **Don't** translate rounded miniature geometry into childish bubble UI.
- **Don't** add motion that exists only to attract attention; every loop should imply life, work, atmosphere, or interaction.
- **Don't** fabricate visual proof, project imagery, clients, credentials, or metrics.
