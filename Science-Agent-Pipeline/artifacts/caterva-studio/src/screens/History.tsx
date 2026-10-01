/**
 * /history: every run in the workspace, with its request, outcome and
 * files, to reopen, rerun, export or delete.
 *
 * Refused and negative runs are listed with their reasons and can be
 * filtered to, because "which of my questions did Caterva decline, and
 * why" is a question worth asking of a workspace. The selected run is in
 * the address (`?run=<id>`), so a link to a run in History survives a
 * reload. Deleting asks once, in place, when the settings say to; it
 * removes the run's folder in the workspace and never a file the run wrote
 * into a folder of yours (CONTRACT.md 15).
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, ExternalLink, FileDown, RotateCw, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useLocation } from "wouter";

import { createRun, deleteRun, downloadArtifact, downloadBundle, getRun, isTerminal, listRuns } from "@/api/runs";
import type { RunKind, RunRecord, RunSummary } from "@/api/types";
import { Disclosure } from "@/components/forms/Disclosure";
import { Select } from "@/components/forms/Field";
import { Segmented } from "@/components/forms/Segmented";
import { Split } from "@/components/layout/Split";
import { useCommand } from "@/components/palette/commands";
import { CommandSlab } from "@/components/report/Report";
import { RunRow } from "@/components/run/RunRow";
import { Screen, Section } from "@/components/screen/Screen";
import { RunStatusMark, runStatusLabel } from "@/components/shell/RunStatusMark";
import { useShownRunId } from "@/components/shell/TopBar";
import { Loading, SkeletonRows } from "@/components/states/Loading";
import { EmptyState, ErrorState, OutcomeNotice, RunFailedState } from "@/components/states/States";
import { describeError } from "@/lib/errors";
import { elapsed, formatBytes, formatDateTime } from "@/lib/format";
import { runHref, useJobActionsOptional } from "@/lib/jobs";
import { useSettings } from "@/lib/settings";
import { notify } from "@/lib/toast";

type Filter = "all" | "working" | "produced" | "refused" | "negative" | "failed";

const FILTERS: { value: Filter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "working", label: "Working" },
  { value: "produced", label: "Results" },
  { value: "refused", label: "Refused" },
  { value: "negative", label: "Negative" },
  { value: "failed", label: "Failed" },
];

const KINDS: RunKind[] = [
  "compose",
  "constants",
  "sim",
  "bind",
  "structure",
  "prepare",
  "md.setup",
  "md.summarise",
  "analyze",
  "fep.status",
  "complex.check",
  "rates",
];

export function matchesFilter(run: RunSummary, filter: Filter): boolean {
  switch (filter) {
    case "all":
      return true;
    case "working":
      return !isTerminal(run.status);
    case "produced":
      return run.status === "done" && run.outcome?.meaning === "produced";
    case "refused":
      return run.status === "done" && run.outcome?.meaning === "refused";
    case "negative":
      return run.status === "done" && run.outcome?.meaning === "negative";
    case "failed":
      return run.status === "failed" || run.status === "interrupted";
  }
}

const PAGE = 50;

function useAllRuns(kind: RunKind | "") {
  const [pages, setPages] = useState(1);
  const query = useQuery({
    queryKey: ["runs", "history", kind, pages],
    queryFn: async () => {
      const out: RunSummary[] = [];
      let cursor: string | null = null;
      let more = false;
      for (let p = 0; p < pages; p++) {
        const page = await listRuns({ kind: kind || undefined, limit: PAGE, cursor });
        out.push(...page.runs);
        cursor = page.next_cursor;
        more = cursor !== null;
        if (!more) break;
      }
      return { runs: out, more };
    },
    placeholderData: (prev) => prev,
  });
  return { ...query, loadMore: () => setPages((p) => p + 1) };
}

function RunDetail({ id, onDeleted }: { id: string; onDeleted: () => void }) {
  const client = useQueryClient();
  const jobs = useJobActionsOptional();
  const [, navigate] = useLocation();
  const settings = useSettings();
  const [confirming, setConfirming] = useState(false);
  const run = useQuery({ queryKey: ["run", id], queryFn: () => getRun(id) });

  const rerun = useMutation({
    mutationFn: (r: RunRecord) => createRun(r.kind, r.request as never, r.title),
    onSuccess: ({ run: created }) => {
      jobs?.track(created, "here");
      void client.invalidateQueries({ queryKey: ["runs"] });
      navigate(runHref(created));
    },
    onError: (e) => notify("failed", "The run was not started again", { description: describeError(e).message }),
  });
  const remove = useMutation({
    mutationFn: () => deleteRun(id),
    onSuccess: (removed) => {
      void client.invalidateQueries({ queryKey: ["runs"] });
      void client.invalidateQueries({ queryKey: ["capabilities"] });
      client.removeQueries({ queryKey: ["run", id] });
      notify("info", `Deleted: ${removed.title}`);
      onDeleted();
    },
    onError: (e) => notify("failed", "The run was not deleted", { description: describeError(e).message }),
  });
  const exportBundle = useMutation({
    mutationFn: () => downloadBundle(id),
    onError: (e) => notify("failed", "The bundle was not exported", { description: describeError(e).message }),
  });

  useCommand(
    run.data
      ? { id: "history.export", title: `Export ${run.data.title} as a bundle`, hint: `caterva-${id}.zip`, run: () => exportBundle.mutate() }
      : null,
  );

  if (run.isPending) return <Loading label="Reading the run" />;
  if (run.isError) return <ErrorState error={run.error} />;
  const r = run.data;
  const live = !isTerminal(r.status);
  const askFirst = settings.data?.confirm_delete ?? true;

  return (
    <article className="run-detail" aria-label={r.title}>
      <header className="run-detail-head">
        <RunStatusMark status={r.status} meaning={r.outcome?.meaning ?? null} />
        <div>
          <h2 className="run-detail-title">{r.title}</h2>
          <p className="run-detail-meta font-mono">
            {r.kind} · {runStatusLabel(r.status, r.outcome?.meaning ?? null)} · {formatDateTime(r.created_at)}
            {r.finished_at ? ` · ${elapsed(r.started_at ?? r.created_at, r.finished_at)}` : ""} · caterva {r.caterva_version}
          </p>
        </div>
      </header>
      <div className="run-detail-actions">
        <Link href={runHref(r)} className="btn btn-sm btn-primary">
          <ExternalLink size={13} aria-hidden="true" />
          Open
        </Link>
        <button type="button" className="btn btn-sm" onClick={() => rerun.mutate(r)} disabled={rerun.isPending}>
          <RotateCw size={13} aria-hidden="true" />
          {rerun.isPending ? "Starting" : "Run again"}
        </button>
        <button type="button" className="btn btn-sm" onClick={() => exportBundle.mutate()} disabled={exportBundle.isPending}>
          <FileDown size={13} aria-hidden="true" />
          Export bundle
        </button>
        {confirming ? (
          <span className="confirm-inline" role="group" aria-label="Confirm deleting this run">
            <span>Delete this run and its files in the workspace?</span>
            <button type="button" className="btn btn-sm btn-danger" onClick={() => remove.mutate()} disabled={remove.isPending}>
              Delete
            </button>
            <button type="button" className="btn btn-sm btn-quiet" onClick={() => setConfirming(false)}>
              Keep it
            </button>
          </span>
        ) : (
          <button
            type="button"
            className="btn btn-sm btn-danger"
            disabled={live || remove.isPending}
            title={live ? "A run that is still working cannot be deleted; cancel it first." : undefined}
            onClick={() => (askFirst ? setConfirming(true) : remove.mutate())}
          >
            <Trash2 size={13} aria-hidden="true" />
            Delete
          </button>
        )}
      </div>

      {r.status === "failed" && r.error ? <RunFailedState error={r.error} /> : null}
      {r.status === "interrupted" && r.error ? (
        <ErrorState inset title="Interrupted" error={{ code: "unavailable", message: r.error.message }} />
      ) : null}
      {r.outcome ? (
        r.outcome.meaning === "produced" ? (
          <p className="run-detail-summary">{r.outcome.summary}</p>
        ) : (
          <OutcomeNotice outcome={r.outcome} />
        )
      ) : null}

      <Section title="The same run in a terminal">
        <CommandSlab argv={r.cli} />
      </Section>

      {r.artifacts.length ? (
        <Section title="Files" aside={<span className="font-mono">{r.artifacts.length}</span>}>
          <ul className="artifact-list">
            {r.artifacts.map((a) => (
              <li key={a.name}>
                <button
                  type="button"
                  className="artifact"
                  onClick={() =>
                    void downloadArtifact(r.id, a.name).catch((e: unknown) =>
                      notify("failed", `${a.name} was not saved`, { description: describeError(e).message }),
                    )
                  }
                >
                  <Download size={13} aria-hidden="true" />
                  <span className="font-mono">{a.name}</span>
                  <span className="muted">{a.description}</span>
                  <span className="font-mono muted">{formatBytes(a.bytes)}</span>
                </button>
              </li>
            ))}
          </ul>
        </Section>
      ) : null}

      <Disclosure title="The request as the server accepted it">
        <pre className="report-text">{JSON.stringify(r.request, null, 2)}</pre>
      </Disclosure>
    </article>
  );
}

export default function HistoryScreen() {
  const [kind, setKind] = useState<RunKind | "">("");
  const [filter, setFilter] = useState<Filter>("all");
  const shown = useShownRunId();
  const [, navigate] = useLocation();
  const all = useAllRuns(kind);
  const runs = useMemo(() => (all.data?.runs ?? []).filter((r) => matchesFilter(r, filter)), [all.data, filter]);
  const select = (id: string | null) => navigate(id ? `/history?run=${encodeURIComponent(id)}` : "/history", { replace: true });

  const list = (
    <div className="history-list">
      <div className="history-filters">
        <Segmented<Filter> label="Show" size="sm" value={filter} onChange={setFilter} options={FILTERS} />
        <label className="sr-only" htmlFor="history-kind">
          Kind of run
        </label>
        <Select id="history-kind" value={kind} onChange={(e) => setKind(e.target.value as RunKind | "")} className="history-kind">
          <option value="">Every kind</option>
          {KINDS.map((k) => (
            <option key={k} value={k}>
              {k}
            </option>
          ))}
        </Select>
      </div>
      {all.isPending ? (
        <SkeletonRows rows={7} label="Reading the workspace" />
      ) : all.isError ? (
        <ErrorState error={all.error} />
      ) : runs.length === 0 ? (
        <EmptyState title={all.data?.runs.length ? "No run matches" : "Nothing has run here yet"}>
          <p>
            {all.data?.runs.length
              ? "Choose another filter, or every kind."
              : "Runs appear here as soon as they start, from any screen or the command palette."}
          </p>
        </EmptyState>
      ) : (
        <div className="run-list" role="list" aria-label="Runs, newest first">
          {runs.map((r) => (
            <div role="listitem" key={r.id}>
              <RunRow run={r} selected={r.id === shown} onSelect={() => select(r.id)} />
            </div>
          ))}
          {all.data?.more ? (
            <button type="button" className="btn btn-sm history-more" onClick={all.loadMore} disabled={all.isFetching}>
              {all.isFetching ? "Reading" : "Older runs"}
            </button>
          ) : null}
        </div>
      )}
    </div>
  );

  return (
    <Screen title="History" purpose="Every run, its request, its outcome and its files, to reopen, rerun or export.">
      <Split
        id="history"
        firstSize={40}
        first={list}
        second={
          shown ? (
            <RunDetail key={shown} id={shown} onDeleted={() => select(null)} />
          ) : (
            <EmptyState title="Choose a run">
              <p>Its request, outcome, files and the command that reproduces it appear here.</p>
            </EmptyState>
          )
        }
      />
    </Screen>
  );
}
