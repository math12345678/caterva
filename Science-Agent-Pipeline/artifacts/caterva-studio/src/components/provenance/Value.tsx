/**
 * A number with its provenance: the only way a SourcedValue is drawn
 * (docs/studio/CONTRACT.md 9 and 17.3).
 *
 * The number is set in DM Mono with tabular figures, the unit beside it,
 * the provenance mark after. The whole is one focusable button; activating
 * it opens the provenance detail: the citation (a link when the contract
 * carries a working one), the conditions, the row's own words, the spread,
 * why this row was chosen, or the reason a placeholder is a placeholder. A
 * citation is therefore one click from any cited number, and a reason one
 * keypress from any placeholder.
 *
 * There is deliberately no prop that hides the mark: a number on this page
 * without its kind is the defect the studio exists to prevent. `inline`
 * draws the detail in place instead of in a popover, for a detail pane.
 */
import * as Popover from "@radix-ui/react-popover";

import type { SourcedValue } from "@/api/types";
import { cn } from "@/lib/cn";
import { formatValue } from "@/lib/format";

import { ProvenanceDetail } from "./ProvenanceDetail";
import { ProvenanceMark, provenanceLabel } from "./ProvenanceMark";

export function valueName(v: SourcedValue): string {
  return v.label ?? v.id ?? "value";
}

/** The sentence a screen reader hears for a value, before it is opened. */
export function valueAccessibleName(v: SourcedValue): string {
  const unit = v.unit ? ` ${v.unit}` : "";
  return `${valueName(v)}, ${formatValue(v)}${unit}, ${provenanceLabel(v.provenance)}`;
}

function Face({ v, showUnit }: { v: SourcedValue; showUnit: boolean }) {
  return (
    <>
      <span className="value-number">{formatValue(v)}</span>
      {showUnit && v.unit ? <span className="value-unit">{v.unit}</span> : null}
      <ProvenanceMark provenance={v.provenance} decorative />
    </>
  );
}

export function Value({
  v,
  showUnit = true,
  className,
}: {
  v: SourcedValue;
  showUnit?: boolean;
  className?: string;
}) {
  return (
    <Popover.Root>
      <Popover.Trigger
        className={cn("value value-trigger", className)}
        data-kind={v.provenance.kind}
        aria-label={valueAccessibleName(v)}
      >
        <Face v={v} showUnit={showUnit} />
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          className="overlay popover"
          sideOffset={6}
          collisionPadding={12}
          align="start"
          aria-label={`Where ${valueName(v)} came from`}
        >
          <ProvenanceDetail v={v} />
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}

/** The value and its detail drawn in place, for a pane that has room. */
export function ValueInline({ v }: { v: SourcedValue }) {
  return (
    <div className="value-inline">
      <ProvenanceDetail v={v} />
    </div>
  );
}

/** A value with its name, for a definition list or a parameter table cell. */
export function NamedValue({ v }: { v: SourcedValue }) {
  return (
    <span className="named-value">
      <span className="named-value-name font-mono">{valueName(v)}</span>
      <Value v={v} />
    </span>
  );
}
