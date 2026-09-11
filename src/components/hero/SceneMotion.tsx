import { useFrame, useThree } from "@react-three/fiber";
import { useEffect, useRef, useSyncExternalStore } from "react";

const reducedMotionQuery = "(prefers-reduced-motion: reduce)";

function subscribeReducedMotion(notify: () => void) {
  const preference = window.matchMedia(reducedMotionQuery);
  preference.addEventListener("change", notify);
  return () => preference.removeEventListener("change", notify);
}

export function useReducedMotion() {
  return useSyncExternalStore(
    subscribeReducedMotion,
    () => window.matchMedia(reducedMotionQuery).matches,
    () => true,
  );
}

export function SceneMotion({
  animate,
  enabled,
}: {
  animate: (time: number) => void;
  enabled: boolean;
}) {
  const { gl, invalidate } = useThree();
  const elapsed = useRef(0);

  useEffect(() => {
    if (!enabled) return;
    const mobile = window.matchMedia("(max-width: 768px)");
    let visible = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let previous = performance.now();
    const active = () => visible && !document.hidden;
    const interval = () => Math.ceil(1000 / (mobile.matches ? 15 : 24));
    const tick = () => {
      timer = undefined;
      if (!active()) return;
      const now = performance.now();
      elapsed.current += Math.min((now - previous) / 1000, 0.25);
      previous = now;
      invalidate();
      timer = setTimeout(tick, interval());
    };
    const updateSchedule = () => {
      clearTimeout(timer);
      timer = undefined;
      previous = performance.now();
      if (active()) timer = setTimeout(tick, interval());
    };
    const observer = new IntersectionObserver(([entry]) => {
      visible = entry.isIntersecting;
      updateSchedule();
    });
    observer.observe(gl.domElement);
    document.addEventListener("visibilitychange", updateSchedule);
    mobile.addEventListener("change", updateSchedule);
    return () => {
      clearTimeout(timer);
      observer.disconnect();
      document.removeEventListener("visibilitychange", updateSchedule);
      mobile.removeEventListener("change", updateSchedule);
    };
  }, [enabled, gl, invalidate]);

  // Also face steam toward the camera during an orbit while motion is paused.
  // Animation precedes the priority-1 postprocessing pass and never sets React state.
  useFrame(() => animate(elapsed.current));
  return null;
}
