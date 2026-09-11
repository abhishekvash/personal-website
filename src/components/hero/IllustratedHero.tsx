import { ClientOnly } from "@tanstack/react-router";
import { Component, Suspense, lazy, useCallback, useId, useState } from "react";
import type { ErrorInfo, ReactNode } from "react";

const StudioScene = lazy(() => import("./StudioScene"));

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
  const [status, setStatus] = useState<"loading" | "ready" | "failed">(
    "loading",
  );
  const handleReady = useCallback(() => setStatus("ready"), []);
  const handleError = useCallback((error: unknown) => {
    console.error("The 3D curiosity house could not render.", error);
    setStatus("failed");
  }, []);

  return (
    <main className="studio-page" aria-label="Curiosity house">
      <figure
        className="studio-artwork"
        aria-labelledby={`${id}-title`}
        aria-describedby={`${id}-description`}
        data-scene-status={status}
      >
        <img
          className="studio-reference"
          src="/scene/curiosity-house-preview.jpg"
          width="2000"
          height="1710"
          alt=""
          aria-hidden="true"
          fetchPriority="high"
          decoding="async"
        />
        {status !== "failed" ? (
          <SceneErrorBoundary onError={handleError}>
            <ClientOnly fallback={null}>
              <Suspense fallback={null}>
                <StudioScene onReady={handleReady} onError={handleError} />
              </Suspense>
            </ClientOnly>
          </SceneErrorBoundary>
        ) : null}
        <figcaption className="sr-only">
          <span id={`${id}-title`}>A little world of curiosity.</span>{" "}
          <span id={`${id}-description`}>
            A blue and cream three-storey creative house beside a flowering
            cherry tree. Open rooms contain a study, kitchen, recording studio,
            gaming room, and rooftop observatory.
          </span>
        </figcaption>
        <span className="sr-only" role="status">
          {status === "failed"
            ? "The interactive scene is unavailable. A rendered preview is displayed."
            : ""}
        </span>
      </figure>
    </main>
  );
}
