import { MathUtils, Vector3 } from "three";

// One sun drives the sky, surface lighting, shadows, and indoor scattering.
const elevation = MathUtils.degToRad(7);
const azimuth = MathUtils.degToRad(4);

export const sunlight = {
  direction: new Vector3(
    Math.cos(elevation) * Math.cos(azimuth),
    Math.sin(elevation),
    Math.cos(elevation) * Math.sin(azimuth),
  ),
  target: new Vector3(0, 2.5, 0),
  color: "#ffb080",
  intensity: 4,
  // Widen the shadow filter by 20% without reducing the sun's energy.
  diffusion: 0.2,
};

export const sunPosition = sunlight.target
  .clone()
  .addScaledVector(sunlight.direction, 24);
