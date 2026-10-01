/**
 * The pieces the four structure screens (Structure, Prepare, Dynamics,
 * Analyze) share: their form fields, the run area that shows a run's stage,
 * refusal or failure, the verdict word, the command that reproduces a run,
 * and the report the terminal prints.
 *
 * They compose the foundation's components (Loading, the states, Value)
 * rather than copying them; what is here is only what these screens need
 * beyond them. Every number still reaches the page as a SourcedValue and is
 * drawn by Value; nothing in this file formats a number.
 */
import MarkdownIt from "markdown-it";
import { type ReactNode, useId, useMemo, useState } from "react";

import { ApiRequestError, apiFetch } from "@/api/client";
import type { ApiError, Outcome, RunRecord, RunStatus } from "@/api/types";
import { Loading } from "@/components/states/Loading";
import { ErrorState, RefusalState } from "@/components/states/States";
import { chooseDirectory, chooseFile, isDesktop, reveal } from "@/lib/desktop";

/* ------------------------------------------------------------------ */
/* Form fields                                                         */
/* ------------------------------------------------------------------ */

export function FieldRow({
  label,
  hint,
  error,
  children,
  htmlFor,
}: {
  label: string;
  hint?: ReactNode;
  error?: string | null;
  children: ReactNode;
  htmlFor: string;
}) {
  const hintId = `${htmlFor}-hint`;
  return (
    <div className="grid gap-1">
      <label htmlFor={htmlFor} className="text-[13px] font-semibold text-fg">
        {label}
      </label>
      {children}
      {hint ? (
        <p id={hintId} className="m-0 text-[12.5px] leading-snug text-muted">
          {hint}
        </p>
      ) : null}
      {error ? (
        <p className="m-0 text-[12.5px] leading-snug text-danger" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}

const inputClass =
  "w-full rounded-[3px] border border-rule bg-surface px-2.5 py-1.5 text-[14px] text-fg " +
  "placeholder:text-muted/70 focus-visible:outline-2 focus-visible:outline-offset-1 " +
  "focus-visible:outline-[var(--focus)] aria-[invalid=true]:border-danger";

export function TextField({
  id,
  label,
  value,
  onChange,
  placeholder,
  hint,
  error,
  mono = false,
  autoFocus,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  hint?: ReactNode;
  error?: string | null;
  mono?: boolean;
  autoFocus?: boolean;
}) {
  return (
    <FieldRow label={label} hint={hint} error={error} htmlFor={id}>
      <input
        id={id}
        className={`${inputClass} ${mono ? "font-mono" : ""}`}
        value={value}
        placeholder={placeholder}
        spellCheck={false}
        autoComplete="off"
        autoFocus={autoFocus}
        aria-invalid={error ? true : undefined}
        aria-describedby={hint ? `${id}-hint` : undefined}
        onChange={(e) => onChange(e.target.value)}
      />
    </FieldRow>
  );
}

/** A number typed by the person; empty means "leave it to the command's default". */
export function NumberField({
  id,
  label,
  value,
  onChange,
  placeholder,
  hint,
  error,
  step = "any",
}: {
  id: string;
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  hint?: ReactNode;
  error?: string | null;
  step?: string;
}) {
  return (
    <FieldRow label={label} hint={hint} error={error} htmlFor={id}>
      <input
        id={id}
        className={`${inputClass} font-mono tabular-nums`}
        inputMode="decimal"
        type="number"
        step={step}
        value={value}
        placeholder={placeholder}
        aria-invalid={error ? true : undefined}
        aria-describedby={hint ? `${id}-hint` : undefined}
        onChange={(e) => onChange(e.target.value)}
      />
    </FieldRow>
  );
}

/** The number in a field, or undefined when it is empty or not a number. */
export function parsed(text: string): number | undefined {
  if (text.trim() === "") return undefined;
  const n = Number(text);
  return Number.isFinite(n) ? n : undefined;
}

export function CheckField({
  id,
  label,
  checked,
  onChange,
  hint,
}: {
  id: string;
  label: string;
  checked: boolean;
  onChange: (v: boolean) => void;
  hint?: ReactNode;
}) {
  return (
    <div className="grid gap-1">
      <label htmlFor={id} className="inline-flex items-center gap-2 text-[14px]">
        <input
          id={id}
          type="checkbox"
          className="size-4 accent-[var(--signal-deep)]"
          checked={checked}
          onChange={(e) => onChange(e.target.checked)}
        />
        {label}
      </label>
      {hint ? <p className="m-0 pl-6 text-[12.5px] leading-snug text-muted">{hint}</p> : null}
    </div>
  );
}

/**
 * An absolute path on this computer. Inside Caterva.app a button opens the
 * native panel; in a browser the path is typed (a page cannot learn a
 * folder's location).
 */
export function PathField({
  id,
  label,
  value,
  onChange,
  kind,
  purpose,
  extensions = [],
  hint,
  error,
  placeholder,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (v: string) => void;
  kind: "directory" | "file";
  purpose: string;
  extensions?: string[];
  hint?: ReactNode;
  error?: string | null;
  placeholder?: string;
}) {
  const desktop = isDesktop();
  return (
    <FieldRow label={label} hint={hint} error={error} htmlFor={id}>
      <div className="flex gap-2">
        <input
          id={id}
          className={`${inputClass} font-mono text-[13px]`}
          value={value}
          placeholder={placeholder}
          spellCheck={false}
          autoComplete="off"
          aria-invalid={error ? true : undefined}
          aria-describedby={hint ? `${id}-hint` : undefined}
          onChange={(e) => onChange(e.target.value)}
        />
        {desktop ? (
          <button
            type="button"
            className="btn-quiet shrink-0"
            onClick={async () => {
              const chosen =
                kind === "directory" ? await chooseDirectory(purpose) : await chooseFile(purpose, extensions);
              if (chosen) onChange(chosen);
            }}
          >
            Choose
          </button>
        ) : null}
      </div>
    </FieldRow>
  );
}

/** The one primary action of a form. */
export function PrimaryButton({ children, busy, disabled }: { children: ReactNode; busy?: boolean; disabled?: boolean }) {
  return (
    <button
      type="submit"
      disabled={disabled || busy}
      className={
        "inline-flex items-center justify-center rounded-[3px] bg-[var(--signal-deep)] px-4 py-2 text-[14px] " +
        "font-semibold text-[var(--surface)] transition-opacity duration-200 ease-[var(--ease-out-expo)] " +
        "hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
      }
    >
      {children}
    </button>
  );
}

/** The 400 for this field, when the server named it. */
export function fieldError(error: ApiError | null, field: string): string | null {
  return error && error.code === "malformed" && error.field === field ? error.message : null;
}

/* ------------------------------------------------------------------ */
/* A run's life on the page                                            */
/* ------------------------------------------------------------------ */

export interface RunView {
  run: RunRecord | null;
  status: RunStatus | "idle";
  stage: { label: string; fraction: number | null } | null;
  outcome: Outcome | null;
  requestError: ApiError | null;
  runError: { type: string; message: string } | null;
}

/**
 * Everything a run shows before its result: the mark in motion with the
 * stage the server reported, a request the server would not accept (a 400
 * under its field is shown by the form; anything else here), a crash, a
 * cancel, a refusal in the command's words. `children` renders the result
 * once there is one; a refusal that still produced a result shows both.
 */
export function RunArea({
  view,
  waiting,
  hasResult,
  children,
  fieldErrors = [],
}: {
  view: RunView;
  waiting: string;
  hasResult: boolean;
  children?: ReactNode;
  fieldErrors?: string[];
}) {
  const { status, stage, outcome, requestError, runError } = view;
  if (requestError) {
    if (requestError.code === "malformed" && requestError.field && fieldErrors.includes(requestError.field)) {
      return null;
    }
    return <ErrorState error={requestError} />;
  }
  if (status === "queued" || status === "running") {
    return (
      <div className="py-6">
        <Loading label={stage?.label ?? (status === "queued" ? "Waiting for a free worker" : waiting)} />
      </div>
    );
  }
  if (status === "failed" || status === "interrupted" || status === "cancelled") {
    const message =
      status === "cancelled"
        ? "The run was cancelled; a cancelled run keeps no result."
        : `${runError?.type ?? "Error"}: ${runError?.message ?? "the run stopped without saying why"}`;
    return (
      <ErrorState
        error={{ code: status === "failed" ? "crash" : "unavailable", message }}
      />
    );
  }
  if (status !== "done") return null;
  return (
    <>
      {outcome?.meaning === "refused" && outcome.reason ? <RefusalState reason={outcome.reason} /> : null}
      {hasResult ? children : null}
    </>
  );
}

/** The command a run reproduces in a terminal, as the server recorded it. */
export function CommandLine({ run }: { run: RunRecord | null }) {
  if (!run) return null;
  const text = run.cli.map(shellQuote).join(" ");
  return (
    <p className="m-0 flex flex-wrap items-baseline gap-x-2 text-[12.5px] text-muted">
      <span>In a terminal:</span>
      <code className="font-mono break-all text-fg">{text}</code>
    </p>
  );
}

export function shellQuote(arg: string): string {
  return /^[A-Za-z0-9_@%+=:,./-]+$/.test(arg) ? arg : `'${arg.replace(/'/g, `'\\''`)}'`;
}

/* ------------------------------------------------------------------ */
/* Words the library uses for its judgements                           */
/* ------------------------------------------------------------------ */

const STEADY = new Set(["consistent", "held", "kept", "agrees", "settled, protonated", "settled, deprotonated"]);

/**
 * A verdict word, set as the library wrote it. A word that means "this is a
 * result" is ink; anything else is the caution colour that means "read
 * twice". Never red: a negative finding is a finding.
 */
export function Verdict({ word }: { word: string }) {
  const steady = STEADY.has(word);
  return (
    <span
      className={`inline-block whitespace-nowrap rounded-[2px] px-1.5 py-px font-mono text-[12px] ${
        steady ? "bg-surface-raised text-fg" : "bg-[color-mix(in_oklch,var(--caution)_14%,transparent)] text-caution"
      }`}
    >
      {word}
    </span>
  );
}

/** "doi:10.x/y" and "PMID n" inside library prose, as links of the forms the contract allows. */
export function Linkified({ text }: { text: string }) {
  const parts: ReactNode[] = [];
  const re = /doi:(10\.\d{4,9}\/[^\s;,)]+[^\s;,.)])/g;
  let last = 0;
  for (let m = re.exec(text); m; m = re.exec(text)) {
    parts.push(text.slice(last, m.index));
    parts.push(
      <a key={m.index} href={`https://doi.org/${m[1]}`} target="_blank" rel="noreferrer noopener">
        doi:{m[1]}
      </a>,
    );
    last = m.index + m[0].length;
  }
  parts.push(text.slice(last));
  return <>{parts}</>;
}

/* ------------------------------------------------------------------ */
/* The terminal's own report                                           */
/* ------------------------------------------------------------------ */

const md = new MarkdownIt({ html: false, linkify: false, typographer: false });

export function TerminalReport({ text, markdown, title = "The report the terminal prints" }: {
  text: string;
  markdown: boolean;
  title?: string;
}) {
  const html = useMemo(() => (markdown ? md.render(text) : ""), [markdown, text]);
  return (
    <details className="group border-t border-rule pt-3">
      <summary className="cursor-pointer select-none text-[13px] font-semibold text-muted hover:text-fg">
        {title}
      </summary>
      {markdown ? (
        <div className="report-md mt-3 max-w-[80ch] overflow-x-auto text-[13.5px]" dangerouslySetInnerHTML={{ __html: html }} />
      ) : (
        <pre className="mt-3 overflow-x-auto whitespace-pre font-mono text-[12.5px] leading-relaxed">{text}</pre>
      )}
    </details>
  );
}

/* ------------------------------------------------------------------ */
/* Files                                                               */
/* ------------------------------------------------------------------ */

/** Download a run's artifact (the session header rides on the request, never in a URL). */
export function ArtifactButton({ runId, name, label }: { runId: string; name: string; label: string }) {
  const [error, setError] = useState<string | null>(null);
  return (
    <span className="inline-flex items-baseline gap-2">
      <button
        type="button"
        className="btn-quiet"
        onClick={async () => {
          setError(null);
          try {
            const response = await apiFetch(
              `/api/runs/${encodeURIComponent(runId)}/artifacts/${encodeURIComponent(name)}`,
            );
            const url = URL.createObjectURL(await response.blob());
            const a = document.createElement("a");
            a.href = url;
            a.download = name;
            a.click();
            setTimeout(() => URL.revokeObjectURL(url), 1000);
          } catch (e) {
            setError(e instanceof ApiRequestError ? e.error.message : String(e));
          }
        }}
      >
        {label}
      </button>
      {error ? <span className="text-[12.5px] text-danger">{error}</span> : null}
    </span>
  );
}

/** A path the run wrote on this computer: shown, never served; revealed in Finder inside the app. */
export function WrittenPath({ path }: { path: string }) {
  return (
    <span className="inline-flex flex-wrap items-baseline gap-2">
      <code className="font-mono text-[12.5px] break-all">{path}</code>
      {isDesktop() ? (
        <button type="button" className="btn-quiet" onClick={() => void reveal(path)}>
          Show in Finder
        </button>
      ) : null}
    </span>
  );
}

/* ------------------------------------------------------------------ */
/* Layout                                                              */
/* ------------------------------------------------------------------ */

/** A titled part of a result: a heading on a hairline, an aside on the same line. Not a card. */
export function Part({ title, aside, children }: { title: string; aside?: ReactNode; children: ReactNode }) {
  const id = useId();
  return (
    <section aria-labelledby={id} className="grid gap-3">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 border-b border-rule pb-1.5">
        <h2 id={id} className="m-0 text-[1.15rem] leading-tight">
          {title}
        </h2>
        {aside ? <div className="text-[12.5px] text-muted">{aside}</div> : null}
      </div>
      {children}
    </section>
  );
}

/** A dense table of results; the caller supplies the rows. */
export function Table({ caption, head, children }: { caption?: string; head: ReactNode[]; children: ReactNode }) {
  return (
    <div className="overflow-x-auto">
      <table className="data-table w-full border-collapse text-[13.5px]">
        {caption ? <caption className="sr-only">{caption}</caption> : null}
        <thead>
          <tr>
            {head.map((h, i) => (
              <th
                key={i}
                scope="col"
                className="border-b border-rule px-2 py-1.5 text-left align-bottom text-[12px] font-semibold text-muted first:pl-0"
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}

export const td = "border-b border-rule px-2 py-1.5 align-top first:pl-0";
