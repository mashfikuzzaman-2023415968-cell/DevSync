/**
 * Homepage 3D hero: the "talent constellation" (spec §13.12). Lazily loaded as its own chunk.
 *
 * - ~48 glowing developer nodes in ONE InstancedMesh (icosahedron, 320 faces each) and faint
 *   links in one LineSegments; a soft pulse travels along a link every few seconds.
 * - Rotates once per ~60 s; scrolling the first 600 px (or 6 s idle) snaps four nodes into a
 *   team in front, the newcomer glowing amber, with an HTML chip "✓ Balanced team".
 * - Pointer tilts the scene by at most 6°, damped. Colours come from design/tokens.ts.
 * - Studio lighting: ambient + key light + a locally generated environment of two light
 *   panels (no remote HDR; drei's Environment would pull in HDR/EXR loaders, so the panels
 *   are rendered with PMREMGenerator directly).
 * - PerformanceMonitor: < 50 fps → dpr 1 and no pulse; < 30 fps → stop and keep the frame.
 * - The render loop runs only while `active` (on screen, tab visible); WebGL resources are
 *   released on unmount.
 */
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { Html } from "@react-three/drei/web/Html";
import { PerformanceMonitor } from "@react-three/drei/core/PerformanceMonitor";
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { colors, type ThemeName } from "@/design/tokens";
import {
  buildConstellation,
  positionAt,
  ROTATION_PERIOD_S,
  writePositions,
  snapTarget,
  TEAM_LINKS,
  TEAM_TARGETS,
} from "./model";

export interface SceneProps {
  theme: ThemeName;
  /** Render loop allowed (hero on screen and tab visible). */
  active: boolean;
  /** Fewer nodes and dpr 1 (phones). */
  compact?: boolean;
  /** Fixed snap progress (stills rendering); otherwise scroll/idle drive it. */
  snap?: number;
  /** Fixed rotation angle (stills rendering). */
  angle?: number;
  chipText?: string;
  /** Exact device pixel ratio (stills rendering); otherwise [1, 1.5] with degradation. */
  dpr?: number;
  onReady?: () => void;
  onContextLost?: () => void;
}

declare global {
  interface Window {
    /** Frames rendered by the hero scene (read by the E2E pause test). */
    __dsHeroFrames?: number;
  }
}

const DEG6 = (6 * Math.PI) / 180;
const COMPILE_TIMEOUT_MS = 1500;

/** Each node glows in its own instance colour (teal, indigo or the newcomer's amber) instead
 * of one shared emissive colour. */
function glowInOwnColour(shader: { fragmentShader: string }) {
  shader.fragmentShader = shader.fragmentShader.replace(
    "vec3 totalEmissiveRadiance = emissive;",
    [
      "vec3 totalEmissiveRadiance = emissive;",
      "#if defined( USE_COLOR ) || defined( USE_COLOR_ALPHA )",
      "  totalEmissiveRadiance *= vColor.rgb;",
      "#endif",
    ].join("\n"),
  );
}

/**
 * Builds the small local environment, then compiles every shader asynchronously before the
 * first frame (KHR_parallel_shader_compile where available), so starting the scene never
 * blocks the main thread in one long task.
 */
function LocalEnvironment({ onWarm }: { onWarm: () => void }) {
  const { gl, scene, camera } = useThree();
  const warm = useRef(onWarm);
  warm.current = onWarm;
  useEffect(() => {
    let cancelled = false;
    const pmrem = new THREE.PMREMGenerator(gl);
    const room = new THREE.Scene();
    const panel = new THREE.PlaneGeometry(1, 1);
    const bright = new THREE.MeshBasicMaterial({
      color: new THREE.Color(2.2, 2.2, 2.2),
      side: THREE.DoubleSide,
    });
    const soft = new THREE.MeshBasicMaterial({
      color: new THREE.Color(0.9, 1, 1),
      side: THREE.DoubleSide,
    });
    const key = new THREE.Mesh(panel, bright);
    key.position.set(-3, 3, 4);
    key.scale.set(6, 3, 1);
    key.lookAt(0, 0, 0);
    const rim = new THREE.Mesh(panel, soft);
    rim.position.set(4, -1, -3);
    rim.scale.set(4, 6, 1);
    rim.lookAt(0, 0, 0);
    room.add(key, rim);
    // Soft studio light only needs a tiny map (32 px faces instead of the default 256).
    const env = pmrem.fromScene(room, 0, 0.1, 100, { size: 32 }).texture;
    scene.environment = env;
    // Some drivers never report parallel compilation as finished; start anyway after a moment
    // (shaders then compile on first use, as without compileAsync).
    const giveUp = new Promise<void>((resolve) => setTimeout(resolve, COMPILE_TIMEOUT_MS));
    void Promise.race([gl.compileAsync(scene, camera).catch(() => undefined), giveUp]).then(() => {
      if (!cancelled) warm.current();
    });
    return () => {
      cancelled = true;
      scene.environment = null;
      env.dispose();
      pmrem.dispose();
      panel.dispose();
      bright.dispose();
      soft.dispose();
    };
  }, [gl, scene, camera]);
  return null;
}

function Constellation({
  theme,
  compact,
  snap: fixedSnap,
  angle: fixedAngle,
  pulse,
  chipText,
  onFirstFrame,
}: {
  theme: ThemeName;
  compact: boolean;
  snap: number | undefined;
  angle: number | undefined;
  pulse: boolean;
  chipText: string;
  onFirstFrame: () => void;
}) {
  const palette = colors[theme];
  const model = useMemo(() => buildConstellation(compact ? 24 : 48), [compact]);
  const count = model.nodes.length;
  const group = useRef<THREE.Group>(null);
  const mesh = useRef<THREE.InstancedMesh>(null);
  const linksRef = useRef<THREE.LineSegments>(null);
  const teamLinksRef = useRef<THREE.LineSegments>(null);
  const pulseRef = useRef<THREE.Mesh>(null);
  const chipRef = useRef<HTMLDivElement>(null);
  const state = useRef({
    angle: fixedAngle ?? 0,
    snap: fixedSnap ?? 0,
    start: performance.now(),
    scrolled: false,
    pointer: new THREE.Vector2(),
    pulseLink: 0,
    pulseT: 0,
    first: true,
    colourSnap: -1,
    chipOpacity: -1,
  });
  const positions = useMemo(() => new Float32Array(model.nodes.length * 3), [model]);
  const teamSet = useMemo(() => new Set<number>(model.team), [model]);
  const dummy = useMemo(() => new THREE.Object3D(), []);

  const linkPositions = useMemo(() => new Float32Array(model.links.length * 6), [model]);
  const teamPositions = useMemo(() => new Float32Array(TEAM_LINKS.length * 6), []);

  const baseColors = useMemo(() => {
    const teal = new THREE.Color(palette.primary);
    const indigo = new THREE.Color(palette.accent);
    const amber = new THREE.Color(theme === "dark" ? palette.newcomer : "#F59E0B");
    return model.nodes.map((_, i) => {
      if (i === model.team[3]) return amber;
      return model.accent.has(i) ? indigo : teal;
    });
  }, [model, palette, theme]);
  const dim = useMemo(() => new THREE.Color(palette.bg), [palette.bg]);
  const scratch = useMemo(() => new THREE.Color(), []);

  // Instance colours and positions exist before the shaders are compiled, so the material is
  // compiled once, with per-instance colour, instead of again on the first frame.
  useLayoutEffect(() => {
    const m = mesh.current;
    if (!m) return;
    for (let i = 0; i < count; i += 1) {
      const p = positionAt(model, i, state.current.angle, state.current.snap);
      dummy.position.set(p.x, p.y, p.z);
      dummy.scale.setScalar(0.07);
      dummy.updateMatrix();
      m.setMatrixAt(i, dummy.matrix);
      m.setColorAt(i, baseColors[i] ?? scratch);
    }
    m.instanceMatrix.needsUpdate = true;
    if (m.instanceColor) m.instanceColor.needsUpdate = true;
  }, [model, count, baseColors, dummy, scratch]);

  useEffect(() => {
    const onScroll = () => {
      state.current.scrolled = true;
    };
    const onPointer = (e: PointerEvent) => {
      state.current.pointer.set(
        (e.clientX / window.innerWidth) * 2 - 1,
        (e.clientY / window.innerHeight) * 2 - 1,
      );
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("pointermove", onPointer, { passive: true });
    return () => {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("pointermove", onPointer);
    };
  }, []);

  useFrame((_, delta) => {
    const s = state.current;
    const dt = Math.min(delta, 0.05);
    const target = fixedSnap ?? snapTarget(window.scrollY, performance.now() - s.start, s.scrolled);
    s.snap += (target - s.snap) * Math.min(1, dt * 3.2);
    if (fixedAngle === undefined)
      s.angle += ((dt * Math.PI * 2) / ROTATION_PERIOD_S) * (1 - s.snap * 0.85);
    else s.angle = fixedAngle;

    if (group.current && fixedSnap === undefined) {
      const g = group.current;
      g.rotation.x += (s.pointer.y * DEG6 - g.rotation.x) * Math.min(1, dt * 2);
      g.rotation.y += (s.pointer.x * DEG6 - g.rotation.y) * Math.min(1, dt * 2);
    }

    // One allocation-free pass computes every node position; links and the pulse read it.
    writePositions(model, s.angle, s.snap, positions);
    const colourChanged = Math.abs(s.snap - s.colourSnap) > 0.002 || s.first;
    const m = mesh.current;
    if (m) {
      for (let i = 0; i < count; i += 1) {
        const o = i * 3;
        const inTeam = teamSet.has(i);
        dummy.position.set(positions[o] ?? 0, positions[o + 1] ?? 0, positions[o + 2] ?? 0);
        dummy.scale.setScalar(inTeam ? 0.085 * (1 + 0.65 * s.snap) : 0.07 * (1 - 0.25 * s.snap));
        dummy.updateMatrix();
        m.setMatrixAt(i, dummy.matrix);
        if (colourChanged) {
          scratch.copy(baseColors[i] ?? scratch);
          if (!inTeam) scratch.lerp(dim, 0.45 * s.snap);
          m.setColorAt(i, scratch);
        }
      }
      m.instanceMatrix.needsUpdate = true;
      if (colourChanged && m.instanceColor) {
        m.instanceColor.needsUpdate = true;
        s.colourSnap = s.snap;
      }
    }

    const copyLink = (target: Float32Array, k: number, a: number, b: number) => {
      const o = k * 6;
      target[o] = positions[a * 3] ?? 0;
      target[o + 1] = positions[a * 3 + 1] ?? 0;
      target[o + 2] = positions[a * 3 + 2] ?? 0;
      target[o + 3] = positions[b * 3] ?? 0;
      target[o + 4] = positions[b * 3 + 1] ?? 0;
      target[o + 5] = positions[b * 3 + 2] ?? 0;
    };

    const lines = linksRef.current;
    if (lines) {
      for (let k = 0; k < model.links.length; k += 1) {
        const link = model.links[k];
        if (link) copyLink(linkPositions, k, link[0], link[1]);
      }
      (lines.geometry.getAttribute("position") as THREE.BufferAttribute).needsUpdate = true;
      (lines.material as THREE.LineBasicMaterial).opacity =
        (theme === "dark" ? 0.34 : 0.26) * (1 - 0.6 * s.snap);
    }

    const teamLines = teamLinksRef.current;
    if (teamLines) {
      for (let k = 0; k < TEAM_LINKS.length; k += 1) {
        const pair = TEAM_LINKS[k];
        if (pair) copyLink(teamPositions, k, model.team[pair[0]] ?? 0, model.team[pair[1]] ?? 0);
      }
      (teamLines.geometry.getAttribute("position") as THREE.BufferAttribute).needsUpdate = true;
      (teamLines.material as THREE.LineBasicMaterial).opacity =
        Math.max(0, (s.snap - 0.35) / 0.65) * 0.9;
    }

    const dot = pulseRef.current;
    if (dot) {
      dot.visible = pulse && s.snap < 0.5;
      if (dot.visible) {
        s.pulseT += dt / 1.6;
        if (s.pulseT >= 1.8) {
          s.pulseT = 0;
          s.pulseLink = (s.pulseLink + 7) % model.links.length;
        }
        const link = model.links[s.pulseLink];
        const t = Math.min(1, s.pulseT);
        if (link) {
          const a = link[0] * 3;
          const b = link[1] * 3;
          const ax = positions[a] ?? 0;
          const ay = positions[a + 1] ?? 0;
          const az = positions[a + 2] ?? 0;
          dot.position.set(
            ax + ((positions[b] ?? 0) - ax) * t,
            ay + ((positions[b + 1] ?? 0) - ay) * t,
            az + ((positions[b + 2] ?? 0) - az) * t,
          );
          dot.scale.setScalar(s.pulseT <= 1 ? 0.05 : 0);
        }
      }
    }

    const chipOpacity = Math.round(Math.max(0, (s.snap - 0.6) / 0.4) * 100) / 100;
    if (chipRef.current && chipOpacity !== s.chipOpacity) {
      chipRef.current.style.opacity = String(chipOpacity);
      s.chipOpacity = chipOpacity;
    }

    window.__dsHeroFrames = (window.__dsHeroFrames ?? 0) + 1;
    if (s.first) {
      s.first = false;
      onFirstFrame();
    }
  });

  // The chip floats just above the snapped team.
  const chipAnchor: [number, number, number] = [0, (TEAM_TARGETS[1]?.y ?? 0.5) + 0.5, 2.2];

  return (
    <group ref={group}>
      <instancedMesh ref={mesh} args={[undefined, undefined, count]} frustumCulled={false}>
        <icosahedronGeometry args={[1, 2]} />
        <meshStandardMaterial
          roughness={0.35}
          metalness={0.1}
          emissive="#ffffff"
          emissiveIntensity={theme === "dark" ? 0.5 : 0.22}
          envMapIntensity={0.9}
          onBeforeCompile={glowInOwnColour}
        />
      </instancedMesh>
      <lineSegments ref={linksRef} frustumCulled={false}>
        <bufferGeometry>
          <bufferAttribute attach="attributes-position" args={[linkPositions, 3]} />
        </bufferGeometry>
        <lineBasicMaterial color={palette.textSubtle} transparent depthWrite={false} />
      </lineSegments>
      <lineSegments ref={teamLinksRef} frustumCulled={false}>
        <bufferGeometry>
          <bufferAttribute attach="attributes-position" args={[teamPositions, 3]} />
        </bufferGeometry>
        <lineBasicMaterial color={palette.primary} transparent opacity={0} depthWrite={false} />
      </lineSegments>
      <mesh ref={pulseRef} visible={false}>
        <icosahedronGeometry args={[1, 1]} />
        <meshBasicMaterial
          color={palette.primarySoft}
          transparent
          opacity={0.9}
          blending={THREE.AdditiveBlending}
        />
      </mesh>
      <Html position={chipAnchor} center zIndexRange={[10, 0]} pointerEvents="none">
        <div
          ref={chipRef}
          aria-hidden="true"
          data-hero-chip=""
          className="whitespace-nowrap rounded-full border border-border bg-surface/90 px-3 py-1.5 text-caption font-semibold text-text shadow-md backdrop-blur"
          style={{ opacity: fixedSnap ?? 0 }}
        >
          <span className="text-success">✓</span> {chipText}
        </div>
      </Html>
    </group>
  );
}

function ContextWatcher({ onLost }: { onLost: () => void }) {
  const gl = useThree((s) => s.gl);
  const callback = useRef(onLost);
  callback.current = onLost;
  useEffect(() => {
    const canvas = gl.domElement;
    const lost = (e: Event) => {
      e.preventDefault();
      callback.current();
    };
    canvas.addEventListener("webglcontextlost", lost);
    return () => {
      canvas.removeEventListener("webglcontextlost", lost);
      gl.dispose();
      gl.forceContextLoss();
    };
  }, [gl]);
  return null;
}

export default function TalentConstellation({
  theme,
  active,
  compact = false,
  snap,
  angle,
  chipText = "Balanced team",
  dpr: fixedDpr,
  onReady,
  onContextLost,
}: SceneProps) {
  const [quality, setQuality] = useState<"high" | "low" | "frozen">("high");
  const [warm, setWarm] = useState(false);
  const maxDpr = compact ? 1 : 1.5;
  const running = warm && active && quality !== "frozen";
  return (
    <Canvas
      dpr={fixedDpr ?? (quality === "high" ? [1, maxDpr] : 1)}
      gl={{
        antialias: true,
        alpha: true,
        powerPreference: "high-performance",
        preserveDrawingBuffer: snap !== undefined,
      }}
      camera={{ position: [0, 0, 8.6], fov: 40 }}
      frameloop={running ? "always" : "never"}
      aria-hidden="true"
      tabIndex={-1}
      className="!pointer-events-none"
    >
      <ambientLight intensity={theme === "dark" ? 0.35 : 0.55} />
      <directionalLight position={[-4, 5, 6]} intensity={theme === "dark" ? 1.1 : 1.35} />
      <LocalEnvironment
        onWarm={() => {
          setWarm(true);
        }}
      />
      <PerformanceMonitor
        bounds={() => [30, 50]}
        flipflops={2}
        onDecline={({ fps }) => {
          setQuality(fps < 30 ? "frozen" : "low");
        }}
        onFallback={() => {
          setQuality("frozen");
        }}
      />
      <Constellation
        theme={theme}
        compact={compact}
        snap={snap}
        angle={angle}
        pulse={quality === "high"}
        chipText={chipText}
        onFirstFrame={() => onReady?.()}
      />
      <ContextWatcher onLost={() => onContextLost?.()} />
    </Canvas>
  );
}
