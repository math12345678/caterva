/**
 * What a kinetics screen shows beside its form, for each state of a run.
 *
 *   idle            the screen's own empty state
 *   queued/running  the mark's dots in motion with the stage the server
 *                   last reported ("Looking up reaction_Km in BRENDA's km
 *                   table for EC 1.1.1.27"), never a generic spinner
 *   400 and friends the error, in the server's words
 *   failed          the crash's type and message
 *   refused         the command's reason, as a finding; with the result
 *                   underneath when the command still produced one
 *   negative        the result, whose own verdict says what was negative
 *   done            the result
 *
 * Every finished run also shows the command that reproduces it and the
 * files it wrote.
 */
import { useState, type ReactNode } from "react";

import { apiFetch } from "@/api/client";
import { cancelRun } from "@/api/runs";
import type { RunState } from "@/api/useRun";
import type { ArtifactInfo, RunKind, RunRecord, RunResults } from "@/api/types";
import { Loading } from "@/components/states/Loading";
import { ErrorState, RefusalState } from "@/components/states/States";

/** One argument as a POSIX shell would need it written. */
export function shellQuote(arg: string): string {
  if (arg !== "" && /^[A-Za-z0-9_@%+=:,./-]+$/.test(arg)) return arg;
  return `'${arg.replace(/'/g, `'"'"'`)}'`;
}

export function CommandLine({ cli }: { cli: string[] }) {
  const text = cli.map(shellQuote).join(" ");
  const [copied, setCopied] = useState(false);
  return (
    <section className="k-section" aria-label="The command that reproduces this run">
      <div className="k-actions">
        <h3 className="k-section-sub">The same run in a terminal, from the repository root</h3>
        <button
          type="button"
          className="k-button k-button-quiet"
          onClick={() => {
            void navigator.clipboard?.writeText(text).then(() => setCopied(true));
          }}
        >
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <pre className="k-command">{text}</pre>
    </section>
  );
}

async function download(runId: string, artifact: ArtifactInfo): Promise<void> {
  const response = await apiFetch(
    `/api/runs/${encodeURIComponent(runId)}/artifacts/${encodeURIComponent(artifact.name)}`,
  );
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = artifact.name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 30_000);
}

export function Artifacts({ run }: { run: RunRecord }) {
  const [failure, setFailure] = useState<string | null>(null);
  if (run.artifacts.length === 0) return null;
  return (
    <section className="k-section" aria-label="Files this run wrote">
      <h3 className="k-section-title">Files</h3>
      <ul className="k-list" style={{ listStyle: "none", paddingLeft: 0 }}>
        {run.artifacts.map((a) => (
          <li key={a.name} className="k-actions">
            <button
              type="button"
              className="k-button k-button-quiet k-code"
              onClick={() => {
                setFailure(null);
                download(run.id, a).catch((e: unknown) => setFailure(String(e)));
              }}
            >
              {a.name}
            </button>
            <span className="k-small k-muted">{a.description}</span>
          </li>
        ))}
      </ul>
      {failure ? <p className="k-field-error">{failure}</p> : null}
    </section>
  );
}

export function RunView<K extends RunKind>({
  state,
  empty,
  children,
}: {
  state: RunState<K>;
  empty: ReactNode;
  children: (result: RunResults[K], run: RunRecord) => ReactNode;
}) {
  const { status, stage, requestError, runError, outcome, result, run } = state;

  if (requestError) return <ErrorState error={requestError} />;
  if (status === "idle" || !run) return <>{empty}</>;
  if (status === "queued" || status === "running") {
    return <Loading label={stage?.label ?? (status === "queued" ? "Waiting for a free worker" : "Starting")} />;
  }
  if (status === "failed" || status === "interrupted" || status === "cancelled") {
    const error = runError ?? {
      type: status === "cancelled" ? "Cancelled" : "Interrupted",
      message: status === "cancelled" ? "The run was cancelled; a cancelled run keeps no result." : "The run stopped.",
    };
    return (
      <div className="k-result">
        <ErrorState error={{ code: "crash", message: `${error.type}: ${error.message}` }} />
        <CommandLine cli={run.cli} />
      </div>
    );
  }
  // done
  return (
    <div className="k-result">
      {outcome?.meaning === "refused" && outcome.reason ? (
        <RefusalState title={result ? "Refused in part, and why" : "Refused, and why"} reason={outcome.reason} />
      ) : null}
      {result ? children(result as RunResults[K], run) : null}
      <Artifacts run={run} />
      <CommandLine cli={run.cli} />
    </div>
  );
}

/** Cancel the run a state is following, when it is still going. */
export function cancelling(state: { run: RunRecord | null; status: string }): (() => void) | undefined {
  if (!state.run || (state.status !== "queued" && state.status !== "running")) return undefined;
  const id = state.run.id;
  return () => {
    void cancelRun(id);
  };
}
