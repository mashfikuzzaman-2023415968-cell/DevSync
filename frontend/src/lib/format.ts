/**
 * Display formats (spec §13.1, §13.8 #4): money as ৳12,500 with Bangladeshi grouping,
 * dates as "12 Oct 2026" in Asia/Dhaka, relative times with the full date available,
 * percentages with at most one decimal, large counts abbreviated (12.4k), 0–1 scores
 * shown as whole numbers 0–100.
 */
const TZ = "Asia/Dhaka";

const grouped = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });
const dateFmt = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
  year: "numeric",
  timeZone: TZ,
});
const dateTimeFmt = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  timeZone: TZ,
});
const relative = new Intl.RelativeTimeFormat("en", { numeric: "auto" });

/** Paisa (integer) → "৳12,500". Whole taka unless paisa are present. */
export function formatMoney(paisa: number): string {
  const taka = paisa / 100;
  const whole = Number.isInteger(taka);
  const body = whole
    ? grouped.format(Math.abs(taka))
    : new Intl.NumberFormat("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(
        Math.abs(taka),
      );
  return `${taka < 0 ? "−" : ""}৳${body}`;
}

export function formatCount(n: number): string {
  const abs = Math.abs(n);
  if (abs < 1000) return grouped.format(n);
  const units: [number, string][] = [
    [1e9, "B"],
    [1e6, "M"],
    [1e3, "k"],
  ];
  for (const [size, unit] of units) {
    if (abs >= size) {
      const v = n / size;
      return `${v.toFixed(Math.abs(v) >= 100 ? 0 : 1).replace(/\.0$/, "")}${unit}`;
    }
  }
  return grouped.format(n);
}

export function formatPercent(fraction: number): string {
  return `${(fraction * 100).toFixed(1).replace(/\.0$/, "")}%`;
}

/** Reputation and test scores are stored 0–1 and shown 0–100 (spec §13.8 #4). */
export function formatScore(fraction: number): string {
  return String(Math.round(Math.min(1, Math.max(0, fraction)) * 100));
}

export function formatDate(value: Date | string): string {
  return dateFmt.format(new Date(value));
}

export function formatDateTime(value: Date | string): string {
  return dateTimeFmt.format(new Date(value));
}

export function formatDays(days: number): string {
  return `${String(days)} ${Math.abs(days) === 1 ? "day" : "days"}`;
}

const STEPS: [Intl.RelativeTimeFormatUnit, number][] = [
  ["year", 365 * 24 * 3600],
  ["month", 30 * 24 * 3600],
  ["week", 7 * 24 * 3600],
  ["day", 24 * 3600],
  ["hour", 3600],
  ["minute", 60],
];

/** "2 days ago" / "in 3 hours"; the caller shows formatDateTime in a tooltip. */
export function formatRelative(value: Date | string, now: Date = new Date()): string {
  const seconds = (new Date(value).getTime() - now.getTime()) / 1000;
  for (const [unit, size] of STEPS) {
    if (Math.abs(seconds) >= size) return relative.format(Math.round(seconds / size), unit);
  }
  return "just now";
}
