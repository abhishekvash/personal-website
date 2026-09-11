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
    <main className="relative grid h-svh grid-rows-[40%_60%] overflow-hidden bg-scene-paper text-scene-ink min-[1025px]:block">
      <header className="pointer-events-none z-10 w-full max-w-[44rem] self-end px-[max(1.5rem,env(safe-area-inset-left))] pb-[clamp(1.5rem,4svh,2.5rem)] min-[1025px]:absolute min-[1025px]:top-1/2 min-[1025px]:left-[7vw] min-[1025px]:w-auto min-[1025px]:max-w-[30rem] min-[1025px]:-translate-y-1/2 min-[1025px]:px-0 min-[1025px]:pb-0">
        <h1 className="font-display text-[clamp(2.625rem,10vw,4.75rem)] leading-[0.9] font-medium tracking-[-0.035em] text-warm-ivory min-[1025px]:text-[clamp(4rem,6vw,5.5rem)]">
          <span className="block">Hi!</span>
          <span className="block whitespace-nowrap">I&apos;m Abhishek :)</span>
        </h1>
        <p className="mt-5 max-w-[29rem] text-base leading-relaxed font-medium text-moonlit-rose sm:mt-7 sm:text-lg">
          I spend my time making things with code, sound, and words, usually
          wherever curiosity takes me.
        </p>
      </header>
      <figure
        className="relative isolate m-0 h-full min-h-0 w-full overflow-hidden min-[1025px]:absolute min-[1025px]:inset-0 min-[1025px]:h-svh"
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
