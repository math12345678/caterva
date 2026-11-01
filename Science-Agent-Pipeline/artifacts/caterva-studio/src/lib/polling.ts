/**
 * How often the page asks the server again, and when it stops.
 *
 * Health and the live-run list are asked on a timer so a server that stopped
 * or a run started in another window is noticed. That is wasted work when
 * nobody is looking: a hidden tab asks nothing, a window left alone for a
 * couple of minutes asks a quarter as often, and a server that keeps failing
 * is asked less and less often (doubling, up to eight times the base)
 * instead of every few seconds forever. Any input brings the base rate back.
 */

/** Seconds of no input after which a window counts as idle. */
export const IDLE_AFTER_MS = 2 * 60_000;
/** An idle window asks this many times less often. */
export const IDLE_FACTOR = 4;
/** A failing server is asked at most this many times less often. */
export const MAX_BACKOFF = 8;

export interface PollInputs {
  base: number;
  hidden: boolean;
  idleForMs: number;
  /** Consecutive failures so far. */
  failures: number;
}

/** The delay before the next ask in ms, or false for not at all. A pure function of what the page knows. */
export function nextPollDelay({ base, hidden, idleForMs, failures }: PollInputs): number | false {
  if (hidden) return false;
  const idle = idleForMs >= IDLE_AFTER_MS ? IDLE_FACTOR : 1;
  const backoff = Math.min(MAX_BACKOFF, 2 ** Math.max(0, failures));
  return base * Math.max(idle, backoff);
}

let lastInput = Date.now();
let listening = false;

function listen(): void {
  if (listening || typeof window === "undefined") return;
  listening = true;
  const touch = () => {
    lastInput = Date.now();
  };
  for (const type of ["pointerdown", "keydown", "wheel", "touchstart"]) window.addEventListener(type, touch, { passive: true });
}

/** A `refetchInterval` for react-query that follows `nextPollDelay`. */
export function pollInterval(base: number): (query: { state: { errorUpdateCount: number } }) => number | false {
  listen();
  return (query) =>
    nextPollDelay({
      base,
      hidden: typeof document !== "undefined" && document.visibilityState === "hidden",
      idleForMs: Date.now() - lastInput,
      failures: query.state.errorUpdateCount,
    });
}
