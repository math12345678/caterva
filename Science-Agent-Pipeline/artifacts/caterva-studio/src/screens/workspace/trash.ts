/**
 * Deleting a run from History, with an undo instead of a question first.
 *
 * `DELETE /api/runs/{id}` moves the run's folder into the workspace's
 * trash folder, and the API has no route that moves it back; a page that
 * sent the DELETE at once could only tell the reader to move the folder
 * back by hand. So the page holds the delete: the run leaves the list at
 * once and a notification offers Undo; only when that notification has
 * gone (it stays while the reader hovers or focuses it, so reaching the
 * Undo button never races a timer), or the page is being left (the request
 * then goes with `keepalive` so it outlives the page), is the DELETE sent.
 * An undo before then sends nothing at all. A DELETE the server refuses (409: the run started again
 * under another window) brings the run back with the server's words.
 */
import { useSyncExternalStore } from "react";

import { SESSION_HEADER } from "@/api/types";
import { sessionToken } from "@/api/client";
import { deleteRun } from "@/api/runs";

/** How long Undo is offered, in milliseconds. */
export const UNDO_MS = 8000;

interface Pending {
  timer: number;
  title: string;
}

const pending = new Map<string, Pending>();
const listeners = new Set<() => void>();
let snapshot: ReadonlySet<string> = new Set();

function emit(): void {
  snapshot = new Set(pending.keys());
  for (const l of listeners) l();
}

function path(id: string): string {
  return `/api/runs/${encodeURIComponent(id)}`;
}

/** How often a held delete looks again whether its Undo is still offered. */
const RECHECK_MS = 500;

/**
 * Hold a delete for at least `delay`, and for as long after that as
 * `offered()` says Undo is still on screen; then send it. `onSent` hears
 * how it ended: null when the server moved the run to its trash, else the
 * error.
 */
export function scheduleDelete(
  id: string,
  title: string,
  onSent: (error: unknown | null) => void,
  offered: () => boolean = () => false,
  delay = UNDO_MS,
): void {
  if (pending.has(id)) return;
  const send = () => {
    if (offered()) {
      const p = pending.get(id);
      if (p) p.timer = window.setTimeout(send, RECHECK_MS);
      return;
    }
    pending.delete(id);
    deleteRun(id).then(
      () => {
        emit();
        onSent(null);
      },
      (e: unknown) => {
        emit();
        onSent(e);
      },
    );
  };
  pending.set(id, { timer: window.setTimeout(send, delay), title });
  emit();
}

/** Undo a held delete; true when there was one to undo (nothing was sent). */
export function undoDelete(id: string): boolean {
  const p = pending.get(id);
  if (!p) return false;
  window.clearTimeout(p.timer);
  pending.delete(id);
  emit();
  return true;
}

/** Send every held delete now, so leaving the page does not quietly keep a run. */
export function flushDeletes(): void {
  const token = sessionToken();
  for (const [id, p] of pending) {
    window.clearTimeout(p.timer);
    if (token) {
      void fetch(path(id), { method: "DELETE", headers: { [SESSION_HEADER]: token }, keepalive: true }).catch(() => {});
    }
  }
  pending.clear();
  emit();
}

if (typeof window !== "undefined") window.addEventListener("pagehide", flushDeletes);

function subscribe(onChange: () => void): () => void {
  listeners.add(onChange);
  return () => listeners.delete(onChange);
}

function read(): ReadonlySet<string> {
  return snapshot;
}

/** The ids whose delete is being held: hidden from lists, still on the server. */
export function useHeldDeletes(): ReadonlySet<string> {
  return useSyncExternalStore(subscribe, read, read);
}

export function resetTrashForTests(): void {
  for (const p of pending.values()) window.clearTimeout(p.timer);
  pending.clear();
  emit();
}
