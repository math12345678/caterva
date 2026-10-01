/**
 * A `scripts/cite.py` result: for each constant asked for, the row the
 * resolver chose and every other row it read, each with the paper that
 * measured it; the values the person supplied (marked as theirs or as the
 * script's defaults); what was declined and why; and the document cite.py
 * prints.
 *
 * "Use in Compose" fills Compose's form with the same enzyme, organism and
 * substrate. Compose then looks the constants up itself, through the same
 * resolver, when its button is pressed: a number is never carried from one
 * screen into another's model by the page.
 */
import { ArrowRight } from "lucide-react";
import { Link } from "wouter";

import type { ConstantRow, ConstantsResult as Result, SourcedValue } from "@/api/types";
import { Disclosure } from "@/components/forms/Disclosure";
import { Citation } from "@/components/provenance/Citation";
import { Value } from "@/components/provenance/Value";
import { MarkdownReport } from "@/components/report/Report";
import { Section } from "@/components/screen/Screen";
import { DataTable } from "@/components/table/DataTable";

const QUANTITY_LABEL: Record<string, string> = { km: "Km", kcat: "kcat", ki: "Ki" };

interface Row {
  key: string;
  v: SourcedValue;
  role: "chosen" | "other";
}

function conditionsText(v: SourcedValue): string {
  const c = v.provenance.conditions;
  if (!c) return "";
  const parts: string[] = [];
  if (c.ph !== null) parts.push(`pH ${c.ph}`);
  if (c.temperature_c !== null) parts.push(`${c.temperature_c} °C`);
  if (c.buffer) parts.push(c.buffer);
  return parts.join(", ");
}

/** The address that fills Compose's form with this lookup's enzyme, organism and substrate. */
export function composeHref(request: Record<string, unknown>, quantity: string): string {
  const params = new URLSearchParams();
  params.set("description", quantity === "ki" ? "Michaelis-Menten with a competitive inhibitor" : "Michaelis-Menten");
  const subject = typeof request.ec === "string" ? request.ec : typeof request.enzyme === "string" ? request.enzyme : "";
  if (subject) params.set("subject", subject);
  if (typeof request.organism === "string") params.set("organism", request.organism);
  if (typeof request.substrate === "string") params.set("substrate", request.substrate);
  return `/compose?${params.toString()}`;
}

function Constant({ row, request }: { row: ConstantRow; request: Record<string, unknown> }) {
  const rows: Row[] = [
    ...(row.value ? [{ key: row.value.id ?? "chosen", v: row.value, role: "chosen" as const }] : []),
    ...row.alternatives.map((a, i) => ({ key: a.id ?? `alt-${i}`, v: a, role: "other" as const })),
  ];
  const label = QUANTITY_LABEL[row.quantity] ?? row.quantity;
  return (
    <Section
      title={label}
      id={`k-constant-${row.name}`}
      aside={
        row.found ? (
          <Link href={composeHref(request, row.quantity)} className="k-inline-link">
            Use in Compose
            <ArrowRight size={12} aria-hidden="true" />
          </Link>
        ) : undefined
      }
    >
      {row.value ? (
        <p className="k-constant-headline">
          <span className="k-constant-value">
            <Value v={row.value} />
          </span>
          <span className="muted">
            the resolver&apos;s pick ({row.source}); {rows.length} row(s) read in all
          </span>
        </p>
      ) : (
        <p className="k-constant-headline">
          <span className="text-caution">Not found</span>{" "}
          <span className="muted">
            ({row.source}){row.organisms_available.length ? `. Measured in: ${row.organisms_available.join(", ")}` : ""}
          </span>
        </p>
      )}
      {rows.length ? (
        <DataTable
          caption={`Every ${label} row the resolver read`}
          rows={rows}
          rowKey={(r) => r.key}
          columns={[
            { key: "v", header: "Value", cell: (r) => <Value v={r.v} />, sortValue: (r) => r.v.value, align: "end" },
            {
              key: "ref",
              header: "Reference",
              cell: (r) => (r.v.provenance.citation ? <Citation citation={r.v.provenance.citation} /> : <span className="muted">none recorded</span>),
              sortValue: (r) => r.v.provenance.citation?.text ?? null,
            },
            { key: "org", header: "Organism", cell: (r) => <em>{r.v.provenance.organism ?? ""}</em>, sortValue: (r) => r.v.provenance.organism ?? null },
            { key: "cond", header: "Conditions", cell: (r) => <span className="font-mono">{conditionsText(r.v)}</span> },
            { key: "says", header: "The row says", cell: (r) => <span className="k-cell-prose">{r.v.provenance.commentary ?? ""}</span> },
            { key: "role", header: "", cell: (r) => (r.role === "chosen" ? <span className="chip" data-tone="signal">chosen</span> : null) },
          ]}
        />
      ) : null}
      {row.isoforms_available.length || row.modes_available.length || row.variants_available.length ? (
        <p className="k-invariants muted">
          {row.isoforms_available.length ? `Isoforms with rows: ${row.isoforms_available.join(", ")}. ` : ""}
          {row.modes_available.length ? `Inhibition modes stated: ${row.modes_available.join(", ")}. ` : ""}
          {row.variants_available.length ? `Variants: ${row.variants_available.join(", ")}.` : ""}
        </p>
      ) : null}
    </Section>
  );
}

export function ConstantsResultView({ result, request }: { result: Result; request: Record<string, unknown> }) {
  return (
    <>
      <section className="k-verdict" aria-label="Summary">
        <p className="k-eyebrow">From the literature</p>
        <h2 className="k-verdict-word" data-tone={result.sourced.length ? undefined : "caution"}>
          {result.sourced.length ? result.sourced.map((n) => QUANTITY_LABEL[n] ?? n).join(", ") : "nothing found"}
        </h2>
        <p className="k-verdict-licence">
          {result.defensible
            ? "Every number in the lab report is either cited or declared as yours (cite.py's own check)."
            : "Not every number in the lab report is cited or declared as yours (cite.py's own check); the document says which."}
        </p>
        {result.organism_note ? <p className="k-verdict-behaviour muted">{result.organism_note}</p> : null}
        {result.refusals.length ? (
          <div className="k-part-refusal" role="note">
            <span className="state-kicker">Declined</span>
            {result.refusals.map((r) => (
              <p key={r} className="k-part-refusal-reason">
                {r}
              </p>
            ))}
          </div>
        ) : null}
      </section>
      {result.constants.map((row) => (
        <Constant key={row.name} row={row} request={request} />
      ))}
      {result.supplied.length ? (
        <Section title="Yours, not the literature's" id="k-supplied">
          <div className="table-wrap">
            <table className="table">
              <tbody>
                {result.supplied.map((v) => (
                  <tr key={v.id}>
                    <th scope="row" className="font-mono k-ledger-name">
                      {v.id}
                    </th>
                    <td data-align="end">
                      <Value v={v} />
                    </td>
                    <td className="muted">{v.provenance.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Section>
      ) : null}
      <Disclosure title="The document cite.py prints">
        <MarkdownReport source={result.document_markdown} />
      </Disclosure>
    </>
  );
}
