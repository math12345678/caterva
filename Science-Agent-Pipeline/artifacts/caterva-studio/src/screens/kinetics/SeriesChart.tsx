/**
 * A time course drawn from the arrays the server sent, point for point.
 *
 * Nothing is smoothed, resampled or interpolated here: each line joins the
 * rows the engine produced (as steps for a stochastic run, whose counts
 * jump at events). Colours are theme tokens, and a legend below names each
 * line, so the chart reads in both themes and without colour.
 */
import { useMemo } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { formatNumber } from "@/lib/format";

const COLOURS = ["var(--signal-deep)", "var(--fg)", "var(--caution)", "var(--muted)", "var(--signal)", "var(--danger)"];
const DASHES = ["", "6 3", "2 3", "8 3 2 3", "", "4 4"];

export function SeriesChart({
  x,
  series,
  xLabel,
  yLabel,
  step = false,
  label,
}: {
  x: (number | null)[];
  series: Record<string, (number | null)[]>;
  xLabel: string;
  yLabel: string;
  step?: boolean;
  label: string;
}) {
  const names = Object.keys(series);
  const rows = useMemo(
    () =>
      x.map((t, i) => {
        const row: Record<string, number | null> = { x: t };
        for (const name of names) row[name] = series[name][i] ?? null;
        return row;
      }),
    [x, series, names],
  );
  return (
    <figure className="k-section" aria-label={label} style={{ margin: 0 }}>
      <div className="k-chart">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={rows} margin={{ top: 8, right: 16, bottom: 24, left: 8 }}>
            <CartesianGrid stroke="var(--rule)" vertical={false} />
            <XAxis
              dataKey="x"
              type="number"
              domain={["dataMin", "dataMax"]}
              tickFormatter={(v: number) => formatNumber(v, 3)}
              stroke="var(--muted)"
              label={{ value: xLabel, position: "insideBottom", offset: -14, fill: "var(--muted)" }}
            />
            <YAxis
              tickFormatter={(v: number) => formatNumber(v, 3)}
              stroke="var(--muted)"
              width={64}
              label={{ value: yLabel, angle: -90, position: "insideLeft", fill: "var(--muted)" }}
            />
            <Tooltip
              formatter={(v: number) => formatNumber(v)}
              labelFormatter={(v: number) => `${xLabel} ${formatNumber(v)}`}
              contentStyle={{ background: "var(--surface-raised)", border: "1px solid var(--rule)", fontFamily: "var(--font-mono)", fontSize: 12 }}
            />
            {names.map((name, i) => (
              <Line
                key={name}
                dataKey={name}
                name={name}
                type={step ? "stepAfter" : "linear"}
                stroke={COLOURS[i % COLOURS.length]}
                strokeDasharray={DASHES[i % DASHES.length]}
                strokeWidth={1.6}
                dot={false}
                isAnimationActive={false}
                connectNulls={false}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
      <figcaption className="k-legend-row">
        {names.map((name, i) => (
          <span key={name} className="k-code">
            <svg width="18" height="6" aria-hidden="true" style={{ marginRight: 6, verticalAlign: "middle" }}>
              <line
                x1="0"
                y1="3"
                x2="18"
                y2="3"
                stroke={COLOURS[i % COLOURS.length]}
                strokeWidth="2"
                strokeDasharray={DASHES[i % DASHES.length]}
              />
            </svg>
            {name}
          </span>
        ))}
      </figcaption>
    </figure>
  );
}
