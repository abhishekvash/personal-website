import {
  Box3,
  Group,
  MeshStandardMaterial,
  OrthographicCamera,
  Texture,
  Vector3,
} from "three";
import { MeshoptDecoder } from "three/addons/libs/meshopt_decoder.module.js";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import sceneUrl from "../../assets/scene/curiosity-house.glb?url";
import { installCharacterPortraits } from "./CharacterPortraits";
import { installSceneAnimation } from "./SceneAnimation";
import { installScreenContent } from "./ScreenContent";
import { batchStaticScene } from "./StaticSceneBatching";
import { positionStudyTaskLamp } from "./StudyTaskLamp";
import {
  studioCeilingHeight,
  studioCeilingLights,
  studioConsoleX,
} from "./roomLayout";
import type { Material, Mesh } from "three";

export type SceneLoadPhase = "download" | "parse" | "setup";

export type SceneAssets = {
  scene: Group;
  camera: OrthographicCamera;
  animate: (time: number) => void;
  dispose: () => void;
};

const materialColors: Record<string, string> = {
  "Blossom • 0": "#d9366f",
  "Blossom • 1": "#ef5c88",
  "Blossom • 2": "#ff7d9d",
  "Blossom • 3": "#b92358",
  "Blossom • 4": "#ff94aa",
  "Cherry • amber bark ridges": "#b36d32",
  "Cherry • dark sculpted bark": "#4a2c29",
  "Frame • warm ivory": "#f3d6b8",
};

// Keep practical lights luminous without giving screens the same bloom as lamps.
const materialEmission: Partial<Record<string, number>> = {
  "Lamp • glowing diffuser": 1.4,
  "Props • warm LED": 0.65,
  "Neon • coral": 0.65,
  "Neon • peach": 0.6,
  "Display • raspberry": 0.45,
  "Display • midnight plum": 0.4,
};

function positionChairs(scene: Group, chairParts: Array<Mesh>): void {
  const layouts = [
    {
      prefix: "Study_chair__",
      screens: ["Study_display__screen", "Study_display__screen001"],
    },
    {
      prefix: "Studio_chair__",
      screens: ["Studio_display__screen"],
      consoleName: "Mixing_console__brass_case",
    },
    {
      prefix: "Gaming_chair__",
      screens: ["Gaming_ultrawide__screen"],
    },
  ];
  scene.updateMatrixWorld(true);
  for (const { prefix, screens: screenNames, consoleName } of layouts) {
    const seat = scene.getObjectByName(`${prefix}seat`);
    const back = scene.getObjectByName(`${prefix}upholstered_back`);
    const screens = screenNames
      .map((name) => scene.getObjectByName(name))
      .filter((screen) => screen !== undefined);
    if (!seat || !back || screens.length !== screenNames.length) continue;

    const pivot = new Box3().setFromObject(seat).getCenter(new Vector3());
    const backCenter = new Box3().setFromObject(back).getCenter(new Vector3());
    const screenCenter = new Vector3();
    for (const screen of screens) {
      screenCenter.add(
        new Box3().setFromObject(screen).getCenter(new Vector3()),
      );
    }
    screenCenter.divideScalar(screens.length);
    const destination = pivot.clone();
    const consoleCase = consoleName
      ? scene.getObjectByName(consoleName)
      : undefined;
    if (consoleCase) {
      const bounds = new Box3().setFromObject(consoleCase);
      destination.x = bounds.getCenter(new Vector3()).x;
      destination.z = bounds.max.z + 0.3;
    }

    const forward = pivot.clone().sub(backCenter);
    const towardsScreen = screenCenter.sub(destination);
    const chair = new Group();
    chair.name = `${prefix}facing_screens`;
    chair.position.copy(pivot);
    scene.add(chair);
    chair.updateMatrixWorld(true);
    // Keep seats, backs, armrests, and casters together when turning each chair.
    for (const part of chairParts) {
      if (part.name.startsWith(prefix)) chair.attach(part);
    }
    chair.rotation.y =
      Math.atan2(towardsScreen.x, towardsScreen.z) -
      Math.atan2(forward.x, forward.z);
    chair.position.copy(destination);
  }
}

function mark(name: string): void {
  performance.mark(`scene:${name}`);
}

function measure(name: string, start: string, end: string): void {
  try {
    performance.measure(`scene:${name}`, `scene:${start}`, `scene:${end}`);
  } catch {
    // A direct route transition may begin after an optional earlier mark.
  }
}

export async function loadScene(
  signal: AbortSignal,
  onPhase: (phase: SceneLoadPhase) => void,
): Promise<SceneAssets> {
  onPhase("download");
  mark("download-start");
  const response = await fetch(sceneUrl, { signal });
  if (!response.ok) {
    throw new Error(`Could not load scene: HTTP ${response.status}.`);
  }

  const buffer = await response.arrayBuffer();
  mark("download-end");
  measure("download", "download-start", "download-end");
  onPhase("parse");
  mark("parse-start");

  const loader = new GLTFLoader();
  loader.setMeshoptDecoder(MeshoptDecoder);

  const sceneBaseUrl = new URL(".", new URL(sceneUrl, window.location.href))
    .href;
  const gltf = await loader.parseAsync(buffer, sceneBaseUrl);
  signal.throwIfAborted();
  mark("parse-end");
  measure("parse", "parse-start", "parse-end");
  onPhase("setup");
  mark("setup-start");
  const sourceCamera = gltf.cameras.find(
    (camera) => camera.name === "HeroCamera",
  );
  if (!(sourceCamera instanceof OrthographicCamera)) {
    throw new Error("Scene is missing its HeroCamera.");
  }

  const camera = sourceCamera.clone();
  sourceCamera.getWorldPosition(camera.position);
  sourceCamera.getWorldQuaternion(camera.quaternion);
  camera.scale.set(1, 1, 1);
  Object.assign(camera, { manual: true });
  camera.updateMatrixWorld(true);

  const geometries = new Set<Mesh["geometry"]>();
  const materials = new Set<Material>();
  const textures = new Set<Texture>();
  const deviceMaterials = new Map<string, MeshStandardMaterial>();
  const chairParts: Array<Mesh> = [];
  const speakerParts: Array<Mesh> = [];

  gltf.scene.traverse((object) => {
    if (object.type !== "Mesh") return;
    const mesh = object as Mesh;
    if (/^(Study|Studio|Gaming)_chair__/.test(mesh.name)) chairParts.push(mesh);
    if (mesh.name.startsWith("Studio_nearfield_monitor__")) {
      mesh.position.x += studioConsoleX - 0.85 - 0.4;
      speakerParts.push(mesh);
    }
    // Center the display and its artwork between the speakers, slightly nearer the chair.
    if (
      mesh.name.startsWith("Studio_display__") ||
      (mesh.name.startsWith("Display_star") &&
        mesh.position.y > 3.6 &&
        mesh.position.y < 4.3)
    ) {
      mesh.position.x += studioConsoleX - 1.48;
      mesh.position.z += 0.08;
    }
    mesh.castShadow = true;
    mesh.receiveShadow = true;
    // Recess the diffuser into the ceiling; remove the hanging shade and stem.
    if (mesh.name.startsWith("Pendant_lamp__")) {
      if (mesh.name === "Pendant_lamp__warm_diffuser") {
        const { x, z } = studioCeilingLights[0];
        mesh.position.set(x, studioCeilingHeight - 0.005, z);
      } else {
        mesh.visible = false;
      }
    }
    const meshMaterials = Array.isArray(mesh.material)
      ? mesh.material
      : [mesh.material];
    for (const material of meshMaterials) {
      materials.add(material);
      const color = materialColors[material.name];
      if (material instanceof MeshStandardMaterial) {
        if (color) material.color.set(color);
        material.roughness = Math.min(material.roughness, 0.76);
        const emission = materialEmission[material.name];
        if (emission !== undefined) material.emissiveIntensity = emission;
        material.needsUpdate = true;
      }
    }

    const original = mesh.material;
    if (!(original instanceof MeshStandardMaterial)) return;
    let deviceColor: string | undefined;
    let deviceIntensity = 0.9;
    if (mesh.name.startsWith("PC__illuminated_fan_ring")) {
      deviceColor = mesh.position.y > 5.85 ? "#c391ff" : "#65e3ff";
      deviceIntensity = 1.2;
    } else if (mesh.name.startsWith("Mixer__VU_meter")) {
      deviceColor = "#adc998";
      deviceIntensity = 0.22;
    } else if (mesh.name.startsWith("Gaming__concealed_coral_light_strip")) {
      deviceColor = "#f57ab6";
      deviceIntensity = 1.1;
    }
    if (!deviceColor) return;

    // Device accents must not recolor the shared neon/LED materials elsewhere.
    const key = `${original.uuid}:${deviceColor}`;
    let material = deviceMaterials.get(key);
    if (!material) {
      material = original.clone();
      material.color.set(deviceColor);
      material.emissive.set(deviceColor);
      material.emissiveIntensity = deviceIntensity;
      deviceMaterials.set(key, material);
    }
    mesh.material = material;
  });

  for (const part of speakerParts) {
    // Duplicate every cabinet, driver, and trim component for a matching stereo pair.
    const speaker = part.clone();
    speaker.name = part.name.replace(
      "Studio_nearfield_monitor__",
      "Studio_right_nearfield_monitor__",
    );
    speaker.position.x += 1.7;
    gltf.scene.add(speaker);
  }

  const studioDiffuser = gltf.scene.getObjectByName(
    "Pendant_lamp__warm_diffuser",
  );
  if (studioDiffuser) {
    for (const { name, x, z } of studioCeilingLights.slice(1)) {
      // Share geometry and material so both recessed fixtures remain identical.
      const diffuser = studioDiffuser.clone();
      diffuser.name = `${name} diffuser`;
      diffuser.position.set(x, studioCeilingHeight - 0.005, z);
      gltf.scene.add(diffuser);
    }
  }

  positionChairs(gltf.scene, chairParts);

  function collectResources(): void {
    gltf.scene.traverse((object) => {
      if (object.type !== "Mesh") return;
      const mesh = object as Mesh;
      geometries.add(mesh.geometry);
      const meshMaterials = Array.isArray(mesh.material)
        ? mesh.material
        : [mesh.material];
      for (const material of meshMaterials) {
        materials.add(material);
        for (const value of Object.values(material)) {
          if (value instanceof Texture) textures.add(value);
        }
      }
    });
  }

  function dispose(): void {
    collectResources();
    geometries.forEach((geometry) => geometry.dispose());
    materials.forEach((material) => material.dispose());
    textures.forEach((texture) => texture.dispose());
  }

  try {
    positionStudyTaskLamp(gltf.scene);
    const preview = installScreenContent(gltf.scene);
    await installCharacterPortraits(gltf.scene);
    signal.throwIfAborted();
    const room = installSceneAnimation(gltf.scene, camera);
    const dynamicObjects = new Set([
      ...room.dynamicObjects,
      ...preview.dynamicObjects,
    ]);
    // Batching detaches source meshes; keep their shared resources owned until teardown.
    collectResources();
    batchStaticScene(gltf.scene, dynamicObjects);
    function animate(time: number): void {
      room.animate(time);
      preview.animate(time);
    }
    mark("setup-end");
    measure("setup", "setup-start", "setup-end");
    return { scene: gltf.scene, camera, animate, dispose };
  } catch (error) {
    dispose();
    throw error;
  }
}
