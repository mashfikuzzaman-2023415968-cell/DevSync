/** Question and answer text from the bank marks code with backticks (`useRef`, `null`). Render
 * those spans as code instead of showing the backticks, without parsing any other markup: the
 * text is split on the backticks and the pieces are rendered as plain React children, so nothing
 * from the database is ever treated as HTML. An unclosed backtick keeps its text as written. */
import type { ReactNode } from "react";

export function inlineCode(text: string): ReactNode {
  const parts = text.split("`");
  if (parts.length < 3) return text; // no pair of backticks: leave it exactly as written
  const unpaired = parts.length % 2 === 0; // a trailing backtick with no closing one
  return parts.map((part, i) => {
    const last = i === parts.length - 1;
    if (i % 2 === 0) return part;
    // The unpaired tail keeps the backtick the split removed, so nothing is lost.
    if (unpaired && last) return `\`${part}`;
    return (
      <code key={i} className="rounded bg-surface-2 px-1 py-0.5 font-mono text-[0.9em]">
        {part}
      </code>
    );
  });
}
