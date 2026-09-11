import { createFileRoute } from "@tanstack/react-router";

import { IllustratedHero } from "../components/hero/IllustratedHero";

export const Route = createFileRoute("/")({
  component: IllustratedHero,
  head: () => ({
    meta: [{ title: "Abhishek — A little world of curiosity" }],
  }),
});
