import path from "node:path";

import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { loadEnv } from "vite";
import { defineConfig } from "vitest/config";

function isAbsoluteHttpUrl(value: string): boolean {
  if (!URL.canParse(value)) {
    return false;
  }
  const { protocol } = new URL(value);
  return protocol === "http:" || protocol === "https:";
}

export default defineConfig(({ command, mode }) => {
  if (command === "build") {
    const env = loadEnv(mode, import.meta.dirname);
    const apiUrl = env.VITE_API_URL ?? "";
    if (!isAbsoluteHttpUrl(apiUrl)) {
      throw new Error("VITE_API_URL is not set");
    }
    if (!(env.VITE_CLERK_PUBLISHABLE_KEY ?? "").startsWith("pk_")) {
      throw new Error("VITE_CLERK_PUBLISHABLE_KEY is not set");
    }
  }

  return {
    plugins: [react(), tailwindcss()],
    resolve: {
      alias: {
        "@": path.resolve(import.meta.dirname, "./src"),
      },
    },
    server: {
      port: 5173,
      strictPort: true,
    },
    test: {
      environment: "jsdom",
      setupFiles: ["src/testing/setup.ts"],
      env: {
        VITE_API_URL: "http://localhost:8000",
        // Tests mock @clerk/react. This value never reaches Clerk.
        VITE_CLERK_PUBLISHABLE_KEY:
          "pk_test_ZXhhbXBsZS5jbGVyay5hY2NvdW50cy5kZXYk",
      },
    },
  };
});
