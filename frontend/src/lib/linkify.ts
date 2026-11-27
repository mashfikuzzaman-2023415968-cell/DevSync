/**
 * Safe linkification for user text (spec §13.7; D146). Comments and posts are plain text; this
 * only finds `https://` URLs so they can be rendered as links with
 * `rel="noopener noreferrer nofollow"`. Everything else stays text — `javascript:`, `data:`,
 * `http:` and any other scheme never become links — and nothing is ever parsed as HTML.
 */

export type Segment = { kind: "text"; value: string } | { kind: "link"; value: string; href: string };

// A run of non-space characters starting with https:// (lowercase scheme only).
const CANDIDATE = /https:\/\/[^\s<>"']+/g;
// Sentence punctuation that usually follows a URL rather than belonging to it.
const TRAILING = /[.,;:!?)\]}'"]+$/;
const MAX_URL = 2048;

function safeHref(raw: string): string | null {
  if (raw.length > MAX_URL) return null;
  try {
    const url = new URL(raw);
    if (url.protocol !== "https:" || url.username || url.password || !url.hostname) return null;
    return url.href;
  } catch {
    return null;
  }
}

export function linkify(text: string): Segment[] {
  const out: Segment[] = [];
  let last = 0;
  for (const match of text.matchAll(CANDIDATE)) {
    const start = match.index;
    let raw = match[0];
    const trail = TRAILING.exec(raw);
    if (trail) raw = raw.slice(0, raw.length - trail[0].length);
    const href = safeHref(raw);
    if (!href || raw.length <= "https://".length) continue;
    if (start > last) out.push({ kind: "text", value: text.slice(last, start) });
    out.push({ kind: "link", value: raw, href });
    last = start + raw.length;
  }
  if (last < text.length) out.push({ kind: "text", value: text.slice(last) });
  return out;
}
