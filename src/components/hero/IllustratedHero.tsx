import { ClientOnly } from "@tanstack/react-router";
import { LazyMotion, MotionConfig, m, useReducedMotion } from "motion/react";
import { Component, Suspense, lazy, useCallback, useId, useState } from "react";
import { SceneLoader } from "./SceneLoader";
import type { ScenePhase } from "./StudioScene";
import type { ErrorInfo, ReactNode } from "react";

export type SceneStatus = "module" | ScenePhase | "ready" | "failed";

const loadMotionFeatures = () =>
  import("./motion-features").then((module) => module.default);

const StudioScene = lazy(async () => {
  performance.mark("scene:module-start");
  const module = await import("./StudioScene");
  performance.mark("scene:module-end");
  performance.measure("scene:module", "scene:module-start", "scene:module-end");
  return module;
});

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
  const reduceMotion = useReducedMotion();
  const [status, setStatus] = useState<SceneStatus>("module");
  const [attempt, setAttempt] = useState(0);
  const handlePhase = useCallback((phase: ScenePhase) => setStatus(phase), []);
  const handleReady = useCallback(() => setStatus("ready"), []);
  const handleError = useCallback((error: unknown) => {
    console.error("The 3D curiosity house could not render.", error);
    setStatus("failed");
  }, []);
  const handleRetry = useCallback(() => {
    setStatus("module");
    setAttempt((value) => value + 1);
  }, []);
  const publicStatus =
    status === "ready" ? "ready" : status === "failed" ? "failed" : "loading";

  return (
    <MotionConfig reducedMotion="user">
      <LazyMotion features={loadMotionFeatures} strict>
        <main
          className="relative grid h-svh grid-rows-[40%_60%] overflow-hidden bg-scene-paper text-scene-ink min-[1025px]:block"
          aria-busy={publicStatus === "loading"}
        >
          <SceneLoader status={status} onRetry={handleRetry} />
          <m.header className="pointer-events-none z-10 w-full max-w-[44rem] self-end px-[max(1.5rem,env(safe-area-inset-left))] pb-[clamp(1.5rem,4svh,2.5rem)] min-[1025px]:absolute min-[1025px]:top-1/2 min-[1025px]:left-[7vw] min-[1025px]:w-auto min-[1025px]:max-w-[30rem] min-[1025px]:-translate-y-1/2 min-[1025px]:px-0 min-[1025px]:pb-0">
            <h1 className="font-display text-[clamp(2.625rem,10vw,4.75rem)] leading-[0.9] font-medium tracking-[-0.035em] text-warm-ivory min-[1025px]:text-[clamp(4rem,6vw,5.5rem)]">
              <m.span
                className="block"
                initial={false}
                animate={{
                  opacity: status === "ready" ? 1 : 0,
                  y: status === "ready" || reduceMotion ? 0 : 6,
                }}
                transition={{
                  duration: reduceMotion ? 0.2 : 0.42,
                  delay: reduceMotion ? 0.08 : 0.34,
                  ease: [0.16, 1, 0.3, 1],
                }}
              >
                Hi!
              </m.span>
              <m.span
                className="block whitespace-nowrap"
                initial={false}
                animate={{
                  opacity: status === "ready" ? 1 : 0,
                  y: status === "ready" || reduceMotion ? 0 : 6,
                }}
                transition={{
                  duration: reduceMotion ? 0.2 : 0.42,
                  delay: reduceMotion ? 0.12 : 0.43,
                  ease: [0.16, 1, 0.3, 1],
                }}
              >
                I&apos;m Abhishek :)
              </m.span>
            </h1>
            <m.p
              className="mt-5 max-w-[29rem] text-base leading-relaxed font-medium text-moonlit-rose sm:mt-7 sm:text-lg"
              initial={false}
              animate={{
                opacity: status === "ready" ? 1 : 0,
                y: status === "ready" || reduceMotion ? 0 : 6,
              }}
              transition={{
                duration: reduceMotion ? 0.2 : 0.42,
                delay: reduceMotion ? 0.16 : 0.52,
                ease: [0.16, 1, 0.3, 1],
              }}
            >
              I spend my time making things with code, sound, and words, usually
              wherever curiosity takes me.
            </m.p>
          </m.header>
          <m.figure
            className="relative isolate m-0 h-full min-h-0 w-full overflow-hidden min-[1025px]:absolute min-[1025px]:inset-0 min-[1025px]:h-svh"
            aria-labelledby={`${id}-title`}
            aria-describedby={`${id}-description`}
            data-scene-status={publicStatus}
            data-scene-phase={status}
            initial={false}
            animate={{
              clipPath:
                status === "ready" || reduceMotion
                  ? "circle(150% at 50% 52%)"
                  : "circle(12% at 50% 52%)",
              opacity: status === "ready" || reduceMotion ? 1 : 0.68,
            }}
            transition={{
              duration: reduceMotion ? 0.18 : 0.9,
              ease: [0.16, 1, 0.3, 1],
            }}
          >
            {status !== "failed" ? (
              <SceneErrorBoundary key={attempt} onError={handleError}>
                <ClientOnly fallback={null}>
                  <Suspense fallback={null}>
                    <StudioScene
                      onReady={handleReady}
                      onError={handleError}
                      onPhase={handlePhase}
                    />
                  </Suspense>
                </ClientOnly>
              </SceneErrorBoundary>
            ) : null}
            <figcaption className="sr-only">
              <span id={`${id}-title`}>A little world of curiosity.</span>{" "}
              <span id={`${id}-description`}>
                A blue and cream three-storey creative house beside a flowering
                cherry tree. Open rooms contain a study, kitchen, recording
                studio, gaming room, and rooftop observatory.
              </span>
            </figcaption>
            <span className="sr-only" role="status" aria-live="polite">
              {status === "failed"
                ? "The interactive scene could not load. Try again."
                : status === "ready"
                  ? "The interactive scene is ready."
                  : "Loading the interactive scene."}
            </span>
          </m.figure>
        </main>
      </LazyMotion>
    </MotionConfig>
  );
}
