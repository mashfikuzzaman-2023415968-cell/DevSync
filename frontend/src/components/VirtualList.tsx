/**
 * A list that renders only what is on screen once it grows long (spec §13.14 performance, D158).
 * Up to `VIRTUALIZE_AFTER` items it is a plain list; beyond that it follows the page scroll with
 * `@tanstack/react-virtual` (window scrolling, measured rows), so a long activity feed or
 * notification history stays fast on phones. Rows are positioned with transforms set through
 * React (no inline `<style>`, CSP-safe). Keyboard and screen-reader order is the DOM order of
 * the rows on screen, top to bottom. Spacing between rows is padding inside each row (`gap`),
 * the same in both modes, because positioned rows can't use margins.
 */
import { useWindowVirtualizer } from "@tanstack/react-virtual";
import { useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { cn } from "@/lib/cn";

export const VIRTUALIZE_AFTER = 50;
const OVERSCAN = 8;

interface Props<T> {
  items: readonly T[];
  /** A stable key per item. */
  getKey: (item: T) => string;
  render: (item: T, index: number) => ReactNode;
  /** A typical row height in px, gap included (rows are measured once shown). */
  estimate: number;
  /** Space below each row in px. */
  gap?: number;
  className?: string;
  "aria-label"?: string;
}

export function VirtualList<T>(props: Props<T>) {
  const { items, getKey, render, className, gap = 0 } = props;
  if (items.length <= VIRTUALIZE_AFTER) {
    return (
      <ul className={className} aria-label={props["aria-label"]}>
        {items.map((item, i) => (
          <li key={getKey(item)} style={gap ? { paddingBottom: gap } : undefined}>
            {render(item, i)}
          </li>
        ))}
      </ul>
    );
  }
  return <Windowed {...props} />;
}

function Windowed<T>({ items, getKey, render, estimate, gap = 0, className, ...rest }: Props<T>) {
  const list = useRef<HTMLUListElement>(null);
  const [offset, setOffset] = useState(0);
  useLayoutEffect(() => {
    setOffset(list.current?.offsetTop ?? 0);
  }, []);
  const v = useWindowVirtualizer({
    count: items.length,
    estimateSize: () => estimate,
    overscan: OVERSCAN,
    scrollMargin: offset,
    getItemKey: (i) => {
      const item = items[i];
      return item === undefined ? i : getKey(item);
    },
  });
  return (
    <ul
      ref={list}
      className={cn("relative", className)}
      aria-label={rest["aria-label"]}
      style={{ height: v.getTotalSize() }}
      data-virtual=""
    >
      {v.getVirtualItems().map((row) => {
        const item = items[row.index];
        if (item === undefined) return null;
        return (
          <li
            key={row.key}
            data-index={row.index}
            ref={v.measureElement}
            className="absolute left-0 top-0 w-full"
            style={{
              transform: `translateY(${String(row.start - v.options.scrollMargin)}px)`,
              paddingBottom: gap || undefined,
            }}
          >
            {render(item, row.index)}
          </li>
        );
      })}
    </ul>
  );
}
