/**
 * Everything the contract carries about where one number came from, laid
 * out the same way wherever it is shown: in the popover a Value opens, or
 * inline in a detail pane.
 *
 * Every sentence here is the library's own (the source row's commentary,
 * verbatim; the placeholder's reason, from ParameterOrigin.sentence(); the
 * spread's sentence; the scope concerns' plain text). The page adds labels
 * and order, never a summary of its own, because a paraphrase of a caveat
 * is a second, weaker caveat.
 */
import { Check, Copy } from "lucide-react";
import { useState } from "react";

import type { SourcedValue } from "@/api/types";
import { formatNumber, fullValue } from "@/lib/format";

import { type PlaceholderReading, placeholderRowReason, plain, readPlaceholder } from "@/lib/copy";

import { Citation } from "./Citation";
import { PROVENANCE_MEANING, ProvenanceMark, provenanceLabel } from "./ProvenanceMark";

function Conditions({ v }: { v: SourcedValue }) {
  const c = v.provenance.conditions;
  if (!c) return null;
  const parts = [
    c.ph !== null ? `pH ${c.ph}` : "pH not stated",
    c.temperature_c !== null ? `${c.temperature_c} °C` : "temperature not stated",
  ];
  if (c.buffer) parts.push(c.buffer);
  return (
    <>
      <dt>Conditions</dt>
      <dd>
        <span className="font-mono">{parts.join(", ")}</span>
        {c.unreported.length ? <span className="muted"> · not reported: {c.unreported.join(", ")}</span> : null}
      </dd>
    </>
  );
}

export function CopyValue({ v }: { v: SourcedValue }) {
  const [copied, setCopied] = useState(false);
  if (v.value === null) return null;
  const text = v.unit ? `${fullValue(v)} ${v.unit}` : fullValue(v);
  return (
    <button
      type="button"
      className="btn btn-sm btn-quiet"
      onClick={() => {
        void navigator.clipboard?.writeText(text).then(
          () => {
            setCopied(true);
            window.setTimeout(() => setCopied(false), 1600);
          },
          () => setCopied(false),
        );
      }}
    >
      {copied ? <Check size={13} aria-hidden="true" /> : <Copy size={13} aria-hidden="true" />}
      {copied ? "Copied" : "Copy full value"}
    </button>
  );
}

export function ProvenanceDetail({ v, showValue = true }: { v: SourcedValue; showValue?: boolean }) {
  const p = v.provenance;
  const name = v.label ?? v.id;
  return (
    <div className="prov-detail">
      <div className="prov-detail-head">
        <ProvenanceMark provenance={p} decorative />
        <span>
          {provenanceLabel(p).replace(/^./, (c) => c.toUpperCase())}
          {name ? <span className="muted font-mono"> · {name}</span> : null}
        </span>
      </div>
      {showValue ? (
        <div className="flex items-baseline justify-between gap-3">
          <span className="prov-detail-value">
            {fullValue(v)}
            {v.unit ? <span className="value-unit"> {v.unit}</span> : null}
          </span>
          <CopyValue v={v} />
        </div>
      ) : null}
      <dl className="prov-detail-rows">
        {p.citation ? (
          <>
            <dt>Source</dt>
            <dd>
              <Citation citation={p.citation} detailed />
            </dd>
          </>
        ) : null}
        {p.organism ? (
          <>
            <dt>Organism</dt>
            <dd>
              <em>{p.organism}</em>
              {p.cross_species ? <span className="text-caution"> · measured in another organism than the model's</span> : null}
            </dd>
          </>
        ) : null}
        <Conditions v={v} />
        {p.kind === "fitted" && p.fit ? (
          <>
            <dt>Fit</dt>
            <dd>
              {p.fit.method}
              <span className="font-mono muted">
                {p.fit.n_points != null ? ` · n = ${p.fit.n_points}` : ""}
                {p.fit.r_squared != null ? ` · R² = ${formatNumber(p.fit.r_squared)}` : ""}
                {p.fit.stderr != null ? ` · s.e. ${formatNumber(p.fit.stderr)}` : ""}
                {p.fit.residual != null ? ` · residual ${formatNumber(p.fit.residual)}` : ""}
              </span>
            </dd>
          </>
        ) : null}
        {p.method ? (
          <>
            <dt>Method</dt>
            <dd>{plain(p.method)}</dd>
          </>
        ) : null}
        {p.inputs?.length ? (
          <>
            <dt>From</dt>
            <dd className="font-mono">{p.inputs.join(", ")}</dd>
          </>
        ) : null}
        {p.kind === "chosen" ? (
          <>
            <dt>Chosen by</dt>
            <dd>{p.by === "user" ? "you, in this request" : "a stated default of the command"}</dd>
          </>
        ) : null}
        {p.table ? (
          <>
            <dt>Would come from</dt>
            <dd>
              the <span className="font-mono">{p.table}</span> table
            </dd>
          </>
        ) : null}
        {v.interval ? (
          <>
            <dt>Interval</dt>
            <dd>
              <span className="font-mono">
                {v.interval.low !== null ? formatNumber(v.interval.low) : "open"} to{" "}
                {v.interval.high !== null ? formatNumber(v.interval.high) : "open"}
              </span>{" "}
              <span className="muted">{v.interval.meaning}</span>
            </dd>
          </>
        ) : null}
      </dl>
      {p.commentary ? (
        <div className="grid gap-1">
          <span className="text-xs muted">The source row says</span>
          <blockquote className="prov-quote">{p.commentary}</blockquote>
        </div>
      ) : null}
      {p.reason ? <p className="m-0">{plain(readPlaceholder(p.reason) ? placeholderRowReason(readPlaceholder(p.reason) as PlaceholderReading) : p.reason)}</p> : null}
      {p.chosen_because ? (
        <p className="m-0">
          <span className="muted">Chosen because </span>
          {plain(p.chosen_because)}
        </p>
      ) : null}
      {p.spread ? <p className="m-0 prov-note">{plain(p.spread.sentence)}</p> : null}
      {p.scope?.length ? (
        <div className="grid gap-1">
          <span className="text-xs muted">Where this could be the wrong number for this model</span>
          <ul className="prov-scope">
            {p.scope.map((line) => (
              <li key={line}>{plain(line)}</li>
            ))}
          </ul>
        </div>
      ) : null}
      {p.note && p.note !== p.reason ? <p className="m-0 prov-note">{plain(readPlaceholder(p.note) ? placeholderRowReason(readPlaceholder(p.note) as PlaceholderReading) : p.note)}</p> : null}
      {!p.citation && !p.reason && !p.method && !p.fit && p.kind !== "chosen" ? (
        <p className="m-0 muted">{PROVENANCE_MEANING[p.kind]}.</p>
      ) : null}
    </div>
  );
}
