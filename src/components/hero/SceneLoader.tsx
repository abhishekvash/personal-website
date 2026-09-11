import { LazyMotion, MotionConfig, m, useReducedMotion } from "motion/react";
import { useState } from "react";

import type { SceneStatus } from "./IllustratedHero";

const loadMotionFeatures = () =>
  import("./motion-features").then((module) => module.default);

const windows = [0, 1, 2, 3, 4, 5];

function TinyHouse({ active }: { active: boolean }) {
  return (
    <div className="relative h-20 w-16" aria-hidden="true">
      <div className="absolute top-1 left-1/2 size-10 -translate-x-1/2 rotate-45 rounded-tl-[0.8rem] border-t-2 border-l-2 border-warm-ivory/70" />
      <div className="absolute inset-x-0 bottom-0 grid h-16 grid-cols-2 grid-rows-3 gap-1.5 rounded-[0.9rem] border-2 border-warm-ivory/70 bg-midnight-paper p-2.5 shadow-[0_10px_28px_rgba(239,92,136,0.14)]">
        {windows.map((window, index) => (
          <m.span
            key={window}
            className="rounded-[0.22rem] bg-blossom-pink"
            initial={false}
            animate={
              active
                ? {
                    backgroundColor: ["#702342", "#ffb080", "#702342"],
                    boxShadow: [
                      "0 0 0 rgba(255,176,128,0)",
                      "0 0 12px rgba(255,176,128,0.72)",
                      "0 0 0 rgba(255,176,128,0)",
                    ],
                    opacity: [0.42, 1, 0.42],
                  }
                : { opacity: 0.42 }
            }
            transition={{
              duration: 2.8,
              delay: index * 0.28,
              ease: "easeInOut",
              repeat: Infinity,
            }}
          />
        ))}
      </div>
    </div>
  );
}

export function SceneLoader({
  status,
  onRetry,
}: {
  status: SceneStatus;
  onRetry: () => void;
}) {
  const [mounted, setMounted] = useState(true);
  const reduceMotion = useReducedMotion();
  const ready = status === "ready";
  const failed = status === "failed";

  if (!mounted) return null;

  return (
    <MotionConfig reducedMotion="user">
      <LazyMotion features={loadMotionFeatures} strict>
        <m.div
          className="fixed inset-0 z-50 grid place-items-center bg-midnight-paper px-6 text-center"
          initial={false}
          animate={{ opacity: ready ? 0 : 1 }}
          transition={{
            duration: reduceMotion ? 0 : 0.38,
            ease: [0.22, 1, 0.36, 1],
          }}
          onAnimationComplete={() => {
            if (ready) setMounted(false);
          }}
        >
          <div className="flex flex-col items-center gap-5">
            <TinyHouse active={!ready && !failed && !reduceMotion} />
            <p className="text-sm font-medium tracking-[0.01em] text-moonlit-rose">
              {failed ? "The house couldn’t wake up." : "Waking the house…"}
            </p>
            {failed ? (
              <button
                className="text-sm font-semibold text-warm-ivory underline decoration-blossom-pink/80 underline-offset-4 transition-colors hover:text-sunlight-peach focus-visible:rounded-sm focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-electric-cyan"
                type="button"
                onClick={onRetry}
              >
                Try again
              </button>
            ) : null}
          </div>
        </m.div>
      </LazyMotion>
    </MotionConfig>
  );
}
