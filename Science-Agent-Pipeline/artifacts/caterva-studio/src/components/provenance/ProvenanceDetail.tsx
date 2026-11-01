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
 *
 * A number of a compose run also carries its claim (CONTRACT.md 9, "The
 * claim object"): the derivation the run's claims bundle holds, down to the
 * pinned page's bytes. The `Derivation` block below lays it out the same
 * way, field for field as the bundle has it, so what `caterva why` prints
 * in a terminal is one click from the number here.
 */
import { Check, Copy } from "lucide-react";
import { useState } from "react";

import type { ClaimInfo, SourcedValue } from "@/api/types";
import { formatNumber, fullValue } from "@/lib/format";

import { type PlaceholderReading, placeholderRowReason, plain, readPlaceholder } from "@/lib/copy";

import { Citation, External, pubmedUrl } from "./Citation";
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

/** Copies a text on demand and says so for a moment: the one pattern every copy button here follows. */
function useCopied(): { copied: boolean; copy: (text: string) => void } {
  const [copied, setCopied] = useState(false);
  const copy = (text: string) => {
    void navigator.clipboard?.writeText(text).then(
      () => {
        setCopied(true);
        window.setTimeout(() => setCopied(false), 1600);
      },
      () => setCopied(false),
    );
  };
  return { copied, copy };
}

export function CopyValue({ v }: { v: SourcedValue }) {
  const { copied, copy } = useCopied();
  if (v.value === null) return null;
  const text = v.unit ? `${fullValue(v)} ${v.unit}` : fullValue(v);
  return (
    <button type="button" className="btn btn-sm btn-quiet" onClick={() => copy(text)}>
      {copied ? <Check size={13} aria-hidden="true" /> : <Copy size={13} aria-hidden="true" />}
      {copied ? "Copied" : "Copy full value"}
    </button>
  );
}

/** The claim id, copied whole: what `caterva why CLAIM --bundle DIR` takes and the exports' claim_id column carries. */
export function CopyClaimId({ claim }: { claim: ClaimInfo }) {
  const { copied, copy } = useCopied();
  return (
    <button type="button" className="btn btn-sm btn-quiet" title={claim.id} onClick={() => copy(claim.id)}>
      {copied ? <Check size={13} aria-hidden="true" /> : <Copy size={13} aria-hidden="true" />}
      {copied ? "Copied" : "Copy claim id"}
    </button>
  );
}

/**
 * A digest shortened to its first twelve hex characters for a line with no
 * room for sixty-four; the whole stays in a title and in what a copy takes.
 * Anything that is not a digest is returned as it is.
 */
export function shortDigest(ref: string): string {
  const m = /^((?:claim|row|snapshot):)?sha256:([0-9a-f]{64})$/.exec(ref);
  return m ? `${m[1] ?? ""}sha256:${m[2].slice(0, 12)}…` : ref;
}

/**
 * Where a claim came from, as the run's claims bundle holds it (ADR 0179):
 * the rule with its decision record, the row's locator and its own words,
 * the pinned page with its date, licence and digest, the paper when the
 * bundle holds its page, the texts certified to be in the pinned bytes, and
 * for a refused claim what was asked for and the rows that were not it. A
 * part the bundle does not hold is left out, never guessed; the run's claims
 * section says why. The paper links to PubMed only by the contract's known
 * form, and only when the bundle's own link is that one.
 */
export function Derivation({ claim }: { claim: ClaimInfo }) {
  const paper = claim.reference;
  const pubmed = paper?.pmid ? pubmedUrl(paper.pmid) : null;
  const paperLink = pubmed !== null && paper?.url === pubmed ? pubmed : null;
  const source = paper ? [paper.journal, paper.year].filter((x): x is string => Boolean(x)) : [];
  return (
    <div className="grid gap-1" role="group" aria-label="Derivation">
      <span className="text-xs muted">Derivation</span>
      <dl className="prov-detail-rows">
        <dt>Claim</dt>
        <dd className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <span className="chip chip-mono">{claim.kind}</span>
          <span className="font-mono text-xs">{claim.id}</span>
          <CopyClaimId claim={claim} />
        </dd>
        <dt>Rule</dt>
        <dd>
          <span className="font-mono">
            {claim.rule.rule_id} v{claim.rule.version}
          </span>
          <span className="muted"> · {claim.rule.adr}</span>
        </dd>
        {claim.row ? (
          <>
            <dt>Row</dt>
            <dd className="grid gap-1">
              <span className="font-mono text-xs">{claim.row.locator}</span>
              {claim.row.commentary ? (
                <blockquote className="prov-quote">{claim.row.commentary}</blockquote>
              ) : (
                <span className="citation-meta">the row has no commentary</span>
              )}
            </dd>
          </>
        ) : null}
        {claim.snapshot ? (
          <>
            <dt>Page</dt>
            <dd className="grid gap-1">
              <span className="font-mono text-xs">{claim.snapshot.locator}</span>
              <span className="citation-meta">
                retrieved <span className="font-mono">{claim.snapshot.retrieved_at}</span> · {claim.snapshot.licence} ·{" "}
                <span className="font-mono" title={claim.snapshot.id}>
                  {shortDigest(claim.snapshot.id)}
                </span>
              </span>
            </dd>
          </>
        ) : null}
        {paper ? (
          <>
            <dt>Paper</dt>
            <dd className="grid gap-1">
              <span>{paper.title}</span>
              {source.length ? <span className="citation-meta">{source.join(", ")}</span> : null}
              {paper.pmid ? (
                <span className="citation">
                  {paperLink ? <External href={paperLink}>PMID {paper.pmid}</External> : <span>PMID {paper.pmid}</span>}
                </span>
              ) : null}
            </dd>
          </>
        ) : null}
        {claim.certificates.length ? (
          <>
            <dt>Certified</dt>
            <dd>
              <ul className="m-0 grid list-none gap-1 p-0" aria-label="Texts certified to be in the pinned page">
                {claim.certificates.map((c, i) => (
                  <li key={`${i}-${c.matched}`} className="font-mono text-xs">
                    {c.matched}
                  </li>
                ))}
              </ul>
            </dd>
          </>
        ) : null}
        {claim.refusal ? (
          <>
            <dt>Refused</dt>
            <dd className="grid gap-1">
              <span>
                <span className="font-mono">{claim.refusal.kind}</span>
                {": "}
                {claim.refusal.requested}
              </span>
              {claim.refusal.candidates.length ? (
                <ul className="m-0 grid list-none gap-1 p-0" aria-label="The rows that were not the one">
                  {claim.refusal.candidates.map((c) => (
                    <li key={c} className="font-mono text-xs">
                      {c}
                    </li>
                  ))}
                </ul>
              ) : null}
            </dd>
          </>
        ) : null}
      </dl>
    </div>
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
      {p.claim ? <Derivation claim={p.claim} /> : null}
    </div>
  );
}
