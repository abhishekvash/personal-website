import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import {
  ACESFilmicToneMapping,
  Box3,
  DepthTexture,
  Group,
  HalfFloatType,
  MathUtils,
  MeshStandardMaterial,
  OrthographicCamera,
  PCFShadowMap,
  SRGBColorSpace,
  Spherical,
  Texture,
  Vector2,
  Vector3,
  WebGLRenderTarget,
  WebGLRenderer,
} from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { OutputPass } from "three/addons/postprocessing/OutputPass.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { MeshoptDecoder } from "three/addons/libs/meshopt_decoder.module.js";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";
import {
  RoomLighting,
  studioCeilingHeight,
  studioCeilingLights,
  studioConsoleX,
} from "./RoomLighting";
import { installCharacterPortraits } from "./CharacterPortraits";
import { installScreenContent } from "./ScreenContent";
import { installSceneAnimation } from "./SceneAnimation";
import { SceneMotion, useReducedMotion } from "./SceneMotion";
import { positionStudyTaskLamp } from "./StudyTaskLamp";
import { SunRaysPass } from "./SunRaysPass";
import { sunPosition, sunlight } from "./sunlight";
import type { RefObject } from "react";
import type { DirectionalLight, Material, Mesh } from "three";

type SceneProps = {
  onReady: () => void;
  onError: (error: unknown) => void;
};

type SceneAssets = {
  scene: Group;
  camera: OrthographicCamera;
  animate: (time: number) => void;
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

  const chairLayouts = [
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
  gltf.scene.updateMatrixWorld(true);
  for (const { prefix, screens: screenNames, consoleName } of chairLayouts) {
    const seat = gltf.scene.getObjectByName(`${prefix}seat`);
    const back = gltf.scene.getObjectByName(`${prefix}upholstered_back`);
    const screens = screenNames
      .map((name) => gltf.scene.getObjectByName(name))
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
      ? gltf.scene.getObjectByName(consoleName)
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
    gltf.scene.add(chair);
    chair.updateMatrixWorld(true);
    // Keep seats, backs, armrests, and casters together when turning each chair.
    chairParts
      .filter((part) => part.name.startsWith(prefix))
      .forEach((part) => chair.attach(part));
    chair.rotation.y =
      Math.atan2(towardsScreen.x, towardsScreen.z) -
      Math.atan2(forward.x, forward.z);
    chair.position.copy(destination);
  }

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

  try {
    positionStudyTaskLamp(gltf.scene);
    const animatePreview = installScreenContent(gltf.scene);
    await installCharacterPortraits(gltf.scene);
    signal.throwIfAborted();
    const animateRoom = installSceneAnimation(gltf.scene, camera);
    const animate = (time: number) => {
      animateRoom(time);
      animatePreview(time);
    };
    return { scene: gltf.scene, camera, animate, dispose };
  } catch (error) {
    dispose();
    throw error;
  }
}

function PostProcessing({ sun }: { sun: RefObject<DirectionalLight | null> }) {
  const { camera, gl, scene, size } = useThree();
  const composer = useRef<EffectComposer | null>(null);

  useLayoutEffect(() => {
    if (!sun.current) return;
    const target = new WebGLRenderTarget(size.width, size.height, {
      type: HalfFloatType,
      depthTexture: new DepthTexture(size.width, size.height),
    });
    const effect = new EffectComposer(gl, target);
    effect.addPass(new RenderPass(scene, camera));
    effect.addPass(new SunRaysPass(camera, sun.current));
    effect.addPass(
      new UnrealBloomPass(
        new Vector2(size.width, size.height),
        0.28,
        0.45,
        1.05,
      ),
    );
    effect.addPass(new OutputPass());
    effect.setPixelRatio(gl.getPixelRatio());
    effect.setSize(size.width, size.height);
    composer.current = effect;

    return () => {
      composer.current = null;
      effect.passes.forEach((pass) => pass.dispose());
      effect.dispose();
    };
  }, [camera, gl, scene, size.height, size.width, sun]);

  useFrame(() => composer.current?.render(), 1);
  return null;
}

function CameraFraming() {
  const { camera, size, invalidate } = useThree();

  useLayoutEffect(() => {
    if (!(camera instanceof OrthographicCamera)) return;

    const stacked = size.width <= 1024;
    const artworkWidth = stacked
      ? Math.min(size.width * 1.05, size.height * 1.3)
      : Math.min(size.width * 0.72, size.height * 1.1688) * 0.85;
    const artworkHeight = (artworkWidth * 77) / 90;
    camera.setViewOffset(
      artworkWidth,
      artworkHeight,
      stacked ? (artworkWidth - size.width) / 2 : artworkWidth - size.width,
      (artworkHeight - size.height) / 2 +
        (size.width <= 640 ? size.height * 0.18 : 0),
      size.width,
      size.height,
    );
    invalidate();

    return () => camera.clearViewOffset();
  }, [camera, invalidate, size.height, size.width]);

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
  const sun = useRef<DirectionalLight>(null);
  const reducedMotion = useReducedMotion();

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
    <div className="absolute inset-0">
      <Canvas
        aria-hidden="true"
        className="[&_canvas]:block [&_canvas]:cursor-grab [&_canvas]:touch-none [&_canvas:active]:cursor-grabbing"
        camera={assets.camera}
        frameloop="demand"
        dpr={[1, 2]}
        shadows={{
          type: PCFShadowMap,
          autoUpdate: false,
          needsUpdate: true,
        }}
        gl={(defaults) => {
          const renderer = new WebGLRenderer({
            ...defaults,
            antialias: true,
            alpha: true,
            powerPreference: "high-performance",
          });
          renderer.outputColorSpace = SRGBColorSpace;
          renderer.toneMapping = ACESFilmicToneMapping;
          renderer.toneMappingExposure = 1.15;
          return renderer;
        }}
        onCreated={({ gl }) => {
          // Transparent pixels must also have zero RGB for premultiplied compositing.
          gl.setClearColor(0x000000, 0);
          requestAnimationFrame(() => {
            if (!ready.current) {
              ready.current = true;
              onReady();
            }
          });
        }}
      >
        <primitive object={assets.scene} dispose={null} />
        <ambientLight color="#a69bcd" intensity={0.045} />
        <hemisphereLight args={["#a4ace5", "#9d5063", 0.3]} />
        {/* Near-horizontal light from +X lets the tree cast shadows onto the house. */}
        <directionalLight
          ref={sun}
          color={sunlight.color}
          position={sunPosition}
          intensity={sunlight.intensity}
          castShadow
          shadow-mapSize={[2048, 2048]}
          shadow-radius={1 + sunlight.diffusion}
          shadow-camera-near={1}
          shadow-camera-far={90}
          shadow-camera-left={-10}
          shadow-camera-right={10}
          shadow-camera-top={10}
          shadow-camera-bottom={-10}
          shadow-bias={-0.0002}
          shadow-normalBias={0.025}
        >
          <object3D
            attach="target"
            position={sunlight.target}
            onUpdate={(target) => target.updateMatrixWorld()}
          />
        </directionalLight>
        <directionalLight
          color="#a6b5ef"
          position={[-8, 12, 10]}
          intensity={0.25}
        >
          <object3D
            attach="target"
            position={cameraTarget}
            onUpdate={(target) => target.updateMatrixWorld()}
          />
        </directionalLight>
        {/* A transparent ground receiver anchors the long, low-sun shadows without a visible platform. */}
        <mesh
          rotation={[-Math.PI / 2, 0, 0]}
          position={[-20, -0.04, 0]}
          receiveShadow
        >
          <planeGeometry args={[100, 40]} />
          <shadowMaterial
            color="#120b20"
            opacity={0.28}
            depthWrite={false}
            onBeforeCompile={(shader) => {
              // Local lamps shadow their rooms, not the distant atmospheric ground.
              shader.fragmentShader = shader.fragmentShader.replace(
                "#include <shadowmask_pars_fragment>",
                /* glsl */ `
                  float getShadowMask() {
                    #if defined(USE_SHADOWMAP) && NUM_DIR_LIGHT_SHADOWS > 0
                      DirectionalLightShadow sun = directionalLightShadows[0];
                      return getShadow(directionalShadowMap[0], sun.shadowMapSize,
                        sun.shadowIntensity, sun.shadowBias, sun.shadowRadius,
                        vDirectionalShadowCoord[0]);
                    #else
                      return 1.0;
                    #endif
                  }
                `,
              );
            }}
          />
        </mesh>
        <RoomLighting />
        <SceneMotion animate={assets.animate} enabled={!reducedMotion} />
        <CameraFraming />
        <CameraControls />
        <PostProcessing sun={sun} />
      </Canvas>
    </div>
  );
}
