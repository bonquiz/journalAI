import { defineConfig } from "vitest/config";
import { svelte } from "@sveltejs/vite-plugin-svelte";
import path from "path";

export default defineConfig({
  plugins: [svelte({ hot: false })],
  resolve: {
    alias: { $lib: path.resolve("./src/lib") },
    conditions: ["browser"],
  },
  test: { environment: "jsdom", include: ["tests/unit/**/*.test.ts"], setupFiles: ["tests/setup.ts"] },
});
