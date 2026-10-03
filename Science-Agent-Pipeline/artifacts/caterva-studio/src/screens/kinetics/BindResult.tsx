/**
 * A `caterva bind` result: the measured ΔG°bind band a simulation is held
 * to, with the arithmetic that turns each cited Ki into it shown step by
 * step; the verdict on a computed value when one was given; the rows
 * excluded, with why; the survey; or the list of compounds.
 *
 * The arithmetic is the library's: each step names its method in the
 * library's words (`provenance.method`, "ΔG°bind = RT ln(Ki / 1 M) at the
 * row's assay temperature (bind.core.dg_kj)") and shows the numbers it
 * took and gave, each a SourcedValue with its mark. The page computes
 * none of them. The band figure draws only what the server sent: each
 * row's ΔG°bind (a point at its stated temperature, or its whole range
 * when the row states none), the band's two edges, and the computed value
 * with its 2σ whiskers.
 */
import { scaleLinear } from "d3-scale";
import { ArrowRight } from "lucide-react";

import type { BindResult as Result, BindSurveyRow, BindTarget, BindVerdict, KiRow, RunRecord, SourcedValue } from "@/api/types";
import { Disclosure } from "@/components/forms/Disclosure";
import { Citation } from "@/components/provenance/Citation";
import { Value } from "@/components/provenance/Value";
import { TextReport } from "@/components/report/Report";
import { Section } from "@/components/screen/Screen";
import { NegativeState } from "@/components/states/States";
import { DataTable } from "@/components/table/DataTable";
import { plural } from "@/lib/copy";
import { formatNumber } from "@/lib/format";

function dgSpan(v: SourcedValue): [number, number] | null {
  if (v.value !== null) return [v.value, v.value];
  if (v.interval && v.interval.low !== null && v.interval.high !== null) return [v.interval.low, v.interval.high];
  return null;
}

export function BandFigure({ target, verdict }: { target: BindTarget; verdict: BindVerdict | null }) {
  const rows = target.used;
  const spans = rows.map((r) => dgSpan(r.dg)).filter((s): s is [number, number] => s !== null);
  const values = spans.flat();
  if (target.band_low?.value != null) values.push(target.band_low.value);
  if (target.band_high?.value != null) values.push(target.band_high.value);
  let whisker: [number, number] | null = null;
  if (verdict?.computed.value != null) {
    const sigma = verdict.computed_error?.value ?? 0;
    whisker = [verdict.computed.value - 2 * sigma, verdict.computed.value + 2 * sigma];
    values.push(...whisker);
  }
  if (values.length === 0) return null;
  const width = 640;
  const rowH = 20;
  const top = 14;
  const labelW = 0;
  const height = top + rows.length * rowH + (whisker ? rowH + 8 : 0) + 34;
  const lo = Math.min(...values);
  const hi = Math.max(...values);
  const pad = (hi - lo || 1) * 0.08;
  const x = scaleLinear()
    .domain([lo - pad, hi + pad])
    .range([24 + labelW, width - 24]);
  const ticks = x.ticks(6);
  const bandLow = target.band_low?.value;
  const bandHigh = target.band_high?.value;
  const axisY = height - 24;
  return (
    <figure className="chart k-band">
      <div className="chart-head">
        <h3 className="chart-title">Each row&apos;s ΔG°bind and the band</h3>
      </div>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label={`ΔG°bind of ${plural(rows.length, "Ki row")}${bandLow != null && bandHigh != null ? `, the band from ${formatNumber(bandLow)} to ${formatNumber(bandHigh)} kcal/mol` : ", no band"}${whisker && verdict?.computed.value != null ? `, and the computed value ${formatNumber(verdict.computed.value)} kcal/mol with its 2σ range` : ""}`}
      >
        {bandLow != null && bandHigh != null ? (
          <rect x={x(bandLow)} y={top - 8} width={Math.max(1, x(bandHigh) - x(bandLow))} height={axisY - top + 4} className="k-band-fill" />
        ) : null}
        {rows.map((r, i) => {
          const span = dgSpan(r.dg);
          if (!span) return null;
          const y = top + i * rowH + rowH / 2;
          return span[0] === span[1] ? (
            <rect key={r.ki.id} x={x(span[0]) - 4} y={y - 4} width={8} height={8} className="k-band-point" />
          ) : (
            <line key={r.ki.id} x1={x(span[0])} x2={x(span[1])} y1={y} y2={y} className="k-band-range" />
          );
        })}
        {whisker && verdict ? (
          <g className="k-band-computed">
            <line x1={x(whisker[0])} x2={x(whisker[1])} y1={top + rows.length * rowH + rowH / 2 + 6} y2={top + rows.length * rowH + rowH / 2 + 6} />
            <rect x={x(verdict.computed.value as number) - 1.5} y={top + rows.length * rowH + 6} width={3} height={rowH - 2} />
          </g>
        ) : null}
        <line x1={24} x2={width - 24} y1={axisY} y2={axisY} className="k-band-axis" />
        {ticks.map((t) => (
          <text key={t} x={x(t)} y={axisY + 16} textAnchor="middle" className="k-band-tick">
            {formatNumber(t, 3)}
          </text>
        ))}
      </svg>
      <figcaption className="chart-caption">
        ΔG°bind in kcal/mol, computed by Caterva from each cited Ki. Squares: a row at its stated assay temperature;
        bars: a row stating none, over the range bind uses instead. Shaded: the band.
        {whisker ? " Below the rows: the computed value and its ±2σ range." : ""}
      </figcaption>
    </figure>
  );
}

function temperatureOf(row: KiRow): string {
  const t = row.ki.provenance.conditions?.temperature_c;
  if (t !== null && t !== undefined) return `at ${t} °C`;
  return row.dg.interval?.meaning ?? "temperature not stated";
}

/** Ki to ΔG°bind, one row per cited Ki: the arithmetic, with both numbers marked. */
function Arithmetic({ rows }: { rows: KiRow[] }) {
  const method = rows.find((r) => r.dg.provenance.method)?.dg.provenance.method;
  return (
    <div className="k-arith">
      {method ? (
        <p className="k-arith-method">
          <span className="k-label-inline">Each row</span>
          <span className="font-mono">{method}</span>
        </p>
      ) : null}
      <ol className="k-arith-rows">
        {rows.map((r) => (
          <li key={r.ki.id}>
            <span className="k-arith-in">
              Ki <Value v={r.ki} />
            </span>
            <span className="k-arith-at muted">{temperatureOf(r)}</span>
            <ArrowRight size={13} aria-label="gives" />
            <span className="k-arith-out">
              ΔG°bind <Value v={r.dg} />
            </span>
            <span className="k-arith-ref">{r.ki.provenance.citation ? <Citation citation={r.ki.provenance.citation} /> : null}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}

function RowsTable({ rows, caption, excluded }: { rows: KiRow[]; caption: string; excluded?: boolean }) {
  if (rows.length === 0) return null;
  return (
    <DataTable
      caption={caption}
      rows={rows}
      rowKey={(r) => r.ki.id ?? r.reference ?? r.compound}
      columns={[
        { key: "ki", header: "Ki", align: "end", cell: (r) => <Value v={r.ki} />, sortValue: (r) => r.ki.value },
        { key: "dg", header: "ΔG°bind", align: "end", cell: (r) => <Value v={r.dg} />, sortValue: (r) => r.dg.value ?? r.dg.interval?.low ?? null },
        { key: "ref", header: "Reference", cell: (r) => (r.ki.provenance.citation ? <Citation citation={r.ki.provenance.citation} /> : r.reference ?? "") },
        { key: "mode", header: "Mode", cell: (r) => `${r.mode}${r.versus ? ` vs ${r.versus}` : ""}` },
        { key: "iso", header: "Isoform", cell: (r) => r.isoform ?? "" },
        {
          key: "says",
          header: excluded ? "Why it is not comparable" : "The row says",
          cell: (r) => <span className="k-cell-prose">{excluded ? r.excluded : r.commentary}</span>,
        },
      ]}
    />
  );
}

function VerdictBlock({ verdict, run }: { verdict: BindVerdict; run: RunRecord }) {
  const negative = run.outcome?.meaning === "negative";
  const body = (
    <>
      <p className="k-verdict-licence">{verdict.detail}.</p>
      <ol className="k-derivation" aria-label="How the verdict was reached">
        <li>
          <span className="k-label-inline">Computed</span>
          <Value v={verdict.computed} />
          {verdict.computed_error ? (
            <>
              <span className="muted"> ± </span>
              <Value v={verdict.computed_error} />
              <span className="muted"> (σ; judged at 2σ)</span>
            </>
          ) : null}
        </li>
        <li>
          <span className="k-label-inline">Beyond the band</span>
          <Value v={verdict.gap_kcal} />
          <span className="k-derivation-method muted">{verdict.gap_kcal.provenance.method}</span>
        </li>
        <li>
          <span className="k-label-inline">As a Ki error</span>
          <Value v={verdict.ki_fold} />
          <span className="k-derivation-method muted">{verdict.ki_fold.provenance.method}</span>
        </li>
        {verdict.temperature_c ? (
          <li>
            <span className="k-label-inline">Judged at</span>
            <Value v={verdict.temperature_c} />
            <span className="k-derivation-method muted">{verdict.temperature_c.provenance.method}</span>
          </li>
        ) : null}
      </ol>
    </>
  );
  if (negative) {
    return (
      <NegativeState title={`The computed value ${verdict.word}`} reason={run.outcome?.reason ?? verdict.word}>
        {body}
      </NegativeState>
    );
  }
  return (
    <section className="k-verdict" aria-labelledby="k-bind-word">
      <p className="k-eyebrow">Verdict on the computed value</p>
      <h2 className="k-verdict-word" id="k-bind-word">
        {verdict.word}
      </h2>
      {body}
    </section>
  );
}

function Target({ target, verdict, run }: { target: BindTarget; verdict: BindVerdict | null; run: RunRecord }) {
  return (
    <>
      {verdict ? <VerdictBlock verdict={verdict} run={run} /> : null}
      <Section title={`${target.compound} binding ${target.organism}, ${target.state} state`} id="k-target">
        {target.band_low && target.band_high ? (
          <div className="k-bandline">
            <p className="k-eyebrow">The measured band</p>
            <p className="k-bandline-values">
              <Value v={target.band_low} /> <span className="muted">to</span> <Value v={target.band_high} />
            </p>
            <p className="muted">
              From {plural(target.references.length, "publication")}: {target.references.map((r) => `BRENDA ref ${r}`).join(", ")}.
              The band&apos;s edges are the lowest and highest ΔG°bind of the rows below.
            </p>
          </div>
        ) : (
          <p className="k-lede">No row fits this state, so there is no band to hold a simulation to.</p>
        )}
        {target.used.length ? <Arithmetic rows={target.used} /> : null}
        <BandFigure target={target} verdict={verdict} />
        {target.caveats.length ? (
          <div className="k-caveats">
            <p className="k-eyebrow">Read before using it</p>
            <ul>
              {target.caveats.map((c) => (
                <li key={c}>{c}</li>
              ))}
            </ul>
          </div>
        ) : null}
        <RowsTable rows={target.used} caption={`${plural(target.used.length, "row")} ${target.used.length === 1 ? "fits" : "fit"} this state`} />
        {target.excluded.length ? (
          <Disclosure title="Rows not comparable, and why" aside={<span className="font-mono">{target.excluded.length}</span>}>
            <RowsTable rows={target.excluded} caption="Shown so each exclusion can be argued with" excluded />
          </Disclosure>
        ) : null}
      </Section>
    </>
  );
}

function Survey({ rows, onPick }: { rows: BindSurveyRow[]; onPick?: (compound: string) => void }) {
  return (
    <Section title="Every inhibitor's target" id="k-survey" aside={<span className="font-mono">{rows.length}</span>}>
      <DataTable
        caption="One row per compound, organism and isoform"
        captionHidden
        rows={rows}
        rowKey={(r) => `${r.compound}-${r.organism}-${r.isoform ?? ""}`}
        onRowSelect={onPick ? (r) => onPick(r.compound) : undefined}
        columns={[
          {
            key: "c",
            header: "Compound",
            cell: (r) => (
              <>
                {r.compound}
                {r.isoform ? <span className="muted"> [{r.isoform}]</span> : null}
              </>
            ),
            sortValue: (r) => r.compound,
          },
          { key: "o", header: "Organism", cell: (r) => <em>{r.organism}</em> },
          { key: "u", header: "Rows used", numeric: true, cell: (r) => `${r.used} of ${r.rows}`, sortValue: (r) => r.used },
          {
            key: "b",
            header: "Band",
            cell: (r) =>
              r.band_low && r.band_high ? (
                <>
                  <Value v={r.band_low} showUnit={false} /> <span className="muted">to</span> <Value v={r.band_high} />
                </>
              ) : (
                <span className="muted">none</span>
              ),
            sortValue: (r) => r.band_low?.value ?? null,
          },
          { key: "k", header: "Benchmark", cell: (r) => (r.benchmark ? "usable" : <span className="k-cell-prose">{r.why_not.join("; ")}</span>) },
        ]}
      />
      {onPick ? <p className="k-invariants muted">Select a row to build that compound&apos;s target.</p> : null}
    </Section>
  );
}

export function BindResultView({
  result,
  run,
  onPick,
}: {
  result: Result;
  run: RunRecord;
  /** Called with a compound from the list or the survey, to ask for its target. */
  onPick?: (compound: string) => void;
}) {
  return (
    <>
      {result.target ? <Target target={result.target} verdict={result.verdict} run={run} /> : null}
      {result.mode === "survey" && result.survey.length ? <Survey rows={result.survey} onPick={onPick} /> : null}
      {result.mode === "list" && result.compounds.length ? (
        <Section title="Compounds with a recorded Ki" id="k-compounds" aside={<span className="font-mono">{result.compounds.length}</span>}>
          <ul className="k-compounds">
            {result.compounds.map((c) => (
              <li key={c}>
                {onPick ? (
                  <button type="button" className="k-compound" onClick={() => onPick(c)}>
                    <span>{c}</span>
                    <ArrowRight size={13} aria-hidden="true" />
                  </button>
                ) : (
                  c
                )}
              </li>
            ))}
          </ul>
          {onPick ? <p className="k-invariants muted">Choose one to build its target; it runs at once.</p> : null}
        </Section>
      ) : null}
      <Disclosure title="What caterva bind prints">
        <TextReport text={result.report_text} />
      </Disclosure>
    </>
  );
}
