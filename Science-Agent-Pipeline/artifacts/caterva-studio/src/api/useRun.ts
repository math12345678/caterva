/**
 * useRun: submit a run, follow its events, fetch its result.
 *
 * The one hook every science screen uses, so each shows the same stages
 * (the SSE `stage` labels under the loading mark), the same refusal and
 * the same failure. Skeleton from the contract (owner: ui); screens may
 * rely on the returned fields, which the ui owner keeps.
 */
import { useCallback, useEffect, useRef, useState } from "react";

import { ApiRequestError } from "./client";
import { createRun, followRun, getResult, getRun, type RunEvent } from "./runs";
import type { ApiError, Outcome, RunError, RunKind, RunRecord, RunRequests, RunResults, RunStatus } from "./types";

export interface RunState<K extends RunKind> {
  run: RunRecord | null;
  status: RunStatus | "idle";
  stage: { label: string; fraction: number | null } | null;
  log: string[];
  outcome: Outcome | null;
  result: RunResults[K] | null;
  /** A request the server refused before a run existed (400 malformed, ...). */
  requestError: ApiError | null;
  /** A run that crashed, was cancelled or was interrupted. */
  runError: RunError | null;
}

const IDLE = {
  run: null,
  status: "idle",
  stage: null,
  log: [],
  outcome: null,
  result: null,
  requestError: null,
  runError: null,
} as const;

export function useRun<K extends RunKind>(kind: K, existingRunId?: string | null) {
  const [state, setState] = useState<RunState<K>>(IDLE as unknown as RunState<K>);
  const abort = useRef<AbortController | null>(null);

  const follow = useCallback(async (run: RunRecord) => {
    abort.current?.abort();
    const controller = new AbortController();
    abort.current = controller;
    setState((s) => ({ ...s, run, status: run.status, outcome: run.outcome, runError: run.error }));
    const onEvent = (e: RunEvent) => {
      setState((s) => {
        switch (e.event) {
          case "status":
            return { ...s, status: e.data.status, outcome: e.data.outcome ?? s.outcome };
          case "stage":
            return { ...s, stage: { label: e.data.label, fraction: e.data.fraction } };
          case "log":
            return { ...s, log: [...s.log, e.data.line] };
          case "result":
            return { ...s, outcome: e.data.outcome };
          case "error":
            return { ...s, runError: e.data.error };
          case "end":
            return { ...s, status: e.data.status };
        }
      });
    };
    try {
      await followRun(run.id, onEvent, controller.signal);
      const finished = await getRun(run.id);
      let result: RunResults[K] | null = null;
      if (finished.status === "done") {
        try {
          result = await getResult<K>(run.id);
        } catch (e) {
          // A refused run may have no result; its outcome says why.
          if (!(e instanceof ApiRequestError && e.status === 404)) throw e;
        }
      }
      setState((s) => ({ ...s, run: finished, status: finished.status, outcome: finished.outcome, runError: finished.error, result }));
    } catch (e) {
      if (controller.signal.aborted) return;
      const error = e instanceof ApiRequestError ? e.error : { code: "crash" as const, message: String(e) };
      setState((s) => ({ ...s, requestError: error }));
    }
  }, []);

  const submit = useCallback(
    async (request: RunRequests[K], title?: string) => {
      setState(IDLE as unknown as RunState<K>);
      try {
        const { run } = await createRun(kind, request, title);
        await follow(run);
      } catch (e) {
        const error = e instanceof ApiRequestError ? e.error : { code: "crash" as const, message: String(e) };
        setState({ ...(IDLE as unknown as RunState<K>), requestError: error });
      }
    },
    [kind, follow],
  );

  useEffect(() => {
    if (!existingRunId) return;
    getRun(existingRunId).then(follow, (e: unknown) => {
      const error = e instanceof ApiRequestError ? e.error : { code: "crash" as const, message: String(e) };
      setState((s) => ({ ...s, requestError: error }));
    });
    return () => abort.current?.abort();
  }, [existingRunId, follow]);

  return { ...state, submit };
}
