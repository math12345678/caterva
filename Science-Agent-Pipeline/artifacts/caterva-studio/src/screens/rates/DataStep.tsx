/**
 * Step one of Rates: your measurements.
 *
 * A table gets in three ways, all of which end in the same text: dropped on
 * the page, chosen with the button (a real <button> and a real file input,
 * so the keyboard and a screen reader get the same door as the mouse), or
 * pasted with Ctrl or Cmd V anywhere on the screen while focus is not in a
 * field (a spreadsheet's clipboard is tab-separated text). The browser reads
 * the file as text and sends the text; no path leaves the page, and the
 * server decides what the text is.
 *
 * What comes back is shown plainly: every parse decision as a sentence,
 * every problem by line and column, the table itself with its columns' roles
 * as controls on the headings, and the units with the conversion written
 * out. Nothing is dropped or repaired without a sentence saying so. The
 * result of reading a table is announced once, in a polite live region, so a
 * screen-reader user hears "Read 23 measurements" and not every keystroke.
 */
import { AlertTriangle, ClipboardPaste, FileUp, FlaskConical } from "lucide-react";
import { type ChangeEvent, type DragEvent, useCallback, useEffect, useId, useRef, useState } from "react";

import type { RatesMapping, RatesPreview, RatesUnitReading } from "@/api/types";
import { RATES_MAX_BYTES, RATES_MAX_ROWS } from "@/api/types";
import { Disclosure } from "@/components/forms/Disclosure";
import { Select, TextArea, TextInput } from "@/components/forms/Field";
import { modKey } from "@/lib/keyboard";
import { cn } from "@/lib/cn";

import {
  announcement,
  CONCENTRATION_TARGETS,
  RATE_TARGETS,
  readFile,
  readPasted,
  ROLE_CHOICES,
  roleOf,
  type Source,
  unitLabel,
  withRole,
} from "./model";
import { PUROMYCIN_SOURCE } from "./puromycin";

function typingInto(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName);
}

export function DropZone({
  onSource,
  onExample,
  compact,
  disabled,
}: {
  onSource: (source: Source) => void;
  onExample: () => void;
  compact: boolean;
  disabled?: boolean;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [typed, setTyped] = useState("");
  const boxId = useId();

  const take = useCallback(
    (result: { ok: true; source: Source } | { ok: false; message: string }) => {
      if (result.ok) {
        setMessage(null);
        onSource(result.source);
      } else {
        setMessage(result.message);
      }
    },
    [onSource],
  );

  // Ctrl or Cmd V anywhere on the screen, unless focus is in a field (where paste means paste into it).
  useEffect(() => {
    if (disabled) return;
    const onPaste = (e: ClipboardEvent) => {
      if (typingInto(e.target) || typingInto(document.activeElement)) return;
      const text = e.clipboardData?.getData("text/plain") ?? "";
      if (!text) return;
      e.preventDefault();
      take(readPasted(text));
    };
    document.addEventListener("paste", onPaste);
    return () => document.removeEventListener("paste", onPaste);
  }, [take, disabled]);

  const onFiles = async (files: FileList | null) => {
    const file = files?.[0];
    if (!file) return;
    take(await readFile(file));
  };
  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setOver(false);
    void onFiles(e.dataTransfer.files);
  };
  const clipboard = async () => {
    try {
      take(readPasted(await navigator.clipboard.readText()));
    } catch {
      setMessage(`This browser did not let the page read the clipboard. Press ${modKey()} V on this screen, or paste into the box below.`);
    }
  };

  return (
    <div className="r-intake" data-compact={compact ? "true" : undefined}>
      <div
        className="r-drop"
        data-over={over ? "true" : undefined}
        onDragEnter={(e) => {
          e.preventDefault();
          setOver(true);
        }}
        onDragOver={(e) => {
          e.preventDefault();
          setOver(true);
        }}
        onDragLeave={(e) => {
          if (e.currentTarget === e.target) setOver(false);
        }}
        onDrop={onDrop}
      >
        <FileUp size={compact ? 16 : 22} aria-hidden="true" className="r-drop-icon" />
        <div className="r-drop-text">
          <p className="r-drop-title">{compact ? "Use another table" : "Drop a CSV, TSV or text file here"}</p>
          {compact ? null : (
            <p className="r-drop-hint">
              or paste the cells from your spreadsheet: press <kbd>{modKey()}</kbd> <kbd>V</kbd> anywhere on this screen. The file is read in
              this browser and sent to this computer only.
            </p>
          )}
        </div>
        <div className="r-drop-actions">
          <button type="button" className="btn btn-primary" onClick={() => input.current?.click()} disabled={disabled}>
            <FileUp size={14} aria-hidden="true" />
            Choose a file
          </button>
          <button type="button" className="btn" onClick={() => void clipboard()} disabled={disabled}>
            <ClipboardPaste size={14} aria-hidden="true" />
            Paste from clipboard
          </button>
          <button type="button" className="btn" onClick={onExample} disabled={disabled}>
            <FlaskConical size={14} aria-hidden="true" />
            Open an example
          </button>
        </div>
        <input
          ref={input}
          type="file"
          className="sr-only"
          tabIndex={-1}
          aria-label="Choose a CSV, TSV or text file of initial rates"
          accept=".csv,.tsv,.txt,.dat,text/csv,text/tab-separated-values,text/plain"
          onChange={(e: ChangeEvent<HTMLInputElement>) => {
            void onFiles(e.target.files);
            e.target.value = "";
          }}
        />
      </div>
      {message ? (
        <p className="r-intake-error" role="alert">
          <AlertTriangle size={14} aria-hidden="true" />
          {message}
        </p>
      ) : null}
      {compact ? null : (
        <>
          <p className="r-limits">
            Up to {RATES_MAX_ROWS.toLocaleString("en-US")} rows and {Math.round(RATES_MAX_BYTES / 1024)} kB. The example is {PUROMYCIN_SOURCE}.
          </p>
          <Disclosure title="Type or paste into a box instead">
            <div className="r-typed">
              <label htmlFor={boxId} className="field-label">
                Table text
              </label>
              <TextArea
                id={boxId}
                rows={6}
                className="r-typed-box"
                value={typed}
                onChange={(e) => setTyped(e.target.value)}
                placeholder={"[S] (mM)\tv0 (uM/min)\n0.5\t12.1\n1\t20.3"}
              />
              <p className="field-hint">Columns separated by tabs, commas or semicolons; a header with units reads best, as in [S] (mM).</p>
              <button
                type="button"
                className="btn btn-sm"
                disabled={!typed.trim()}
                onClick={() => {
                  const r = readPasted(typed);
                  if (r.ok) r.source.origin = "typed";
                  take(r);
                }}
              >
                Use this text
              </button>
            </div>
          </Disclosure>
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// The table as read
// ---------------------------------------------------------------------------

export function PreviewTable({ preview, mapping, onMapping }: { preview: RatesPreview; mapping: RatesMapping; onMapping: (m: RatesMapping) => void }) {
  const { columns, preview: table } = preview;
  const flaggedLines = new Set(table.rows.filter((r) => Object.keys(r.flags).length).map((r) => r.line));
  return (
    <div className="r-table-wrap" role="region" aria-label="The table as read" tabIndex={0}>
      <table className="r-table">
        <caption className="sr-only">
          The first {table.shown} of {table.total} rows, with the role each column plays. Cells marked with a warning are listed under the table.
        </caption>
        <thead>
          <tr>
            <th scope="col" className="r-line">
              Line
            </th>
            {columns.map((c) => (
              <th key={c.index} scope="col" data-role={c.role ?? "none"}>
                <label className="sr-only" htmlFor={`role-${c.index}`}>
                  Role of column {c.index + 1}, {c.header || c.name}
                </label>
                <Select id={`role-${c.index}`} value={roleOf(mapping, c.index)} onChange={(e) => onMapping(withRole(mapping, c.index, e.target.value))}>
                  {ROLE_CHOICES.map((r) => (
                    <option key={r.value} value={r.value}>
                      {r.label}
                    </option>
                  ))}
                </Select>
                <span className="r-colname">{c.header || c.name}</span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {table.rows.map((row, i) => {
            const prev = table.rows[i - 1];
            const gap = prev && row.line - prev.line > 1 && flaggedLines.has(row.line);
            return (
              <tr key={row.line} data-used={row.used ? "true" : "false"} data-gap={gap ? "true" : undefined}>
                <td className="r-line">
                  {row.line}
                  {row.used ? null : <span className="r-skipped"> skipped</span>}
                </td>
                {row.cells.map((cell, k) => {
                  const flag = row.flags[String(k)];
                  return (
                    <td key={k} data-flag={flag ? "true" : undefined} title={flag}>
                      {cell}
                      {flag ? (
                        <span className="sr-only">
                          {" "}
                          (problem: {flag})
                        </span>
                      ) : null}
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
      {table.total > table.shown ? (
        <p className="r-more">
          {table.shown} of {table.total} rows shown: the first rows, and every row with a problem. All {table.total} are read.
        </p>
      ) : null}
    </div>
  );
}

function UnitControl({
  role,
  label,
  reading,
  mapping,
  onMapping,
  targets,
}: {
  role: "substrate" | "rate" | "inhibitor";
  label: string;
  reading: RatesUnitReading | undefined;
  mapping: RatesMapping;
  onMapping: (m: RatesMapping) => void;
  targets: readonly string[];
}) {
  const given = mapping.units?.[role] ?? reading?.given ?? "";
  const [text, setText] = useState(given ?? "");
  useEffect(() => setText(given ?? ""), [given]);
  const id = useId();
  const commit = () => {
    if (text !== given) onMapping({ ...mapping, units: { ...(mapping.units ?? {}), [role]: text.trim() || null } });
  };
  const key = role === "inhibitor" ? "substrate" : role;
  const target = mapping.target?.[key] ?? "";
  const convertible = Boolean(reading?.convertible);
  return (
    <div className="r-unit" data-problem={reading?.problem ? "true" : undefined}>
      <label className="field-label" htmlFor={id}>
        {label}
      </label>
      <div className="r-unit-row">
        <TextInput
          id={id}
          mono
          list={`${id}-list`}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onBlur={commit}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              commit();
            }
          }}
          aria-invalid={reading?.problem ? true : undefined}
          aria-describedby={`${id}-note`}
          placeholder={role === "rate" ? "uM/min" : "mM"}
        />
        <datalist id={`${id}-list`}>
          {(role === "rate" ? RATE_TARGETS : CONCENTRATION_TARGETS).map((u) => (
            <option key={u} value={u} />
          ))}
        </datalist>
        {role !== "inhibitor" ? (
          <>
            <span className="r-unit-arrow" aria-hidden="true">
              to
            </span>
            <Select
              aria-label={`Express the ${label.toLowerCase()} in`}
              value={target}
              disabled={!convertible}
              onChange={(e) => onMapping({ ...mapping, target: { ...(mapping.target ?? {}), [key]: e.target.value || null } })}
            >
              <option value="">as given</option>
              {targets.map((u) => (
                <option key={u} value={u}>
                  {unitLabel(u)}
                </option>
              ))}
            </Select>
          </>
        ) : null}
      </div>
      <p className="field-hint" id={`${id}-note`}>
        {reading?.problem
          ? reading.problem
          : reading?.read_as && reading.factor !== 1
            ? `Read as ${unitLabel(reading.read_as)}; every value is multiplied by ${reading.factor} to give ${unitLabel(reading.target ?? "")}.`
            : reading?.read_as
              ? `Read as ${unitLabel(reading.read_as)}${convertible ? "" : ", a unit with no molar conversion: fitted as given, and not comparable with a cited constant"}.`
              : "Name the unit: every constant the fit reports inherits it."}
      </p>
    </div>
  );
}

export function Units({ preview, mapping, onMapping }: { preview: RatesPreview; mapping: RatesMapping; onMapping: (m: RatesMapping) => void }) {
  const roles = new Set(preview.columns.map((c) => c.role));
  return (
    <div className="r-units">
      <UnitControl role="substrate" label="Substrate unit" reading={preview.units.substrate} mapping={mapping} onMapping={onMapping} targets={CONCENTRATION_TARGETS} />
      <UnitControl role="rate" label="Rate unit" reading={preview.units.rate} mapping={mapping} onMapping={onMapping} targets={RATE_TARGETS} />
      {roles.has("inhibitor") ? (
        <UnitControl role="inhibitor" label="Inhibitor unit" reading={preview.units.inhibitor} mapping={mapping} onMapping={onMapping} targets={CONCENTRATION_TARGETS} />
      ) : null}
    </div>
  );
}

const DELIMITERS = [
  ["tab", "tabs"],
  ["comma", "commas"],
  ["semicolon", "semicolons"],
  ["pipe", "vertical bars"],
  ["space", "spaces"],
] as const;

export function FormatControls({ preview, mapping, onMapping }: { preview: RatesPreview; mapping: RatesMapping; onMapping: (m: RatesMapping) => void }) {
  const f = (preview.format ?? {}) as Record<string, unknown>;
  const reread = (change: Partial<RatesMapping>) =>
    onMapping({ delimiter: String(f.delimiter ?? "auto"), decimal: String(f.decimal ?? "auto"), header: Boolean(f.header), ...change });
  return (
    <div className="r-format">
      <div className="field">
        <label className="field-label" htmlFor="r-delimiter">
          Fields are separated by
        </label>
        <Select id="r-delimiter" value={String(f.delimiter ?? "comma")} onChange={(e) => reread({ delimiter: e.target.value })}>
          {DELIMITERS.map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </Select>
      </div>
      <div className="field">
        <label className="field-label" htmlFor="r-decimal">
          Decimals are written with
        </label>
        <Select id="r-decimal" value={String(f.decimal ?? ".")} onChange={(e) => reread({ decimal: e.target.value })}>
          <option value=".">a point (0.5)</option>
          <option value=",">a comma (0,5)</option>
        </Select>
      </div>
      <div className="field">
        <label className="field-label" htmlFor="r-header">
          The first row is
        </label>
        <Select id="r-header" value={f.header ? "yes" : "no"} onChange={(e) => reread({ header: e.target.value === "yes" })}>
          <option value="yes">a header (names and units)</option>
          <option value="no">data (no header)</option>
        </Select>
      </div>
    </div>
  );
}

export function Problems({ preview }: { preview: RatesPreview }) {
  if (preview.problems.length === 0) return null;
  const blocking = preview.problems.filter((p) => p.severity === "blocking");
  const skipped = preview.problems.filter((p) => p.severity === "skipped");
  const notes = preview.problems.filter((p) => p.severity === "note");
  const groups: [string, typeof blocking][] = [
    ["Stops the fit", blocking],
    ["Skipped, and left out of the fit", skipped],
    ["Noted", notes],
  ];
  return (
    <div className="r-problems">
      {groups.map(([title, list]) =>
        list.length ? (
          <div key={title} className="r-problem-group" data-kind={title.startsWith("Stops") ? "blocking" : title.startsWith("Skipped") ? "skipped" : "note"}>
            <h4 className="r-problem-title">
              <AlertTriangle size={13} aria-hidden="true" />
              {title}
              <span className="font-mono"> {list.length}</span>
            </h4>
            <ul>
              {list.map((p, i) => (
                <li key={i}>
                  <span className="font-mono r-where">
                    {p.line !== null ? `line ${p.line}` : "table"}
                    {p.column ? `, ${p.column}` : ""}
                  </span>{" "}
                  {p.message}
                </li>
              ))}
            </ul>
          </div>
        ) : null,
      )}
      {preview.problems_total > preview.problems.length ? (
        <p className="r-more">{preview.problems_total - preview.problems.length} more are not listed here.</p>
      ) : null}
    </div>
  );
}

export function Decisions({ preview }: { preview: RatesPreview }) {
  return (
    <div className="r-decisions">
      <h4 className="r-minor">How it was read</h4>
      <ul>
        {preview.decisions.map((d, i) => (
          <li key={i}>{d}</li>
        ))}
      </ul>
    </div>
  );
}

export function Summary({ preview }: { preview: RatesPreview }) {
  const s = preview.summary;
  if (!s) return null;
  return (
    <dl className="r-summary">
      <div>
        <dt>Measurements used</dt>
        <dd className="font-mono">{s.rows_used}</dd>
      </div>
      <div>
        <dt>Distinct conditions</dt>
        <dd className="font-mono">{s.conditions}</dd>
      </div>
      <div>
        <dt>Replicate rows</dt>
        <dd className="font-mono">{s.replicate_rows}</dd>
      </div>
      <div>
        <dt>Skipped</dt>
        <dd className="font-mono">{s.rows_skipped}</dd>
      </div>
      {s.groups.length ? (
        <div>
          <dt>Groups</dt>
          <dd>
            {s.groups.map((g) => (
              <span key={g.label} className="r-chip">
                {g.label} <span className="font-mono">{g.rows}</span>
              </span>
            ))}
          </dd>
        </div>
      ) : null}
      <div>
        <dt>Substrate range</dt>
        <dd className="font-mono">
          {s.lowest_substrate} to {s.highest_substrate} {s.substrate_unit}
        </dd>
      </div>
    </dl>
  );
}

export function DataStep({
  source,
  preview,
  pending,
  error,
  mapping,
  onMapping,
  onSource,
  onExample,
}: {
  source: Source | null;
  preview: RatesPreview | undefined;
  pending: boolean;
  error: string | null;
  mapping: RatesMapping;
  onMapping: (m: RatesMapping) => void;
  onSource: (s: Source) => void;
  onExample: () => void;
}) {
  const [announced, setAnnounced] = useState("");
  const last = useRef<RatesPreview | null>(null);
  useEffect(() => {
    if (preview && preview !== last.current && source) {
      last.current = preview;
      setAnnounced(announcement(preview));
    }
  }, [preview, source]);
  useEffect(() => {
    if (!source) {
      last.current = null;
      setAnnounced("");
    }
  }, [source]);
  const origin =
    source?.origin === "example"
      ? `Example: ${PUROMYCIN_SOURCE}`
      : source?.origin === "paste"
        ? "Pasted text"
        : source?.origin === "typed"
          ? "Typed text"
          : source?.origin === "run"
            ? `Restored from the run${source.filename ? `: ${source.filename}` : ""}`
            : source?.filename
              ? source.filename
              : null;
  return (
    <div className="r-data">
      <p className="sr-only" role="status" aria-live="polite">
        {announced}
      </p>
      <DropZone onSource={onSource} onExample={onExample} compact={Boolean(source)} />
      {source ? (
        <div className="r-read" aria-busy={pending ? "true" : undefined}>
          <p className="r-origin">
            <span className="font-mono">{origin}</span>
            {preview?.shape ? <span className="r-chip">{preview.shape} layout</span> : null}
            {pending ? <span className="muted"> reading</span> : null}
          </p>
          {source.note ? <p className="r-note">{source.note}</p> : null}
          {error ? (
            <p className="r-intake-error" role="alert">
              <AlertTriangle size={14} aria-hidden="true" />
              {error}
            </p>
          ) : null}
          {preview ? (
            <>
              {preview.refusal && !preview.columns.length ? (
                <p className="r-refusal" role="alert">
                  <AlertTriangle size={14} aria-hidden="true" />
                  {preview.refusal}
                </p>
              ) : (
                <>
                  <PreviewTable preview={preview} mapping={mapping} onMapping={onMapping} />
                  <Units preview={preview} mapping={mapping} onMapping={onMapping} />
                  <Summary preview={preview} />
                  <Problems preview={preview} />
                  <div className={cn("r-decisions-wrap")}>
                    <Decisions preview={preview} />
                    <Disclosure title="Change how it is read">
                      <FormatControls preview={preview} mapping={mapping} onMapping={onMapping} />
                    </Disclosure>
                  </div>
                </>
              )}
            </>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
