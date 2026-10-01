/**
 * A `caterva compose` result, in the order a reader decides whether to
 * trust it: the verdict (what the model can answer, and the worst thing
 * wrong with it), then where every number came from, then what the model
 * does (time course, influence, steady states, sweeps), then each analysis
 * that was asked for under its own heading with its chart, then the report
 * the terminal prints.
 *
 * Every number drawn as a value is a SourcedValue from the server and goes
 * through <Value>, so it wears its provenance mark and its citation or
 * reason is one click away. Numbers the library computed inside a section
 * (a steady state, a sensitivity) are labelled computed where they are
 * drawn. The library's own sentences (the verdict, the concerns, each
 * section's text, a placeholder's reason) are shown as the library wrote
 * them: a paraphrase of a caveat is a second, weaker caveat.
 */
import { ArrowRight } from "lucide-react";
import { useState } from "react";

import type { ComposeResult as Result, Concern, RunRecord, SourcedValue, StructuredSection } from "@/api/types";
import { TimeCourseChart } from "@/components/charts/TimeCourseChart";
import { Disclosure } from "@/components/forms/Disclosure";
import { Citation } from "@/components/provenance/Citation";
import { countKinds, ProvenanceLegend } from "@/components/provenance/ProvenanceLegend";
import { ProvenanceMark } from "@/components/provenance/ProvenanceMark";
import { Value } from "@/components/provenance/Value";
import { MarkdownReport } from "@/components/report/Report";
import { Section } from "@/components/screen/Screen";
import { RefusalState } from "@/components/states/States";
import { formatNumber } from "@/lib/format";

import type { ExportChoice } from "./kit";
import { SectionFigure, SweepFigure } from "./sections";

/** compose.verdict: broken names a defect; structural rests on placeholders. */
const VERDICT_TONE: Record<string, string | undefined> = {
  broken: "danger",
  structural: "caution",
};

const EXPORT_LABEL: Record<string, string> = {
  methods: "Methods",
  csv: "CSV",
  sbml: "SBML",
  antimony: "Antimony",
};

/** The exports a compose run wrote, in the order a methods section needs them, then the result as JSON. */
export function composeExports(result: Result, run: RunRecord): ExportChoice[] {
  const out: ExportChoice[] = [];
  for (const format of ["methods", "csv", "sbml", "antimony"]) {
    const e = result.exports[format];
    if (!e?.available || !e.artifact) continue;
    const recorded = run.artifacts.find((a) => a.name === e.artifact);
    if (!recorded) continue;
    out.push({ label: EXPORT_LABEL[format], artifact: e.artifact, description: recorded.description });
  }
  out.push({ label: "JSON", artifact: "result.json", description: "the result exactly as the studio API sent it" });
  return out;
}

function ConcernLine({ c }: { c: Concern }) {
  return (
    <>
      <span className="chip chip-mono">{c.source}</span> <span>{c.detail}</span>
      {c.remedy ? <span className="k-remedy">{c.remedy}</span> : null}
    </>
  );
}

/** The refused sections a partly refused compose run names, linked to where each says why. */
function PartRefusal({ result, run }: { result: Result; run: RunRecord }) {
  const refused = result.sections.filter((s) => s.status !== "answered");
  const outcome = run.outcome;
  if (!outcome || outcome.meaning !== "refused") return null;
  return (
    <div className="k-part-refusal" role="note">
      <span className="state-kicker">Refused in part</span>
      <p className="k-part-refusal-reason">{outcome.reason}</p>
      {refused.length ? (
        <ul className="k-anchors">
          {refused.map((s) => (
            <li key={s.key}>
              <a href={`#k-section-${s.key}`}>
                {s.title}
                <ArrowRight size={12} aria-hidden="true" />
              </a>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

export function Verdict({ result, run }: { result: Result; run: RunRecord }) {
  const v = result.verdict;
  if (!v) {
    return (
      <section className="k-verdict" aria-label="Verdict">
        <p className="k-eyebrow">Verdict</p>
        <p className="k-verdict-licence">The command gave no verdict for this request (its stability analysis or simulation was switched off).</p>
        <PartRefusal result={result} run={run} />
      </section>
    );
  }
  const [worst, ...rest] = v.concerns;
  const checked = Object.entries(v.consulted);
  const unexamined = Object.entries(v.unavailable);
  return (
    <section className="k-verdict" aria-labelledby="k-verdict-word">
      <div className="k-verdict-head">
        <p className="k-eyebrow">Verdict</p>
        <h2 className="k-verdict-word" id="k-verdict-word" data-tone={VERDICT_TONE[v.verdict]}>
          {v.verdict}
        </h2>
      </div>
      <p className="k-verdict-licence">
        <span className="k-label-inline">What it supports</span> {v.licence}
      </p>
      {worst ? (
        <div className="k-worst" data-severity={worst.severity}>
          <p className="k-eyebrow">The worst thing wrong with it</p>
          <p className="k-worst-detail">
            <ConcernLine c={worst} />
          </p>
        </div>
      ) : null}
      {v.behaviour ? (
        <p className="k-verdict-behaviour">
          <span className="k-label-inline">What it does</span> {v.behaviour}
        </p>
      ) : null}
      {v.next_step && v.next_step !== worst?.remedy ? (
        <p className="k-verdict-next">
          <span className="k-label-inline">Do this next</span> {v.next_step}
        </p>
      ) : null}
      <PartRefusal result={result} run={run} />
      {rest.length || checked.length || unexamined.length ? (
        <div className="k-verdict-more">
          {rest.length ? (
            <Disclosure title="Other concerns, worst first" aside={<span className="font-mono">{rest.length}</span>}>
              <ul className="k-concerns">
                {rest.map((c) => (
                  <li key={`${c.source}-${c.detail}`}>
                    <ConcernLine c={c} />
                  </li>
                ))}
              </ul>
            </Disclosure>
          ) : null}
          {checked.length || unexamined.length ? (
            <Disclosure
              title="What the verdict consulted"
              aside={
                <span className="font-mono">
                  {checked.length} checked{unexamined.length ? `, ${unexamined.length} not run` : ""}
                </span>
              }
            >
              <dl className="k-consulted">
                {checked.map(([k, why]) => (
                  <div key={k}>
                    <dt className="font-mono">{k}</dt>
                    <dd>{why}</dd>
                  </div>
                ))}
                {unexamined.map(([k, why]) => (
                  <div key={k} data-state="unexamined">
                    <dt className="font-mono">{k}</dt>
                    <dd>{why}</dd>
                  </div>
                ))}
              </dl>
            </Disclosure>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

/** A long sentence of the library's, three lines tall until asked for whole. */
function Clamp({ children }: { children: string }) {
  const [open, setOpen] = useState(false);
  const long = children.length > 220;
  return (
    <span className="k-clamp" data-open={open || !long ? "true" : undefined}>
      <span className="k-clamp-text">{children}</span>
      {long ? (
        <button type="button" className="k-clamp-toggle" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
          {open ? "less" : "all of it"}
        </button>
      ) : null}
    </span>
  );
}

function Conditions({ v }: { v: SourcedValue }) {
  const c = v.provenance.conditions;
  if (!c) return null;
  const parts: string[] = [];
  if (c.ph !== null) parts.push(`pH ${c.ph}`);
  if (c.temperature_c !== null) parts.push(`${c.temperature_c} °C`);
  if (c.buffer) parts.push(c.buffer);
  const missing = c.unreported.length ? `not reported: ${c.unreported.join(", ")}` : null;
  if (!parts.length && !missing) return null;
  return (
    <span className="k-conditions">
      {parts.length ? <span className="font-mono">{parts.join(", ")}</span> : null}
      {parts.length && missing ? " · " : null}
      {missing ? <span className="text-caution">{missing}</span> : null}
    </span>
  );
}

/** Where one number came from, inline: the facts the provenance detail carries, laid out for a table row. */
export function Origin({ v }: { v: SourcedValue }) {
  const p = v.provenance;
  switch (p.kind) {
    case "measured":
      return (
        <div className="k-origin">
          <div className="k-origin-line">
            {p.citation ? <Citation citation={p.citation} /> : null}
            {p.organism ? (
              <span>
                <em>{p.organism}</em>
                {p.cross_species ? <span className="text-caution"> (another organism than the model's)</span> : null}
              </span>
            ) : null}
            <Conditions v={v} />
          </div>
          {p.commentary ? <blockquote className="k-row-says">{p.commentary}</blockquote> : null}
          {p.scope?.length ? (
            <ul className="k-scope" aria-label="Where this could be the wrong number for this model">
              {p.scope.map((s) => (
                <li key={s}>{s}</li>
              ))}
            </ul>
          ) : null}
          {p.spread ? (
            <p className="k-spread">
              <Clamp>{p.spread.sentence}</Clamp>
            </p>
          ) : null}
          {p.chosen_because ? (
            <p className="k-spread">
              <span className="muted">Chosen because </span>
              {p.chosen_because}
            </p>
          ) : null}
        </div>
      );
    case "placeholder":
      return (
        <div className="k-origin">
          <p className="k-origin-reason">
            <Clamp>{p.reason ?? "no reason was recorded"}</Clamp>
          </p>
          {p.table ? (
            <p className="k-spread muted">
              The measurement that would replace it is in BRENDA&apos;s <span className="font-mono">{p.table}</span> table.
            </p>
          ) : null}
        </div>
      );
    case "computed":
      return (
        <div className="k-origin">
          <p className="k-origin-reason">{p.method ?? "computed by Caterva"}</p>
          {p.inputs?.length ? <p className="k-spread muted font-mono">from {p.inputs.join(", ")}</p> : null}
        </div>
      );
    case "fitted":
      return <p className="k-origin-reason">{p.fit?.method ?? "fitted"}</p>;
    case "chosen":
      return (
        <p className="k-origin-reason">
          {p.by === "user" ? "Chosen by you in this request" : "A stated default of the command"}
          {p.reason ? <span className="muted">: {p.reason}</span> : null}
        </p>
      );
  }
}

function LedgerRows({ values, name }: { values: { key: string; name: string; v: SourcedValue }[]; name: string }) {
  return (
    <div className="table-wrap">
      <table className="table k-ledger">
        <thead>
          <tr>
            <th scope="col">{name}</th>
            <th scope="col" data-align="end">
              Value
            </th>
            <th scope="col">Where it came from</th>
          </tr>
        </thead>
        <tbody>
          {values.map(({ key, name: label, v }) => (
            <tr key={key} data-kind={v.provenance.kind}>
              <th scope="row" className="k-ledger-name">
                <span className="font-mono">{label}</span>
                {v.label && v.label !== label ? <span className="k-ledger-sub">{v.label}</span> : null}
              </th>
              <td data-align="end" className="k-ledger-value">
                <Value v={v} />
              </td>
              <td>
                <Origin v={v} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function NumbersLedger({ result }: { result: Result }) {
  const { parameters, species, concentration_unit } = result.model;
  const all = [...parameters, ...species.map((s) => s.initial)];
  const counts = countKinds(all);
  return (
    <Section
      title="Where the numbers come from"
      id="k-numbers"
      aside={<ProvenanceLegend counts={counts} only={Object.keys(counts) as (keyof typeof counts)[]} />}
    >
      <p className="k-lede">
        Activate a number for its paper, its assay conditions and the source row&apos;s own words, or for the reason it is
        a placeholder. Concentrations are in <span className="font-mono">{concentration_unit}</span>.
      </p>
      <LedgerRows name="Constant" values={parameters.map((p) => ({ key: p.id ?? p.label ?? "", name: p.id ?? p.label ?? "", v: p }))} />
      {species.length ? (
        <Disclosure title="Starting amounts" aside={<span className="font-mono">{species.length}</span>}>
          <LedgerRows name="Species" values={species.map((s) => ({ key: s.id, name: s.id, v: s.initial }))} />
        </Disclosure>
      ) : null}
    </Section>
  );
}

function Search({ result }: { result: Result }) {
  const s = result.search;
  if (!s.asked) return null;
  return (
    <div className="k-search" aria-label="The literature search">
      <p>
        <span className="k-label-inline">Searched</span>
        EC <span className="font-mono">{s.ec ?? s.subject}</span>
        {s.organism ? (
          <>
            {", "}
            <em>{s.organism}</em>
          </>
        ) : null}
        {s.substrate ? `, substrate ${s.substrate}` : ""}
        {s.isoform ? `, isoform ${s.isoform}` : ""}
        {Object.entries(s.compounds).map(([port, name]) => `, ${port.replace(/^@/, "")} ${name}`)}
        {". "}
        <span className="font-mono">{s.measured}</span> measured, <span className="font-mono">{s.placeholders}</span> still
        placeholders{s.refused ? "; the search could not run" : ""}.
      </p>
      {s.note ? <p className="muted">{s.note}</p> : null}
    </div>
  );
}

function TimeCourse({ result }: { result: Result }) {
  const t = result.trajectory;
  if (!t) return null;
  const broken = t.invariants.filter((i) => !i.held);
  return (
    <Section title="Time course" id="k-time" aside={<ComputedNote />}>
      <TimeCourseChart
        title="Every species over the simulated window"
        caption={`${t.points} points; the window is ${t.window_basis}. Simulated by Caterva from the values in the table above.`}
        times={t.times}
        series={t.columns}
        timeUnit="s"
        unit={result.model.concentration_unit}
      />
      {t.invariants.length ? (
        <p className={broken.length ? "k-invariants text-caution" : "k-invariants muted"}>
          {broken.length
            ? `${broken.length} conservation law(s) did not hold over the run: ${broken.map((i) => i.law).join("; ")}`
            : `Every conservation law held over the run: ${t.invariants.map((i) => i.law).join("; ")}.`}
        </p>
      ) : null}
      {t.unmeasured.length ? (
        <p className="k-invariants muted">Drawn with placeholders standing in for: {t.unmeasured.join(", ")}.</p>
      ) : null}
    </Section>
  );
}

function ComputedNote() {
  return (
    <span className="k-computed-note">
      <ProvenanceMark provenance={{ kind: "computed" }} decorative /> computed by Caterva
    </span>
  );
}

function Influence({ result }: { result: Result }) {
  const s = result.sensitivity;
  if (!s || s.sensitivities.length === 0) return null;
  const max = Math.max(0, ...s.sensitivities.map((r) => (r.relative === null ? 0 : Math.abs(r.relative))));
  return (
    <Section title="Which constants matter" id="k-influence" aside={<ComputedNote />}>
      <p className="k-lede">
        Relative sensitivity of {s.quantity} to each constant: the fraction it moves for a fraction moved in the
        constant. Measure the top of this list first.
      </p>
      <div className="table-wrap">
        <table className="table k-influence">
          <thead>
            <tr>
              <th scope="col">Constant</th>
              <th scope="col" data-align="end">
                Relative sensitivity
              </th>
              <th scope="col" aria-hidden="true" />
            </tr>
          </thead>
          <tbody>
            {s.sensitivities.map((row) => (
              <tr key={row.parameter}>
                <th scope="row" className="font-mono k-ledger-name">
                  {row.parameter}
                </th>
                <td data-align="end" data-numeric="true">
                  {row.relative === null ? "not computed" : formatNumber(row.relative)}
                  {row.unresolvable ? <span className="muted"> below resolution</span> : row.negligible ? <span className="muted"> negligible</span> : null}
                </td>
                <td className="k-bar-cell" aria-hidden="true">
                  {row.relative !== null && max > 0 ? (
                    <span className="k-bar" data-sign={row.relative < 0 ? "neg" : "pos"} style={{ width: `${(Math.abs(row.relative) / max) * 100}%` }} />
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {Object.keys(s.skipped).length ? (
        <p className="k-invariants muted">
          Not ranked: {Object.entries(s.skipped).map(([k, why]) => `${k} (${why})`).join("; ")}
        </p>
      ) : null}
    </Section>
  );
}

function SteadyStates({ result }: { result: Result }) {
  const st = result.stability;
  if (!st) return null;
  return (
    <Section
      title="Steady states"
      id="k-steady"
      aside={
        <span className="font-mono">
          {st.fixed_points.length} found from {st.starts_tried} starts
        </span>
      }
    >
      {st.fixed_points.length ? (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th scope="col">State</th>
                {st.species.map((sp) => (
                  <th scope="col" key={sp} data-align="end" className="font-mono">
                    {sp}
                  </th>
                ))}
                <th scope="col" data-align="end">
                  Slowest timescale (s)
                </th>
              </tr>
            </thead>
            <tbody>
              {st.fixed_points.map((fp, i) => (
                <tr key={i}>
                  <th scope="row">
                    <span className="k-state-class" data-stable={fp.stable ? "true" : "false"}>
                      {fp.classification}
                    </span>
                    {!fp.physical ? <span className="text-caution"> not physical</span> : null}
                  </th>
                  {st.species.map((sp) => (
                    <td key={sp} data-align="end" data-numeric="true">
                      {fp.state[sp] === null || fp.state[sp] === undefined ? "none" : formatNumber(fp.state[sp] as number)}
                    </td>
                  ))}
                  <td data-align="end" data-numeric="true">
                    {fp.slowest_timescale === null ? "none" : formatNumber(fp.slowest_timescale)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      <p className="k-invariants muted">
        Amounts in {result.model.concentration_unit}, computed by Caterva
        <ProvenanceMark provenance={{ kind: "computed" }} />.
        {st.notes.length ? ` ${st.notes.join(" ")}` : ""}
      </p>
      <Disclosure title="As the report prints it">
        <pre className="report-text">{st.text}</pre>
      </Disclosure>
    </Section>
  );
}

const STATUS_WORD: Record<StructuredSection["status"], string> = {
  answered: "answered",
  refused: "refused",
  partly_refused: "partly refused",
};

function AnalysisSection({ section }: { section: StructuredSection }) {
  return (
    <section className="k-analysis" id={`k-section-${section.key}`} aria-labelledby={`k-section-${section.key}-title`}>
      <div className="k-analysis-head">
        <h3 className="k-analysis-title" id={`k-section-${section.key}-title`}>
          {section.title}
        </h3>
        <span className="chip" data-tone={section.status === "answered" ? "signal" : undefined}>
          {STATUS_WORD[section.status]}
        </span>
      </div>
      {section.status === "refused" && section.refusals.length ? (
        <RefusalState title="Refused, and why" reason={section.refusals.join("\n\n")} />
      ) : null}
      {section.status === "partly_refused" ? (
        <p className="k-partly">
          <span className="state-kicker">Refused in part</span> {section.refusals.length} of the questions in this section
          {section.refusals.length === 1 ? " was" : " were"} refused; each says why, and what it would need, where it stands in the text below.
        </p>
      ) : null}
      <SectionFigure section={section} />
      {section.status !== "refused" || !section.refusals.length ? <MarkdownReport source={section.text} className="k-analysis-text" /> : null}
    </section>
  );
}

export function ComposeResultView({ result, run }: { result: Result; run: RunRecord }) {
  const refusedExports = Object.entries(result.exports).filter(([, e]) => !e.available);
  return (
    <>
      <Verdict result={result} run={run} />
      <p className="k-reading">
        Read <span className="font-mono">{result.query}</span> as {result.recognition.reading}{" "}
        <span className="muted font-mono">({result.recognition.rule})</span>
      </p>
      <Search result={result} />
      <NumbersLedger result={result} />
      <TimeCourse result={result} />
      <Influence result={result} />
      <SteadyStates result={result} />
      {result.sweeps.length ? (
        <Section title="Sweeps" id="k-sweeps" aside={<ComputedNote />}>
          {result.sweeps.map((s, i) => (
            <SweepFigure key={i} sweep={s} unit={result.model.concentration_unit} />
          ))}
        </Section>
      ) : null}
      {result.sections.length ? (
        <Section title="Analyses you asked for" id="k-sections" aside={<span className="font-mono">{result.sections.length}</span>}>
          {result.sections.map((s) => (
            <AnalysisSection key={s.key} section={s} />
          ))}
        </Section>
      ) : null}
      {result.notes.length ? (
        <Section title="Notes" id="k-notes">
          <ul className="k-notes">
            {result.notes.map((n) => (
              <li key={n}>{n}</li>
            ))}
          </ul>
        </Section>
      ) : null}
      {refusedExports.length ? (
        <Section title="Not exported" id="k-not-exported">
          <ul className="k-notes">
            {refusedExports.map(([format, e]) => (
              <li key={format}>
                <span className="font-mono">{format}</span> {e.refused}
              </li>
            ))}
          </ul>
        </Section>
      ) : null}
      <Disclosure title="The report caterva compose prints">
        <MarkdownReport source={result.report_markdown} />
      </Disclosure>
    </>
  );
}
