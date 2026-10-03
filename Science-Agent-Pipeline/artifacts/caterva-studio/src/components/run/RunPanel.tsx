/**
 * A run, from submission to answer, drawn the same way on every screen.
 *
 * `RunPanel` takes the state `useRun` returns and chooses what to show:
 * the request the server refused before a run existed (400, 503), the
 * loading mark with the run's current stage label while it works, a crash,
 * a cancel, an interruption, or the finished outcome (a refusal, a
 * negative finding) followed by the screen's own drawing of the result.
 * The screen passes only how to draw its result; the states are shared.
 */
import { Square } from "lucide-react";
import { type ReactNode, useEffect, useState } from "react";

import { isTerminal } from "@/api/runs";
import type { RunKind, RunResults } from "@/api/types";
import type { RunState } from "@/api/useRun";
import { Disclosure } from "@/components/forms/Disclosure";
import { NameRefusalChoices } from "@/components/enzyme/NameRefusal";
import { CommandSlab } from "@/components/report/Report";
import { Loading } from "@/components/states/Loading";
import { EmptyState, ErrorState, OutcomeNotice, RunFailedState } from "@/components/states/States";
import { elapsed } from "@/lib/format";

function useNow(active: boolean): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return;
    const t = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(t);
  }, [active]);
  return now;
}

const STATUS_LABEL: Record<string, string> = {
  queued: "Waiting for a free worker",
  running: "Working",
};

export function RunProgress<K extends RunKind>({
  state,
  onCancel,
}: {
  state: RunState<K>;
  onCancel?: () => void;
}) {
  const live = !isTerminal(state.status) && state.status !== "idle";
  const now = useNow(live);
  const label = state.submitting
    ? "Sending the request"
    : state.cancelling
      ? "Cancelling: the current step finishes first"
      : (state.stage?.label ?? STATUS_LABEL[state.status] ?? "Working");
  const since = state.run?.started_at ?? state.run?.created_at ?? null;
  const time = since ? elapsed(since, null, now) : "";
  return (
    <div className="run-progress">
      <Loading
        label={label}
        fraction={state.cancelling ? null : (state.stage?.fraction ?? null)}
        detail={time ? `${time} elapsed` : undefined}
      />
      <div className="run-progress-meta">
        {state.stages.length > 1 ? (
          <ol className="run-stages" aria-label="Stages so far">
            {state.stages.map((s, i) => (
              <li key={`${s.stage}-${i}`} data-current={i === state.stages.length - 1 ? "true" : undefined}>
                {s.label}
              </li>
            ))}
          </ol>
        ) : null}
        {onCancel && live ? (
          <button type="button" className="btn btn-sm" onClick={onCancel} disabled={state.cancelling}>
            <Square size={11} aria-hidden="true" />
            {state.cancelling ? "Cancelling" : "Cancel"}
          </button>
        ) : null}
      </div>
      {state.log.length ? (
        <Disclosure title="What the command wrote" aside={<span className="font-mono">{state.log.length}</span>}>
          <pre className="report-text run-log">{state.log.join("\n")}</pre>
        </Disclosure>
      ) : null}
    </div>
  );
}

export function RunPanel<K extends RunKind>({
  state,
  onCancel,
  onRetry,
  onChooseEnzyme,
  idle,
  children,
}: {
  state: RunState<K>;
  onCancel?: () => void;
  onRetry?: () => void;
  /** Sets the form's enzyme when the person picks one of the candidates a refused name was given. */
  onChooseEnzyme?: (ec: string) => void;
  /** Shown before anything was submitted. */
  idle?: ReactNode;
  /** The screen's drawing of a finished result. */
  children: (result: RunResults[K]) => ReactNode;
}) {
  if (state.requestError) {
    return <ErrorState error={state.requestError} inset />;
  }
  if (state.status === "idle" && !state.submitting) return <>{idle ?? null}</>;
  if (state.submitting || !isTerminal(state.status) || (state.status === "done" && !state.settled)) {
    return <RunProgress state={state} onCancel={onCancel} />;
  }
  const retry = onRetry ? (
    <button type="button" className="btn btn-sm" onClick={onRetry}>
      Run it again
    </button>
  ) : undefined;
  const command = state.run?.cli?.length ? (
    <Disclosure title="The same run in a terminal">
      <CommandSlab argv={state.run.cli} />
    </Disclosure>
  ) : null;
  switch (state.status) {
    case "failed":
      return (
        <div className="run-finished">
          <RunFailedState error={state.runError ?? { type: "Error", message: "the run failed without a message" }} action={retry} />
          {command}
        </div>
      );
    case "cancelled":
      return (
        <EmptyState title="Cancelled" inset actions={retry}>
          <p>The run was stopped before it finished, so it kept no result.</p>
        </EmptyState>
      );
    case "abandoned":
      return (
        <ErrorState
          inset
          title="Abandoned, not stopped"
          error={{
            code: "unavailable",
            message:
              state.runError?.message ??
              "The run was asked to stop and did not. It may still be running in the background; its result was discarded.",
          }}
          action={retry}
        />
      );
    case "interrupted":
      return (
        <ErrorState
          inset
          title="Interrupted"
          error={{ code: "unavailable", message: state.runError?.message ?? "the studio stopped while this run was in progress" }}
          action={retry}
        />
      );
    default:
      return (
        <div className="run-finished">
          <OutcomeNotice outcome={state.outcome}>
            {state.outcome?.name_refusal ? <NameRefusalChoices refusal={state.outcome.name_refusal} onChoose={onChooseEnzyme} /> : null}
          </OutcomeNotice>
          {state.result !== null ? children(state.result) : null}
          {command}
        </div>
      );
  }
}
