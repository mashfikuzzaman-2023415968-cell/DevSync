import { useEffect, useRef, type ClipboardEvent, type KeyboardEvent } from "react";

interface Props {
  value: string;
  onChange: (value: string) => void;
  label: string;
  disabled?: boolean;
  /** Move focus to the first box when the screen opens (the code is its only task). */
  focusFirst?: boolean;
}

/** Six one-digit boxes with auto-advance, backspace and paste support (spec §13.5 #4). */
export function OtpInput({ value, onChange, label, disabled = false, focusFirst = false }: Props) {
  const refs = useRef<(HTMLInputElement | null)[]>([]);
  useEffect(() => {
    if (focusFirst) refs.current[0]?.focus();
  }, [focusFirst]);
  const digits = Array.from({ length: 6 }, (_, i) => value[i] ?? "");

  const setAt = (index: number, digit: string) => {
    const next = digits.slice();
    next[index] = digit;
    onChange(next.join("").replace(/\D/g, "").slice(0, 6));
  };

  const onKeyDown = (index: number) => (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Backspace" && !digits[index] && index > 0) refs.current[index - 1]?.focus();
    if (e.key === "ArrowLeft" && index > 0) refs.current[index - 1]?.focus();
    if (e.key === "ArrowRight" && index < 5) refs.current[index + 1]?.focus();
  };

  const onPaste = (e: ClipboardEvent<HTMLInputElement>) => {
    const pasted = e.clipboardData.getData("text").replace(/\D/g, "").slice(0, 6);
    if (pasted) {
      e.preventDefault();
      onChange(pasted);
      refs.current[Math.min(pasted.length, 5)]?.focus();
    }
  };

  return (
    <fieldset>
      <legend className="mb-1.5 text-body-sm font-medium text-text">{label}</legend>
      <div className="flex gap-2">
        {digits.map((digit, i) => (
          <input
            key={i}
            ref={(el) => {
              refs.current[i] = el;
            }}
            value={digit}
            disabled={disabled}
            inputMode="numeric"
            autoComplete={i === 0 ? "one-time-code" : "off"}
            enterKeyHint={i === 5 ? "done" : "next"}
            maxLength={1}
            aria-label={`Digit ${String(i + 1)} of 6`}
            onPaste={onPaste}
            onKeyDown={onKeyDown(i)}
            onChange={(e) => {
              const d = e.target.value.replace(/\D/g, "").slice(-1);
              setAt(i, d);
              if (d && i < 5) refs.current[i + 1]?.focus();
            }}
            className="size-12 rounded-md border border-border bg-surface text-center text-h4 font-semibold tabular text-text focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
          />
        ))}
      </div>
    </fieldset>
  );
}
