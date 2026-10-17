/**
 * The slim three entry must export everything React Three Fiber, drei's Html and our scene use;
 * otherwise the 3D hero would fail at runtime in production only (DECISIONS D25).
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import * as slim from "./three-slim";

const root = resolve(__dirname, "../../..");
const read = (p: string) => readFileSync(resolve(root, p), "utf8");

const LIBS = [
  "node_modules/@react-three/fiber/dist/react-three-fiber.esm.js",
  "node_modules/@react-three/fiber/dist/events-776716bd.esm.js",
  "node_modules/@react-three/drei/web/Html.js",
  "node_modules/@react-three/drei/core/PerformanceMonitor.js",
];
const OURS = ["src/components/three/TalentConstellation.tsx"];

function namespaceMembers(src: string): string[] {
  return [...src.matchAll(/THREE\.([A-Za-z_][A-Za-z0-9_]*)/g)].map((m) => m[1] ?? "");
}

function namedImports(src: string): string[] {
  return [...src.matchAll(/import\s*\{([^}]*)\}\s*from\s*['"]three['"]/g)].flatMap((m) =>
    (m[1] ?? "")
      .split(",")
      .map((s) => s.trim().split(/\s+as\s+/)[0] ?? "")
      .filter(Boolean),
  );
}

/** R3F JSX intrinsics (<instancedMesh>, <bufferAttribute>…) resolve to PascalCase THREE classes. */
function jsxElements(src: string): string[] {
  // A JSX tag never directly follows an identifier (that would be a generic like Promise<void>).
  return [...src.matchAll(/(?<![\w.])<([a-z][A-Za-z0-9]*)[\s>/]/g)]
    .map((m) => m[1] ?? "")
    .filter((tag) => !["div", "span", "p", "main", "h1", "a", "button"].includes(tag))
    .map((tag) => tag.charAt(0).toUpperCase() + tag.slice(1));
}

describe("three-slim", () => {
  it("covers every three member the 3D chunk uses", () => {
    const needed = new Set<string>();
    for (const f of LIBS) {
      const src = read(f);
      for (const n of [...namespaceMembers(src), ...namedImports(src)]) needed.add(n);
    }
    for (const f of OURS) {
      const src = read(f);
      for (const n of [...namespaceMembers(src), ...jsxElements(src)]) needed.add(n);
    }
    const exported = new Set(Object.keys(slim));
    const missing = [...needed].filter((n) => !exported.has(n)).sort();
    expect(missing).toEqual([]);
    expect(needed.size).toBeGreaterThan(20);
  });

  it("re-exports working three classes", () => {
    expect(new slim.Color("#0F766E").getHexString()).toBe("0f766e");
    expect(new slim.Vector3(1, 2, 2).length()).toBe(3);
    expect(typeof slim.WebGLRenderer).toBe("function");
  });
});
