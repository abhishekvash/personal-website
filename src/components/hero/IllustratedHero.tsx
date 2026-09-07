import { ClientOnly } from "@tanstack/react-router";
import {
  Component,
  Suspense,
  lazy,
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";
import type { ErrorInfo, ReactNode } from "react";

const StudioScene = lazy(() => import("./StudioScene"));
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

class SceneErrorBoundary extends Component<
  { children: ReactNode; onError: (error: unknown) => void },
  { failed: boolean }
> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error: Error, _info: ErrorInfo) {
    this.props.onError(error);
  }

  render() {
    return this.state.failed ? null : this.props.children;
  }
}

export function IllustratedHero() {
  const id = useId();
  const artworkRef = useRef<HTMLElement>(null);
  const [isInView, setIsInView] = useState(false);
  const [status, setStatus] = useState<"loading" | "ready" | "failed">(
    "loading",
  );
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
  const handleReady = useCallback(() => {
    setStatus((current) => (current === "failed" ? current : "ready"));
  }, []);
  const handleError = useCallback((error: unknown) => {
    console.error(
      "The 3D studio could not render. Showing the original artwork.",
      error,
    );
    setStatus("failed");
  }, []);

  useEffect(() => {
    const artwork = artworkRef.current;
    if (!artwork || !("IntersectionObserver" in window)) return;
    const observer = new IntersectionObserver(([entry]) => {
      setIsInView(entry.isIntersecting);
    });
    observer.observe(artwork);
    return () => observer.disconnect();
  }, []);

  return (
    <main className="studio-page" aria-label="Illustrated creative studio">
      <figure
        ref={artworkRef}
        className="studio-artwork"
        aria-labelledby={`${id}-title`}
        aria-describedby={`${id}-description`}
        data-scene-status={status}
        data-motion={motionPlaying ? "playing" : "paused"}
      >
        <img
          className="studio-reference"
          src="/scene/reference.png"
          width="1536"
          height="1024"
          alt=""
          aria-hidden="true"
          fetchPriority="high"
          decoding="sync"
        />
        {status !== "failed" ? (
          <SceneErrorBoundary onError={handleError}>
            <ClientOnly fallback={null}>
              <Suspense fallback={null}>
                <StudioScene
                  motionPlaying={motionPlaying}
                  onReady={handleReady}
                  onError={handleError}
                />
              </Suspense>
            </ClientOnly>
          </SceneErrorBoundary>
        ) : null}
        <figcaption className="sr-only">
          <span id={`${id}-title`}>A little world of curiosity.</span>{" "}
          <span id={`${id}-description`}>
            A blue and cream, three-storey creative studio beneath an
            observatory. Its open rooms contain a computer desk, a recording
            studio, a workspace and a tiny kitchen. A pink flowering bonsai
            stands beside it on a wooden tabletop against a warm beige
            background, all illustrated in textured risograph inks and
            reconstructed in three dimensions.
          </span>
        </figcaption>
        <span className="sr-only" role="status">
          {status === "failed"
            ? "The interactive scene is unavailable. The original artwork is displayed."
            : ""}
        </span>
      </figure>
    </main>
  );
}
