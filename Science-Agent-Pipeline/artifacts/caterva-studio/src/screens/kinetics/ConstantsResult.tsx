/**
 * A `scripts/cite.py` result: each constant the resolver returned, with the
 * paper that measured it, the rows it could not rank below it, the values
 * the person supplied, and the document cite.py prints.
 */
import type { ConstantRow, ConstantsResult as Result } from "@/api/types";
import { Value } from "@/components/provenance/Value";

import { Report } from "./Report";

function Constant({ row }: { row: ConstantRow }) {
  const p = row.value?.provenance;
  return (
    <section className="k-section" aria-label={`${row.name}, ${row.quantity}`}>
      <div className="k-actions" style={{ alignItems: "baseline" }}>
        <h3 className="k-section-title k-code" style={{ fontSize: "1.2rem" }}>
          {row.name}
        </h3>
        {row.value ? (
          <span style={{ fontSize: "1.35rem" }}>
            <Value v={row.value} />
          </span>
        ) : (
          <span className="k-muted">not found ({row.source})</span>
        )}
      </div>
      {p?.kind === "measured" ? (
        <p className="k-prose k-small">
          {p.citation?.url ? (
            <a href={p.citation.url} target="_blank" rel="noreferrer noopener">
              {p.citation.text}
            </a>
          ) : (
            p.citation?.text
          )}
          {p.organism ? `, ${p.organism}` : ""}
          {p.conditions
            ? `, ${p.conditions.ph !== null ? `pH ${p.conditions.ph}` : "pH not stated"}, ${
                p.conditions.temperature_c !== null ? `${p.conditions.temperature_c} °C` : "temperature not stated"
              }`
            : ""}
          {p.commentary ? <span className="k-muted block">BRENDA's row: {p.commentary}</span> : null}
        </p>
      ) : null}
      {row.alternatives.length > 0 ? (
        <div className="k-table-wrap">
          <table className="k-table">
            <caption className="k-section-sub" style={{ textAlign: "left", paddingBottom: "0.35rem" }}>
              Other rows the resolver read for {row.name}
            </caption>
            <thead>
              <tr>
                <th scope="col">Value</th>
                <th scope="col">Reference</th>
                <th scope="col">Organism</th>
                <th scope="col">Row</th>
              </tr>
            </thead>
            <tbody>
              {row.alternatives.map((a) => (
                <tr key={a.id}>
                  <td className="k-num">
                    <Value v={a} />
                  </td>
                  <td className="k-code">{a.provenance.citation?.text}</td>
                  <td>{a.provenance.organism}</td>
                  <td className="k-small k-muted">{a.provenance.commentary}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      {!row.found && row.organisms_available.length > 0 ? (
        <p className="k-small">Measured in: {row.organisms_available.join(", ")}</p>
      ) : null}
      {row.isoforms_available.length > 0 ? (
        <p className="k-small k-muted">Isoforms with rows: {row.isoforms_available.join(", ")}</p>
      ) : null}
    </section>
  );
}

export function ConstantsResultView({ result }: { result: Result }) {
  return (
    <>
      <section className="k-verdict" aria-label="Summary">
        <p className="k-section-sub">From the literature</p>
        <p className="k-verdict-word">{result.sourced.length > 0 ? result.sourced.join(", ") : "nothing found"}</p>
        <p className="k-prose">
          {result.defensible
            ? "Every number in the model is either cited or declared as yours (the lab report's own check)."
            : "Not every number in the model is cited or declared as yours (the lab report's own check); the document says which."}
        </p>
        {result.organism_note ? <p className="k-small k-muted">{result.organism_note}</p> : null}
      </section>
      {result.constants.map((row) => (
        <Constant key={row.name} row={row} />
      ))}
      {result.supplied.length > 0 ? (
        <section className="k-section" aria-labelledby="k-supplied">
          <h2 className="k-section-title" id="k-supplied">
            Supplied, not measured
          </h2>
          <div className="k-table-wrap">
            <table className="k-table">
              <tbody>
                {result.supplied.map((v) => (
                  <tr key={v.id}>
                    <th scope="row" className="k-code" style={{ fontWeight: 400 }}>
                      {v.id}
                    </th>
                    <td className="k-num">
                      <Value v={v} />
                    </td>
                    <td className="k-small k-muted">{v.provenance.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}
      {result.refusals.length > 0 ? (
        <section className="k-section" aria-labelledby="k-declined">
          <h2 className="k-section-title" id="k-declined">
            Declined, and why
          </h2>
          <ul className="k-list">
            {result.refusals.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
        </section>
      ) : null}
      <Report title="The document cite.py prints" markdown={result.document_markdown} />
    </>
  );
}
