/**
 * Integer paisa arithmetic for the screens that preview money (spec §0.2: money is integer
 * paisa, never floats). BigInt keeps every intermediate product exact.
 */

const BP = 10_000n;

/** `paisa × bp / 10,000`, rounded half up (bp = basis points, 10,000 = 100%). */
export function bpOf(paisa: number, bp: number): number {
  if (!Number.isSafeInteger(paisa) || !Number.isSafeInteger(bp) || paisa < 0 || bp < 0) return 0;
  return Number((BigInt(paisa) * BigInt(bp) * 2n + BP) / (BP * 2n));
}

/** What reaches the team after the platform fee: `budget × (10,000 − fee) / 10,000`, rounded
 * down like the server (`services/bids.py`), so the fee is the remainder. */
export function afterFee(budgetPaisa: number, feeBp: number): number {
  if (!Number.isSafeInteger(budgetPaisa) || budgetPaisa < 0) return 0;
  const bp = Number.isFinite(feeBp) ? Math.trunc(feeBp) : 0;
  const fee = BigInt(Math.max(0, Math.min(10_000, bp)));
  return Number((BigInt(budgetPaisa) * (BP - fee)) / BP);
}

/** Basis points as a percentage with at most one decimal: 500 → "5%", 1250 → "12.5%". */
export function bpPercent(bp: number): string {
  return `${String(Math.round(bp / 10) / 10)}%`;
}
