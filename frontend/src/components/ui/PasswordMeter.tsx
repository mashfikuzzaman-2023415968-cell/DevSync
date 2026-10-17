/**
 * Lightweight strength hint while typing. The server's zxcvbn check and breached-
 * password list are the authority (spec §14.4); bundling zxcvbn in the browser would
 * blow the route budget (§13.7), so this only nudges toward long passphrases.
 */
export function strength(password: string): 0 | 1 | 2 | 3 | 4 {
  if (!password) return 0;
  let score = 0;
  if (password.length >= 10) score += 1;
  if (password.length >= 14) score += 1;
  if (/\s/.test(password) || password.length >= 18) score += 1;
  if (/[^A-Za-z]/.test(password) && /[A-Za-z]/.test(password)) score += 1;
  if (/^(.)\1+$/.test(password)) score = 0;
  return Math.min(score, 4) as 0 | 1 | 2 | 3 | 4;
}

const LABELS = ["Too short", "Weak", "Fair", "Looks good", "Looks strong"] as const;
const COLORS = ["bg-border", "bg-danger", "bg-warning", "bg-primary", "bg-success"] as const;

export function PasswordMeter({ password }: { password: string | undefined }) {
  const s = strength(password ?? "");
  return (
    <div className="space-y-1" aria-live="polite">
      <div className="flex gap-1" aria-hidden="true">
        {[1, 2, 3, 4].map((step) => (
          <span
            key={step}
            className={`h-1.5 flex-1 rounded-full transition-colors duration-base ${s >= step ? COLORS[s] : "bg-surface-2"}`}
          />
        ))}
      </div>
      <p className="text-caption text-text-muted">
        <span className="font-medium text-text">{LABELS[s]}.</span>
        {s >= 3
          ? " This is an estimate; we check it against leaked and common passwords when you continue."
          : " A few unrelated words make a strong, memorable password."}
      </p>
    </div>
  );
}
