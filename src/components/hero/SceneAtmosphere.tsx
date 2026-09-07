import { useFrame } from "@react-three/fiber";
import { useLayoutEffect, useRef } from "react";
import { Mesh } from "three";
import type { Group, Material, Object3D, Vector3 } from "three";

type MotionPart = {
  object: Object3D;
  position: Vector3;
  rotation: number;
  kind: "steam" | "petal" | "glow";
  duration: number;
  phase: number;
  drift: number;
  rise: number;
  materials: { material: Material; opacity: number }[];
};

function finiteValue(value: unknown, fallback: number) {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function collectMotion(scene: Group) {
  const parts: MotionPart[] = [];
  const restore: (() => void)[] = [];
  scene.traverse((object) => {
    const kind = object.name.startsWith("Steam")
      ? "steam"
      : object.name.startsWith("FallingPetal")
        ? "petal"
        : object.name.startsWith("ScreenGlow")
          ? "glow"
          : null;
    if (!kind) return;
    const options = (object.userData.motion ?? {}) as Record<string, unknown>;
    const materials: MotionPart["materials"] = [];
    object.traverse((child) => {
      if (!(child instanceof Mesh)) return;
      const originalMaterial = child.material;
      const source = Array.isArray(child.material)
        ? child.material
        : [child.material];
      const cloned = source.map((material) => {
        const copy = material.clone();
        materials.push({ material: copy, opacity: material.opacity });
        copy.transparent = true;
        copy.depthWrite = false;
        copy.opacity = kind === "steam" ? material.opacity : 0;
        return copy;
      });
      child.material = Array.isArray(child.material) ? cloned : cloned[0];
      restore.push(() => {
        child.material = originalMaterial;
        cloned.forEach((material) => material.dispose());
      });
    });
    parts.push({
      object,
      position: object.position.clone(),
      rotation: object.rotation.z,
      kind,
      duration: Math.max(
        1,
        finiteValue(options.duration, kind === "steam" ? 7 : 15),
      ),
      phase: finiteValue(options.phase, 0),
      drift: finiteValue(options.drift, kind === "steam" ? 3 : 15),
      rise: finiteValue(options.rise, kind === "steam" ? 10 : -55),
      materials,
    });
  });
  return {
    parts,
    dispose: () => {
      restore.forEach((reset) => reset());
      for (const part of parts) {
        part.object.position.copy(part.position);
        part.object.rotation.z = part.rotation;
      }
    },
  };
}

export function SceneAtmosphere({
  scene,
  playing,
}: {
  scene: Group;
  playing: boolean;
}) {
  const parts = useRef<MotionPart[]>([]);
  const elapsed = useRef(0);

  useLayoutEffect(() => {
    const motion = collectMotion(scene);
    parts.current = motion.parts;
    elapsed.current = 0;
    return () => {
      parts.current = [];
      motion.dispose();
    };
  }, [scene]);

  useFrame((_state, delta) => {
    if (!playing) return;
    elapsed.current += Math.min(delta, 0.05);
    for (const part of parts.current) {
      if (part.kind === "steam") {
        const angle = (elapsed.current / part.duration) * Math.PI * 2;
        part.object.position.copy(part.position);
        part.object.position.x += Math.sin(angle) * part.drift;
        part.object.position.y += (1 - Math.cos(angle)) * part.rise;
        for (const { material, opacity } of part.materials) {
          material.opacity = opacity * (0.9 + Math.cos(angle) * 0.1);
        }
        continue;
      }
      const cycle = (elapsed.current / part.duration + part.phase) % 1;
      const fadeIn = Math.min(elapsed.current / 2, 1);
      const envelope = Math.sin(cycle * Math.PI) * fadeIn;
      if (part.kind !== "glow") {
        part.object.position.copy(part.position);
        part.object.position.x += Math.sin(cycle * Math.PI) * part.drift;
        part.object.position.y += cycle * part.rise;
        part.object.rotation.z = part.rotation + cycle * 1.3;
      }
      for (const { material, opacity } of part.materials) {
        material.opacity =
          opacity * envelope * (part.kind === "glow" ? 0.045 : 0.6);
      }
    }
  });

  return null;
}
