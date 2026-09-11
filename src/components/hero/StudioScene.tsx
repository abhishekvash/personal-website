import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import {
  LinearToneMapping,
  MathUtils,
  MeshStandardMaterial,
  OrthographicCamera,
  PCFSoftShadowMap,
  SRGBColorSpace,
  Spherical,
  Texture,
  Vector2,
  Vector3,
  WebGLRenderer,
} from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { OutputPass } from "three/addons/postprocessing/OutputPass.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { MeshoptDecoder } from "three/addons/libs/meshopt_decoder.module.js";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";
import type { Group, Material, Mesh } from "three";

type SceneProps = {
  onReady: () => void;
  onError: (error: unknown) => void;
};

type SceneAssets = {
  scene: Group;
  camera: OrthographicCamera;
  dispose: () => void;
};

const cameraTarget = new Vector3(1.8, 4.5, 0);
const materialColors: Record<string, string> = {
  "Blossom • 0": "#d9366f",
  "Blossom • 1": "#ef5c88",
  "Blossom • 2": "#ff7d9d",
  "Blossom • 3": "#b92358",
  "Blossom • 4": "#ff94aa",
  "Cherry • amber bark ridges": "#b36d32",
  "Cherry • dark sculpted bark": "#4a2c29",
  "Frame • warm ivory": "#f2ca7c",
};

async function loadScene(signal: AbortSignal): Promise<SceneAssets> {
  const response = await fetch("/scene/curiosity-house.glb", { signal });
  if (!response.ok) {
    throw new Error(`Could not load scene: HTTP ${response.status}.`);
  }

  const loader = new GLTFLoader();
  loader.setMeshoptDecoder(MeshoptDecoder);

  const gltf = await loader.parseAsync(await response.arrayBuffer(), "/scene/");
  signal.throwIfAborted();
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

  gltf.scene.traverse((object) => {
    if (object.type !== "Mesh") return;
    const mesh = object as Mesh;
    mesh.castShadow = true;
    mesh.receiveShadow = true;
    const meshMaterials = Array.isArray(mesh.material)
      ? mesh.material
      : [mesh.material];
    for (const material of meshMaterials) {
      const color = materialColors[material.name];
      if (material instanceof MeshStandardMaterial) {
        if (color) material.color.set(color);
        material.roughness = Math.min(material.roughness, 0.76);
        if (
          /Display|Lamp|Neon|warm LED|luminous/.test(material.name) &&
          material.emissive.getHex() !== 0
        ) {
          material.emissiveIntensity = 2.4;
        }
        material.needsUpdate = true;
      }
    }
  });

  const dispose = () => {
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
    geometries.forEach((geometry) => geometry.dispose());
    materials.forEach((material) => material.dispose());
    textures.forEach((texture) => texture.dispose());
  };

  return { scene: gltf.scene, camera, dispose };
}

function PostProcessing() {
  const { camera, gl, scene, size } = useThree();
  const composer = useRef<EffectComposer | null>(null);

  useLayoutEffect(() => {
    const effect = new EffectComposer(gl);
    effect.addPass(new RenderPass(scene, camera));
    effect.addPass(
      new UnrealBloomPass(
        new Vector2(size.width, size.height),
        0.48,
        0.38,
        0.86,
      ),
    );
    effect.addPass(new OutputPass());
    effect.setPixelRatio(gl.getPixelRatio());
    effect.setSize(size.width, size.height);
    composer.current = effect;

    return () => {
      composer.current = null;
      effect.dispose();
    };
  }, [camera, gl, scene, size.height, size.width]);

  useFrame(() => composer.current?.render(), 1);
  return null;
}

function CameraControls() {
  const { camera, gl, invalidate } = useThree();

  useLayoutEffect(() => {
    const controls = new OrbitControls(camera, gl.domElement);
    const homePosition = camera.position.clone();
    const homeQuaternion = camera.quaternion.clone();
    const home = new Spherical().setFromVector3(
      homePosition.clone().sub(cameraTarget),
    );
    const horizontalLimit = MathUtils.degToRad(12);
    const verticalLimit = MathUtils.degToRad(7);

    controls.target.copy(cameraTarget);
    controls.enablePan = false;
    controls.enableZoom = false;
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.rotateSpeed = 0.3;
    controls.minAzimuthAngle = home.theta - horizontalLimit;
    controls.maxAzimuthAngle = home.theta + horizontalLimit;
    controls.minPolarAngle = home.phi - verticalLimit;
    controls.maxPolarAngle = home.phi + verticalLimit;
    const handleChange = () => invalidate();
    controls.addEventListener("change", handleChange);
    controls.update();

    return () => {
      controls.removeEventListener("change", handleChange);
      controls.dispose();
      camera.position.copy(homePosition);
      camera.quaternion.copy(homeQuaternion);
    };
  }, [camera, gl, invalidate]);

  return null;
}

export default function StudioScene({ onReady, onError }: SceneProps) {
  const [assets, setAssets] = useState<SceneAssets | null>(null);
  const ready = useRef(false);

  useEffect(() => {
    const controller = new AbortController();
    let loadedAssets: SceneAssets | null = null;

    void loadScene(controller.signal)
      .then((loaded) => {
        if (controller.signal.aborted) {
          loaded.dispose();
          return;
        }
        loadedAssets = loaded;
        setAssets(loaded);
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) onError(error);
      });

    return () => {
      controller.abort();
      loadedAssets?.dispose();
    };
  }, [onError]);

  if (!assets) return null;

  return (
    <div className="studio-viewer" aria-hidden="true">
      <Canvas
        className="studio-canvas"
        camera={assets.camera}
        frameloop="demand"
        dpr={[1, 2]}
        gl={(defaults) => {
          const renderer = new WebGLRenderer({
            ...defaults,
            antialias: true,
            alpha: true,
            powerPreference: "high-performance",
          });
          renderer.outputColorSpace = SRGBColorSpace;
          renderer.shadowMap.enabled = true;
          renderer.shadowMap.type = PCFSoftShadowMap;
          renderer.toneMapping = LinearToneMapping;
          renderer.toneMappingExposure = 1;
          return renderer;
        }}
        onCreated={({ gl }) => {
          gl.setClearColor("#050711", 0);
          requestAnimationFrame(() => {
            if (!ready.current) {
              ready.current = true;
              onReady();
            }
          });
        }}
      >
        <primitive object={assets.scene} dispose={null} />
        <ambientLight color="#53659d" intensity={0.32} />
        <hemisphereLight args={["#708cff", "#280d32", 0.42]} />
        <directionalLight
          color="#75d9ff"
          position={[-8, 18, -12]}
          intensity={1.45}
          castShadow
          shadow-mapSize={[2048, 2048]}
          shadow-camera-near={1}
          shadow-camera-far={50}
          shadow-camera-left={-10}
          shadow-camera-right={10}
          shadow-camera-top={10}
          shadow-camera-bottom={-10}
          shadow-bias={-0.0002}
          shadow-normalBias={0.02}
        >
          <object3D
            attach="target"
            position={cameraTarget}
            onUpdate={(target) => target.updateMatrixWorld()}
          />
        </directionalLight>
        <directionalLight
          color="#ff4fbd"
          position={[10, 12, 4]}
          intensity={1.05}
        >
          <object3D
            attach="target"
            position={cameraTarget}
            onUpdate={(target) => target.updateMatrixWorld()}
          />
        </directionalLight>
        <pointLight
          color="#ff365c"
          position={[0, 6.1, -0.25]}
          intensity={5}
          distance={4}
          decay={2}
        />
        <pointLight
          color="#ff563c"
          position={[-1, 4.1, -0.25]}
          intensity={4}
          distance={3.5}
          decay={2}
        />
        <pointLight
          color="#ffbd68"
          position={[-2.6, 1.7, 0.3]}
          intensity={2}
          distance={2.5}
          decay={2}
        />
        <CameraControls />
        <PostProcessing />
      </Canvas>
    </div>
  );
}
