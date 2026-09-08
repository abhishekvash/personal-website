import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import {
  Box3,
  MathUtils,
  NoToneMapping,
  SRGBColorSpace,
  Spherical,
  Vector2,
  Vector3,
  WebGLRenderer,
} from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { OutputPass } from "three/addons/postprocessing/OutputPass.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { ShaderPass } from "three/addons/postprocessing/ShaderPass.js";

import { SceneAtmosphere } from "./SceneAtmosphere";
import { getScenePreview, loadSceneAssets } from "./scene-assets";
import type { SceneAssets, ScenePose } from "./scene-assets";
import type { MutableRefObject } from "react";

type OrbitHandle = {
  reset: () => void;
  key: (key: string) => boolean;
};

type SceneProps = {
  motionPlaying: boolean;
  onReady: () => void;
  onError: (error: unknown) => void;
};

function CameraControls({
  assets,
  pose,
  handle,
  onMoved,
}: {
  assets: SceneAssets;
  pose: ScenePose;
  handle: MutableRefObject<OrbitHandle | null>;
  onMoved: (moved: boolean) => void;
}) {
  const { camera, gl, invalidate } = useThree();

  useLayoutEffect(() => {
    const homePosition = camera.position.clone();
    const homeQuaternion = camera.quaternion.clone();
    const homeZoom = assets.camera.zoom;
    const controls = new OrbitControls(camera, gl.domElement);
    const target = new Vector3(...assets.metadata.cameraTarget);
    controls.target.copy(target);
    const home = new Spherical().setFromVector3(
      homePosition.clone().sub(target),
    );
    const horizontal = MathUtils.degToRad(
      assets.metadata.horizontalLimitDegrees,
    );
    const vertical = MathUtils.degToRad(assets.metadata.verticalLimitDegrees);
    controls.enablePan = false;
    controls.enableZoom = false;
    controls.enableDamping = false;
    controls.autoRotate = false;
    controls.rotateSpeed = 0.35;
    controls.minAzimuthAngle = home.theta - horizontal;
    controls.maxAzimuthAngle = home.theta + horizontal;
    controls.minPolarAngle = home.phi - vertical;
    controls.maxPolarAngle = home.phi + vertical;
    controls.update();

    function change() {
      onMoved(camera.position.distanceToSquared(homePosition) > 0.001);
      invalidate();
    }

    function rotate(horizontalOffset: number, verticalOffset: number) {
      const spherical = new Spherical().setFromVector3(
        camera.position.clone().sub(controls.target),
      );
      spherical.theta = MathUtils.clamp(
        spherical.theta + horizontalOffset,
        controls.minAzimuthAngle,
        controls.maxAzimuthAngle,
      );
      spherical.phi = MathUtils.clamp(
        spherical.phi + verticalOffset,
        controls.minPolarAngle,
        controls.maxPolarAngle,
      );
      camera.position.setFromSpherical(spherical).add(controls.target);
      controls.update();
      change();
    }

    function reset() {
      camera.position.copy(homePosition);
      camera.quaternion.copy(homeQuaternion);
      assets.camera.zoom = homeZoom;
      assets.camera.updateProjectionMatrix();
      controls.target.copy(target);
      controls.minAzimuthAngle = home.theta - horizontal;
      controls.maxAzimuthAngle = home.theta + horizontal;
      controls.minPolarAngle = home.phi - vertical;
      controls.maxPolarAngle = home.phi + vertical;
      controls.update();
      change();
    }

    controls.addEventListener("change", change);
    handle.current = {
      reset,
      key(key) {
        const step = MathUtils.degToRad(0.75);
        switch (key) {
          case "ArrowLeft":
            rotate(-step, 0);
            return true;
          case "ArrowRight":
            rotate(step, 0);
            return true;
          case "ArrowUp":
            rotate(0, -step);
            return true;
          case "ArrowDown":
            rotate(0, step);
            return true;
          case "Home":
            reset();
            return true;
          default:
            return false;
        }
      },
    };

    const x = pose.includes("left")
      ? -horizontal
      : pose.includes("right")
        ? horizontal
        : 0;
    const y =
      pose === "up" || pose.startsWith("top-")
        ? -vertical
        : pose === "down" || pose.startsWith("bottom-")
          ? vertical
          : 0;
    if (import.meta.env.DEV && pose.startsWith("review-")) {
      const angles: Record<string, [number, number]> = {
        "review-front": [0, Math.PI / 2],
        "review-left": [-Math.PI / 2, Math.PI / 2],
        "review-right": [Math.PI / 2, Math.PI / 2],
        "review-rear": [Math.PI, Math.PI / 2],
        "review-top": [0, 0.001],
      };
      const [theta, phi] = angles[pose];
      controls.minAzimuthAngle = -Infinity;
      controls.maxAzimuthAngle = Infinity;
      controls.minPolarAngle = 0;
      controls.maxPolarAngle = Math.PI;
      camera.position
        .setFromSpherical(new Spherical(home.radius, phi, theta))
        .add(target);
      controls.update();
      const bounds = new Box3();
      assets.scene.traverseVisible((object) => {
        if (object.type === "Mesh") bounds.expandByObject(object, true);
      });
      if (!bounds.isEmpty()) {
        const center = bounds.getCenter(new Vector3());
        const right = new Vector3(1, 0, 0).applyQuaternion(camera.quaternion);
        const up = new Vector3(0, 1, 0).applyQuaternion(camera.quaternion);
        let halfWidth = 0;
        let halfHeight = 0;
        for (const cornerX of [bounds.min.x, bounds.max.x]) {
          for (const cornerY of [bounds.min.y, bounds.max.y]) {
            for (const cornerZ of [bounds.min.z, bounds.max.z]) {
              const corner = new Vector3(cornerX, cornerY, cornerZ).sub(center);
              halfWidth = Math.max(halfWidth, Math.abs(corner.dot(right)));
              halfHeight = Math.max(halfHeight, Math.abs(corner.dot(up)));
            }
          }
        }
        camera.position.add(center.clone().sub(target));
        controls.target.copy(center);
        const orthographic = assets.camera;
        orthographic.zoom =
          0.9 *
          Math.min(
            (orthographic.right - orthographic.left) / (2 * halfWidth),
            (orthographic.top - orthographic.bottom) / (2 * halfHeight),
          );
        orthographic.updateProjectionMatrix();
        controls.update();
      }
      change();
    } else {
      rotate(x, y);
    }

    return () => {
      handle.current = null;
      controls.removeEventListener("change", change);
      controls.dispose();
      camera.position.copy(homePosition);
      camera.quaternion.copy(homeQuaternion);
      assets.camera.zoom = homeZoom;
      assets.camera.updateProjectionMatrix();
    };
  }, [assets, camera, gl, handle, invalidate, onMoved, pose]);

  return null;
}

// The painting is 1536 pixels wide. When the canvas draws it larger, bilinear
// magnification softens the ink; a light unsharp mask restores the edge the
// browser's own image resampling would have kept.
const SOURCE_WIDTH = 1536;
const sharpenShader = {
  uniforms: {
    tDiffuse: { value: null },
    texelSize: { value: new Vector2(1 / SOURCE_WIDTH, 1 / 1024) },
    strength: { value: 0 },
  },
  vertexShader: `
    varying vec2 vUv;
    void main() {
      vUv = uv;
      gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
    }
  `,
  fragmentShader: `
    uniform sampler2D tDiffuse;
    uniform vec2 texelSize;
    uniform float strength;
    varying vec2 vUv;
    void main() {
      vec4 center = texture2D(tDiffuse, vUv);
      if (strength <= 0.0) {
        gl_FragColor = center;
        return;
      }
      vec4 blur = center * 4.0
        + texture2D(tDiffuse, vUv + vec2(texelSize.x, 0.0)) * 2.0
        + texture2D(tDiffuse, vUv - vec2(texelSize.x, 0.0)) * 2.0
        + texture2D(tDiffuse, vUv + vec2(0.0, texelSize.y)) * 2.0
        + texture2D(tDiffuse, vUv - vec2(0.0, texelSize.y)) * 2.0
        + texture2D(tDiffuse, vUv + texelSize)
        + texture2D(tDiffuse, vUv - texelSize)
        + texture2D(tDiffuse, vUv + vec2(texelSize.x, -texelSize.y))
        + texture2D(tDiffuse, vUv - vec2(texelSize.x, -texelSize.y));
      blur /= 16.0;
      gl_FragColor = vec4(clamp(center.rgb + (center.rgb - blur.rgb) * strength, 0.0, 1.0), center.a);
    }
  `,
};

function RenderLifecycle({
  capture,
  onReady,
  onError,
}: Pick<SceneProps, "onReady" | "onError"> & { capture: boolean }) {
  const { gl, scene, camera } = useThree();
  const complete = useRef(false);
  const failed = useRef(false);
  const readyFrame = useRef<number | null>(null);
  const composer = useRef<EffectComposer | null>(null);
  const sharpen = useRef<ShaderPass | null>(null);

  useLayoutEffect(() => {
    const pass = new ShaderPass(sharpenShader);
    const effect = new EffectComposer(gl);
    effect.addPass(new RenderPass(scene, camera));
    effect.addPass(pass);
    // Restores the renderer's output colour space after the offscreen passes.
    effect.addPass(new OutputPass());
    composer.current = effect;
    sharpen.current = pass;
    return () => {
      effect.dispose();
      pass.dispose();
      composer.current = null;
      sharpen.current = null;
    };
  }, [gl, scene, camera]);

  useLayoutEffect(() => {
    const canvas = gl.domElement;
    const onContextLost = (event: Event) => {
      event.preventDefault();
      failed.current = true;
      onError(new Error("The browser lost the studio's WebGL context."));
    };
    canvas.addEventListener("webglcontextlost", onContextLost);
    gl.debug.onShaderError = (
      context,
      program,
      vertexShader,
      fragmentShader,
    ) => {
      failed.current = true;
      const details = [
        context.getProgramInfoLog(program),
        context.getShaderInfoLog(vertexShader),
        context.getShaderInfoLog(fragmentShader),
      ]
        .filter(Boolean)
        .join("\n");
      onError(
        new Error(
          `A studio material could not compile on this graphics device.\n${details}`,
        ),
      );
    };
    return () => {
      canvas.removeEventListener("webglcontextlost", onContextLost);
      gl.debug.onShaderError = null;
      if (readyFrame.current !== null) cancelAnimationFrame(readyFrame.current);
    };
  }, [gl, onError]);

  useFrame(({ size, viewport }) => {
    if (failed.current) return;
    try {
      const effect = composer.current;
      const pass = sharpen.current;
      if (effect && pass) {
        const width = size.width * viewport.dpr;
        const height = size.height * viewport.dpr;
        effect.setSize(size.width, size.height);
        effect.setPixelRatio(viewport.dpr);
        const magnification = width / SOURCE_WIDTH;
        pass.uniforms.strength.value =
          magnification > 1.05 ? Math.min(0.9, (magnification - 1) * 0.6) : 0;
        pass.uniforms.texelSize.value.set(
          magnification / width,
          magnification / height,
        );
        effect.render();
      } else {
        gl.render(scene, camera);
      }
    } catch (error) {
      failed.current = true;
      onError(error);
      return;
    }
    if (complete.current) return;
    complete.current = true;
    // The positive priority owns rendering, so a failed draw cannot reveal the scene.
    readyFrame.current = requestAnimationFrame(() => {
      if (failed.current || gl.getContext().isContextLost()) return;
      if (import.meta.env.DEV && capture) {
        try {
          gl.domElement.dataset.referenceCapture =
            gl.domElement.toDataURL("image/png");
        } catch (error) {
          failed.current = true;
          onError(error);
          return;
        }
      }
      onReady();
    });
  }, 1);

  return null;
}

export default function StudioScene({
  motionPlaying,
  onReady,
  onError,
}: SceneProps) {
  const instructionId = useId();
  const [preview] = useState(getScenePreview);
  const [assets, setAssets] = useState<SceneAssets | null>(null);
  const [moved, setMoved] = useState(false);
  const handle = useRef<OrbitHandle | null>(null);
  const viewer = useRef<HTMLDivElement>(null);
  const playing = motionPlaying && preview.motion && !preview.clay;

  useEffect(() => {
    const controller = new AbortController();
    let ownedAssets: SceneAssets | null = null;
    void loadSceneAssets(
      controller.signal,
      preview.clay,
      preview.pose.startsWith("review-"),
    )
      .then((loaded) => {
        if (controller.signal.aborted) {
          loaded.dispose();
          return;
        }
        ownedAssets = loaded;
        setAssets(loaded);
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) onError(error);
      });
    return () => {
      controller.abort();
      ownedAssets?.dispose();
    };
  }, [onError, preview.clay, preview.pose]);

  if (!assets) return null;

  return (
    <div
      ref={viewer}
      className="studio-viewer"
      role="group"
      aria-label="Explore the three-dimensional studio"
      aria-describedby={instructionId}
      tabIndex={0}
      data-scene-view={preview.clay ? "clay" : "artwork"}
      data-scene-pose={preview.pose}
      data-motion={playing ? "playing" : "paused"}
      onPointerDown={(event) => {
        if (event.target instanceof HTMLCanvasElement) {
          viewer.current?.focus({ preventScroll: true });
        }
      }}
      onKeyDown={(event) => {
        if (
          event.target !== event.currentTarget ||
          event.altKey ||
          event.ctrlKey ||
          event.metaKey
        )
          return;
        if (handle.current?.key(event.key)) event.preventDefault();
      }}
    >
      <Canvas
        className="studio-canvas"
        camera={assets.camera}
        frameloop={playing ? "always" : "demand"}
        dpr={import.meta.env.DEV && !preview.motion ? 1 : [1, 2]}
        flat
        shadows={preview.clay}
        gl={(defaults) => {
          try {
            const renderer = new WebGLRenderer({
              ...defaults,
              antialias: true,
              alpha: false,
              powerPreference: "high-performance",
              preserveDrawingBuffer: import.meta.env.DEV,
            });
            renderer.toneMapping = NoToneMapping;
            renderer.outputColorSpace = SRGBColorSpace;
            return renderer;
          } catch (error) {
            onError(error);
            throw error;
          }
        }}
        aria-hidden="true"
      >
        <color attach="background" args={["#fbe3be"]} />
        <primitive object={assets.scene} dispose={null} />
        {preview.clay ? (
          <>
            <ambientLight intensity={0.45} />
            <directionalLight
              position={[-800, 1600, 2200]}
              intensity={2}
              castShadow
              shadow-mapSize={[2048, 2048]}
              shadow-camera-near={10}
              shadow-camera-far={6000}
              shadow-camera-left={-1600}
              shadow-camera-right={1600}
              shadow-camera-top={1600}
              shadow-camera-bottom={-1600}
              shadow-bias={-0.0001}
              shadow-normalBias={2}
            >
              <object3D
                attach="target"
                position={assets.metadata.cameraTarget}
                onUpdate={(target) => target.updateMatrixWorld()}
              />
            </directionalLight>
            <directionalLight position={[1300, 100, 2200]} intensity={0.7}>
              <object3D
                attach="target"
                position={assets.metadata.cameraTarget}
                onUpdate={(target) => target.updateMatrixWorld()}
              />
            </directionalLight>
          </>
        ) : (
          <SceneAtmosphere scene={assets.scene} playing={playing} />
        )}
        <CameraControls
          assets={assets}
          pose={preview.pose}
          handle={handle}
          onMoved={setMoved}
        />
        <RenderLifecycle
          capture={preview.capture}
          onReady={onReady}
          onError={onError}
        />
      </Canvas>
      <span className="sr-only" id={instructionId}>
        Drag or use the arrow keys to look around. Press Home to return to the
        original view.
      </span>
      {moved ? (
        <button
          className="studio-reset"
          type="button"
          onClick={() => {
            handle.current?.reset();
            viewer.current?.focus({ preventScroll: true });
          }}
        >
          <svg viewBox="0 0 20 20" width="16" height="16" aria-hidden="true">
            <path
              d="M4 7a6.5 6.5 0 1 1-.3 5M4 3v4h4"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
          Original view
        </button>
      ) : null}
    </div>
  );
}
