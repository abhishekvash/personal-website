import {
  HeadContent,
  Scripts,
  createRootRouteWithContext,
} from "@tanstack/react-router";
import { TanStackRouterDevtoolsPanel } from "@tanstack/react-router-devtools";
import { TanStackDevtools } from "@tanstack/react-devtools";

import { useSyncExternalStore } from "react";
import TanStackQueryDevtools from "../integrations/tanstack-query/devtools";

import PostHogProvider from "../integrations/posthog/provider";

import appCss from "../styles.css?url";

import type { QueryClient } from "@tanstack/react-query";

const subscribeDevtools = () => () => {};
const showDevtools = () =>
  new URLSearchParams(window.location.search).has("devtools");
const hideDevtoolsOnServer = () => false;

interface MyRouterContext {
  queryClient: QueryClient;
}

export const Route = createRootRouteWithContext<MyRouterContext>()({
  head: () => ({
    meta: [
      {
        charSet: "utf-8",
      },
      {
        name: "viewport",
        content: "width=device-width, initial-scale=1",
      },
      {
        title: "TanStack Start Starter",
      },
    ],
    links: [
      {
        rel: "stylesheet",
        href: appCss,
      },
    ],
  }),
  shellComponent: RootDocument,
});

function RootDocument({ children }: { children: React.ReactNode }) {
  const devtools = useSyncExternalStore(
    subscribeDevtools,
    showDevtools,
    hideDevtoolsOnServer,
  );
  return (
    <html lang="en" className="min-h-full bg-scene-paper scheme-light">
      <head>
        <HeadContent />
      </head>
      <body className="m-0 min-h-svh overflow-x-hidden bg-scene-paper font-sans text-scene-ink antialiased">
        <PostHogProvider>
          {children}
          {import.meta.env.DEV && devtools ? (
            <TanStackDevtools
              config={{
                position: "bottom-right",
              }}
              plugins={[
                {
                  name: "Tanstack Router",
                  render: <TanStackRouterDevtoolsPanel />,
                },
                TanStackQueryDevtools,
              ]}
            />
          ) : null}
        </PostHogProvider>
        <Scripts />
      </body>
    </html>
  );
}
