/** Tiny toast queue (no context needed): `toast({ title, tone })` from anywhere, including
 * the API layer (403/429 feedback, spec §13.7). The <Toaster/> renders the queue. */
import { useSyncExternalStore } from "react";

export type ToastTone = "info" | "success" | "warning" | "danger";

export interface ToastItem {
  id: number;
  title: string;
  description?: string;
  tone: ToastTone;
}

let items: ToastItem[] = [];
let nextId = 1;
const listeners = new Set<() => void>();

function emit() {
  for (const l of listeners) l();
}

export function toast(input: Omit<ToastItem, "id" | "tone"> & { tone?: ToastTone }): number {
  const id = nextId++;
  // Identical messages don't stack (e.g. several 429s at once).
  items = [
    ...items.filter((t) => t.title !== input.title),
    { ...input, tone: input.tone ?? "info", id },
  ].slice(-4);
  emit();
  return id;
}

export function dismissToast(id: number): void {
  items = items.filter((t) => t.id !== id);
  emit();
}

export function clearToasts(): void {
  items = [];
  emit();
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function useToasts(): ToastItem[] {
  return useSyncExternalStore(
    subscribe,
    () => items,
    () => items,
  );
}
