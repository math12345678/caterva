/**
 * Job activity: every run that is queued or working, wherever it was
 * started, and a notification when one finishes out of sight.
 *
 * A literature search or an analysis over a trajectory can take minutes,
 * and a reader who starts one and goes to read another screen must not
 * lose it. So the page keeps one list of live runs: those submitted here
 * (useRun, the command palette) and those it finds already running on the
 * server when it loads (another window, a reload). Each is followed
 * through the shared event stream (src/api/runs.ts), the top bar shows the
 * list with each run's stage and a cancel control, and when one finishes
 * while no screen is showing it, a notification says how it ended, in the
 * run's own words (the outcome's summary or reason), with a way to open
 * it.
 */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, type ReactNode, useCallback, useContext, useEffect, useMemo, useReducer, useRef } from "react";
import { useLocation } from "wouter";

import { ApiRequestError, sessionToken } from "@/api/client";
import { cancelRun, isTerminal, listRuns, type RunEvent, subscribeToRun } from "@/api/runs";
import type { Outcome, RunError, RunKind, RunRecord, RunStatus, RunSummary } from "@/api/types";
import { routeForKind } from "@/routes";

import { describeError } from "./errors";
import { notify } from "./toast";

export interface Job {
  id: string;
  kind: RunKind;
  title: string;
  status: RunStatus;
  stage: { label: string; fraction: number | null } | null;
  outcome: Outcome | null;
  error: RunError | null;
  createdAt: string;
  finishedAt: string | null;
  /** Started from this page, or found running on the server. */
  origin: "here" | "found";
  cancelling: boolean;
}

export interface JobActions {
  track(run: RunRecord | RunSummary, origin: "here" | "found"): void;
  cancel(id: string): Promise<void>;
  /** A screen showing this run; returns the function that stops showing it. */
  markViewing(id: string): () => void;
  /** Where a run is shown: its kind's screen with ?run=<id>. */
  hrefFor(job: Pick<Job, "id" | "kind">): string;
}

export interface JobsApi extends JobActions {
  /** Live runs first, then those that finished during this session, newest first. */
  jobs: Job[];
  active: Job[];
}

// Two contexts: the actions never change, so a screen that only submits
// and cancels is not re-rendered every time some other run reports a stage.
const ActionsContext = createContext<JobActions | null>(null);
const ListContext = createContext<Pick<JobsApi, "jobs" | "active">>({ jobs: [], active: [] });

export function useJobs(): JobsApi {
  const actions = useContext(ActionsContext);
  const list = useContext(ListContext);
  if (!actions) throw new Error("useJobs needs <JobsProvider>, which App mounts around every screen.");
  return { ...actions, ...list };
}

/** For hooks that also work outside the app shell (tests, a lone component). */
export function useJobActionsOptional(): JobActions | null {
  return useContext(ActionsContext);
}

export function runHref(job: Pick<Job, "id" | "kind">): string {
  const route = routeForKind(job.kind);
  return `${route?.path ?? "/history"}?run=${encodeURIComponent(job.id)}`;
}

function fromRun(run: RunRecord | RunSummary, origin: "here" | "found"): Job {
  const progress = "progress" in run ? run.progress : null;
  return {
    id: run.id,
    kind: run.kind,
    title: run.title,
    status: run.status,
    stage: progress ? { label: progress.label, fraction: progress.fraction } : null,
    outcome: run.outcome,
    error: "error" in run ? run.error : null,
    createdAt: run.created_at,
    finishedAt: run.finished_at,
    origin,
    cancelling: false,
  };
}

function firstLine(text: string | null | undefined): string {
  if (!text) return "";
  const line = text.split("\n").find((l) => l.trim()) ?? "";
  return line.length > 220 ? `${line.slice(0, 217)}...` : line;
}

/** How a finished run is announced: in its own words, never an invented summary. */
export function announcement(job: Job): { tone: "done" | "refused" | "negative" | "failed" | "stopped"; title: string; description: string } {
  switch (job.status) {
    case "done": {
      const meaning = job.outcome?.meaning ?? "produced";
      if (meaning === "refused")
        return { tone: "refused", title: `Refused: ${job.title}`, description: firstLine(job.outcome?.reason) };
      if (meaning === "negative")
        return { tone: "negative", title: `Negative finding: ${job.title}`, description: firstLine(job.outcome?.reason) };
      return { tone: "done", title: `Finished: ${job.title}`, description: firstLine(job.outcome?.summary) };
    }
    case "failed":
      return {
        tone: "failed",
        title: `Failed: ${job.title}`,
        description: job.error ? `${job.error.type}: ${firstLine(job.error.message)}` : "",
      };
    case "cancelled":
      return { tone: "stopped", title: `Cancelled: ${job.title}`, description: "" };
    case "interrupted":
      return { tone: "stopped", title: `Interrupted: ${job.title}`, description: firstLine(job.error?.message) };
    default:
      return { tone: "done", title: job.title, description: "" };
  }
}

const FOUND_POLL_MS = 15_000;
const KEEP_FINISHED = 8;

export function JobsProvider({ children }: { children: ReactNode }) {
  // The list lives in a ref and a counter re-renders its readers, so the
  // event handlers below read and write it without side effects hiding in
  // a state updater (which React may call twice).
  const store = useRef(new Map<string, Job>());
  const [version, bump] = useReducer((n: number) => n + 1, 0);
  const viewing = useRef(new Map<string, number>());
  const followers = useRef(new Map<string, () => void>());
  const client = useQueryClient();
  const [, navigate] = useLocation();

  const put = useCallback((job: Job) => {
    store.current.set(job.id, job);
    bump();
  }, []);

  const update = useCallback(
    (id: string, change: (job: Job) => Job) => {
      const job = store.current.get(id);
      if (job) put(change(job));
    },
    [put],
  );

  const finished = useCallback(
    (job: Job) => {
      void client.invalidateQueries({ queryKey: ["runs"] });
      void client.invalidateQueries({ queryKey: ["run", job.id] });
      void client.invalidateQueries({ queryKey: ["capabilities"] });
      if ((viewing.current.get(job.id) ?? 0) > 0) return;
      const a = announcement(job);
      const action = { label: "Open", onClick: () => navigate(runHref(job)) };
      notify(a.tone === "stopped" ? "info" : a.tone, a.title, {
        description: a.description,
        action,
        id: `run-${job.id}`,
      });
    },
    [client, navigate],
  );

  const unfollow = useCallback((id: string) => {
    const stop = followers.current.get(id);
    followers.current.delete(id);
    stop?.();
  }, []);

  const follow = useCallback(
    (id: string) => {
      if (followers.current.has(id)) return;
      const onEvent = (e: RunEvent) => {
        switch (e.event) {
          case "status":
            update(id, (j) => ({ ...j, status: e.data.status, outcome: e.data.outcome ?? j.outcome }));
            break;
          case "stage":
            update(id, (j) => ({ ...j, stage: { label: e.data.label, fraction: e.data.fraction } }));
            break;
          case "result":
            update(id, (j) => ({ ...j, outcome: e.data.outcome }));
            break;
          case "error":
            update(id, (j) => ({ ...j, error: e.data.error }));
            break;
          case "end": {
            const job = store.current.get(id);
            if (!job) break;
            const done: Job = { ...job, status: e.data.status, cancelling: false, finishedAt: e.data.at, stage: null };
            put(done);
            // After this event is delivered: a stream stopped from inside its own callback would drop the rest.
            queueMicrotask(() => unfollow(id));
            finished(done);
            break;
          }
          case "log":
            break;
        }
      };
      const unsubscribe = subscribeToRun(id, {
        onEvent,
        onError: () => {
          // The run went away (deleted) or the server stopped: stop showing it as live.
          queueMicrotask(() => unfollow(id));
          if (store.current.delete(id)) bump();
        },
      });
      followers.current.set(id, unsubscribe);
    },
    [update, put, finished, unfollow],
  );

  const track = useCallback(
    (run: RunRecord | RunSummary, origin: "here" | "found") => {
      if (isTerminal(run.status) || store.current.has(run.id)) return;
      put(fromRun(run, origin));
      follow(run.id);
    },
    [follow, put],
  );

  const cancel = useCallback(
    async (id: string) => {
      update(id, (j) => ({ ...j, cancelling: true }));
      try {
        await cancelRun(id);
      } catch (e) {
        update(id, (j) => ({ ...j, cancelling: false }));
        if (!(e instanceof ApiRequestError && e.status === 409)) {
          notify("failed", "The run was not cancelled", { description: describeError(e).message });
        }
      }
    },
    [update],
  );

  const markViewing = useCallback((id: string) => {
    viewing.current.set(id, (viewing.current.get(id) ?? 0) + 1);
    return () => {
      const n = (viewing.current.get(id) ?? 1) - 1;
      if (n <= 0) viewing.current.delete(id);
      else viewing.current.set(id, n);
    };
  }, []);

  // Runs already live on the server: found at load, and every so often,
  // so a run started in another window shows up here too.
  const live = useQuery({
    queryKey: ["runs", "live"],
    queryFn: async () => {
      const [running, queued] = await Promise.all([
        listRuns({ status: "running", limit: 50 }),
        listRuns({ status: "queued", limit: 50 }),
      ]);
      return [...running.runs, ...queued.runs];
    },
    refetchInterval: FOUND_POLL_MS,
    refetchIntervalInBackground: false,
    // Without a session every request is refused; the shell says why instead.
    enabled: sessionToken() !== null,
  });
  useEffect(() => {
    for (const run of live.data ?? []) track(run, "found");
  }, [live.data, track]);

  useEffect(() => {
    const all = followers.current;
    return () => {
      for (const stop of all.values()) stop();
      all.clear();
    };
  }, []);

  const actions = useMemo<JobActions>(
    () => ({ track, cancel, markViewing, hrefFor: runHref }),
    [track, cancel, markViewing],
  );
  const list = useMemo(() => {
    void version; // the lists below are read from the store this counter tracks
    const all = [...store.current.values()];
    const active = all.filter((j) => !isTerminal(j.status)).sort((a, b) => a.createdAt.localeCompare(b.createdAt));
    const done = all
      .filter((j) => isTerminal(j.status))
      .sort((a, b) => (b.finishedAt ?? "").localeCompare(a.finishedAt ?? ""))
      .slice(0, KEEP_FINISHED);
    return { jobs: [...active, ...done], active };
  }, [version]);

  return (
    <ActionsContext.Provider value={actions}>
      <ListContext.Provider value={list}>{children}</ListContext.Provider>
    </ActionsContext.Provider>
  );
}
