/**
 * What the four kinetics screens (Compose, Constants, Stochastic, Binding)
 * share beyond the foundation's components: the form | result layout, the
 * form frame with its keyboard submit, the toolbar every finished run
 * carries (its permalink, its exports, its bundle), and the two ways a form
 * is filled before anyone types: from a run being reopened (`?run=<id>`,
 * so a permalink shows the question beside its answer) and from a link
 * that carries the question (`/compose?subject=2.7.1.1&...`, which Home's
 * first questions and Constants' "Use in Compose" write).
 *
 * Nothing here runs anything on its own: a prefilled form waits for its
 * button. The run panel delegates every state but a finished result to the
 * foundation's RunPanel, so a refusal, a crash, a cancel or an interruption
 * reads the same on every screen; a screen draws its own finished result
 * because only it knows what comes first (Compose's verdict, a negative
 * finding's verdict on Binding).
 */
import { Check as CheckIcon, Download, FileArchive, Link2 } from "lucide-react";
import { type FormEvent, type ReactNode, useEffect, useRef, useState } from "react";
import { useLocation, useSearch } from "wouter";

import { downloadFrom } from "@/api/client";
import { downloadArtifact, downloadBundle } from "@/api/runs";
import type { RunKind, RunRecord, RunResults } from "@/api/types";
import type { RunState } from "@/api/useRun";
import { Disclosure } from "@/components/forms/Disclosure";
import { FormActions } from "@/components/forms/Field";
import { Split } from "@/components/layout/Split";
import { useCommand } from "@/components/palette/commands";
import { CommandSlab } from "@/components/report/Report";
import { RunPanel } from "@/components/run/RunPanel";
import { describeError } from "@/lib/errors";
import { formatBytes } from "@/lib/format";
import { modKey, useHotkey } from "@/lib/keyboard";
import { notify } from "@/lib/toast";

/** The comma- or line-separated names in a text field, trimmed, empties dropped. */
export function names(text: string): string[] {
  return text
    .split(/[,\n]/)
    .map((s) => s.trim())
    .filter(Boolean);
}

/** The run a screen was opened on (`?run=<id>`); the server checks the id against its pattern. */
export function useReopenedRun(): string | null {
  return new URLSearchParams(useSearch()).get("run");
}

/** The question a link carried, as text fields: only `keys`, only non-empty values. */
export function useLinkedQuestion(keys: readonly string[]): Record<string, string> | null {
  const search = useSearch();
  const params = new URLSearchParams(search);
  if (params.get("run")) return null;
  const out: Record<string, string> = {};
  for (const k of keys) {
    const v = params.get(k);
    if (v && v.trim()) out[k] = v.trim().slice(0, 500);
  }
  return Object.keys(out).length ? out : null;
}

/**
 * Fill a form once from what the address carries: the request of the run
 * being reopened (when it arrives) or the linked question. A later reopen
 * of a different run fills it again; typing in between is kept otherwise.
 */
export function usePrefill(
  run: RunRecord | null,
  reopened: string | null,
  linked: Record<string, string> | null,
  fromRequest: (request: Record<string, unknown>) => void,
  fromLink: (fields: Record<string, string>) => void,
): void {
  const filled = useRef<string | null>(null);
  const linkKey = linked ? JSON.stringify(linked) : null;
  useEffect(() => {
    if (reopened && run && run.id === reopened && filled.current !== `run:${run.id}`) {
      filled.current = `run:${run.id}`;
      fromRequest(run.request);
    }
    // The callbacks are recreated each render; the ids above decide when to fill.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reopened, run?.id]);
  useEffect(() => {
    if (linked && linkKey && filled.current !== `link:${linkKey}`) {
      filled.current = `link:${linkKey}`;
      fromLink(linked);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [linkKey]);
}

/**
 * Once a run submitted here exists, the address becomes its permalink
 * (`<path>?run=<id>`, replacing the linked question rather than adding a
 * history entry), so a reload or a copied address reopens this run instead
 * of filling the form for a new one.
 */
export function useRunAddress(path: string, run: RunRecord | null, reopened: string | null): void {
  const [, navigate] = useLocation();
  const id = run?.id ?? null;
  useEffect(() => {
    if (id && id !== reopened) navigate(`${path}?run=${encodeURIComponent(id)}`, { replace: true });
    // navigate is stable; the run id is what decides.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);
}

/** A request value read back as text for a form field ("" when absent). */
export function text(v: unknown): string {
  return typeof v === "string" ? v : typeof v === "number" && Number.isFinite(v) ? String(v) : "";
}

/** The screen's form beside its result; the panes stack below 1100 px. */
export function KineticsLayout({ id, form, result }: { id: string; form: ReactNode; result: ReactNode }) {
  return (
    <Split
      id={id}
      firstSize={34}
      minFirst={26}
      minSecond={40}
      first={<div className="k-form-pane">{form}</div>}
      second={
        <div className="k-result-pane" aria-live="polite">
          {result}
        </div>
      }
    />
  );
}

/**
 * The form frame: Enter in a field, and Cmd-Enter (Ctrl-Enter) anywhere on
 * the screen, submit; while the run works the primary action becomes Cancel. The
 * same submit is registered in the command palette under `label`.
 */
export function RunForm({
  id,
  label,
  hint,
  onSubmit,
  running,
  onCancel,
  disabled = false,
  children,
}: {
  /** The palette command id, e.g. "compose.submit". */
  id: string;
  label: string;
  /** A second line for the palette entry. */
  hint?: string;
  onSubmit: () => void;
  running: boolean;
  onCancel?: () => void;
  disabled?: boolean;
  children: ReactNode;
}) {
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!running && !disabled) onSubmit();
  };
  // Anywhere on the screen, not only inside the form: WebKit does not focus a
  // button or checkbox on click, so a key pressed after ticking a box would
  // otherwise land on the page and be lost. Not inside an open dialog (the
  // command palette has its own Enter).
  useHotkey(
    { key: "Enter", mod: true },
    (e) => {
      if (e.target instanceof Element && e.target.closest("dialog, [role='dialog']")) return;
      if (!running && !disabled) onSubmit();
    },
  );
  useCommand({ id, title: label, hint, run: onSubmit, disabled: running || disabled });
  return (
    <form className="k-form" onSubmit={submit} aria-label={label} noValidate>
      {children}
      <FormActions>
        <button type="submit" className="btn btn-primary" disabled={running || disabled}>
          {label}
        </button>
        {running && onCancel ? (
          <button type="button" className="btn" onClick={onCancel}>
            Cancel
          </button>
        ) : (
          <span className="k-shortcut" aria-hidden="true">
            <kbd>{modKey()}</kbd>
            <kbd>Enter</kbd>
          </span>
        )}
      </FormActions>
    </form>
  );
}

/** A group of fields under a small heading, without a box around it. */
export function FieldGroup({ title, children, aside }: { title: string; children: ReactNode; aside?: ReactNode }) {
  return (
    <fieldset className="k-group">
      <legend className="k-group-title">
        {title}
        {aside ? <span className="k-group-aside">{aside}</span> : null}
      </legend>
      <div className="k-group-body">{children}</div>
    </fieldset>
  );
}

function failed(what: string) {
  return (e: unknown) => notify("failed", `${what} was not saved`, { description: describeError(e).message });
}

/** The path that opens a run on its screen, and the full address while this server runs. */
export function permalink(path: string, run: Pick<RunRecord, "id">): { path: string; url: string } {
  const p = `${path}?run=${encodeURIComponent(run.id)}`;
  return { path: p, url: `${window.location.origin}${p}` };
}

export function CopyLink({ path, run }: { path: string; run: RunRecord }) {
  const [copied, setCopied] = useState(false);
  const link = permalink(path, run);
  return (
    <button
      type="button"
      className="btn btn-sm"
      title={`${link.path}: opens this run while this studio is running; History opens it in any later session`}
      onClick={() => {
        void navigator.clipboard?.writeText(link.url).then(
          () => {
            setCopied(true);
            window.setTimeout(() => setCopied(false), 1600);
          },
          () => setCopied(false),
        );
      }}
    >
      {copied ? <CheckIcon size={13} aria-hidden="true" /> : <Link2 size={13} aria-hidden="true" />}
      {copied ? "Link copied" : "Copy link"}
    </button>
  );
}

export interface ExportChoice {
  /** What the reader recognises: "SBML", "CSV". */
  label: string;
  /** The run's recorded artifact, or "result.json" for the API's result itself. */
  artifact: string;
  description?: string;
}

/**
 * A finished run's toolbar: the permalink, each export as a real download
 * (the server's recorded file, fetched with the session header and saved
 * as a Blob, which the macOS shell turns into a save panel), and the
 * bundle of everything.
 */
export function RunToolbar({ path, run, exports = [] }: { path: string; run: RunRecord; exports?: ExportChoice[] }) {
  return (
    <div className="k-toolbar" role="toolbar" aria-label="This run">
      <CopyLink path={path} run={run} />
      {exports.length ? (
        <span className="k-toolbar-group" role="group" aria-label="Export">
          <span className="k-toolbar-label">Export</span>
          {exports.map((x) => (
            <button
              key={x.artifact}
              type="button"
              className="btn btn-sm"
              title={x.description}
              onClick={() =>
                void (x.artifact === "result.json"
                  ? downloadFrom(`/api/runs/${encodeURIComponent(run.id)}/result`, `caterva-${run.id}-result.json`)
                  : downloadArtifact(run.id, x.artifact)
                ).catch(failed(x.label))
              }
            >
              <Download size={13} aria-hidden="true" />
              {x.label}
            </button>
          ))}
        </span>
      ) : null}
      <button
        type="button"
        className="btn btn-sm btn-quiet"
        title={`caterva-${run.id}.zip: the request, the result, every event and file, and the command`}
        onClick={() => void downloadBundle(run.id).catch(failed("The bundle"))}
      >
        <FileArchive size={13} aria-hidden="true" />
        Bundle (.zip)
      </button>
    </div>
  );
}

/** Every file a run wrote, each one a download, with what it is. */
export function RunFiles({ run }: { run: RunRecord }) {
  if (run.artifacts.length === 0) return null;
  return (
    <Disclosure title="Files this run wrote" aside={<span className="font-mono">{run.artifacts.length}</span>}>
      <ul className="artifact-list">
        {run.artifacts.map((a) => (
          <li key={a.name}>
            <button type="button" className="artifact" onClick={() => void downloadArtifact(run.id, a.name).catch(failed(a.name))}>
              <Download size={13} aria-hidden="true" />
              <span className="font-mono">{a.name}</span>
              <span className="muted">{a.description}</span>
              <span className="font-mono muted">{formatBytes(a.bytes)}</span>
            </button>
          </li>
        ))}
      </ul>
    </Disclosure>
  );
}

/**
 * A run on a kinetics screen. Everything but a finished result is the
 * foundation's RunPanel (progress with the stage labels, the 400 under the
 * form's fields, crash, cancel, interruption, a refusal with no result).
 * A finished result is drawn by `children`, between the toolbar and the
 * files, so each screen decides what reads first.
 */
export function KineticsRun<K extends RunKind>({
  state,
  path,
  idle,
  exports,
  onRetry,
  children,
}: {
  state: RunState<K> & { cancel: () => Promise<void> };
  /** The screen's route, for the permalink. */
  path: string;
  idle: ReactNode;
  exports?: (result: RunResults[K], run: RunRecord) => ExportChoice[];
  onRetry?: () => void;
  children: (result: RunResults[K], run: RunRecord) => ReactNode;
}) {
  const finished =
    state.status === "done" && state.settled && state.result !== null && state.run !== null && !state.requestError;
  if (!finished) {
    return (
      <RunPanel state={state} onCancel={() => void state.cancel()} onRetry={onRetry} idle={idle}>
        {() => null}
      </RunPanel>
    );
  }
  const run = state.run as RunRecord;
  const result = state.result as RunResults[K];
  return (
    <div className="k-result">
      <RunToolbar path={path} run={run} exports={exports ? exports(result, run) : []} />
      {children(result, run)}
      <div className="k-result-foot">
        <RunFiles run={run} />
        <Disclosure title="The same run in a terminal">
          <CommandSlab argv={run.cli} />
        </Disclosure>
      </div>
    </div>
  );
}
