/**
 * Pure model of the "talent constellation" (spec §13.12), separate from WebGL so it can be
 * unit-tested: seeded node layout, nearest-neighbour links, the four-node team that snaps to
 * the front (one of them the newcomer) and the per-frame positions.
 */

export interface Vec3 {
  x: number;
  y: number;
  z: number;
}

export interface Constellation {
  nodes: Vec3[];
  /** Index pairs for the faint links. */
  links: [number, number][];
  /** Four node indices; the last one is the newcomer (amber). */
  team: [number, number, number, number];
  /** Accent (indigo) nodes; the rest are teal. */
  accent: Set<number>;
}

/** Mulberry32: tiny deterministic PRNG so the scene (and its stills) never change by chance. */
export function rng(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export const RADIUS = 2.6;

/** Positions on a flattened shell (wider than tall) with a little depth jitter. */
export function buildConstellation(count: number, seed = 20261012): Constellation {
  const rand = rng(seed);
  const nodes: Vec3[] = [];
  const golden = Math.PI * (3 - Math.sqrt(5));
  for (let i = 0; i < count; i += 1) {
    const y = 1 - (i / Math.max(1, count - 1)) * 2;
    const r = Math.sqrt(1 - y * y);
    const theta = golden * i + rand() * 0.6;
    const shell = RADIUS * (0.8 + rand() * 0.24);
    nodes.push({
      x: Math.cos(theta) * r * shell * 1.15,
      y: y * shell * 0.78,
      z: Math.sin(theta) * r * shell,
    });
  }
  const links: [number, number][] = [];
  const seen = new Set<string>();
  nodes.forEach((a, i) => {
    const nearest = nodes
      .map((b, j) => ({ j, d: (a.x - b.x) ** 2 + (a.y - b.y) ** 2 + (a.z - b.z) ** 2 }))
      .filter((n) => n.j !== i)
      .sort((p, q) => p.d - q.d)
      .slice(0, 2);
    for (const n of nearest) {
      const key = i < n.j ? `${String(i)}-${String(n.j)}` : `${String(n.j)}-${String(i)}`;
      if (!seen.has(key)) {
        seen.add(key);
        links.push(i < n.j ? [i, n.j] : [n.j, i]);
      }
    }
  });
  // The team: four nodes spread around the shell, so the "snap" visibly gathers them.
  const step = Math.floor(count / 4);
  const team: [number, number, number, number] = [
    Math.floor(step * 0.5),
    Math.floor(step * 1.5),
    Math.floor(step * 2.5),
    Math.floor(step * 3.5),
  ];
  const accent = new Set<number>();
  for (let i = 0; i < count; i += 1) if (!team.includes(i) && rand() < 0.3) accent.add(i);
  return { nodes, links, team, accent };
}

/** Where the team sits once snapped: a compact diamond in front of the shell. */
export const TEAM_TARGETS: Vec3[] = [
  { x: -0.75, y: 0.35, z: 2.1 },
  { x: 0.75, y: 0.5, z: 2.1 },
  { x: 0.55, y: -0.6, z: 2.25 },
  { x: -0.55, y: -0.5, z: 2.25 },
];

/** Every pair of team members is linked once snapped (6 solid lines). */
export const TEAM_LINKS: [number, number][] = [
  [0, 1],
  [1, 2],
  [2, 3],
  [3, 0],
  [0, 2],
  [1, 3],
];

export function rotateY(p: Vec3, angle: number): Vec3 {
  const c = Math.cos(angle);
  const s = Math.sin(angle);
  return { x: p.x * c + p.z * s, y: p.y, z: -p.x * s + p.z * c };
}

function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t;
}

/** Smooth 0 → 1 (eased like ease.emphasized, never overshooting). */
export function smooth(t: number): number {
  const x = Math.min(1, Math.max(0, t));
  return x * x * (3 - 2 * x);
}

/**
 * Node position at rotation `angle` and snap progress `snap` (0 = constellation,
 * 1 = team formed). Team members move to TEAM_TARGETS; the others drift 12% outward.
 */
export function positionAt(c: Constellation, i: number, angle: number, snap: number): Vec3 {
  const node = c.nodes[i];
  if (!node) return { x: 0, y: 0, z: 0 };
  const base = rotateY(node, angle);
  const k = smooth(snap);
  const slot = c.team.indexOf(i);
  if (slot >= 0) {
    const target = TEAM_TARGETS[slot] ?? base;
    return {
      x: lerp(base.x, target.x, k),
      y: lerp(base.y, target.y, k),
      z: lerp(base.z, target.z, k),
    };
  }
  const spread = 1 + 0.12 * k;
  return { x: base.x * spread, y: base.y * spread, z: base.z * spread - 0.4 * k };
}

/** Scroll and idle drive the snap (spec §13.12): the first 600 px of scrolling, or 6 s without
 * any scrolling; once the visitor has scrolled, only the scroll position counts. */
export const SNAP_SCROLL_PX = 600;
export const IDLE_SNAP_MS = 6000;

export function snapTarget(scrollY: number, idleElapsedMs: number, hasScrolled: boolean): number {
  const fromScroll = Math.min(1, Math.max(0, scrollY / SNAP_SCROLL_PX));
  if (hasScrolled) return fromScroll;
  return Math.max(fromScroll, idleElapsedMs >= IDLE_SNAP_MS ? 1 : 0);
}

/** One rotation in about 60 s (spec §13.12); slowed to a stop as the team forms. */
export const ROTATION_PERIOD_S = 60;
