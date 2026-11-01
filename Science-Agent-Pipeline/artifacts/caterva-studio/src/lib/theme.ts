/**
 * The theme: light paper by default, dark ink surfaces for evening work,
 * following the operating system unless the reader chooses.
 *
 * Three places hold the choice and must agree. `settings.theme` on the
 * server is the record (it survives a new browser profile and is what the
 * macOS app reads back); `localStorage["caterva.theme"]` mirrors it so the
 * first paint, before any request returns, is already right; and
 * `data-theme` on <html> is what the stylesheet reads. "system" is the
 * absence of the attribute, so the CSS media query decides
 * (docs/studio/CONTRACT.md 17.2). This module owns the last two and keeps a
 * tiny store so every switch on the page moves together; src/lib/settings.ts
 * writes the first.
 */
import { useSyncExternalStore } from "react";

import type { Theme } from "@/api/types";

export const THEME_STORAGE_KEY = "caterva.theme";
const DARK_QUERY = "(prefers-color-scheme: dark)";

function isTheme(v: unknown): v is Theme {
  return v === "system" || v === "light" || v === "dark";
}

export function readStoredTheme(): Theme {
  try {
    const v = window.localStorage.getItem(THEME_STORAGE_KEY);
    return isTheme(v) ? v : "system";
  } catch {
    // Storage can be unavailable (a locked-down browser); the OS decides.
    return "system";
  }
}

let current: Theme | null = null;
const listeners = new Set<() => void>();

export function currentTheme(): Theme {
  if (current === null) current = readStoredTheme();
  return current;
}

/** Put the choice on <html> and in storage, and tell every subscriber. */
export function applyTheme(choice: Theme): void {
  current = choice;
  const root = document.documentElement;
  if (choice === "system") delete root.dataset.theme;
  else root.dataset.theme = choice;
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, choice);
  } catch {
    // Not remembered in this browser; the server's settings still are.
  }
  for (const l of listeners) l();
}

function systemDark(): boolean {
  return typeof window.matchMedia === "function" && window.matchMedia(DARK_QUERY).matches;
}

export function resolveTheme(choice: Theme): "light" | "dark" {
  if (choice === "system") return systemDark() ? "dark" : "light";
  return choice;
}

function subscribe(onChange: () => void): () => void {
  listeners.add(onChange);
  const m = typeof window.matchMedia === "function" ? window.matchMedia(DARK_QUERY) : null;
  m?.addEventListener("change", onChange);
  return () => {
    listeners.delete(onChange);
    m?.removeEventListener("change", onChange);
  };
}

/** The reader's choice and the theme actually showing. */
export function useTheme(): { choice: Theme; resolved: "light" | "dark" } {
  const choice = useSyncExternalStore(subscribe, currentTheme, () => "system" as Theme);
  const resolved = useSyncExternalStore(
    subscribe,
    () => resolveTheme(currentTheme()),
    () => "light" as const,
  );
  return { choice, resolved };
}

/** For tests: forget the in-memory choice so the next read comes from storage. */
export function resetThemeForTests(): void {
  current = null;
  listeners.clear();
}
