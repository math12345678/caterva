/**
 * What the four structure screens (Structures, Prepare, Dynamics, Analyze)
 * need beyond the foundation's components, and nothing the foundation
 * already has: a path field that opens the native panel inside Caterva.app,
 * a verdict word set as the library wrote it, a run artifact downloaded
 * with the session header, a path the run wrote shown (never served), the
 * query parameter a screen was opened with, and the form | result frame
 * every one of them uses.
 *
 * Forms, fields, the run's states, tables, the viewer, charts and the
 * report are the foundation's (src/components); these screens compose them
 * and keep no copy. Nothing in this file formats a number: every number is
 * a SourcedValue drawn by Value.
 */
import { FolderOpen } from "lucide-react";
import { type FormEvent, type ReactNode, useEffect, useId, useRef, useState } from "react";
import { useSearch } from "wouter";

import { ApiRequestError, apiFetch } from "@/api/client";
import type { RunKind, RunResults } from "@/api/types";
import type { RunState } from "@/api/useRun";
import { Field, FormActions, TextInput } from "@/components/forms/Field";
import { Split } from "@/components/layout/Split";
import { useCommand } from "@/components/palette/commands";
import { RunAnnouncer, RunPanel } from "@/components/run/RunPanel";
import { chooseDirectory, chooseFile, isDesktop, reveal } from "@/lib/desktop";
import { modKey, useHotkey } from "@/lib/keyboard";

/** One query parameter of the current location (`?pdb=1I10`), or null. */
export function useParam(name: string): string | null {
  return new URLSearchParams(useSearch()).get(name);
}

/**
 * Refill a form from the request of the run it was opened on (`?run=` from
 * History), once that run's record has arrived, so a reopened run can be
 * changed and asked again rather than retyped. Values are written back as
 * the text the form holds; nothing is computed.
 */
export function useRefill(
  reopened: string | null,
  run: { id: string; request: Record<string, unknown> } | null,
  apply: (request: Record<string, unknown>) => void,
): void {
  const done = useRef<string | null>(null);
  const latest = useRef(apply);
  latest.current = apply;
  useEffect(() => {
    if (!reopened || !run || run.id !== reopened || done.current === reopened) return;
    done.current = reopened;
    latest.current(run.request);
  }, [reopened, run]);
}

/** A request value as the text a form field holds. */
export function text(v: unknown): string {
  return v === undefined || v === null ? "" : String(v);
}

export function busy(state: { status: string; submitting: boolean }): boolean {
  return state.submitting || state.status === "queued" || state.status === "running";
}

/**
 * The frame of a structure screen: the form in the first pane, the run in
 * the second (the foundation's Split, stacked below 1100 px). The form's
 * primary action is the submit button, Cmd-Enter from anywhere on the
 * screen, and an entry in the command palette.
 */
export function RunScreen<K extends RunKind>({
  kind: _kind,
  id,
  form,
  action,
  canSubmit,
  blockedReason,
  retryVerb,
  onSubmit,
  run,
  idle,
  children,
  formLabel,
  firstSize = 30,
  active = true,
  onChooseEnzyme,
}: {
  /** The run's kind; it fixes the result type the children draw. */
  kind: K;
  id: string;
  form: ReactNode;
  /** The primary action's name: "Search", "Audit", "Write setup", "Analyze". */
  action: string;
  canSubmit: boolean;
  /** Why the button is not available while `canSubmit` is false ("Choose an enzyme first"), shown under it. */
  blockedReason?: string;
  /** Finishes "Check the network, then ...", for an outage's message. */
  retryVerb?: string;
  onSubmit: () => void;
  run: RunState<NoInfer<K>> & { cancel: () => Promise<void> };
  idle: ReactNode;
  children: (result: RunResults[NoInfer<K>]) => ReactNode;
  formLabel: string;
  firstSize?: number;
  /** False while the screen shows another of its panels (Dynamics' tabs): no hotkey, no palette entry. */
  active?: boolean;
  /** Sets the form's enzyme when the person picks one of the candidates a refused name was given. */
  onChooseEnzyme?: (ec: string) => void;
}) {
  const working = busy(run);
  const whyId = useId();
  const resultRoot = useRef<HTMLDivElement>(null);
  const why = working ? "A run is in progress." : !canSubmit ? blockedReason : undefined;
  const submit = () => {
    if (canSubmit && !working) onSubmit();
  };
  useHotkey({ key: "Enter", mod: true }, submit, active);
  useCommand(active ? {
    id: `${id}.submit`,
    title: action,
    hint: working ? "a run is in progress" : canSubmit ? `${modKey()} Enter on this screen` : "fill in the form first",
    disabled: working || !canSubmit,
    run: submit,
  } : null);
  useCommand(
    working && active
      ? { id: `${id}.cancel`, title: `Cancel: ${action}`, hint: "the current step finishes first", run: () => void run.cancel() }
      : null,
  );
  return (
    <Split
      id={id}
      firstSize={firstSize}
      minFirst={22}
      first={
        <form
          className="st-form"
          aria-label={formLabel}
          onSubmit={(e: FormEvent) => {
            e.preventDefault();
            submit();
          }}
        >
          {form}
          <FormActions>
            <button
              type="submit"
              className="btn btn-primary"
              aria-disabled={!canSubmit || working}
              aria-describedby={why ? whyId : undefined}
            >
              {action}
            </button>
            <span className="field-hint">
              <kbd className="kbd">{modKey()}</kbd> <kbd className="kbd">Enter</kbd>
            </span>
          </FormActions>
          {why ? (
            <p className="form-why" id={whyId}>
              {why}
            </p>
          ) : null}
        </form>
      }
      second={
        <div className="st-result" ref={resultRoot}>
          <RunAnnouncer state={run} root={resultRoot} />
          <RunPanel
            state={run}
            onCancel={() => void run.cancel()}
            onRetry={submit}
            retryVerb={retryVerb}
            onChooseEnzyme={onChooseEnzyme}
            idle={idle}
          >
            {(result) => children(result)}
          </RunPanel>
        </div>
      }
    />
  );
}

/**
 * An absolute path on this computer. Inside Caterva.app a button opens the
 * native panel; in a browser the path is typed, because a page cannot learn
 * where a folder is (CONTRACT.md 15 and 16). The server checks it either
 * way and a refusal lands under this field.
 */
export function PathField({
  label,
  value,
  onChange,
  kind,
  purpose,
  extensions = [],
  hint,
  error,
  placeholder,
  optional,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  kind: "directory" | "file";
  purpose: string;
  extensions?: string[];
  hint?: ReactNode;
  error?: string | null;
  placeholder?: string;
  optional?: boolean;
}) {
  const desktop = isDesktop();
  return (
    <Field label={label} hint={hint} error={error} optional={optional}>
      <span className="st-path">
        <TextInput mono value={value} placeholder={placeholder} onChange={(e) => onChange(e.target.value)} />
        {desktop ? (
          <button
            type="button"
            className="btn"
            onClick={async () => {
              const chosen = kind === "directory" ? await chooseDirectory(purpose) : await chooseFile(purpose, extensions);
              if (chosen) onChange(chosen);
            }}
          >
            <FolderOpen size={14} aria-hidden="true" />
            Choose
          </button>
        ) : null}
      </span>
    </Field>
  );
}

const STEADY = new Set([
  "consistent",
  "held",
  "kept",
  "kept its face",
  "agrees",
  "hydrated",
  "formed",
  "settled, protonated",
  "settled, deprotonated",
]);

/**
 * A verdict word, as the library wrote it. A word that is a result is set
 * in ink; anything else ("not yet a result", "replicas disagree", "moved")
 * in the caution colour that means "read twice". Never red: a negative
 * finding is a finding.
 */
export function Verdict({ word }: { word: string }) {
  return (
    <span className="chip" data-tone={STEADY.has(word) ? undefined : "caution"}>
      {word}
    </span>
  );
}

/** "doi:10.x/y" inside the library's prose, linked through the DOI resolver (CONTRACT.md 9). */
export function Linkified({ text }: { text: string }) {
  const parts: ReactNode[] = [];
  const re = /doi:(10\.\d{4,9}\/[^\s;,)]+[^\s;,.)])/g;
  let last = 0;
  for (let m = re.exec(text); m; m = re.exec(text)) {
    parts.push(text.slice(last, m.index));
    parts.push(
      <a key={m.index} href={`https://doi.org/${m[1]}`} target="_blank" rel="noopener noreferrer">
        doi:{m[1]}
      </a>,
    );
    last = m.index + m[0].length;
  }
  parts.push(text.slice(last));
  return <>{parts}</>;
}

/** Download one of a run's artifacts. The session header rides on the request, never in a URL. */
export function ArtifactButton({ runId, name, label }: { runId: string; name: string; label: string }) {
  const [error, setError] = useState<string | null>(null);
  return (
    <span className="st-inline">
      <button
        type="button"
        className="btn btn-sm"
        onClick={async () => {
          setError(null);
          try {
            const response = await apiFetch(`/api/runs/${encodeURIComponent(runId)}/artifacts/${encodeURIComponent(name)}`);
            const url = URL.createObjectURL(await response.blob());
            const a = document.createElement("a");
            a.href = url;
            a.download = name;
            document.body.appendChild(a);
            a.click();
            a.remove();
            setTimeout(() => URL.revokeObjectURL(url), 30_000);
          } catch (e) {
            setError(e instanceof ApiRequestError ? e.error.message : String(e));
          }
        }}
      >
        {label}
      </button>
      {error ? <span className="field-error">{error}</span> : null}
    </span>
  );
}

/** A path the run wrote on this computer: shown, never served; revealed in Finder inside the app. */
export function WrittenPath({ path }: { path: string }) {
  return (
    <span className="st-inline">
      <code className="font-mono st-path-text">{path}</code>
      {isDesktop() ? (
        <button type="button" className="btn btn-sm btn-quiet" onClick={() => void reveal(path)}>
          Show in Finder
        </button>
      ) : null}
    </span>
  );
}

/**
 * A table cell's controls (a value's provenance button, a link) kept to
 * themselves: a click or Enter on them must not also select the row the
 * table makes selectable.
 */
export function Own({ children }: { children: ReactNode }) {
  return (
    <span onClick={(e) => e.stopPropagation()} onKeyDown={(e) => e.stopPropagation()}>
      {children}
    </span>
  );
}

/** A residue as people write it: "His192". */
export function residueName(resname: string | null, resseq: string | number): string {
  const r = resname ?? "?";
  return `${r.charAt(0)}${r.slice(1).toLowerCase()}${resseq}`;
}

/** An entry title the PDB stores in capitals, in sentence case; any other title as it is. */
export function sentenceCase(title: string): string {
  if (title !== title.toUpperCase()) return title;
  const lower = title.toLowerCase();
  return lower.charAt(0).toUpperCase() + lower.slice(1);
}
