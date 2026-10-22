import { fileURLToPath, URL } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
  test: {
    environment: "jsdom",
    environmentOptions: { jsdom: { url: "https://testserver/" } }, // forbidden-ok: jsdom test origin, never fetched
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    // Coverage instrumentation in the gate slows rendering-heavy tests well past the 5 s default.
    testTimeout: 20_000,
    // Four workers, not one per core: on a 16-thread laptop with 7 GB RAM, sixteen jsdom
    // workers with coverage pushed it into swap and the pool timed out starting workers.
    maxWorkers: 4,
    include: ["src/**/*.test.{ts,tsx}", "tests/**/*.test.{ts,tsx}"],
    coverage: {
      provider: "v8",
      include: ["src/**/*.{ts,tsx}"],
      exclude: ["src/**/*.test.{ts,tsx}", "src/test/**", "src/main.tsx", "src/vite-env.d.ts"],
      thresholds: { lines: 60, branches: 60, functions: 60, statements: 60 },
    },
  },
});
