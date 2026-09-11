import { StartClient } from "@tanstack/react-start/client";
import { StrictMode } from "react";
import { hydrateRoot } from "react-dom/client";

if (import.meta.env.DEV) {
  import("react-grab");
}

hydrateRoot(
  document,
  <StrictMode>
    <StartClient />
  </StrictMode>,
);
