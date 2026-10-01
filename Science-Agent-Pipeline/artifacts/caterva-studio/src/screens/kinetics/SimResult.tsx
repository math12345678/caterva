/**
 * A `caterva sim ssa` result: the trajectory as the engine wrote it, the
 * final counts, the ODE expectation beside them, and the text the command
 * prints.
 */
import type { SimResult as Result } from "@/api/types";
import { Value } from "@/components/provenance/Value";

import { Report } from "./Report";
import { SeriesChart } from "./SeriesChart";

export function SimResultView({ result }: { result: Result }) {
  const { time, ...counts } = result.series;
  const rows = result.rows ?? result.series.time?.length ?? 0;
  const thinned = (result.every ?? 1) > 1;
  const finalNames = Object.keys(result.final);
  return (
    <>
      <section className="k-verdict" aria-label="Summary">
        <p className="k-section-sub">
          {result.events} events, seed <span className="k-code">{result.seed}</span>
        </p>
        <div className="k-table-wrap">
          <table className="k-table" style={{ width: "auto" }}>
            <thead>
              <tr>
                <th scope="col" />
                {finalNames.map((n) => (
                  <th key={n} scope="col" className="k-code">
                    {n.toUpperCase()}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              <tr>
                <th scope="row">At the end of this run</th>
                {finalNames.map((n) => (
                  <td key={n} className="k-num">
                    <Value v={result.final[n]} showUnit={false} />
                  </td>
                ))}
              </tr>
            </tbody>
          </table>
        </div>
        <p className="k-prose">
          {result.expected.label ?? "Expected (ODE)"}: <Value v={result.expected} />
        </p>
      </section>
      <SeriesChart
        x={time ?? []}
        series={counts}
        xLabel="time"
        yLabel="molecules"
        step
        label="Molecule counts over the run, one step per event"
      />
      <p className="k-section-sub">
        {thinned
          ? `${rows} rows in the event table; every ${result.every}th row and the last are drawn. The CSV file holds them all.`
          : `${rows} rows in the event table, every one drawn.`}
      </p>
      <section className="k-section" aria-labelledby="k-inputs">
        <h2 className="k-section-title" id="k-inputs">
          Inputs
        </h2>
        <div className="k-table-wrap">
          <table className="k-table" style={{ width: "auto" }}>
            <tbody>
              {Object.entries(result.parameters).map(([name, v]) => (
                <tr key={name}>
                  <th scope="row" className="k-code" style={{ fontWeight: 400 }}>
                    {name}
                  </th>
                  <td className="k-num">
                    <Value v={v} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <Report title="What caterva sim ssa prints" text={result.report_text} />
    </>
  );
}
