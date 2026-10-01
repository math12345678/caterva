/**
 * A `caterva compose` result: the verdict first, then every number with
 * where it came from, the time course, each analysis section, and the
 * report the terminal prints.
 *
 * Every number drawn as a value is a SourcedValue from the server and goes
 * through <Value>, so it wears its provenance mark and its citation or
 * reason is one click away. The library's own sentences (the verdict, the
 * stability summary, each section) are shown as the library wrote them.
 */
import type { ComposeResult as Result, SourcedValue, StructuredSection } from "@/api/types";
import { ProvenanceMark, provenanceLabel } from "@/components/provenance/ProvenanceMark";
import { Value } from "@/components/provenance/Value";
import { formatNumber } from "@/lib/format";

import { MarkdownBlock, Report } from "./Report";
import { SeriesChart } from "./SeriesChart";

/** compose.verdict: broken names a defect; structural rests on placeholders. */
const VERDICT_TONE: Record<string, string | undefined> = {
  broken: "danger",
  structural: "caution",
};

function originWords(v: SourcedValue): string {
  const p = v.provenance;
  if (p.kind === "measured") {
    const where = p.organism ? (p.cross_species ? `measured in ${p.organism}, another organism` : p.organism) : null;
    return [p.citation?.text, where].filter(Boolean).join(", ");
  }
  return provenanceLabel(p);
}

export function Verdict({ result }: { result: Result }) {
  const v = result.verdict;
  if (!v) return null;
  return (
    <section className="k-verdict" aria-label="Verdict">
      <p className="k-section-sub">Verdict</p>
      <p className="k-verdict-word" data-tone={VERDICT_TONE[v.verdict]}>
        {v.verdict}
      </p>
      <p className="k-prose">{v.licence}</p>
      {v.behaviour ? <p className="k-prose k-muted">{v.behaviour}</p> : null}
      {v.concerns.length > 0 ? (
        <ul className="k-list">
          {v.concerns.map((c) => (
            <li key={`${c.source}-${c.detail}`}>
              <span className="k-code">{c.source}</span> {c.detail}
              {c.remedy ? <span className="k-muted">. {c.remedy}</span> : null}
            </li>
          ))}
        </ul>
      ) : null}
      {v.next_step ? (
        <p className="k-prose">
          <strong>Next: </strong>
          {v.next_step}
        </p>
      ) : null}
      {Object.keys(v.unavailable).length > 0 ? (
        <details className="k-details">
          <summary>Not examined ({Object.keys(v.unavailable).length})</summary>
          <ul className="k-list k-small">
            {Object.entries(v.unavailable).map(([k, why]) => (
              <li key={k}>
                <span className="k-code">{k}</span> {why}
              </li>
            ))}
          </ul>
        </details>
      ) : null}
    </section>
  );
}

export function ParameterTable({ result }: { result: Result }) {
  const { parameters, species, concentration_unit } = result.model;
  return (
    <section className="k-section" aria-labelledby="k-numbers">
      <h2 className="k-section-title" id="k-numbers">
        Where every number came from
      </h2>
      <p className="k-section-sub">
        Select a number for its citation, its conditions, or the reason it is a placeholder. Concentrations in{" "}
        <span className="k-code">{concentration_unit}</span>.
      </p>
      <div className="k-table-wrap">
        <table className="k-table">
          <thead>
            <tr>
              <th scope="col">Parameter</th>
              <th scope="col">Value</th>
              <th scope="col">Origin</th>
            </tr>
          </thead>
          <tbody>
            {parameters.map((p) => (
              <tr key={p.id}>
                <th scope="row" className="k-code" style={{ fontWeight: 400 }}>
                  {p.id}
                </th>
                <td className="k-num">
                  <Value v={p} />
                </td>
                <td className="k-small">{originWords(p)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="k-table-wrap">
        <table className="k-table">
          <thead>
            <tr>
              <th scope="col">Species</th>
              <th scope="col">Starting amount</th>
              <th scope="col">Origin</th>
            </tr>
          </thead>
          <tbody>
            {species.map((s) => (
              <tr key={s.id}>
                <th scope="row" className="k-code" style={{ fontWeight: 400 }}>
                  {s.id}
                </th>
                <td className="k-num">
                  <Value v={s.initial} />
                </td>
                <td className="k-small">{originWords(s.initial)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function Search({ result }: { result: Result }) {
  const s = result.search;
  if (!s.asked) return null;
  return (
    <section className="k-section" aria-labelledby="k-search">
      <h2 className="k-section-title" id="k-search">
        The literature search
      </h2>
      <p className="k-section-sub">
        EC <span className="k-code">{s.ec}</span>
        {s.organism ? `, ${s.organism}` : ""}
        {s.substrate ? `, substrate ${s.substrate}` : ""}
        {s.isoform ? `, isoform ${s.isoform}` : ""}
        {": "}
        {s.measured} measured, {s.placeholders} still placeholders
        {s.refused ? "; the search could not run" : ""}
      </p>
      {s.note ? <p className="k-prose">{s.note}</p> : null}
    </section>
  );
}

function TimeCourse({ result }: { result: Result }) {
  const t = result.trajectory;
  if (!t) return null;
  return (
    <section className="k-section" aria-labelledby="k-time">
      <h2 className="k-section-title" id="k-time">
        Time course
      </h2>
      <p className="k-section-sub">
        {t.points} points, horizon {t.window_basis}. Simulated by Caterva from the values above{" "}
        <ProvenanceMark provenance={{ kind: "computed" }} />
      </p>
      <SeriesChart
        x={t.times}
        series={t.columns}
        xLabel="time (s)"
        yLabel={result.model.concentration_unit}
        label="Simulated time course of every species"
      />
      {t.invariants.length > 0 ? (
        <ul className="k-list k-small">
          {t.invariants.map((inv) => (
            <li key={inv.law}>
              <span className="k-code">{inv.law}</span> {inv.held ? "held" : "did not hold"} over the run
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}

function Influence({ result }: { result: Result }) {
  const s = result.sensitivity;
  if (!s || s.sensitivities.length === 0) return null;
  return (
    <section className="k-section" aria-labelledby="k-influence">
      <h2 className="k-section-title" id="k-influence">
        Which constants matter
      </h2>
      <p className="k-section-sub">
        Relative sensitivity of the {s.quantity} to each constant, computed by Caterva{" "}
        <ProvenanceMark provenance={{ kind: "computed" }} />
      </p>
      <div className="k-table-wrap">
        <table className="k-table">
          <thead>
            <tr>
              <th scope="col">Constant</th>
              <th scope="col">Relative sensitivity</th>
              <th scope="col" />
            </tr>
          </thead>
          <tbody>
            {s.sensitivities.map((row) => (
              <tr key={row.parameter}>
                <th scope="row" className="k-code" style={{ fontWeight: 400 }}>
                  {row.parameter}
                </th>
                <td className="k-num font-mono tabular-nums">
                  {row.relative === null ? "not computed" : formatNumber(row.relative)}
                </td>
                <td className="k-small k-muted">
                  {row.unresolvable ? "below what the computation can resolve" : row.negligible ? "negligible" : ""}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function Section({ section }: { section: StructuredSection }) {
  const status =
    section.status === "answered" ? "answered" : section.status === "refused" ? "refused" : "partly refused";
  return (
    <section className="k-section" aria-label={section.title}>
      <div className="k-actions">
        <h3 className="k-section-title" style={{ fontSize: "1.1rem" }}>
          {section.title}
        </h3>
        <span className="k-status" data-status={section.status}>
          {status}
        </span>
      </div>
      <MarkdownBlock source={section.text} />
    </section>
  );
}

function Stability({ result }: { result: Result }) {
  if (!result.stability) return null;
  return (
    <section className="k-section" aria-labelledby="k-stability">
      <h2 className="k-section-title" id="k-stability">
        Steady states
      </h2>
      <pre className="k-pre k-small">{result.stability.text}</pre>
    </section>
  );
}

function Exports({ result }: { result: Result }) {
  const refused = Object.entries(result.exports).filter(([, e]) => !e.available);
  if (refused.length === 0) return null;
  return (
    <section className="k-section" aria-label="Exports not written">
      <h3 className="k-section-sub">Not exported</h3>
      <ul className="k-list k-small">
        {refused.map(([format, e]) => (
          <li key={format}>
            <span className="k-code">{format}</span> {e.refused}
          </li>
        ))}
      </ul>
    </section>
  );
}

export function ComposeResultView({ result }: { result: Result }) {
  return (
    <>
      <Verdict result={result} />
      <p className="k-section-sub">
        Read <span className="k-code">{result.query}</span> as {result.recognition.reading} (
        <span className="k-code">{result.recognition.rule}</span>)
      </p>
      <ParameterTable result={result} />
      <Search result={result} />
      <TimeCourse result={result} />
      <Influence result={result} />
      <Stability result={result} />
      {result.sections.length > 0 ? (
        <section className="k-section" aria-labelledby="k-sections">
          <h2 className="k-section-title" id="k-sections">
            Analyses
          </h2>
          {result.sections.map((s) => (
            <Section key={s.key} section={s} />
          ))}
        </section>
      ) : null}
      {result.notes.length > 0 ? (
        <section className="k-section" aria-labelledby="k-notes">
          <h2 className="k-section-title" id="k-notes">
            Notes
          </h2>
          <ul className="k-list">
            {result.notes.map((n) => (
              <li key={n}>{n}</li>
            ))}
          </ul>
        </section>
      ) : null}
      <Exports result={result} />
      <Report title="The report caterva compose prints" markdown={result.report_markdown} />
    </>
  );
}
