/**
 * /history: every run in the workspace, with its request, outcome and
 * files, to reopen, rerun, export or delete.
 *
 * Refused and negative runs are listed with their reasons and can be
 * filtered to, because "which of my questions did Caterva decline, and
 * why" is a question worth asking of a workspace. The selected run is in
 * the address (`?run=<id>`), so a link to a run in History survives a
 * reload. The search reads what the list shows (title, kind, id, how it
 * ended) and "/" puts the cursor in it; the arrow keys walk the list.
 *
 * Deleting takes the run out of the list at once and offers Undo; the
 * delete itself is held until the offer lapses (./workspace/trash.ts), so
 * an undo never needs a folder moved back by hand. When the settings ask
 * for it, the delete is confirmed in place first, never in a dialog. It
 * moves the run's folder to the workspace's trash folder and never touches
 * a file the run wrote into a folder of yours (CONTRACT.md 15).
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, ExternalLink, FileDown, RotateCw, Search, Trash2 } from "lucide-react";
import { type KeyboardEvent, useMemo, useRef, useState } from "react";
import { Link, useLocation } from "wouter";

import { createRun, downloadArtifact, downloadBundle, getRun, isTerminal, listRuns } from "@/api/runs";
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
import { plain, plural } from "@/lib/copy";
import { describeError } from "@/lib/errors";
import { elapsed, formatBytes, formatDateTime } from "@/lib/format";
import { modKey, useHotkey } from "@/lib/keyboard";
import { runHref, useJobActionsOptional } from "@/lib/jobs";
import { useSettings } from "@/lib/settings";
import { isToastShown, notify } from "@/lib/toast";

import { scheduleDelete, undoDelete, UNDO_MS, useHeldDeletes } from "./workspace/trash";
import "./workspace/workspace.css";

type Filter = "all" | "working" | "produced" | "refused" | "negative" | "network" | "failed";

const FILTERS: { value: Filter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "working", label: "Working" },
  { value: "produced", label: "Results" },
  { value: "refused", label: "Refused" },
  { value: "negative", label: "Negative" },
  { value: "network", label: "No answer" },
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
    case "network":
      return run.status === "done" && run.outcome?.meaning === "network";
    case "failed":
      return run.status === "failed" || run.status === "interrupted";
  }
}

/** Whether a run matches what was typed: every word somewhere in what the list shows of it. */
export function matchesSearch(run: RunSummary, query: string): boolean {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  if (!words.length) return true;
  const hay = [run.title, run.kind, run.id, run.status, run.outcome?.summary ?? "", run.outcome?.reason ?? "", run.outcome?.meaning ?? ""]
    .join(" ")
    .toLowerCase();
  return words.every((w) => hay.includes(w));
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
  const remove = () => {
    if (!run.data) return;
    const r = run.data;
    const toast = notify("info", `Moved to the trash: ${r.title}`, {
      description: "Undo keeps it here. Once this note goes, the run waits in the workspace's trash folder.",
      duration: UNDO_MS,
      action: {
        label: "Undo",
        onClick: () => {
          if (undoDelete(r.id)) notify("info", `Kept: ${r.title}`, { duration: 3000 });
        },
      },
    });
    scheduleDelete(
      r.id,
      r.title,
      (error) => {
        void client.invalidateQueries({ queryKey: ["runs"] });
        if (error) {
          notify("failed", "The run was not deleted", { description: describeError(error).message });
          return;
        }
        void client.invalidateQueries({ queryKey: ["capabilities"] });
        client.removeQueries({ queryKey: ["run", r.id] });
      },
      () => isToastShown(toast),
    );
    setConfirming(false);
    onDeleted();
  };
  const exportBundle = useMutation({
    mutationFn: () => downloadBundle(id),
    onError: (e) => notify("failed", "The bundle was not exported", { description: describeError(e).message }),
  });

  useCommand(
    run.data
      ? { id: "history.export", title: `Export ${run.data.title} as a bundle`, hint: `caterva-${id}.zip`, run: () => exportBundle.mutate() }
      : null,
  );
  useCommand(
    run.data && isTerminal(run.data.status)
      ? { id: "history.delete", title: `Delete ${run.data.title}`, hint: "moves it to the workspace's trash, with Undo", run: remove }
      : null,
  );
  const shownRun = run.data;
  useCommand(shownRun ? { id: "history.open", title: `Open ${shownRun.title} on its screen`, run: () => navigate(runHref(shownRun)) } : null);

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
            <span>Move this run and its files to the workspace&apos;s trash folder? Undo stays offered for a few seconds.</span>
            <button type="button" className="btn btn-sm btn-danger" onClick={remove}>
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
            disabled={live}
            title={live ? "A run that is still working cannot be deleted; cancel it first." : undefined}
            onClick={() => (askFirst ? setConfirming(true) : remove())}
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
          <p className="run-detail-summary">{plain(r.outcome.summary)}</p>
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

/** Up and down move between the rows of a list of run buttons; Home and End go to its ends. */
function walk(e: KeyboardEvent<HTMLDivElement>) {
  if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(e.key)) return;
  const rows = [...e.currentTarget.querySelectorAll<HTMLButtonElement>("button.run-row")];
  if (!rows.length) return;
  const at = rows.indexOf(document.activeElement as HTMLButtonElement);
  const next =
    e.key === "Home" ? 0 : e.key === "End" ? rows.length - 1 : e.key === "ArrowDown" ? Math.min(rows.length - 1, at + 1) : Math.max(0, at - 1);
  e.preventDefault();
  rows[next].focus();
  rows[next].click();
}

export default function HistoryScreen() {
  const [kind, setKind] = useState<RunKind | "">("");
  const [filter, setFilter] = useState<Filter>("all");
  const [query, setQuery] = useState("");
  const search = useRef<HTMLInputElement>(null);
  const shown = useShownRunId();
  const held = useHeldDeletes();
  const [, navigate] = useLocation();
  const all = useAllRuns(kind);
  const runs = useMemo(
    () => (all.data?.runs ?? []).filter((r) => !held.has(r.id) && matchesFilter(r, filter) && matchesSearch(r, query)),
    [all.data, filter, query, held],
  );
  const select = (id: string | null) => navigate(id ? `/history?run=${encodeURIComponent(id)}` : "/history", { replace: true });
  useHotkey({ key: "/" }, () => search.current?.focus());
  useCommand({ id: "history.search", title: "Search the runs", hint: "/", run: () => search.current?.focus() });
  const total = (all.data?.runs ?? []).filter((r) => !held.has(r.id)).length;

  const list = (
    <div className="history-list">
      <div className="history-filters">
        <label className="history-search">
          <Search size={13} aria-hidden="true" />
          <span className="sr-only">Search the runs</span>
          <input
            ref={search}
            className="input"
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Escape") setQuery("");
            }}
            placeholder="Search titles, kinds, reasons"
            spellCheck={false}
            autoComplete="off"
          />
          {query ? null : <kbd aria-hidden="true">/</kbd>}
        </label>
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
        <EmptyState title={total ? "No run matches" : "Nothing has run here yet"}>
          <p>
            {total
              ? "Search for other words, choose another filter, or every kind."
              : "Runs appear here as soon as they start, from any screen or the command palette."}
          </p>
        </EmptyState>
      ) : (
        <>
          <p className="history-count" aria-live="polite">
            {runs.length === total ? plural(total, "run") : `${runs.length} of ${plural(total, "run")}`}
            {all.data?.more ? ", older ones not read yet" : ""}
          </p>
          <div className="run-list" role="list" aria-label="Runs, newest first" onKeyDown={walk}>
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
        </>
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
          shown && !held.has(shown) ? (
            <RunDetail key={shown} id={shown} onDeleted={() => select(null)} />
          ) : (
            <EmptyState title="Choose a run">
              <p>
                Its request, outcome, files and the command that reproduces it appear here. The arrow keys walk the
                list; {modKey()} K finds any run by name.
              </p>
            </EmptyState>
          )
        }
      />
    </Screen>
  );
}
