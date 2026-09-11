import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import {
  ACESFilmicToneMapping,
  DepthTexture,
  HalfFloatType,
  MathUtils,
  OrthographicCamera,
  PCFShadowMap,
  SRGBColorSpace,
  Spherical,
  Vector2,
  Vector3,
  WebGLRenderTarget,
  WebGLRenderer,
} from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { OutputPass } from "three/addons/postprocessing/OutputPass.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";
import { RoomLighting } from "./RoomLighting";
import { loadScene } from "./SceneAssets";
import { SceneMotion, useReducedMotion } from "./SceneMotion";
import { SunRaysPass } from "./SunRaysPass";
import { sunPosition, sunlight } from "./sunlight";
import type { SceneAssets, SceneLoadPhase } from "./SceneAssets";
import type { JSX, RefObject } from "react";
import type { DirectionalLight } from "three";

export type ScenePhase = SceneLoadPhase | "first-frame";

type SceneProps = {
  onReady: () => void;
  onError: (error: unknown) => void;
  onPhase: (phase: ScenePhase) => void;
};

type PostProcessingProps = {
  sun: RefObject<DirectionalLight | null>;
};

type FirstFrameProps = {
  onReady: () => void;
};

const cameraTarget = new Vector3(1.8, 4.5, 0);
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

function PostProcessing({ sun }: PostProcessingProps): null {
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

function CameraFraming(): null {
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

function FirstFrame({ onReady }: FirstFrameProps): null {
  const reported = useRef(false);

  useFrame(() => {
    if (reported.current) return;
    reported.current = true;
    mark("first-frame");
    measure("total", "module-start", "first-frame");
    onReady();
  }, 2);

  return null;
}

function CameraControls(): null {
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

export default function StudioScene({
  onReady,
  onError,
  onPhase,
}: SceneProps): JSX.Element | null {
  const [assets, setAssets] = useState<SceneAssets | null>(null);
  const sun = useRef<DirectionalLight>(null);
  const reducedMotion = useReducedMotion();

  useEffect(() => {
    const controller = new AbortController();
    let loadedAssets: SceneAssets | null = null;

    void loadScene(controller.signal, onPhase)
      .then((loaded) => {
        if (controller.signal.aborted) {
          loaded.dispose();
          return;
        }
        loadedAssets = loaded;
        onPhase("first-frame");
        setAssets(loaded);
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) onError(error);
      });

    return () => {
      controller.abort();
      loadedAssets?.dispose();
    };
  }, [onError, onPhase]);

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
        <FirstFrame onReady={onReady} />
      </Canvas>
    </div>
  );
}
