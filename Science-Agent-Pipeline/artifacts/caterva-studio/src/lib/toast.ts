/**
 * Notifications: a run that finished out of sight, a setting the server did
 * not store.
 *
 * Written here rather than taken from a toast library because the one the
 * workspace locks (sonner) inserts a <style> element when it loads, and the
 * studio's Content Security Policy (`style-src 'self'`, CONTRACT.md 3.8)
 * refuses inline style elements: its toasts would arrive unstyled and every
 * launch would log a policy violation. This store is a list and a
 * subscription; src/components/toast/Toaster.tsx draws it with the
 * stylesheet's own classes.
 *
 * A notification never carries a sentence the page made up about a result:
 * callers pass the run's own words (its outcome summary or reason).
 */
import { useSyncExternalStore } from "react";

export type ToastTone = "done" | "refused" | "negative" | "failed" | "info";

export interface ToastAction {
  label: string;
  onClick: () => void;
}

export interface Toast {
  id: string;
  tone: ToastTone;
  title: string;
  description?: string;
  action?: ToastAction;
  /** Milliseconds before it leaves by itself; failures stay until dismissed. */
  duration: number | null;
  createdAt: number;
}

export interface ToastOptions {
  id?: string;
  description?: string;
  action?: ToastAction;
  duration?: number | null;
}

const MAX_VISIBLE = 4;
let toasts: Toast[] = [];
const listeners = new Set<() => void>();
const timers = new Map<string, number>();
let counter = 0;

function emit(): void {
  for (const l of listeners) l();
}

export function dismissToast(id: string): void {
  const timer = timers.get(id);
  if (timer !== undefined) window.clearTimeout(timer);
  timers.delete(id);
  const next = toasts.filter((t) => t.id !== id);
  if (next.length !== toasts.length) {
    toasts = next;
    emit();
  }
}

function schedule(t: Toast): void {
  const old = timers.get(t.id);
  if (old !== undefined) window.clearTimeout(old);
  timers.delete(t.id);
  if (t.duration === null) return;
  timers.set(
    t.id,
    window.setTimeout(() => dismissToast(t.id), t.duration),
  );
}

/** Pause a toast's timer while the reader is looking at it (hover or focus). */
export function holdToast(id: string, held: boolean): void {
  const t = toasts.find((x) => x.id === id);
  if (!t) return;
  if (held) {
    const timer = timers.get(id);
    if (timer !== undefined) window.clearTimeout(timer);
    timers.delete(id);
  } else {
    schedule(t);
  }
}

export function notify(tone: ToastTone, title: string, options: ToastOptions = {}): string {
  counter += 1;
  const id = options.id ?? `toast-${counter}`;
  const duration = options.duration !== undefined ? options.duration : tone === "failed" ? null : 8000;
  const t: Toast = {
    id,
    tone,
    title,
    description: options.description || undefined,
    action: options.action,
    duration,
    createdAt: Date.now(),
  };
  // A second notification with the same id (a run announced twice) replaces the first.
  toasts = [...toasts.filter((x) => x.id !== id), t].slice(-MAX_VISIBLE);
  schedule(t);
  emit();
  return id;
}

function subscribe(onChange: () => void): () => void {
  listeners.add(onChange);
  return () => listeners.delete(onChange);
}

function snapshot(): Toast[] {
  return toasts;
}

/** Whether a notification is still on screen (held open while hovered or focused). */
export function isToastShown(id: string): boolean {
  return toasts.some((t) => t.id === id);
}

export function useToasts(): Toast[] {
  return useSyncExternalStore(subscribe, snapshot, snapshot);
}

/** For tests: forget every notification and timer. */
export function resetToastsForTests(): void {
  for (const timer of timers.values()) window.clearTimeout(timer);
  timers.clear();
  toasts = [];
  emit();
}
