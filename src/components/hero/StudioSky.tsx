import { useFrame, useThree } from "@react-three/fiber";
import { useMemo } from "react";
import { Matrix4 } from "three";
import { sunlight } from "./sunlight";

const vertexShader = /* glsl */ `
  varying vec2 vUv;

  void main() {
    vUv = uv;
    gl_Position = vec4(position.xy, 1.0, 1.0);
  }
`;

const fragmentShader = /* glsl */ `
  varying vec2 vUv;
  uniform float aspect;
  uniform mat4 cameraWorld;
  uniform vec3 sunDirection;

  float hash(vec2 p) {
    return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
  }

  float noise(vec2 p) {
    vec2 cell = floor(p);
    vec2 local = fract(p);
    vec2 blend = local * local * (3.0 - 2.0 * local);
    return mix(
      mix(hash(cell), hash(cell + vec2(1.0, 0.0)), blend.x),
      mix(hash(cell + vec2(0.0, 1.0)), hash(cell + vec2(1.0)), blend.x),
      blend.y
    );
  }

  float cloudNoise(vec2 p) {
    float value = 0.0;
    float weight = 0.5;
    for (int i = 0; i < 5; i++) {
      value += weight * noise(p);
      p = p * 2.03 + vec2(17.1, 9.2);
      weight *= 0.5;
    }
    return value;
  }

  void main() {
    // A perspective sky at infinity sits behind the orthographic diorama.
    // Its orientation follows the camera; its afterglow follows the same world-space sun.
    vec2 screen = vUv * 2.0 - 1.0;
    vec3 ray = normalize((cameraWorld * vec4(screen.x * 1.6, screen.y * 1.6 / aspect, -1.0, 0.0)).xyz);
    float towardsSun = clamp(dot(normalize(ray.xz), normalize(sunDirection.xz)) * 0.5 + 0.5, 0.0, 1.0);
    float horizon = exp(-pow((ray.y - sunDirection.y * 0.3) * 3.1, 2.0));
    float sunset = min(pow(towardsSun, 2.5) * 1.6, 1.0) * horizon;
    float upperSky = smoothstep(0.03, 0.5, ray.y);

    vec3 sky = mix(vec3(0.2, 0.085, 0.28), vec3(0.055, 0.085, 0.23), upperSky);
    sky = mix(sky, vec3(0.78, 0.31, 0.28), sunset * 0.78);
    float afterglow = pow(towardsSun, 6.0)
                      * exp(-pow((ray.y - sunDirection.y) * 5.0, 2.0));
    sky += vec3(0.34, 0.17, 0.055) * afterglow;

    // Wind-stretched cloud banks, with finer structure along their sunlit edges.
    vec2 p = vec2(atan(ray.x, -ray.z) * 2.4 + ray.y * 1.1, ray.y * 9.0);
    float warp = cloudNoise(p * 0.42 + 4.0);
    float density = cloudNoise(p + vec2(warp * 1.5, warp * 0.55));
    float bank = smoothstep(0.43, 0.69, density);
    bank *= smoothstep(-0.45, -0.1, ray.y);
    float edge = smoothstep(0.37, 0.49, density) * (1.0 - smoothstep(0.49, 0.6, density));
    vec3 cloud = mix(vec3(0.11, 0.065, 0.18), vec3(0.055, 0.065, 0.15), upperSky);
    cloud += vec3(0.22, 0.065, 0.1) * sunset;
    sky = mix(sky, cloud, bank * 0.68);
    sky += vec3(0.23, 0.08, 0.1) * edge * sunset * (1.0 - bank);

    // Keep the lower atmosphere and the open left side deep, not pastel.
    sky *= mix(0.56, 1.0, smoothstep(-0.8, -0.1, ray.y));
    sky *= mix(0.7, 1.0, towardsSun);
    // Lift the lower values before the shared filmic pass to retain cloud detail.
    gl_FragColor = vec4(pow(max(sky, vec3(0.0)), vec3(1.6)), 1.0);
  }
`;

export function StudioSky() {
  const { width, height } = useThree((state) => state.size);
  const uniforms = useMemo(
    () => ({
      aspect: { value: width / height },
      cameraWorld: { value: new Matrix4() },
      sunDirection: { value: sunlight.direction },
    }),
    [width, height],
  );

  useFrame(({ camera }) => {
    uniforms.cameraWorld.value.copy(camera.matrixWorld);
  });

  return (
    <mesh frustumCulled={false} renderOrder={-1}>
      <planeGeometry args={[2, 2]} />
      <shaderMaterial
        vertexShader={vertexShader}
        fragmentShader={fragmentShader}
        uniforms={uniforms}
        depthTest={false}
        depthWrite={false}
        toneMapped={false}
      />
    </mesh>
  );
}
