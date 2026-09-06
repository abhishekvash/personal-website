import { useEffect, useRef, useState, useSyncExternalStore } from "react";

import { StudioScene } from "./StudioScene";

const reducedMotionQuery = "(prefers-reduced-motion: reduce)";
const serverReducedMotion = () => true;
const serverVisibility = () => false;
const getReducedMotion = () => window.matchMedia(reducedMotionQuery).matches;
const getVisibility = () => document.visibilityState === "visible";

function subscribeReducedMotion(onChange: () => void) {
  const query = window.matchMedia(reducedMotionQuery);
  query.addEventListener("change", onChange);
  return () => query.removeEventListener("change", onChange);
}

function subscribeVisibility(onChange: () => void) {
  document.addEventListener("visibilitychange", onChange);
  return () => document.removeEventListener("visibilitychange", onChange);
}

export function IllustratedHero() {
  const artworkRef = useRef<HTMLElement>(null);
  const [isInView, setIsInView] = useState(false);
  const reducedMotion = useSyncExternalStore(
    subscribeReducedMotion,
    getReducedMotion,
    serverReducedMotion,
  );
  const isVisible = useSyncExternalStore(
    subscribeVisibility,
    getVisibility,
    serverVisibility,
  );
  const motionPlaying = isInView && isVisible && !reducedMotion;

  useEffect(() => {
    const artwork = artworkRef.current;
    if (!artwork) return;
    // Stay static when visibility observation is unavailable.
    if (!("IntersectionObserver" in window)) return;
    const observer = new IntersectionObserver(([entry]) => {
      setIsInView(entry.isIntersecting);
    });
    observer.observe(artwork);
    return () => observer.disconnect();
  }, []);

  return (
    <main
      className="group/hero grid min-h-svh grid-cols-1 items-start bg-scene-paper pb-20 text-scene-ink lg:grid-cols-2"
      aria-label="Illustrated creative studio"
      data-motion={motionPlaying ? "playing" : "paused"}
    >
      <figure
        ref={artworkRef}
        className="relative col-span-full m-0 w-full min-w-0 lg:w-3/4 lg:justify-self-end"
      >
        <StudioScene />
      </figure>
    </main>
  );
}
