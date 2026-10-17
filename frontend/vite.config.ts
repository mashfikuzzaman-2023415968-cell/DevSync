/**
 * Vite build for a strict-CSP SPA (spec §14.3, §14.18):
 * - no inline scripts/styles in index.html; CSS is emitted as files;
 * - assets are never inlined as data: URIs (fonts must come from 'self');
 * - source maps are generated "hidden" and never served (deleted in the image);
 * - console.* calls are stripped from production bundles.
 */
import { fileURLToPath, URL } from "node:url";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig(({ mode }) => ({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: [
      { find: "@", replacement: fileURLToPath(new URL("./src", import.meta.url)) },
      // Tree-shakeable three for the 3D chunk (DECISIONS D25); only the bare specifier.
      ...(mode === "production"
        ? [
            {
              find: /^three$/,
              replacement: fileURLToPath(
                new URL("./src/components/three/three-slim.ts", import.meta.url),
              ),
            },
          ]
        : []),
    ],
  },
  build: {
    target: "es2022",
    sourcemap: "hidden",
    // dist/.vite/manifest.json lets the gate check per-chunk budgets; removed from the image.
    manifest: true,
    assetsInlineLimit: 0,
    cssCodeSplit: true,
    modulePreload: { polyfill: false },
    reportCompressedSize: true,
  },
  esbuild: mode === "production" ? { drop: ["console", "debugger"] } : {},
  server: { port: 5173, strictPort: true },
}));
