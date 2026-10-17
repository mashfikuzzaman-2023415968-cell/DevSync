/**
 * Layout checks run inside the page (spec §13.14 "How responsiveness is verified"):
 * horizontal overflow, overlapping interactive elements, touch targets ≥ 44 × 44 px on touch
 * viewports, and text clipped by its container. Returns human-readable problems.
 */
export interface LayoutOptions {
  touch: boolean;
}

export function layoutProblems({ touch }: LayoutOptions): string[] {
  const problems: string[] = [];
  const doc = document.documentElement;
  if (doc.scrollWidth > window.innerWidth + 1) {
    problems.push(`horizontal overflow: ${String(doc.scrollWidth)} > ${String(window.innerWidth)}`);
  }

  const describe = (el: Element) => {
    const text = (el.getAttribute("aria-label") ?? el.textContent).trim().replace(/\s+/g, " ");
    return `${el.tagName.toLowerCase()}("${text.slice(0, 40)}")`;
  };
  const visible = (el: Element) => {
    const r = el.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) return false;
    const style = getComputedStyle(el);
    if (
      style.visibility === "hidden" ||
      style.pointerEvents === "none" ||
      Number(style.opacity) === 0
    )
      return false;
    if (el.closest("[aria-hidden=true], [inert], .sr-only")) return false;
    return r.bottom > 0 && r.top < window.innerHeight * 3;
  };

  const interactive = Array.from(
    document.querySelectorAll(
      "a[href], button, input:not([type=hidden]), select, textarea, [role=button], [role=radio], [role=checkbox], [role=switch], [role=tab], [role=slider], [role=combobox]",
    ),
  ).filter(visible);

  // A control's touch target includes the label it belongs to (wrapping or for=id).
  const target = (el: Element): DOMRect => {
    const r = el.getBoundingClientRect();
    const label =
      el.closest("label") ??
      (el.id ? document.querySelector(`label[for="${CSS.escape(el.id)}"]`) : null);
    if (!label) return r;
    const l = label.getBoundingClientRect();
    const left = Math.min(r.left, l.left);
    const top = Math.min(r.top, l.top);
    return new DOMRect(
      left,
      top,
      Math.max(r.right, l.right) - left,
      Math.max(r.bottom, l.bottom) - top,
    );
  };

  if (touch) {
    for (const el of interactive) {
      // WCAG 2.5.8 exception: links inside a sentence.
      if (el.tagName === "A" && el.parentElement?.closest("p, li > p")) continue;
      const r = target(el);
      if (r.width < 43.5 || r.height < 43.5) {
        problems.push(
          `small touch target ${describe(el)} ${String(Math.round(r.width))}×${String(Math.round(r.height))}`,
        );
      }
    }
  }

  // Elements are compared within one layer: content scrolling under a fixed bar is not an
  // overlap, and parts hidden by a scroll container's clipping don't count.
  const layer = (el: Element): Element | null => {
    for (let n: Element | null = el; n; n = n.parentElement) {
      const pos = getComputedStyle(n).position;
      if (pos === "fixed" || pos === "sticky") return n;
    }
    return null;
  };
  const clipped = (el: Element): DOMRect => {
    let r = el.getBoundingClientRect();
    for (let n = el.parentElement; n; n = n.parentElement) {
      const s = getComputedStyle(n);
      if (s.overflowX !== "visible" || s.overflowY !== "visible") {
        const c = n.getBoundingClientRect();
        const left = Math.max(r.left, c.left);
        const top = Math.max(r.top, c.top);
        r = new DOMRect(
          left,
          top,
          Math.max(0, Math.min(r.right, c.right) - left),
          Math.max(0, Math.min(r.bottom, c.bottom) - top),
        );
      }
    }
    return r;
  };

  for (let i = 0; i < interactive.length; i += 1) {
    for (let j = i + 1; j < interactive.length; j += 1) {
      const a = interactive[i];
      const b = interactive[j];
      if (a.contains(b) || b.contains(a)) continue;
      if (a.closest("label") && a.closest("label") === b.closest("label")) continue;
      if (layer(a) !== layer(b)) continue;
      const ra = clipped(a);
      const rb = clipped(b);
      const w = Math.min(ra.right, rb.right) - Math.max(ra.left, rb.left);
      const h = Math.min(ra.bottom, rb.bottom) - Math.max(ra.top, rb.top);
      if (w > 2 && h > 2) problems.push(`overlap ${describe(a)} × ${describe(b)}`);
    }
  }

  for (const el of Array.from(
    document.querySelectorAll("h1, h2, h3, h4, p, label, button, a, li, dt, dd"),
  )) {
    if (!visible(el)) continue;
    const style = getComputedStyle(el);
    const clips =
      ["hidden", "clip"].includes(style.overflowX) || ["hidden", "clip"].includes(style.overflow);
    if (!clips || style.textOverflow === "ellipsis") continue;
    if (el.scrollWidth > el.clientWidth + 1) problems.push(`clipped text ${describe(el)}`);
  }
  return Array.from(new Set(problems));
}
