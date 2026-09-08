import {
  LoadingManager,
  Mesh,
  MeshStandardMaterial,
  OrthographicCamera,
  SRGBColorSpace,
  Texture,
} from "three";
import { MeshoptDecoder } from "three/addons/libs/meshopt_decoder.module.js";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import type { BufferGeometry, Group, Material } from "three";

export type SceneMetadata = {
  cameraTarget: [number, number, number];
  horizontalLimitDegrees: number;
  verticalLimitDegrees: number;
  sourceSize: [number, number];
};

export type SceneAssets = {
  scene: Group;
  camera: OrthographicCamera;
  metadata: SceneMetadata;
  dispose: () => void;
};

export type ScenePose =
  | "home"
  | "left"
  | "right"
  | "up"
  | "down"
  | "top-left"
  | "top-right"
  | "bottom-left"
  | "bottom-right"
  | "review-front"
  | "review-left"
  | "review-right"
  | "review-rear"
  | "review-top";

const poses = new Set<ScenePose>([
  "home",
  "left",
  "right",
  "up",
  "down",
  "top-left",
  "top-right",
  "bottom-left",
  "bottom-right",
  "review-front",
  "review-left",
  "review-right",
  "review-rear",
  "review-top",
]);

export function getScenePreview() {
  const query = new URLSearchParams(import.meta.env.DEV ? location.search : "");
  const pose = query.get("scenePose") as ScenePose | null;
  const motion = query.get("sceneMotion") !== "off";
  return {
    clay: query.get("sceneView") === "clay",
    motion,
    capture: !motion && query.get("sceneCapture") === "on",
    pose: pose && poses.has(pose) ? pose : "home",
  };
}

async function readAsset(url: string, signal: AbortSignal) {
  const response = await fetch(url, { signal });
  if (!response.ok) {
    throw new Error(`Could not load ${url}: HTTP ${response.status}.`);
  }
  return response;
}

function parseMetadata(value: unknown): SceneMetadata {
  const metadata = value as {
    cameraTarget?: unknown;
    sourceSize?: unknown;
    horizontalLimitDegrees?: unknown;
    verticalLimitDegrees?: unknown;
  } | null;
  if (
    !metadata ||
    !Array.isArray(metadata.cameraTarget) ||
    metadata.cameraTarget.length !== 3 ||
    !metadata.cameraTarget.every(Number.isFinite) ||
    !Array.isArray(metadata.sourceSize) ||
    metadata.sourceSize[0] !== 1536 ||
    metadata.sourceSize[1] !== 1024 ||
    typeof metadata.horizontalLimitDegrees !== "number" ||
    !Number.isFinite(metadata.horizontalLimitDegrees) ||
    metadata.horizontalLimitDegrees <= 0 ||
    typeof metadata.verticalLimitDegrees !== "number" ||
    !Number.isFinite(metadata.verticalLimitDegrees) ||
    metadata.verticalLimitDegrees <= 0
  ) {
    throw new Error("The studio scene has invalid camera metadata.");
  }
  return metadata as SceneMetadata;
}

export async function loadSceneAssets(
  signal: AbortSignal,
  clay: boolean,
  inspection = false,
): Promise<SceneAssets> {
  const worldPreview =
    import.meta.env.DEV &&
    new URLSearchParams(location.search).get("sceneModel") === "world";
  const [buffer, metadata] = await Promise.all([
    readAsset(
      worldPreview ? "/scene/studio-world.glb" : "/scene/studio.glb",
      signal,
    ).then((response) => response.arrayBuffer()),
    readAsset(
      worldPreview ? "/scene/scene-world.json" : "/scene/scene.json",
      signal,
    )
      .then((response) => response.json())
      .then(parseMetadata),
  ]);
  signal.throwIfAborted();
  const failedResources = new Set<string>();
  const manager = new LoadingManager();
  manager.onError = (url) => failedResources.add(url);
  const loader = new GLTFLoader(manager);
  loader.setMeshoptDecoder(MeshoptDecoder);
  const gltf = await loader.parseAsync(buffer, "/scene/");
  const geometries = new Set<BufferGeometry>();
  const materials = new Set<Material>();
  const textures = new Set<Texture>();

  function trackMaterial(material: Material) {
    materials.add(material);
    for (const value of Object.values(material)) {
      if (value instanceof Texture) textures.add(value);
    }
  }

  const dispose = () => {
    gltf.scene.traverse((object) => {
      if (!(object instanceof Mesh)) return;
      geometries.add(object.geometry);
      const meshMaterials = Array.isArray(object.material)
        ? object.material
        : [object.material];
      meshMaterials.forEach(trackMaterial);
    });
    geometries.forEach((geometry) => geometry.dispose());
    materials.forEach((material) => material.dispose());
    textures.forEach((texture) => {
      texture.dispose();
      if (
        typeof ImageBitmap !== "undefined" &&
        texture.image instanceof ImageBitmap
      ) {
        texture.image.close();
      }
    });
  };

  // GLTFLoader tolerates failed textures; the reference view requires every one.
  if (failedResources.size > 0) {
    dispose();
    throw new Error(
      `The studio has ${failedResources.size} image asset(s) that could not load or decode.`,
    );
  }

  gltf.scene.updateMatrixWorld(true);
  const sourceCamera = gltf.cameras.find(
    (camera) => camera.name === "ReferenceCamera",
  );
  if (!(sourceCamera instanceof OrthographicCamera)) {
    dispose();
    throw new Error("The studio is missing its orthographic reference camera.");
  }

  const camera = sourceCamera.clone();
  sourceCamera.getWorldPosition(camera.position);
  sourceCamera.getWorldQuaternion(camera.quaternion);
  camera.scale.set(1, 1, 1);
  // R3F must preserve the exported frame instead of treating pixels as world units.
  Object.assign(camera, { manual: true });
  camera.updateMatrixWorld(true);

  gltf.scene.traverse((object) => {
    if (inspection && object.name.startsWith("Setting")) object.visible = false;
    if (clay && /^(Steam|FallingPetal|ScreenGlow)/.test(object.name)) {
      object.visible = false;
    }
    if (!(object instanceof Mesh)) return;
    object.castShadow = clay && !object.name.startsWith("Setting");
    object.receiveShadow = clay;
    geometries.add(object.geometry);
    const meshMaterials = Array.isArray(object.material)
      ? object.material
      : [object.material];
    const mapped = meshMaterials.map((material) => {
      trackMaterial(material);
      material.toneMapped = false;
      const map = "map" in material ? material.map : null;
      if (map instanceof Texture) {
        map.colorSpace = SRGBColorSpace;
      }
      if (!clay) return material;
      const clayMaterial = new MeshStandardMaterial({
        color: "#b2a594",
        roughness: 0.85,
        side: material.side,
        transparent: material.transparent,
        opacity: material.opacity,
        depthWrite: material.depthWrite,
      });
      materials.add(clayMaterial);
      return clayMaterial;
    });
    object.material = mapped.length === 1 ? mapped[0] : mapped;
  });

  return { scene: gltf.scene, camera, metadata, dispose };
}
