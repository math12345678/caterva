/**
 * A number with its provenance: the only way a SourcedValue is drawn.
 *
 * The number is set in DM Mono with tabular figures, the unit beside it,
 * the provenance mark after. The whole is one focusable button; activating
 * it opens the provenance: the citation (a link when the contract carries a
 * working one), the conditions, the row's own words, or the reason a
 * placeholder is a placeholder. A citation is therefore one click from any
 * cited number, and a reason one keypress from any placeholder.
 */
import * as Popover from "@radix-ui/react-popover";

import type { SourcedValue } from "@/api/types";
import { formatValue, fullValue } from "@/lib/format";

import { ProvenanceMark, provenanceLabel } from "./ProvenanceMark";

export function Value({ v, showUnit = true }: { v: SourcedValue; showUnit?: boolean }) {
  const p = v.provenance;
  return (
    <Popover.Root>
      <Popover.Trigger
        className="value-trigger inline-flex items-baseline gap-1 font-mono tabular-nums"
        aria-label={`${v.label ?? v.id ?? "value"} ${formatValue(v)} ${v.unit}, ${provenanceLabel(p)}`}
      >
        <span>{formatValue(v)}</span>
        {showUnit && v.unit ? <span className="value-unit">{v.unit}</span> : null}
        <ProvenanceMark provenance={p} />
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content className="provenance-popover" sideOffset={6} collisionPadding={12}>
          <p className="provenance-kind">{provenanceLabel(p)}</p>
          <p className="font-mono tabular-nums">
            {fullValue(v)} {v.unit}
          </p>
          {p.citation ? (
            <p>
              {p.citation.url ? (
                <a href={p.citation.url} target="_blank" rel="noreferrer noopener">
                  {p.citation.text}
                </a>
              ) : (
                p.citation.text
              )}
            </p>
          ) : null}
          {p.organism ? <p>{p.cross_species ? `measured in another organism: ${p.organism}` : p.organism}</p> : null}
          {p.conditions ? (
            <p className="font-mono">
              {p.conditions.ph !== null ? `pH ${p.conditions.ph}` : "pH not stated"}
              {", "}
              {p.conditions.temperature_c !== null ? `${p.conditions.temperature_c} °C` : "temperature not stated"}
            </p>
          ) : null}
          {p.commentary ? <p className="provenance-commentary">{p.commentary}</p> : null}
          {p.scope?.map((line) => <p key={line}>{line}</p>)}
          {p.spread ? <p>{p.spread.sentence}</p> : null}
          {p.method ? <p>{p.method}</p> : null}
          {p.fit ? <p>{p.fit.method}</p> : null}
          {p.reason ? <p>{p.reason}</p> : null}
          {p.note ? <p>{p.note}</p> : null}
          {v.interval ? <p>{v.interval.meaning}</p> : null}
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}
