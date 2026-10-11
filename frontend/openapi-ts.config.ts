import path from "node:path";

import { defineConfig } from "@hey-api/openapi-ts";

// The drift check in the root Makefile sets OPENAPI_TS_OUTPUT to a
// temporary directory. The runtime config import stays `../api-config.ts`.
const output = process.env.OPENAPI_TS_OUTPUT ?? "src/lib/api";

export default defineConfig({
  input: "openapi.json",
  output,
  plugins: [
    {
      name: "@hey-api/client-fetch",
      baseUrl: false,
      runtimeConfigPath: path.resolve(output, "..", "api-config.ts"),
    },
    "@tanstack/react-query",
    // Request schemas for form validation, from the same spec as the API.
    "zod",
  ],
});
