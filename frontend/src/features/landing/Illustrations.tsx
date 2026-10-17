/**
 * "How it works" illustrations (spec §13.11 #4), SVG in the node-and-line family, each animating
 * once: Gantt bars grow and the critical path turns rose; dots converge into a team; Kanban cards
 * slide; an escrow badge goes Funded → Paid with a drawn check; a reputation radar expands.
 * Values come from the seed sample (content/sample.ts). Reduced motion shows the final state.
 */
import { motion } from "framer-motion";
import { duration, ease, instant } from "@/design/motion";
import { useReducedMotion } from "@/design/preferences";
import { orderingSystem, reputationSample } from "@/content/sample";

function useTiming() {
  const reduced = useReducedMotion();
  return (delay = 0, length: number = duration.slow) =>
    reduced ? instant : { duration: length, delay, ease: ease.emphasized };
}

export function PlanIllustration() {
  const t = useTiming();
  const total = orderingSystem.cpm.durationDays;
  const critical = new Set<string>(orderingSystem.cpm.critical);
  const width = 300;
  return (
    <svg
      viewBox="0 0 380 230"
      className="h-auto w-full"
      role="img"
      aria-label="Gantt chart of the sample project: the critical path is highlighted and Frontend has 4 days of slack."
    >
      {orderingSystem.milestones.map((m, i) => {
        const s = orderingSystem.cpm.schedule[m.id] ?? { es: 0, ef: 0, slack: 0 };
        const x = 70 + (s.es / total) * width;
        const w = ((s.ef - s.es) / total) * width;
        const y = 18 + i * 34;
        const isCritical = critical.has(m.id);
        return (
          <g key={m.id}>
            <text x="0" y={y + 14} className="fill-text-muted text-[11px]">
              {m.name.split(" ")[0]}
            </text>
            <motion.rect
              x={x}
              y={y}
              height="20"
              rx="5"
              initial={{ width: 0 }}
              animate={{ width: w }}
              transition={t(i * 0.04)}
              className="fill-primary"
            />
            {isCritical ? (
              <motion.rect
                x={x}
                y={y}
                width={w}
                height="20"
                rx="5"
                className="fill-danger"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={t(0.6 + i * 0.05)}
              />
            ) : (
              <motion.rect
                x={x + w}
                y={y + 7}
                height="6"
                rx="3"
                className="fill-border"
                initial={{ width: 0 }}
                animate={{ width: (s.slack / total) * width }}
                transition={t(0.7)}
              />
            )}
          </g>
        );
      })}
      <text x="70" y="226" className="fill-text-muted text-[11px]">
        {`${String(total)} days; the critical path is in rose`}
      </text>
    </svg>
  );
}

const SCATTER: [number, number][] = [
  [40, 40],
  [120, 30],
  [210, 52],
  [300, 34],
  [340, 110],
  [290, 190],
  [190, 200],
  [80, 180],
  [30, 120],
  [150, 120],
  [250, 130],
  [100, 90],
];
const TEAM_AT: [number, number][] = [
  [160, 95],
  [220, 95],
  [220, 150],
  [160, 150],
];
const TEAM_FROM = [1, 4, 6, 8];

export function TeamIllustration() {
  const t = useTiming();
  return (
    <svg
      viewBox="0 0 380 230"
      className="h-auto w-full"
      role="img"
      aria-label="Many developers; four of them move together into a balanced team, one a newcomer."
    >
      {SCATTER.map(([x, y], i) =>
        TEAM_FROM.includes(i) ? null : (
          <motion.circle
            key={`s${String(i)}`}
            cx={x}
            cy={y}
            r="6"
            className={i % 3 ? "fill-primary/35" : "fill-accent/35"}
            initial={{ opacity: 1 }}
            animate={{ opacity: 0.55 }}
            transition={t(0.4)}
          />
        ),
      )}
      <motion.path
        d="M160 95 220 95 220 150 160 150Z M160 95 220 150 M220 95 160 150"
        fill="none"
        className="stroke-primary"
        strokeWidth="2"
        initial={{ pathLength: 0, opacity: 0 }}
        animate={{ pathLength: 1, opacity: 1 }}
        transition={t(0.65, 0.5)}
      />
      {TEAM_FROM.map((from, slot) => {
        const [fx, fy] = SCATTER[from] ?? [0, 0];
        const [tx, ty] = TEAM_AT[slot] ?? [0, 0];
        return (
          <motion.circle
            key={`t${String(slot)}`}
            className={slot === 3 ? "fill-newcomer" : "fill-primary"}
            // Framer Motion owns every animated circle attribute, the radius included.
            initial={{ cx: fx, cy: fy, r: 10 }}
            animate={{ cx: tx, cy: ty, r: 10 }}
            transition={t(0.1 + slot * 0.06, 0.6)}
          />
        );
      })}
      <text x="160" y="185" className="fill-text-muted text-[11px]">
        One newcomer included
      </text>
    </svg>
  );
}

export function WorkIllustration() {
  const t = useTiming();
  const columns = ["To do", "In progress", "Done"];
  return (
    <svg
      viewBox="0 0 380 230"
      className="h-auto w-full"
      role="img"
      aria-label="A task board: a card moves from In progress to Done."
    >
      {columns.map((c, i) => (
        <g key={c}>
          <rect
            x={10 + i * 124}
            y="10"
            width="114"
            height="210"
            rx="10"
            className="fill-surface-2"
          />
          <text x={22 + i * 124} y="32" className="fill-text-muted text-[11px] font-medium">
            {c}
          </text>
        </g>
      ))}
      {[0, 1].map((k) => (
        <rect
          key={`todo${String(k)}`}
          x="20"
          y={46 + k * 50}
          width="94"
          height="40"
          rx="7"
          className="fill-surface stroke-border"
        />
      ))}
      <rect x="144" y="46" width="94" height="40" rx="7" className="fill-surface stroke-border" />
      <rect x="268" y="46" width="94" height="40" rx="7" className="fill-surface stroke-border" />
      <motion.g initial={{ x: 0 }} animate={{ x: 124 }} transition={t(0.3, 0.6)}>
        <rect
          x="144"
          y="96"
          width="94"
          height="40"
          rx="7"
          className="fill-surface stroke-primary"
          strokeWidth="1.5"
        />
        <rect x="154" y="108" width="50" height="6" rx="3" className="fill-text-subtle/50" />
        <circle cx="222" cy="124" r="6" className="fill-primary" />
      </motion.g>
    </svg>
  );
}

export function PayIllustration() {
  const t = useTiming();
  return (
    <svg
      viewBox="0 0 380 230"
      className="h-auto w-full"
      role="img"
      aria-label="Escrow for a milestone goes from Funded to Paid once the client approves."
    >
      <rect x="60" y="50" width="260" height="130" rx="14" className="fill-surface stroke-border" />
      <text x="84" y="86" className="fill-text text-[14px] font-semibold">
        Milestone 2: Database
      </text>
      <motion.g initial={{ opacity: 1 }} animate={{ opacity: 0 }} transition={t(0.5)}>
        <rect x="84" y="108" width="84" height="26" rx="13" className="fill-info-bg" />
        <text x="100" y="125" className="fill-info text-[12px] font-medium">
          Funded
        </text>
      </motion.g>
      <motion.g initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={t(0.6)}>
        <rect x="84" y="108" width="84" height="26" rx="13" className="fill-success-bg" />
        <text x="106" y="125" className="fill-success text-[12px] font-medium">
          Paid
        </text>
      </motion.g>
      <circle cx="268" cy="121" r="24" className="fill-success-bg" />
      <motion.path
        d="M256 121 265 130 281 112"
        fill="none"
        className="stroke-success"
        strokeWidth="4"
        strokeLinecap="round"
        strokeLinejoin="round"
        initial={{ pathLength: 0 }}
        animate={{ pathLength: 1 }}
        transition={t(0.75, 0.3)}
      />
    </svg>
  );
}

const AXES = [
  "expertise",
  "communication",
  "teamwork",
  "quality",
  "diversity",
  "punctuality",
] as const;

export function LearnIllustration() {
  const t = useTiming();
  const dev = reputationSample[0];
  const cx = 190;
  const cy = 118;
  const R = 86;
  const point = (k: number, v: number) => {
    const a = (Math.PI * 2 * k) / AXES.length - Math.PI / 2;
    return [cx + Math.cos(a) * R * v, cy + Math.sin(a) * R * v] as const;
  };
  const shape = AXES.map((axis, k) => point(k, dev.params[axis]).join(" ")).join(" ");
  const ring = AXES.map((_, k) => point(k, 1).join(" ")).join(" ");
  return (
    <svg
      viewBox="0 0 380 236"
      className="h-auto w-full"
      role="img"
      aria-label={`Reputation radar for ${dev.name}, built from six parameters measured on real projects.`}
    >
      <polygon points={ring} className="fill-none stroke-border" />
      <polygon
        points={AXES.map((_, k) => point(k, 0.5).join(" ")).join(" ")}
        className="fill-none stroke-border"
      />
      {AXES.map((axis, k) => {
        const [x, y] = point(k, 1.17);
        return (
          <text
            key={axis}
            x={x}
            y={y}
            textAnchor="middle"
            className="fill-text-muted text-[10px] capitalize"
          >
            {axis === "diversity" ? "Client diversity" : axis}
          </text>
        );
      })}
      <motion.polygon
        points={shape}
        className="fill-accent/25 stroke-accent"
        strokeWidth="2"
        style={{ transformOrigin: `${String(cx)}px ${String(cy)}px` }}
        initial={{ scale: 0.2, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={t(0.1, 0.6)}
      />
    </svg>
  );
}
