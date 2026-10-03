/**
 * useRun: submit a run, follow its events, fetch its result, cancel it.
 *
 * The one hook every science screen uses, so each shows the same stages
 * (the SSE `stage` labels under the loading mark), the same refusal, the
 * same negative finding and the same failure (docs/studio/CONTRACT.md 6
 * and 8). The fields below are what screens rely on; new ones are only
 * ever added.
 *
 * Three outcomes stay apart all the way to the screen: a request the
 * server refused before a run existed (`requestError`, 400 malformed and
 * the like: nothing was run), a run that finished (`outcome`: produced,
 * refused with the CLI's reason, or a negative finding), and a run that
 * did not finish (`runError`: a crash, a cancel, an interruption).
 *
 * The run is registered with the job activity (src/lib/jobs.tsx), so if
 * the reader leaves the screen while it works, its completion arrives as a
 * notification instead of being lost; while the screen shows it, it does
 * not notify.
 */
import { useCallback, useEffect, useRef, useState } from "react";

import { describeError } from "@/lib/errors";
import { useJobActionsOptional } from "@/lib/jobs";

import { ApiRequestError } from "./client";
import { cancelRun, createRun, getResult, getRun, isTerminal, liveStatus, type RunEvent, subscribeToRun } from "./runs";
import type {
  ApiError,
  Outcome,
  RunError,
  RunKind,
  RunRecord,
  RunRequests,
  RunResults,
  RunStatus,
  StageEvent,
} from "./types";

export interface RunState<K extends RunKind> {
  run: RunRecord | null;
  status: RunStatus | "idle";
  stage: { stage: string; label: string; fraction: number | null } | null;
  /** Every stage reported so far, in order, for a run's timeline. */
  stages: Pick<StageEvent, "stage" | "label" | "fraction" | "at">[];
  log: string[];
  outcome: Outcome | null;
  result: RunResults[K] | null;
  /** A request the server refused before a run existed (400 malformed, 503 unavailable, ...). */
  requestError: ApiError | null;
  /** A run that crashed, was cancelled or was interrupted. */
  runError: RunError | null;
  /** Submitting: the POST has not answered yet. */
  submitting: boolean;
  /** Cancel was asked for and the run has not stopped yet (`cancelled` or `abandoned` has not arrived). */
  cancelling: boolean;
  /** The run finished and its result (if it has one) has been read. */
  settled: boolean;
}

function idle<K extends RunKind>(): RunState<K> {
  return {
    run: null,
    status: "idle",
    stage: null,
    stages: [],
    log: [],
    outcome: null,
    result: null,
    requestError: null,
    runError: null,
    submitting: false,
    cancelling: false,
    settled: false,
  };
}

function apply<K extends RunKind>(s: RunState<K>, e: RunEvent): RunState<K> {
  // Once the finished record has been read, replayed history only fills in
  // the stages and the log; it never walks the status back to "queued".
  if (s.settled && e.event !== "stage" && e.event !== "log") return s;
  switch (e.event) {
    case "status":
      return {
        ...s,
        status: liveStatus(e.data.status),
        outcome: e.data.outcome ?? s.outcome,
        cancelling: e.data.status === "cancelling" ? true : isTerminal(e.data.status) ? false : s.cancelling,
      };
    case "stage":
      return {
        ...s,
        stage: { stage: e.data.stage, label: e.data.label, fraction: e.data.fraction },
        stages: [...s.stages, { stage: e.data.stage, label: e.data.label, fraction: e.data.fraction, at: e.data.at }],
      };
    case "log":
      return { ...s, log: [...s.log, e.data.line] };
    case "result":
      return { ...s, outcome: e.data.outcome };
    case "error":
      return { ...s, runError: e.data.error };
    case "end":
      return { ...s, status: e.data.status, cancelling: false };
  }
}

function asError(e: unknown): ApiError {
  if (e instanceof ApiRequestError) return e.error;
  return { code: "crash", message: describeError(e).message };
}

export function useRun<K extends RunKind>(kind: K, existingRunId?: string | null) {
  const [state, setState] = useState<RunState<K>>(idle<K>);
  const jobs = useJobActionsOptional();
  const unsubscribe = useRef<(() => void) | null>(null);
  const current = useRef<string | null>(null);

  const stop = useCallback(() => {
    unsubscribe.current?.();
    unsubscribe.current = null;
  }, []);

  const settle = useCallback(async (id: string) => {
    try {
      const finished = await getRun(id);
      let result: RunResults[K] | null = null;
      if (finished.status === "done") {
        try {
          result = await getResult<K>(id);
        } catch (e) {
          // A refused run may have no result; its outcome says why.
          if (!(e instanceof ApiRequestError && e.status === 404)) throw e;
        }
      }
      if (current.current !== id) return;
      setState((s) => ({
        ...s,
        run: finished,
        status: finished.status,
        outcome: finished.outcome,
        runError: finished.error,
        result,
        cancelling: false,
        settled: true,
      }));
    } catch (e) {
      if (current.current !== id) return;
      setState((s) => ({ ...s, requestError: asError(e), settled: true }));
    }
  }, []);

  const follow = useCallback(
    (run: RunRecord) => {
      stop();
      current.current = run.id;
      setState((s) => ({
        ...s,
        run,
        status: liveStatus(run.status),
        cancelling: run.status === "cancelling" ? true : s.cancelling,
        outcome: run.outcome,
        runError: run.error,
        submitting: false,
      }));
      // A finished run's result is read at once; its events are still
      // replayed, for the stages and the log, but nothing waits on them.
      const finishedAlready = isTerminal(run.status);
      if (finishedAlready) void settle(run.id);
      unsubscribe.current = subscribeToRun(run.id, {
        onEvent: (e) => {
          if (current.current !== run.id) return;
          setState((s) => apply(s, e));
          if (e.event === "end" && !finishedAlready) void settle(run.id);
        },
        onError: (error) => {
          if (current.current !== run.id) return;
          if (finishedAlready) return; // the record and result above are the answer
          setState((s) => ({ ...s, requestError: error.error }));
        },
      });
    },
    [settle, stop],
  );

  const submit = useCallback(
    async (request: RunRequests[K], title?: string): Promise<RunRecord | null> => {
      stop();
      current.current = null;
      setState({ ...idle<K>(), submitting: true });
      try {
        const { run } = await createRun(kind, request, title);
        jobs?.track(run, "here");
        follow(run);
        return run;
      } catch (e) {
        setState({ ...idle<K>(), requestError: asError(e) });
        return null;
      }
    },
    [kind, follow, stop, jobs],
  );

  const cancel = useCallback(async () => {
    const id = current.current;
    if (!id) return;
    setState((s) => ({ ...s, cancelling: true }));
    try {
      await cancelRun(id);
    } catch (e) {
      // 409: it finished first. The stream will say how; nothing to undo.
      if (!(e instanceof ApiRequestError && e.status === 409)) {
        setState((s) => ({ ...s, cancelling: false, requestError: asError(e) }));
      }
    }
  }, []);

  const reset = useCallback(() => {
    stop();
    current.current = null;
    setState(idle<K>());
  }, [stop]);

  useEffect(() => {
    if (!existingRunId) return;
    let live = true;
    getRun(existingRunId).then(
      (run) => {
        if (!live) return;
        if (!isTerminal(run.status)) jobs?.track(run, "found");
        follow(run);
      },
      (e: unknown) => {
        if (live) setState({ ...idle<K>(), requestError: asError(e) });
      },
    );
    return () => {
      live = false;
      stop();
      current.current = null;
    };
    // `jobs` is stable for the provider's lifetime.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [existingRunId, follow, stop]);

  useEffect(() => stop, [stop]);

  // While this screen shows the run, its completion is not announced elsewhere.
  const viewingId = state.run?.id ?? null;
  useEffect(() => {
    if (!viewingId || !jobs) return;
    return jobs.markViewing(viewingId);
  }, [viewingId, jobs]);

  return { ...state, submit, cancel, reset };
}
