/**
 * The result at a glance: what the enzyme is, what was measured for it, under
 * which conditions, and which source each number is from.
 *
 * Three parts, one after another, all drawn from the result the engine sent:
 *
 *  1. the map: what was asked (organism, substrate, assay conditions) on one
 *     side, the enzyme in the middle, its constants on the other, so how they
 *     relate is seen before any table is read;
 *  2. the line items: one row per constant with its value, citation, assay
 *     conditions and the range the sources span, so each number is traced to
 *     its source without opening anything;
 *  3. the starting amounts, which no paper supplies and which stay "yours to
 *     set" until the request sets them.
 *
 * Nothing here is typed in or inferred beyond what a function below states.
 * A constant in the model's Km slot whose source row is a K0.5 (a cooperative
 * half-saturation constant) is named K0.5, with its Hill coefficient, because
 * the engine says so in the row's scope (`halfSaturationOf`). The enzyme is
 * named by its EC number and by the isoform only when the request named one:
 * the isoform the engine settled on by itself is in its own sentence in the
 * verdict, and is not parsed out of that sentence here.
 */
import type { ComposeResult as Result, SourcedValue } from "@/api/types";
import { Citation } from "@/components/provenance/Citation";
import { constantName, halfSaturationOf } from "@/components/provenance/halfSaturation";
import { Value } from "@/components/provenance/Value";
import { formatNumber } from "@/lib/format";

/** "pH 7.6 · 25 °C" for a measured value, or null when the row states neither. */
export function conditionsLine(v: SourcedValue): string | null {
  const c = v.provenance.conditions;
  if (!c) return null;
  const parts: string[] = [];
  if (c.ph !== null) parts.push(`pH ${c.ph}`);
  if (c.temperature_c !== null) parts.push(`${c.temperature_c} °C`);
  return parts.length ? parts.join(" · ") : null;
}

/** True when every starting amount is the command's default: nobody set one. */
export function startsAreDefaults(result: Result): boolean {
  const species = result.model.species;
  return species.length > 0 && species.every((s) => s.initial.provenance.kind === "chosen" && s.initial.provenance.by !== "user");
}

function Node({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="k-map-node">
      <span className="k-map-node-label">{label}</span>
      <span className="k-map-node-value">{children}</span>
    </div>
  );
}

export function ResultMap({ result }: { result: Result }) {
  const constants = result.model.parameters;
  if (!constants.length) return null;
  const s = result.search;
  const measured = constants.filter((p) => p.provenance.kind === "measured");
  const conditions = new Set(measured.map(conditionsLine));
  const shared = measured.length > 0 && conditions.size === 1 ? [...conditions][0] : null;
  const organisms = new Set(measured.map((p) => p.provenance.organism ?? null));
  const organism = s.organism ?? (organisms.size === 1 ? [...organisms][0] : null);
  const species = result.model.species;
  const defaults = startsAreDefaults(result);
  const [reaction] = result.model.reactions;

  return (
    <section className="k-map" aria-label="The result at a glance" data-testid="result-map">
      <div className="k-map-diagram">
        <div className="k-map-side" data-side="asked">
          {organism ? (
            <Node label="Organism">
              <em>{organism}</em>
            </Node>
          ) : null}
          {s.substrate ? <Node label="Substrate">{s.substrate}</Node> : null}
          <Node label="Assay conditions">
            {measured.length === 0 ? (
              <span className="muted">no measured constant</span>
            ) : shared ? (
              <span className="font-mono">{shared}</span>
            ) : conditions.size === 1 ? (
              <span className="text-caution">not stated by the source rows</span>
            ) : (
              <span className="text-caution">differ by constant: see each line below</span>
            )}
          </Node>
        </div>

        <div className="k-map-enzyme" data-testid="result-map-enzyme">
          <span className="k-map-node-label">Enzyme</span>
          {s.isoform ? <span className="k-map-enzyme-name">{s.isoform}</span> : null}
          {s.ec || s.subject ? (
            <span className={s.isoform ? "k-map-enzyme-ec font-mono" : "k-map-enzyme-name font-mono"}>EC {s.ec ?? s.subject}</span>
          ) : (
            <span className="k-map-enzyme-name">{result.recognition.reading}</span>
          )}
          <span className="k-map-enzyme-law">modelled as {result.recognition.reading}</span>
        </div>

        <div className="k-map-side" data-side="constants">
          {constants.map((p) => {
            const half = halfSaturationOf(p);
            return (
              <div className="k-map-constant" key={p.id ?? p.label} data-kind={p.provenance.kind} data-testid={`map-constant-${p.id ?? p.label}`}>
                <span className="k-map-node-label">
                  {constantName(p)}
                  {half ? <span className="k-map-slot"> in the model&apos;s Km slot</span> : null}
                </span>
                <Value v={p} className="k-map-value" />
                {half ? (
                  <span className="k-map-hill" data-testid="hill">
                    {half.hill === null ? "Hill coefficient not stated by the row" : `Hill coefficient ${half.hill}`}
                  </span>
                ) : null}
              </div>
            );
          })}
        </div>
      </div>

      {reaction ? (
        <p className="k-map-law">
          <span className="k-label-inline">Rate law</span> <span className="font-mono">{reaction.rate_law}</span>
        </p>
      ) : null}

      <div className="table-wrap">
        <table className="table k-lines" data-testid="result-lines">
          <caption className="k-lines-caption">Each constant, traced to its source</caption>
          <thead>
            <tr>
              <th scope="col">Constant</th>
              <th scope="col" data-align="end">
                Value
              </th>
              <th scope="col">Source</th>
              <th scope="col">Measured at</th>
              <th scope="col">Range across sources</th>
            </tr>
          </thead>
          <tbody>
            {constants.map((p) => {
              const half = halfSaturationOf(p);
              const prov = p.provenance;
              const at = conditionsLine(p);
              const sp = prov.spread;
              return (
                <tr key={p.id ?? p.label} data-kind={prov.kind}>
                  <th scope="row" className="k-ledger-name">
                    <span>{constantName(p)}</span>
                    <span className="k-ledger-sub font-mono">{p.id}</span>
                    {half ? (
                      <span className="k-ledger-sub">
                        {half.hill === null ? "a K0.5, not a Km" : `a K0.5 (Hill ${half.hill}), not a Km`}
                      </span>
                    ) : null}
                  </th>
                  <td data-align="end" className="k-ledger-value">
                    <Value v={p} />
                  </td>
                  <td>
                    {prov.kind === "measured" && prov.citation ? (
                      <Citation citation={prov.citation} />
                    ) : prov.kind === "measured" ? (
                      <span className="text-caution">measured, no citation recorded</span>
                    ) : (
                      <span className="text-caution">not from the literature ({prov.kind})</span>
                    )}
                  </td>
                  <td>
                    {prov.kind !== "measured" ? (
                      <span className="muted">not applicable</span>
                    ) : at ? (
                      <span className="font-mono">{at}</span>
                    ) : (
                      <span className="text-caution">not stated</span>
                    )}
                  </td>
                  <td>
                    {sp && sp.low !== null && sp.high !== null ? (
                      <span>
                        <span className="font-mono">
                          {formatNumber(sp.low)} to {formatNumber(sp.high)} {sp.unit}
                        </span>
                        <span className="muted">
                          {" "}
                          ({sp.n_values} values, {sp.references.length} sources)
                        </span>
                      </span>
                    ) : (
                      <span className="muted">one value</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
          <tfoot>
            <tr>
              <th scope="row" colSpan={4}>
                From the literature
              </th>
              <td className="font-mono" data-testid="lines-total">
                {measured.length} / {constants.length}
              </td>
            </tr>
          </tfoot>
        </table>
      </div>

      {species.length ? (
        <div className="k-map-starts" data-testid="map-starts" data-defaults={defaults ? "true" : "false"}>
          <span className="k-map-node-label">Starting amounts</span>
          {defaults ? (
            <p>
              <strong>Yours to set.</strong> No paper supplies a starting amount and this request set none, so none is shown as a
              result. The time course below was computed with the command&apos;s stand-in defaults and shows the shape of the curve
              only.
            </p>
          ) : (
            <ul className="k-map-start-list">
              {species.map((sp) => (
                <li key={sp.id}>
                  <span className="font-mono">{sp.id}</span> <Value v={sp.initial} />
                </li>
              ))}
            </ul>
          )}
        </div>
      ) : null}
    </section>
  );
}

export { constantName, halfSaturationOf };
