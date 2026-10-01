/**
 * Keyboard: the platform's modifier, and one hook for global shortcuts.
 *
 * Cmd on macOS (the app's home), Ctrl elsewhere, as CONTRACT.md 17.2 says
 * for the command palette. A shortcut never fires while the reader is
 * typing into a field unless it uses the modifier, so a letter typed into
 * a form is never taken as a command.
 */
import { useEffect, useRef } from "react";

export function isMac(): boolean {
  if (typeof navigator === "undefined") return false;
  const platform =
    (navigator as Navigator & { userAgentData?: { platform?: string } }).userAgentData?.platform ?? navigator.platform ?? "";
  return /mac|iphone|ipad/i.test(platform) || /Mac OS X/.test(navigator.userAgent);
}

/** "⌘" on macOS, "Ctrl" elsewhere. */
export function modKey(): string {
  return isMac() ? "⌘" : "Ctrl";
}

export interface Hotkey {
  key: string;
  mod?: boolean;
  shift?: boolean;
  alt?: boolean;
}

export function matches(e: KeyboardEvent, hotkey: Hotkey): boolean {
  const mod = isMac() ? e.metaKey : e.ctrlKey;
  return (
    e.key.toLowerCase() === hotkey.key.toLowerCase() &&
    Boolean(hotkey.mod) === mod &&
    Boolean(hotkey.shift) === e.shiftKey &&
    Boolean(hotkey.alt) === e.altKey
  );
}

function typingInto(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName);
}

/** Call `handler` when `hotkey` is pressed anywhere on the page. */
export function useHotkey(hotkey: Hotkey, handler: (e: KeyboardEvent) => void, enabled = true): void {
  const ref = useRef(handler);
  ref.current = handler;
  const { key, mod, shift, alt } = hotkey;
  useEffect(() => {
    if (!enabled) return;
    const onKey = (e: KeyboardEvent) => {
      if (!matches(e, { key, mod, shift, alt })) return;
      if (!mod && typingInto(e.target)) return;
      e.preventDefault();
      ref.current(e);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [key, mod, shift, alt, enabled]);
}
