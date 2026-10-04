/**
 * What a finished rates run shows, in the order a person needs it.
 *
 * 1. Anything to read before quoting a number: every caution the engine
 *    produced, once each, with what to change, and the measurements that
 *    would make the fit better. A constant the data do not bound is said so
 *    here and shown without a number in the table; nothing confident is
 *    drawn from a flat profile.
 * 2. What the data support, in the engine's words, and how the uncertainty
 *    of each rate was handled and why that matters.
 * 3. The figure.
 * 4. The constants: each estimate marked as fitted from your data, with its
 *    profile-likelihood interval, standard error and unit; kcat when an
 *    enzyme concentration was given.
 * 5. The lack-of-fit test in one sentence and what it means for trust.
 * 6. The laws compared, with AICc and the tests, refusing to over-claim.
 * 7. Differences between groups, then the literature (BRENDA rows with their
 *    references, never merged across organisms or isoforms).
 * 8. Take it away: the tables, the methods paragraph, the citation, the
 *    bundle.
 *
 * Every sentence that states a result comes from the engine; the page adds
 * only labels and the arrangement.
 */
import { Check, ClipboardCopy, Download, FileArchive } from "lucide-react";
import { useState } from "react";

import { downloadArtifact, downloadBundle } from "@/api/runs";
import type {
  RatesCaution,
  RatesComparison,
  RatesLiterature,
  RatesParameter,
  RatesResult,
  RatesTurnover,
  RunRecord,
} from "@/api/types";
import { Disclosure } from "@/components/forms/Disclosure";
import { ProvenanceMark } from "@/components/provenance/ProvenanceMark";
import { Value } from "@/components/provenance/Value";
import { TextReport } from "@/components/report/Report";
import { Section } from "@/components/screen/Screen";
import { DataTable } from "@/components/table/DataTable";
import { describeError } from "@/lib/errors";
import { formatNumber } from "@/lib/format";
import { notify } from "@/lib/toast";

import { modelsCsv, parametersCsv, saveText, SOURCE_WORDS } from "./exports";
import { RatesChart } from "./RatesChart";

const KIND_LABEL: Record<string, string> = {
  undetermined: "Not determined by these data",
  "lack-of-fit": "The law does not follow the data",
  "error-bars": "The error bars and the scatter disagree",
  "second-minimum": "Two fits are almost as good",
  edge: "A constant ran to the edge of the search",
  fit: "About the fit",
  note: "Note",
};

function where(group: string | null, law: string | null): string {
  return [group ? `[${group}]` : "", law ?? ""].filter(Boolean).join(" ");
}

export function ReadFirst({ cautions, better }: { cautions: RatesCaution[]; better: string[] }) {
  if (cautions.length === 0 && better.length === 0) return null;
  return (
    <section className="r-caution-block" aria-labelledby="r-caution-title">
      <h3 className="r-block-title" id="r-caution-title">
        {cautions.length ? "Read before you quote these numbers" : "What would make this better"}
      </h3>
      {cautions.length ? (
        <ul className="r-cautions">
          {cautions.map((c, i) => (
            <li key={i} data-kind={c.kind}>
              <p className="r-caution-kind">
                {KIND_LABEL[c.kind] ?? c.kind}
                {where(c.group, c.law) ? <span className="font-mono muted"> {where(c.group, c.law)}</span> : null}
              </p>
              <p>{c.text}</p>
              {c.change ? (
                <p className="r-change">
                  <strong>What to change:</strong> {c.change}
                </p>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
      {better.length ? (
        <div className="r-better">
          {cautions.length ? <h4 className="r-minor">What would make this better</h4> : null}
          <ul>
            {better.map((b, i) => (
              <li key={i}>{b}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}

export function Support({ result }: { result: RatesResult }) {
  const groups = result.comparison;
  return (
    <div className="r-support">
      {groups.map((c) => (
        <div key={c.group ?? "all"} className="r-support-group">
          {c.group ? <h4 className="r-minor">{c.group}</h4> : null}
          <ul>
            {c.verdict.length ? (
              c.verdict.map((s, i) => <li key={i}>{s}</li>)
            ) : (
              <li>
                {c.laws.find((l) => l.status === "reported")?.title ?? "One law"} was the law asked for; no other law was fitted or tested.
              </li>
            )}
            {c.to_decide.map((s, i) => (
              <li key={`d${i}`}>To decide: {s}</li>
            ))}
          </ul>
        </div>
      ))}
      <p className="r-sigma">
        <strong>Uncertainty of each rate:</strong> {result.sigma.description}. {result.sigma.why}
      </p>
    </div>
  );
}

const interval = (p: { low: number | null; high: number | null; interval: string }) =>
  p.low !== null && p.high !== null ? `${formatNumber(p.low)} to ${formatNumber(p.high)}` : p.interval;

export function ParameterTable({ rows, turnover, basis, refused }: { rows: RatesParameter[]; turnover: RatesTurnover[]; basis: RatesResult["interval_basis"]; refused: string | null }) {
  const grouped = rows.some((r) => r.group);
  const level = rows[0]?.level ?? 0.95;
  const pct = `${Math.round(level * 1000) / 10}%`;
  return (
    <div className="r-params">
      <DataTable
        caption="The constants of each reported law, fitted from your data"
        captionHidden
        rows={rows}
        rowKey={(r, i) => `${r.group}-${r.law}-${r.constant}-${i}`}
        columns={[
          ...(grouped ? [{ key: "group", header: "Group", cell: (r: RatesParameter) => r.group ?? "" }] : []),
          { key: "law", header: "Law", cell: (r: RatesParameter) => r.law_title },
          {
            key: "constant",
            header: "Constant",
            cell: (r: RatesParameter) => <span className="font-mono">{r.constant}</span>,
          },
          {
            key: "value",
            header: "Value",
            numeric: true,
            cell: (r: RatesParameter) =>
              r.value ? <Value v={r.value} showUnit={false} /> : <span className="r-undetermined">not determined</span>,
          },
          { key: "unit", header: "Unit", cell: (r: RatesParameter) => <span className="font-mono">{r.unit || "none"}</span> },
          {
            key: "interval",
            header: `${pct} profile interval`,
            numeric: true,
            cell: (r: RatesParameter) => <span className="font-mono">{interval(r)}</span>,
          },
          { key: "se", header: "Standard error", numeric: true, cell: (r: RatesParameter) => (r.determined && r.standard_error !== null ? formatNumber(r.standard_error) : "none") },
          {
            key: "source",
            header: "Source",
            cell: (r: RatesParameter) => (
              <span className="r-source">
                <ProvenanceMark provenance={{ kind: "fitted" }} decorative />
                {r.determined ? SOURCE_WORDS : `${SOURCE_WORDS}: bounded on one side only`}
              </span>
            ),
          },
        ]}
      />
      <p className="r-basis">
        Interval method: {basis.method}, bounded by {basis.bounded_by}. Standard errors are asymptotic; a profile interval can be lopsided where the standard error cannot.
        A constant the data do not bound on both sides has no value here: the interval shows the one-sided statement, and the reason is under Read before you quote these numbers.
      </p>
      {turnover.length ? (
        <>
          <h4 className="r-minor">Turnover number</h4>
          <DataTable
            caption="kcat, from the fitted Vmax and the enzyme concentration you gave"
            captionHidden
            rows={turnover}
            rowKey={(r, i) => `${r.group}-${r.law}-${r.unit}-${i}`}
            columns={[
              ...(turnover.some((r) => r.group) ? [{ key: "group", header: "Group", cell: (r: RatesTurnover) => r.group ?? "" }] : []),
              { key: "law", header: "Law", cell: (r: RatesTurnover) => r.law_title },
              { key: "value", header: "kcat", numeric: true, cell: (r: RatesTurnover) => (r.value ? <Value v={r.value} showUnit={false} /> : <span className="r-undetermined">not determined</span>) },
              { key: "unit", header: "Unit", cell: (r: RatesTurnover) => <span className="font-mono">{r.unit}</span> },
              {
                key: "interval",
                header: "Interval",
                numeric: true,
                cell: (r: RatesTurnover) => <span className="font-mono">{r.low !== null && r.high !== null ? `${formatNumber(r.low)} to ${formatNumber(r.high)}` : r.low !== null ? `> ${formatNumber(r.low)}` : "none"}</span>,
              },
              { key: "e", header: "Enzyme", cell: (r: RatesTurnover) => <span className="font-mono">{`${r.enzyme.concentration} ${r.enzyme.unit}`}</span> },
            ]}
          />
          <p className="r-basis">kcat is the fitted Vmax divided by the enzyme concentration you gave, taken as exact: its interval is Vmax&apos;s and carries no uncertainty in that concentration.</p>
        </>
      ) : null}
      {refused ? <p className="r-refusal-inline">kcat was not computed: {refused}</p> : null}
    </div>
  );
}

export function LackOfFit({ rows }: { rows: RatesResult["lack_of_fit"] }) {
  return (
    <ul className="r-lof">
      {rows.map((r, i) => (
        <li key={i} data-failed={r.failed ? "true" : undefined}>
          <p>
            {r.group ? <strong>{r.group}, </strong> : null}
            <strong>{r.title}.</strong> {r.sentence}
          </p>
          <p className="r-trust">{r.trust}</p>
        </li>
      ))}
    </ul>
  );
}

const STATUS_CLASS: Record<string, string> = { reported: "reported", "ruled out": "ruled", "not ruled out": "standing" };

export function ModelComparison({ comparison }: { comparison: RatesComparison[] }) {
  return (
    <div className="r-models">
      {comparison.map((c) => (
        <div key={c.group ?? "all"} className="r-model-group">
          {c.group ? <h4 className="r-minor">{c.group}</h4> : null}
          <DataTable
            caption={`Laws fitted${c.group ? ` to ${c.group}` : ""}, with AICc`}
            captionHidden
            rows={c.laws}
            rowKey={(l, i) => `${l.law}-${i}`}
            columns={[
              { key: "law", header: "Law", cell: (l) => l.title ?? l.law },
              { key: "status", header: "Verdict", cell: (l) => <span className="r-status" data-status={STATUS_CLASS[l.status ?? ""] ?? "plain"}>{l.status}</span> },
              { key: "p", header: "Constants", numeric: true, cell: (l) => l.parameters ?? "none" },
              { key: "aicc", header: "AICc", numeric: true, cell: (l) => (l.aicc != null ? formatNumber(l.aicc) : "none") },
              { key: "d", header: "Change in AICc", numeric: true, cell: (l) => (l.delta_aicc != null ? formatNumber(l.delta_aicc) : "none") },
              { key: "lof", header: "Lack-of-fit p", numeric: true, cell: (l) => (l.lack_of_fit_p != null ? formatNumber(l.lack_of_fit_p, 3) : "not tested") },
            ]}
          />
          {c.tests.length ? (
            <DataTable
              caption="Tests between laws"
              captionHidden
              rows={c.tests}
              rowKey={(t, i) => `${t.restricted}-${t.general}-${i}`}
              columns={[
                { key: "t", header: "Test", cell: (t) => `${t.restricted} against ${t.general}` },
                { key: "r", header: "Restriction", cell: (t) => <span className="font-mono">{t.restriction}</span> },
                { key: "s", header: "Statistic", numeric: true, cell: (t) => <span className="font-mono">{t.statistic}</span> },
                { key: "p", header: "p", numeric: true, cell: (t) => <span className="font-mono">{t.p_text}</span> },
                { key: "v", header: "Verdict", cell: (t) => (t.ruled_out ? "ruled out" : "not ruled out") },
              ]}
            />
          ) : null}
          {c.described.map((d, i) => (
            <p key={i} className="r-basis">
              {d}
            </p>
          ))}
          <p className="r-basis">{c.note} Ruled out means p below {c.significance}, a convention; every p is shown so another can be applied.</p>
        </div>
      ))}
    </div>
  );
}

export function GroupsBlock({ groups }: { groups: NonNullable<RatesResult["groups"]> }) {
  return (
    <div className="r-groups">
      <DataTable
        caption={`Which constants differ between ${groups.groups.join(" and ")}, under the ${groups.law_title} law`}
        captionHidden
        rows={groups.tests}
        rowKey={(t) => t.constant}
        columns={[
          { key: "c", header: "Shared constant", cell: (t) => <span className="font-mono">{t.constant}</span> },
          { key: "s", header: "Statistic", numeric: true, cell: (t) => <span className="font-mono">{t.statistic}</span> },
          { key: "p", header: "p", numeric: true, cell: (t) => <span className="font-mono">{t.p_text}</span> },
          { key: "v", header: "Verdict", cell: (t) => t.verdict },
        ]}
      />
      <ul>
        {groups.sentences.map((s, i) => (
          <li key={i}>{s}</li>
        ))}
      </ul>
    </div>
  );
}

export function LiteratureBlock({ rows, refused }: { rows: RatesLiterature[]; refused: string | null }) {
  return (
    <div className="r-literature">
      {refused ? <p className="r-refusal-inline">Not compared: {refused}</p> : null}
      {rows.map((r, i) => (
        <article key={i} className="r-lit-row">
          <p className="r-lit-head">
            <span className="font-mono">
              {r.constant}
              {r.group ? ` [${r.group}]` : ""}
            </span>{" "}
            <span className="muted">{r.law}</span>
          </p>
          <p>{r.sentence}</p>
          {r.found && r.cited ? (
            <p className="r-lit-cited">
              Cited: <Value v={r.cited} /> {r.organism ? <span className="muted">in {r.organism}</span> : null}
            </p>
          ) : null}
          {r.determined && r.fitted_estimate !== null ? (
            <p className="r-lit-fit">
              Yours: <span className="font-mono">{formatNumber(r.fitted_estimate)}</span>{" "}
              {r.fitted_low !== null && r.fitted_high !== null ? (
                <span className="font-mono">
                  ({formatNumber(r.fitted_low)} to {formatNumber(r.fitted_high)})
                </span>
              ) : null}{" "}
              <span className="font-mono">{r.cited_unit}</span>, fitted from your data
            </p>
          ) : null}
          {r.conditional ? <p className="r-note">{r.conditional}.</p> : null}
          {r.spread_text ? <p className="r-note">{r.spread_text}</p> : null}
          {r.evidence_against ? <p className="r-note">{r.evidence_against}.</p> : null}
          {r.concerns.map((c, k) => (
            <p key={k} className="r-note">
              {c}
            </p>
          ))}
          {r.commentary ? <p className="r-note">Row commentary: {r.commentary}</p> : null}
        </article>
      ))}
    </div>
  );
}

function CopyButton({ text, label, done }: { text: string; label: string; done: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      className="btn btn-sm"
      onClick={() => {
        void navigator.clipboard?.writeText(text).then(
          () => {
            setCopied(true);
            window.setTimeout(() => setCopied(false), 1800);
          },
          () => notify("failed", "The text was not copied", { description: "This browser did not let the page write to the clipboard; select the text and copy it." }),
        );
      }}
    >
      {copied ? <Check size={13} aria-hidden="true" /> : <ClipboardCopy size={13} aria-hidden="true" />}
      {copied ? done : label}
    </button>
  );
}

export function TakeItAway({ result, run, base }: { result: RatesResult; run: RunRecord; base: string }) {
  const failed = (what: string) => (e: unknown) => notify("failed", `${what} was not saved`, { description: describeError(e).message });
  const stem = base.replace(/\.[A-Za-z0-9]{1,5}$/, "").replace(/[^A-Za-z0-9._-]+/g, "-") || "rates";
  return (
    <div className="r-away">
      <div className="r-away-row" role="group" aria-label="Tables">
        <span className="r-away-label">Tables</span>
        <button type="button" className="btn btn-sm" onClick={() => saveText(`${stem}-parameters.csv`, parametersCsv(result.parameters, result.turnover), "text/csv;charset=utf-8")}>
          <Download size={13} aria-hidden="true" />
          Parameters, CSV
        </button>
        <button type="button" className="btn btn-sm" onClick={() => saveText(`${stem}-models.csv`, modelsCsv(result.comparison), "text/csv;charset=utf-8")}>
          <Download size={13} aria-hidden="true" />
          Model comparison, CSV
        </button>
        <button type="button" className="btn btn-sm" onClick={() => void downloadArtifact(run.id, "curves.csv").catch(failed("curves.csv"))}>
          <Download size={13} aria-hidden="true" />
          Curves, CSV
        </button>
      </div>
      <div className="r-away-row" role="group" aria-label="Reproduce">
        <span className="r-away-label">Reproduce</span>
        <button type="button" className="btn btn-sm" onClick={() => void downloadBundle(run.id).catch(failed("The bundle"))} title="The table, the request, the result, every file, the versions and the command">
          <FileArchive size={13} aria-hidden="true" />
          Bundle (.zip)
        </button>
        <button type="button" className="btn btn-sm" onClick={() => void downloadArtifact(run.id, "dataset.csv").catch(failed("dataset.csv"))}>
          <Download size={13} aria-hidden="true" />
          The table that was fitted
        </button>
      </div>
      <div className="r-methods">
        <div className="r-methods-head">
          <h4 className="r-minor">Methods paragraph</h4>
          <span className="r-away-actions">
            <CopyButton text={result.methods.trim()} label="Copy" done="Copied" />
            <button type="button" className="btn btn-sm" onClick={() => saveText(`${stem}-methods.txt`, result.methods)}>
              <Download size={13} aria-hidden="true" />
              Save as text
            </button>
          </span>
        </div>
        <p className="r-methods-text" data-testid="methods-text">
          {result.methods.trim()}
        </p>
        <p className="r-basis">Written from this run: every number and every choice in it is the run&apos;s. Check it against your protocol before it goes in a paper.</p>
      </div>
      <div className="r-methods">
        <div className="r-methods-head">
          <h4 className="r-minor">How to cite</h4>
          <CopyButton text={result.cite} label="Copy" done="Copied" />
        </div>
        <p className="r-methods-text" data-testid="cite-line">
          {result.cite}
        </p>
      </div>
      <Disclosure title="The engine's full report">
        <TextReport text={result.report_text} />
      </Disclosure>
    </div>
  );
}

export function RatesResultView({ result, run }: { result: RatesResult; run: RunRecord }) {
  const base = result.dataset.filename ?? "rates";
  return (
    <div className="r-result">
      <ReadFirst cautions={result.cautions} better={result.better} />
      <Section title="What the data support">
        <Support result={result} />
      </Section>
      <Section title="The figure">
        <RatesChart figure={result.figure} base={base} />
      </Section>
      <Section title="The constants">
        <ParameterTable rows={result.parameters} turnover={result.turnover} basis={result.interval_basis} refused={result.turnover_refused} />
      </Section>
      <Section title="Does the law follow the data">
        <LackOfFit rows={result.lack_of_fit} />
      </Section>
      <Section title="The laws compared">
        <ModelComparison comparison={result.comparison} />
      </Section>
      {result.groups ? (
        <Section title="Between groups">
          <GroupsBlock groups={result.groups} />
        </Section>
      ) : null}
      {result.literature.length || result.literature_refused ? (
        <Section title="Against the literature">
          <LiteratureBlock rows={result.literature} refused={result.literature_refused} />
        </Section>
      ) : null}
      <Section title="Take it away">
        <TakeItAway result={result} run={run} base={base} />
      </Section>
    </div>
  );
}
