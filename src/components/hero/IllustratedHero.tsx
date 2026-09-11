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
    <main
      className="grid min-h-svh place-items-center justify-items-end overflow-hidden bg-scene-paper text-scene-ink"
      aria-label="Curiosity house"
    >
      <figure
        className="relative isolate m-0 h-svh w-full overflow-hidden"
        aria-labelledby={`${id}-title`}
        aria-describedby={`${id}-description`}
        data-scene-status={status}
      >
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
        <span
          className={
            status === "failed"
              ? "absolute inset-x-6 top-1/2 text-center text-moonlit-rose"
              : "sr-only"
          }
          role="status"
        >
          {status === "failed"
            ? "The scene could not load. Please refresh to try again."
            : status === "loading"
              ? "Loading the interactive scene."
              : ""}
        </span>
      </figure>
    </main>
  );
}
