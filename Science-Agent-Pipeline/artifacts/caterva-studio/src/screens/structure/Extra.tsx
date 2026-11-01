/**
 * Sections of an analysis this page has no drawing for yet: a newer engine
 * adds them (principal motions and solvent exposure arrive on other
 * branches) and the adapter passes them through `extra` by field name
 * rather than dropping them.
 *
 * They are drawn by shape, not by name: text as text, a SourcedValue with
 * its mark (Value), a list of records as a table. A bare number, one that
 * arrived without a provenance, is never drawn as if it had one: it stays
 * in the section's JSON, shown as the engine wrote it and labelled so,
 * and the report the terminal prints holds the section too.
 */
import type { SourcedValue } from "@/api/types";
import { Disclosure } from "@/components/forms/Disclosure";
import { Value } from "@/components/provenance/Value";
import { Section } from "@/components/screen/Screen";
import { DataTable } from "@/components/table/DataTable";

export function isSourced(x: unknown): x is SourcedValue {
  if (!x || typeof x !== "object") return false;
  const o = x as Record<string, unknown>;
  const p = o.provenance as Record<string, unknown> | undefined;
  return "value" in o && "unit" in o && typeof p === "object" && p !== null && typeof p.kind === "string";
}

function title(key: string): string {
  const words = key.replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

function Cell({ x }: { x: unknown }) {
  if (isSourced(x)) return <Value v={x} />;
  if (typeof x === "string") return <>{x}</>;
  if (typeof x === "boolean") return <>{x ? "yes" : "no"}</>;
  if (x === null || x === undefined) return <span className="muted">none</span>;
  return <span className="muted">in the JSON below</span>;
}

function Body({ value }: { value: unknown }) {
  if (isSourced(value)) return <Value v={value} />;
  if (typeof value === "string") return <p className="st-prose">{value}</p>;
  if (Array.isArray(value) && value.length && value.every((r) => r && typeof r === "object" && !Array.isArray(r))) {
    const rows = value as Record<string, unknown>[];
    const keys = [...new Set(rows.flatMap((r) => Object.keys(r)))];
    return (
      <DataTable
        caption="rows"
        captionHidden
        rows={rows}
        rowKey={(_, i) => String(i)}
        columns={keys.map((k) => ({ key: k, header: k.replace(/_/g, " "), cell: (r: Record<string, unknown>) => <Cell x={r[k]} /> }))}
      />
    );
  }
  if (value && typeof value === "object" && !Array.isArray(value)) {
    const entries = Object.entries(value as Record<string, unknown>).filter(([, v]) => isSourced(v) || typeof v === "string" || typeof v === "boolean");
    if (!entries.length) return null;
    return (
      <dl className="dl">
        {entries.map(([k, v]) => (
          <div key={k} style={{ display: "contents" }}>
            <dt>{k.replace(/_/g, " ")}</dt>
            <dd>
              <Cell x={v} />
            </dd>
          </div>
        ))}
      </dl>
    );
  }
  return null;
}

export function ExtraSections({ extra }: { extra: Record<string, unknown> }) {
  const keys = Object.keys(extra);
  if (!keys.length) return null;
  return (
    <>
      {keys.map((key) => {
        const value = extra[key];
        const refused = value && typeof value === "object" && "unserialised" in (value as object);
        return (
          <Section key={key} title={title(key)} aside="a section from a newer engine, drawn by its shape">
            {refused ? (
              <p className="st-prose">
                The server could not send this section: {String((value as { unserialised: unknown }).unserialised)}. The
                report below holds it as the terminal prints it.
              </p>
            ) : (
              <>
                <Body value={value} />
                <Disclosure title="As the engine sent it (numbers here carry no provenance mark)">
                  <pre className="report-text">{JSON.stringify(value, null, 2)}</pre>
                </Disclosure>
              </>
            )}
          </Section>
        );
      })}
    </>
  );
}
