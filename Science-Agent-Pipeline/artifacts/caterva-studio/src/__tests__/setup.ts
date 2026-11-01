/**
 * The browser features jsdom leaves out and the page relies on, filled in
 * with the smallest stand-in that keeps the behaviour under test honest:
 * <dialog>'s showModal and close (the command palette), matchMedia (theme,
 * reduced motion, the split), ResizeObserver (charts, the viewer) and a
 * canvas without a 2D context (the viewer paints nothing in jsdom; its
 * mathematics are tested directly).
 */
import "@testing-library/jest-dom/vitest";
import { cleanup, configure } from "@testing-library/react";
import { afterEach } from "vitest";

// A busy machine runs a dozen of these files at once; waiting for an answer
// a second is not enough then, and the answer is not wrong, only late.
configure({ asyncUtilTimeout: 6000 });

afterEach(() => {
  cleanup();
  document.documentElement.removeAttribute("data-theme");
  try {
    window.localStorage.clear();
  } catch {
    // Storage disabled in this environment; nothing to clear.
  }
});

if (typeof HTMLDialogElement !== "undefined" && !HTMLDialogElement.prototype.showModal) {
  HTMLDialogElement.prototype.showModal = function showModal(this: HTMLDialogElement) {
    this.setAttribute("open", "");
  };
  HTMLDialogElement.prototype.close = function close(this: HTMLDialogElement) {
    if (!this.hasAttribute("open")) return;
    this.removeAttribute("open");
    this.dispatchEvent(new Event("close"));
  };
}

if (typeof window.matchMedia !== "function") {
  const media = new Map<string, boolean>();
  (window as unknown as { __setMedia: (q: string, v: boolean) => void }).__setMedia = (q, v) => media.set(q, v);
  window.matchMedia = (query: string) =>
    ({
      matches: media.get(query) ?? false,
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    }) as MediaQueryList;
}

if (typeof window.ResizeObserver === "undefined") {
  window.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
}

HTMLCanvasElement.prototype.getContext = (() => null) as unknown as HTMLCanvasElement["getContext"];

if (!Element.prototype.scrollIntoView) Element.prototype.scrollIntoView = () => {};
if (!Element.prototype.hasPointerCapture) {
  Element.prototype.hasPointerCapture = () => false;
  Element.prototype.setPointerCapture = () => {};
  Element.prototype.releasePointerCapture = () => {};
}
