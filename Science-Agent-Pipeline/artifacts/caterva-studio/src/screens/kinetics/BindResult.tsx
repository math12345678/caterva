/**
 * A `caterva bind` result: the measured ΔG°bind band a simulation is held
 * to, the Ki rows it is built from (and the rows excluded, with why), the
 * verdict on a computed value, the survey, or the compound list.
 *
 * The band figure draws only what the server sent: each row's ΔG°bind (a
 * point at its stated temperature, or its range when the row states none),
 * the band's two edges, and the computed value with its 2σ whiskers.
 */
import { scaleLinear } from "d3-scale";

import type { BindResult as Result, BindSurveyRow, BindTarget, BindVerdict, KiRow, SourcedValue } from "@/api/types";
import { Value } from "@/components/provenance/Value";
import { formatNumber } from "@/lib/format";

import { Report } from "./Report";

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
  const rowH = 18;
  const top = 12;
  const height = top + rows.length * rowH + (whisker ? rowH + 6 : 0) + 30;
  const lo = Math.min(...values);
  const hi = Math.max(...values);
  const pad = (hi - lo || 1) * 0.08;
  const x = scaleLinear().domain([lo - pad, hi + pad]).range([24, width - 24]);
  const ticks = x.ticks(6);
  const bandLow = target.band_low?.value;
  const bandHigh = target.band_high?.value;
  const axisY = height - 22;
  return (
    <figure className="k-band" style={{ margin: 0 }}>
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`ΔG°bind of each Ki row and the band ${target.band_low ? "" : "(none)"}`}>
        {bandLow != null && bandHigh != null ? (
          <rect
            x={x(bandLow)}
            y={top - 6}
            width={Math.max(1, x(bandHigh) - x(bandLow))}
            height={axisY - top}
            fill="var(--signal)"
            opacity={0.16}
          />
        ) : null}
        {rows.map((r, i) => {
          const span = dgSpan(r.dg);
          if (!span) return null;
          const y = top + i * rowH + rowH / 2;
          return span[0] === span[1] ? (
            <rect key={r.ki.id} x={x(span[0]) - 4} y={y - 4} width={8} height={8} fill="var(--prov-computed)" />
          ) : (
            <line key={r.ki.id} x1={x(span[0])} x2={x(span[1])} y1={y} y2={y} stroke="var(--prov-computed)" strokeWidth={3} />
          );
        })}
        {whisker && verdict ? (
          <g>
            <line
              x1={x(whisker[0])}
              x2={x(whisker[1])}
              y1={top + rows.length * rowH + rowH / 2 + 4}
              y2={top + rows.length * rowH + rowH / 2 + 4}
              stroke="var(--fg)"
              strokeWidth={1.5}
            />
            <rect
              x={x(verdict.computed.value as number) - 1.5}
              y={top + rows.length * rowH + 4}
              width={3}
              height={rowH - 2}
              fill="var(--fg)"
            />
          </g>
        ) : null}
        <line x1={24} x2={width - 24} y1={axisY} y2={axisY} stroke="var(--rule)" />
        {ticks.map((t) => (
          <text key={t} x={x(t)} y={axisY + 15} textAnchor="middle">
            {formatNumber(t, 3)}
          </text>
        ))}
      </svg>
      <figcaption className="k-small k-muted">
        ΔG°bind in kcal/mol. Squares: each row at its stated temperature; bars: a row stating none, over the range
        bind uses instead. Shaded: the band.{whisker ? " Below: the computed value and ±2σ." : ""}
      </figcaption>
    </figure>
  );
}

function RowsTable({ rows, caption, excluded }: { rows: KiRow[]; caption: string; excluded?: boolean }) {
  if (rows.length === 0) return null;
  return (
    <div className="k-table-wrap">
      <table className="k-table">
        <caption className="k-section-sub" style={{ textAlign: "left", paddingBottom: "0.35rem" }}>
          {caption}
        </caption>
        <thead>
          <tr>
            <th scope="col">Ki</th>
            <th scope="col">ΔG°bind</th>
            <th scope="col">Mode</th>
            <th scope="col">Isoform</th>
            <th scope="col">{excluded ? "Why not comparable" : "BRENDA's row"}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.ki.id}>
              <td className="k-num">
                <Value v={r.ki} />
              </td>
              <td className="k-num">
                <Value v={r.dg} />
              </td>
              <td className="k-small">
                {r.mode}
                {r.versus ? ` vs ${r.versus}` : ""}
              </td>
              <td className="k-small">{r.isoform ?? ""}</td>
              <td className="k-small k-muted">{excluded ? r.excluded : r.commentary}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Verdict({ verdict }: { verdict: BindVerdict }) {
  return (
    <section className="k-verdict" aria-label="Verdict">
      <p className="k-section-sub">Verdict on the computed value</p>
      <p className="k-verdict-word" data-tone={verdict.word === "agrees" ? undefined : "danger"}>
        {verdict.word}
      </p>
      <p className="k-prose">{verdict.detail}.</p>
      <div className="k-table-wrap">
        <table className="k-table" style={{ width: "auto" }}>
          <tbody>
            <tr>
              <th scope="row">Computed</th>
              <td className="k-num">
                <Value v={verdict.computed} />
                {verdict.computed_error ? (
                  <>
                    {" ± "}
                    <Value v={verdict.computed_error} />
                  </>
                ) : null}
              </td>
            </tr>
            <tr>
              <th scope="row">Beyond the band at 2σ</th>
              <td className="k-num">
                <Value v={verdict.gap_kcal} />
              </td>
            </tr>
            <tr>
              <th scope="row">As a Ki error</th>
              <td className="k-num">
                <Value v={verdict.ki_fold} />
              </td>
            </tr>
            {verdict.temperature_c ? (
              <tr>
                <th scope="row">Judged at</th>
                <td className="k-num">
                  <Value v={verdict.temperature_c} />
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function Target({ target, verdict }: { target: BindTarget; verdict: BindVerdict | null }) {
  return (
    <>
      {verdict ? <Verdict verdict={verdict} /> : null}
      <section className="k-section" aria-labelledby="k-target">
        <h2 className="k-section-title" id="k-target">
          {target.compound} binding {target.organism}, {target.state} state
        </h2>
        {target.band_low && target.band_high ? (
          <p className="k-prose">
            The band: <Value v={target.band_low} /> to <Value v={target.band_high} />, from{" "}
            {target.references.length} publication(s) ({target.references.map((r) => `BRENDA ref ${r}`).join(", ")}).
          </p>
        ) : (
          <p className="k-prose">No row fits this state, so there is no band.</p>
        )}
        <BandFigure target={target} verdict={verdict} />
        {target.caveats.length > 0 ? (
          <ul className="k-list k-small">
            {target.caveats.map((c) => (
              <li key={c}>{c}</li>
            ))}
          </ul>
        ) : null}
        <RowsTable rows={target.used} caption={`${target.used.length} row(s) fit this state`} />
        <RowsTable
          rows={target.excluded}
          caption={`${target.excluded.length} row(s) not comparable, shown so the exclusion can be argued with`}
          excluded
        />
      </section>
    </>
  );
}

function Survey({ rows }: { rows: BindSurveyRow[] }) {
  return (
    <section className="k-section" aria-labelledby="k-survey">
      <h2 className="k-section-title" id="k-survey">
        Every inhibitor's target
      </h2>
      <div className="k-table-wrap">
        <table className="k-table">
          <thead>
            <tr>
              <th scope="col">Compound</th>
              <th scope="col">Organism</th>
              <th scope="col">Rows used</th>
              <th scope="col">Band</th>
              <th scope="col">Benchmark</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={`${r.compound}-${r.organism}-${r.isoform ?? ""}`}>
                <td>
                  {r.compound}
                  {r.isoform ? <span className="k-muted"> [{r.isoform}]</span> : null}
                </td>
                <td className="k-small">{r.organism}</td>
                <td className="font-mono tabular-nums">
                  {r.used} of {r.rows}
                </td>
                <td className="k-num">
                  {r.band_low && r.band_high ? (
                    <>
                      <Value v={r.band_low} showUnit={false} /> to <Value v={r.band_high} />
                    </>
                  ) : (
                    <span className="k-muted">none</span>
                  )}
                </td>
                <td className="k-small">{r.benchmark ? "usable" : r.why_not.join("; ")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export function BindResultView({
  result,
  onPick,
}: {
  result: Result;
  /** Called with a compound from the list, to ask for its target. */
  onPick?: (compound: string) => void;
}) {
  return (
    <>
      {result.target ? <Target target={result.target} verdict={result.verdict} /> : null}
      {result.mode === "survey" && result.survey.length > 0 ? <Survey rows={result.survey} /> : null}
      {result.mode === "list" && result.compounds.length > 0 ? (
        <section className="k-section" aria-labelledby="k-compounds">
          <h2 className="k-section-title" id="k-compounds">
            Compounds with a recorded Ki
          </h2>
          <ul className="k-list" style={{ listStyle: "none", paddingLeft: 0 }}>
            {result.compounds.map((c) => (
              <li key={c}>
                {onPick ? (
                  <button type="button" className="k-button k-button-quiet" onClick={() => onPick(c)}>
                    {c}
                  </button>
                ) : (
                  c
                )}
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      <Report title="What caterva bind prints" text={result.report_text} />
    </>
  );
}
