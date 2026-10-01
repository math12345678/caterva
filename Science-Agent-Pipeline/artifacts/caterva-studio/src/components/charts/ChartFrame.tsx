/**
 * The frame every chart sits in: a title, a caption that says what is
 * plotted and from where, the plot, a legend, and the same numbers as a
 * table one activation away.
 *
 * The table is the accessible form of the chart (a screen reader cannot
 * read an SVG polyline) and also the honest one: the chart rounds by
 * drawing, the table shows each value as format.ts writes it. The plot
 * itself carries role="img" and an accessible name built from the title
 * and the caption.
 */
import { type ReactNode, useId } from "react";

import { Disclosure } from "@/components/forms/Disclosure";

import { SeriesSwatch } from "./theme";

export interface LegendEntry {
  label: string;
  index: number;
  note?: string;
}

export function ChartFrame({
  title,
  caption,
  legend,
  table,
  children,
  height = 280,
}: {
  title: string;
  /** What is plotted, in which units, and where it came from. */
  caption?: ReactNode;
  legend?: readonly LegendEntry[];
  /** The same data as a table. */
  table?: ReactNode;
  children: ReactNode;
  height?: number;
}) {
  const id = useId();
  return (
    <figure className="chart" aria-labelledby={`${id}-title`}>
      <div className="chart-head">
        <h3 className="chart-title" id={`${id}-title`}>
          {title}
        </h3>
        {legend && legend.length > 1 ? (
          <ul className="chart-legend" aria-label="Series">
            {legend.map((l) => (
              <li key={l.label}>
                <SeriesSwatch index={l.index} />
                <span className="font-mono">{l.label}</span>
                {l.note ? <span className="muted">{l.note}</span> : null}
              </li>
            ))}
          </ul>
        ) : null}
      </div>
      <div
        className="chart-body"
        role="img"
        aria-labelledby={`${id}-title`}
        aria-describedby={caption ? `${id}-caption` : undefined}
        style={{ height }}
      >
        {children}
      </div>
      {caption ? (
        <figcaption className="chart-caption" id={`${id}-caption`}>
          {caption}
        </figcaption>
      ) : null}
      {table ? <Disclosure title="The numbers as a table">{table}</Disclosure> : null}
    </figure>
  );
}
