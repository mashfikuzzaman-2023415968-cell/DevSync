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
import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { colors, type ThemeName } from "@/design/tokens";
import {
  buildConstellation,
  positionAt,
  ROTATION_PERIOD_S,
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

function LocalEnvironment() {
  const { gl, scene } = useThree();
  useEffect(() => {
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
    const env = pmrem.fromScene(room, 0.04).texture;
    scene.environment = env;
    return () => {
      scene.environment = null;
      env.dispose();
      pmrem.dispose();
      panel.dispose();
      bright.dispose();
      soft.dispose();
    };
  }, [gl, scene]);
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
  });
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

    const m = mesh.current;
    if (m) {
      for (let i = 0; i < count; i += 1) {
        const p = positionAt(model, i, s.angle, s.snap);
        const inTeam = model.team.includes(i);
        dummy.position.set(p.x, p.y, p.z);
        const scale = inTeam ? 0.085 * (1 + 0.65 * s.snap) : 0.07 * (1 - 0.25 * s.snap);
        dummy.scale.setScalar(scale);
        dummy.updateMatrix();
        m.setMatrixAt(i, dummy.matrix);
        const base = baseColors[i] ?? scratch;
        scratch.copy(base);
        if (!inTeam) scratch.lerp(dim, 0.45 * s.snap);
        m.setColorAt(i, scratch);
      }
      m.instanceMatrix.needsUpdate = true;
      if (m.instanceColor) m.instanceColor.needsUpdate = true;
    }

    const lines = linksRef.current;
    if (lines) {
      model.links.forEach(([a, b], k) => {
        const pa = positionAt(model, a, s.angle, s.snap);
        const pb = positionAt(model, b, s.angle, s.snap);
        linkPositions.set([pa.x, pa.y, pa.z, pb.x, pb.y, pb.z], k * 6);
      });
      const attr = lines.geometry.getAttribute("position") as THREE.BufferAttribute;
      attr.needsUpdate = true;
      (lines.material as THREE.LineBasicMaterial).opacity =
        (theme === "dark" ? 0.34 : 0.26) * (1 - 0.6 * s.snap);
    }

    const teamLines = teamLinksRef.current;
    if (teamLines) {
      TEAM_LINKS.forEach(([a, b], k) => {
        const ia = model.team[a] ?? 0;
        const ib = model.team[b] ?? 0;
        const pa = positionAt(model, ia, s.angle, s.snap);
        const pb = positionAt(model, ib, s.angle, s.snap);
        teamPositions.set([pa.x, pa.y, pa.z, pb.x, pb.y, pb.z], k * 6);
      });
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
          const pa = positionAt(model, link[0], s.angle, s.snap);
          const pb = positionAt(model, link[1], s.angle, s.snap);
          dot.position.set(
            pa.x + (pb.x - pa.x) * t,
            pa.y + (pb.y - pa.y) * t,
            pa.z + (pb.z - pa.z) * t,
          );
          dot.scale.setScalar(s.pulseT <= 1 ? 0.05 : 0);
        }
      }
    }

    if (chipRef.current) chipRef.current.style.opacity = String(Math.max(0, (s.snap - 0.6) / 0.4));

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
  const maxDpr = compact ? 1 : 1.5;
  const running = active && quality !== "frozen";
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
      <LocalEnvironment />
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
