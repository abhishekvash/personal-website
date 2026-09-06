//  @ts-check

import { tanstackConfig } from "@tanstack/eslint-config";

export default [
  ...tanstackConfig,
  {
    files: ["**/*.{js,ts,tsx}"],
    rules: {
      "import/no-cycle": "off",
      "import/order": "error",
      "sort-imports": "error",
      "@typescript-eslint/array-type": "off",
      "@typescript-eslint/require-await": "off",
      "pnpm/json-enforce-catalog": "off",
    },
  },
  {
    ignores: ["eslint.config.js", "prettier.config.js"],
  },
];
