/**
 * A `caterva sim ssa` result: the counts at the end beside the deterministic
 * (ODE) expectation the command prints, the trajectory as the engine wrote
 * it, the inputs with whether you or the command's default chose each, and
 * the text the command prints.
 *
 * The comparison is the library's two numbers side by side, each with its
 * mark (the run's count is computed by the SSA, the expectation by its
 * closed form); the page does not subtract them.
 */
import type { SimResult as Result } from "@/api/types";
import { TimeCourseChart } from "@/components/charts/TimeCourseChart";
import { Disclosure } from "@/components/forms/Disclosure";
import { Value } from "@/components/provenance/Value";
import { TextReport } from "@/components/report/Report";
import { Section } from "@/components/screen/Screen";
import { formatCount } from "@/lib/format";

export function SimResultView({ result }: { result: Result }) {
  const { time, ...counts } = result.series;
  const rows = result.rows ?? time?.length ?? 0;
  const every = result.every ?? 1;
  const finalNames = Object.keys(result.final);
  const timeUnit = result.parameters.end?.unit ?? "time units";
  return (
    <>
      <section className="k-verdict" aria-label="At the end of the run">
        <p className="k-eyebrow">
          <span className="font-mono">{formatCount(result.events)}</span> events, seed{" "}
          <span className="font-mono">{result.seed}</span>
        </p>
        <dl className="k-finals">
          {finalNames.map((n) => (
            <div key={n}>
              <dt className="font-mono">{n.toUpperCase()} at the end</dt>
              <dd>
                <Value v={result.final[n]} />
              </dd>
            </div>
          ))}
          <div data-kind="expected">
            <dt>{result.expected.label ?? "Expected (ODE)"}</dt>
            <dd>
              <Value v={result.expected} />
            </dd>
          </div>
        </dl>
        <p className="k-verdict-licence muted">
          One trajectory is one draw; the expectation is the mean a large population would follow. The same seed gives
          this same trajectory again.
        </p>
      </section>
      <TimeCourseChart
        title="Molecule counts, one step per event"
        caption={
          every > 1
            ? `${formatCount(rows)} rows in the event table; every ${every}th row and the last are drawn. The CSV export holds them all.`
            : `${formatCount(rows)} rows in the event table, every one drawn.`
        }
        times={time ?? []}
        series={counts}
        timeUnit={timeUnit}
        unit="molecules"
        step
      />
      <Section title="Inputs" id="k-sim-inputs">
        <div className="table-wrap">
          <table className="table k-inputs">
            <tbody>
              {Object.entries(result.parameters).map(([name, v]) => (
                <tr key={name}>
                  <th scope="row" className="font-mono k-ledger-name">
                    {name}
                  </th>
                  <td data-align="end">
                    <Value v={v} />
                  </td>
                  <td className="muted">
                    {v.provenance.kind === "chosen" ? (v.provenance.by === "user" ? "chosen by you" : "the command's default") : ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>
      <Disclosure title="What caterva sim ssa prints">
        <TextReport text={result.report_text} />
      </Disclosure>
    </>
  );
}
