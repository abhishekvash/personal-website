import {
  AdditiveBlending,
  Box3,
  ConeGeometry,
  DoubleSide,
  Group,
  Mesh,
  MeshStandardMaterial,
  PlaneGeometry,
  ShaderMaterial,
  Vector3,
} from "three";
import { mergeGeometries } from "three/addons/utils/BufferGeometryUtils.js";
import type { BufferGeometry, Camera, Object3D } from "three";

// RGB peripherals lead; cooking and meters provide quieter supporting motion.
// Batch new geometry, animate uniforms directly, and leave room shadows cached.
const vertexShader = /* glsl */ `
  varying vec2 vUv;
  varying vec3 vPosition;
  void main() {
    vUv = uv;
    vPosition = position;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`;
const outputColor = /* glsl */ `
  #include <tonemapping_fragment>
  #include <colorspace_fragment>
`;

function animatedMaterial(fragmentShader: string, phase = 0): ShaderMaterial {
  return new ShaderMaterial({
    vertexShader,
    fragmentShader,
    uniforms: { uTime: { value: 0 }, uPhase: { value: phase } },
  });
}

function mergeParts(parts: Array<BufferGeometry>): BufferGeometry {
  // Three.js returns null for incompatible attributes despite its narrower typings.
  const geometry = mergeGeometries(parts) as BufferGeometry | null;
  parts.forEach((part) => part.dispose());
  if (!geometry)
    throw new Error("Could not build the scene's ambient effects.");
  return geometry;
}

export function installSceneAnimation(
  scene: Group,
  camera: Camera,
): { animate: (time: number) => void; dynamicObjects: Set<Object3D> } {
  const dynamicObjects = new Set<Object3D>();
  scene.updateMatrixWorld(true);
  const meshes: Array<Mesh> = [];
  scene.traverse((object) => {
    if (object instanceof Mesh) meshes.push(object);
  });
  const shaderMaterials: Array<ShaderMaterial> = [];
  const fans: Array<{
    rotor: Group;
    material: MeshStandardMaterial;
    blades: Array<MeshStandardMaterial>;
  }> = [];
  const keys: Array<{ material: MeshStandardMaterial; phase: number }> = [];
  const keyMaterials = new Map<string, MeshStandardMaterial>();
  const steam: Array<{ mesh: Mesh; origin: Vector3; phase: number }> = [];

  // The luminous surfaces sit under the gaming keycaps, not over their faces.
  const keyGlows: Array<BufferGeometry> = [];
  for (const key of meshes) {
    if (!/^Keyboard__(key|space_bar)/.test(key.name)) continue;
    const bounds = new Box3().setFromObject(key);
    if (bounds.min.y < 5) continue;
    dynamicObjects.add(key);
    const size = bounds.getSize(new Vector3());
    const center = bounds.getCenter(new Vector3());
    if (key.material instanceof MeshStandardMaterial) {
      const column = `${key.material.uuid}:${Math.round(center.x * 100)}`;
      let material = keyMaterials.get(column);
      if (!material) {
        material = key.material.clone();
        material.emissiveIntensity = 1.15;
        keyMaterials.set(column, material);
        keys.push({ material, phase: center.x * 0.75 });
      }
      key.material = material;
    }
    keyGlows.push(
      new PlaneGeometry(size.x + 0.014, size.z + 0.014)
        .rotateX(-Math.PI / 2)
        .translate(center.x, bounds.min.y + 0.001, center.z),
    );
  }
  if (keyGlows.length) {
    const material = animatedMaterial(/* glsl */ `
      uniform float uTime;
      varying vec3 vPosition;
      void main() {
        float wave = fract(vPosition.x * 0.75 - uTime * 0.12);
        vec3 rgb = clamp(abs(mod(wave * 6.0 + vec3(0.0, 4.0, 2.0), 6.0)
          - 3.0) - 1.0, 0.0, 1.0);
        gl_FragColor = vec4(rgb * 1.5 + 0.025, 1.0);
        ${outputColor}
      }
    `);
    const backlight = new Mesh(mergeParts(keyGlows), material);
    backlight.name = "Gaming keyboard RGB backlight";
    scene.add(backlight);
    dynamicObjects.add(backlight);
    shaderMaterials.push(material);
  }

  // Rotate actual blades about each hub; leave bezels and housings stationary.
  const fanBlades = meshes.filter((mesh) =>
    mesh.name.startsWith("PC__fan_blade"),
  );
  for (const ring of meshes) {
    if (
      !ring.name.startsWith("PC__illuminated_fan_ring") ||
      !(ring.material instanceof MeshStandardMaterial)
    )
      continue;
    const center = new Box3().setFromObject(ring).getCenter(new Vector3());
    const rotor = new Group();
    rotor.name = `${ring.name} rotor`;
    rotor.position.copy(center);
    scene.add(rotor);
    rotor.updateMatrixWorld(true);
    const bladeMaterials: Array<MeshStandardMaterial> = [];
    for (const blade of fanBlades) {
      const position = new Box3().setFromObject(blade).getCenter(new Vector3());
      if (Math.abs(position.y - center.y) > 0.13) continue;
      blade.castShadow = false;
      if (blade.material instanceof MeshStandardMaterial) {
        const material = blade.material.clone();
        material.color.set("#8daabe");
        // A brighter leading blade makes physical rotation readable at small sizes.
        material.emissiveIntensity = bladeMaterials.length === 0 ? 1.2 : 0.32;
        blade.material = material;
        bladeMaterials.push(material);
      }
      rotor.attach(blade);
    }
    ring.material.emissiveIntensity = 1.65;
    fans.push({ rotor, material: ring.material, blades: bladeMaterials });
    dynamicObjects.add(rotor);
    dynamicObjects.add(ring);
  }

  for (const mesh of meshes) {
    if (mesh.name.startsWith("Cooking__warm_steam_wisp")) mesh.visible = false;
  }
  const steamGeometry = new PlaneGeometry(0.24, 0.4);
  // Cookware straddles the authored burners. Follow the utensils, without moving them.
  for (const [index, name] of ["Frying_pan__bowl", "Stock_pot"].entries()) {
    const utensil = scene.getObjectByName(name);
    if (!utensil) continue;
    const bounds = new Box3().setFromObject(utensil);
    const center = bounds.getCenter(new Vector3());
    const radius = index === 0 ? 0.32 : 0.3;
    const height = index === 0 ? 0.1 : 0.085;
    const jets: Array<BufferGeometry> = [];
    for (let jet = 0; jet < 24; jet++) {
      const angle = (jet / 24) * Math.PI * 2;
      jets.push(
        new ConeGeometry(0.014, height, 5, 1, true).translate(
          Math.cos(angle) * radius,
          height / 2,
          Math.sin(angle) * radius,
        ),
      );
    }
    const flameMaterial = animatedMaterial(/* glsl */ `
      varying vec2 vUv;
      void main() {
        float tip = smoothstep(0.62, 1.0, vUv.y);
        vec3 blue = mix(vec3(0.015, 0.10, 1.6), vec3(0.08, 0.55, 2.2), vUv.y);
        gl_FragColor = vec4(blue, (1.0 - tip) * 0.8);
        ${outputColor}
      }
    `);
    flameMaterial.vertexShader = /* glsl */ `
      uniform float uTime;
      varying vec2 vUv;
      void main() {
        vUv = uv;
        vec3 p = position;
        float phase = atan(p.z, p.x) * 5.0;
        p.y *= 0.84 + 0.14 * sin(uTime * 7.0 + phase)
          + 0.06 * sin(uTime * 11.0 - phase);
        gl_Position = projectionMatrix * modelViewMatrix * vec4(p, 1.0);
      }
    `;
    flameMaterial.transparent = true;
    flameMaterial.depthWrite = false;
    flameMaterial.blending = AdditiveBlending;
    flameMaterial.side = DoubleSide;
    const flame = new Mesh(mergeParts(jets), flameMaterial);
    flame.name = `${name} blue gas flame`;
    flame.position.set(center.x, 1.476, center.z);
    scene.add(flame);
    dynamicObjects.add(flame);
    shaderMaterials.push(flameMaterial);

    const origin = new Vector3(center.x, bounds.max.y + 0.07, center.z);
    if (index === 1) origin.set(center.x - 0.2, 1.87, center.z + 0.05);
    for (let wisp = 0; wisp < 3; wisp++) {
      const phase = wisp / 3 + index * 0.12;
      const material = animatedMaterial(
        /* glsl */ `
        uniform float uTime;
        uniform float uPhase;
        varying vec2 vUv;
        void main() {
          float age = fract(uTime * 0.22 + uPhase);
          float bend = 0.18 * sin(vUv.y * 7.0 - uTime * 1.2 + uPhase * 6.28);
          float width = mix(0.08, 0.24, vUv.y);
          float d = (vUv.x - 0.5 - bend) / width;
          float ribbon = exp(-d * d * 1.8);
          float ends = smoothstep(0.0, 0.18, vUv.y)
            * (1.0 - smoothstep(0.3, 1.0, vUv.y));
          gl_FragColor = vec4(0.65, 0.72, 0.78,
            ribbon * ends * sin(age * 3.141593) * 0.30);
          ${outputColor}
        }
      `,
        phase,
      );
      material.transparent = true;
      material.depthWrite = false;
      const mesh = new Mesh(steamGeometry, material);
      mesh.name = `${name} drifting steam ${wisp + 1}`;
      scene.add(mesh);
      dynamicObjects.add(mesh);
      steam.push({ mesh, origin, phase });
      shaderMaterials.push(material);
    }
  }
  if (!steam.length) steamGeometry.dispose();

  for (const [index, meter] of meshes
    .filter((mesh) => mesh.name.startsWith("Mixer__VU_meter"))
    .entries()) {
    if (meter.material instanceof MeshStandardMaterial) {
      meter.material.color.set("#081812");
      meter.material.emissiveIntensity = 0.025;
    }
    meter.geometry.computeBoundingBox();
    const bounds = meter.geometry.boundingBox!;
    const size = bounds.getSize(new Vector3());
    const center = bounds.getCenter(new Vector3());
    const material = animatedMaterial(
      /* glsl */ `
      uniform float uTime;
      uniform float uPhase;
      varying vec2 vUv;
      void main() {
        vec2 grid = vUv * vec2(18.0, 2.0);
        vec2 cell = fract(grid);
        float channel = uPhase + floor(grid.y) * 1.7;
        float level = 0.56 + 0.19 * sin(uTime * 2.3 + channel)
          + 0.12 * sin(uTime * 5.1 + channel * 2.1);
        float column = floor(grid.x) / 18.0;
        float lit = step(column, level);
        float segment = step(0.16, cell.x) * step(cell.x, 0.84)
          * step(0.20, cell.y) * step(cell.y, 0.80);
        vec3 color = column > 0.88 ? vec3(0.7, 0.10, 0.035)
          : column > 0.72 ? vec3(0.6, 0.40, 0.035) : vec3(0.08, 0.48, 0.19);
        gl_FragColor = vec4(mix(vec3(0.003, 0.009, 0.006),
          color * mix(0.055, 0.85, lit), segment), 1.0);
        ${outputColor}
      }
    `,
      index * 2.4,
    );
    const display = new Mesh(
      new PlaneGeometry(size.x * 0.92, size.z * 0.84).rotateX(-Math.PI / 2),
      material,
    );
    display.name = `${meter.name} animated LEDs`;
    display.position.set(center.x, bounds.max.y + size.y * 0.08, center.z);
    meter.add(display);
    dynamicObjects.add(display);
    shaderMaterials.push(material);
  }

  function animate(time: number): void {
    for (const material of shaderMaterials)
      material.uniforms.uTime.value = time;
    for (const { material, phase } of keys) {
      material.emissive.setHSL((((phase - time * 0.12) % 1) + 1) % 1, 0.9, 0.4);
    }
    fans.forEach(({ rotor, material, blades }, index) => {
      rotor.rotation.z = -time * (3.8 + index * 0.2);
      material.color.setHSL((0.55 + index * 0.18 + time * 0.1) % 1, 0.92, 0.42);
      material.emissive.copy(material.color);
      for (const blade of blades) blade.emissive.copy(material.color);
    });
    for (const { mesh, origin, phase } of steam) {
      const age = (time * 0.22 + phase) % 1;
      mesh.position.set(
        origin.x + Math.sin(age * 4 + phase * 6) * 0.05,
        origin.y + age * 0.38,
        origin.z,
      );
      mesh.scale.setScalar(0.75 + age * 0.55);
      mesh.quaternion.copy(camera.quaternion);
    }
  }
  animate(0);
  return { animate, dynamicObjects };
}
