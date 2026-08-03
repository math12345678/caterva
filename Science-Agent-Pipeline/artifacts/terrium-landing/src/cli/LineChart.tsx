import { useEffect, useState } from "react";
import type { Point } from "@/lib/simulate";

interface Series {
  key: string;
  color: string;
}

interface LineChartProps {
  data: Point[];
  series: Series[];
  height?: number;
}

export default function LineChart({
  data,
  series,
  height = 200,
}: LineChartProps) {
  if (data.length === 0) return null;

  const width = 640;
  const pad = { top: 16, right: 12, bottom: 20, left: 36 };
  const tMax = data[data.length - 1].t || 1;

  let yMax = 0;
  for (const point of data) {
    for (const s of series) {
      yMax = Math.max(yMax, point[s.key] ?? 0);
    }
  }
  yMax = yMax === 0 ? 1 : yMax * 1.1;

  const xf = (t: number) =>
    pad.left + (t / tMax) * (width - pad.left - pad.right);
  const yf = (v: number) =>
    height - pad.bottom - (v / yMax) * (height - pad.top - pad.bottom);

  const linePath = (key: string) =>
    data
      .map(
        (p, i) =>
          `${i === 0 ? "M" : "L"}${xf(p.t).toFixed(1)},${yf(p[key] ?? 0).toFixed(1)}`,
      )
      .join("");

  const areaPath = (key: string) => {
    const pts = data
      .map((p) => `${xf(p.t).toFixed(1)},${yf(p[key] ?? 0).toFixed(1)}`)
      .join("L");
    const last = data[data.length - 1];
    const first = data[0];
    return `M${xf(first.t).toFixed(1)},${yf(0)}L${pts}L${xf(last.t).toFixed(1)},${yf(0)}Z`;
  };

  const yTicks = [0, 0.25, 0.5, 0.75, 1].map((f) => yMax * f);
  const xTicks = (() => {
    const ideal = Math.min(6, Math.floor(width / 80));
    const step = Math.max(1, Math.round(tMax / ideal));
    const ticks: number[] = [];
    for (let t = 0; t <= tMax; t += step) ticks.push(t);
    if (ticks[ticks.length - 1] !== tMax) ticks.push(tMax);
    return ticks;
  })();

  const [animProgress, setAnimProgress] = useState(0);

  useEffect(() => {
    setAnimProgress(0);
    const timer = setTimeout(() => setAnimProgress(1), 50);
    return () => clearTimeout(timer);
  }, [data, series]);

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      className="w-full h-auto"
      role="img"
      aria-label="simulation trajectory"
    >
      <defs>
        {series.map((s) => (
          <linearGradient
            key={s.key}
            id={`grad-${s.key}`}
            x1="0"
            y1="0"
            x2="0"
            y2="1"
          >
            <stop offset="0%" stopColor={s.color} stopOpacity="0.25" />
            <stop offset="100%" stopColor={s.color} stopOpacity="0.01" />
          </linearGradient>
        ))}
      </defs>

      <g style={{ opacity: animProgress, transition: "opacity 0.4s ease" }}>
        {/* horizontal grid */}
        {yTicks.map((v) => (
          <line
            key={`yh-${v}`}
            x1={pad.left}
            x2={width - pad.right}
            y1={yf(v)}
            y2={yf(v)}
            stroke="rgba(255,255,255,0.04)"
            strokeWidth={1}
          />
        ))}

        {/* vertical grid */}
        {xTicks.map((t) => (
          <line
            key={`xv-${t}`}
            x1={xf(t)}
            x2={xf(t)}
            y1={pad.top}
            y2={height - pad.bottom}
            stroke="rgba(255,255,255,0.04)"
            strokeWidth={1}
          />
        ))}

        {/* axes */}
        <line
          x1={pad.left}
          x2={pad.left}
          y1={pad.top}
          y2={height - pad.bottom}
          stroke="rgba(255,255,255,0.08)"
          strokeWidth={1}
        />
        <line
          x1={pad.left}
          x2={width - pad.right}
          y1={height - pad.bottom}
          y2={height - pad.bottom}
          stroke="rgba(255,255,255,0.08)"
          strokeWidth={1}
        />

        {/* y-axis labels */}
        {yTicks.map((v) => (
          <text
            key={`yl-${v}`}
            x={pad.left - 6}
            y={yf(v) + 3}
            textAnchor="end"
            fill="rgba(255,255,255,0.2)"
            fontSize="8"
            fontFamily="DM Mono, monospace"
          >
            {v >= 1000
              ? `${(v / 1000).toFixed(1)}k`
              : v.toFixed(v < 1 ? 2 : v < 10 ? 1 : 0)}
          </text>
        ))}

        {/* x-axis labels */}
        {xTicks.map((t) => (
          <text
            key={`xl-${t}`}
            x={xf(t)}
            y={height - pad.bottom + 12}
            textAnchor="middle"
            fill="rgba(255,255,255,0.2)"
            fontSize="8"
            fontFamily="DM Mono, monospace"
          >
            {t.toFixed(t === Math.round(t) ? 0 : 1)}
          </text>
        ))}

        {/* area fills */}
        {series.map((s) => (
          <path
            key={`area-${s.key}`}
            d={areaPath(s.key)}
            fill={`url(#grad-${s.key})`}
          />
        ))}

        {/* lines */}
        {series.map((s) => (
          <path
            key={s.key}
            d={linePath(s.key)}
            fill="none"
            stroke={s.color}
            strokeWidth="1.5"
            strokeLinejoin="round"
          />
        ))}

        {/* end dots */}
        {series.map((s) => {
          const last = data[data.length - 1];
          return (
            <circle
              key={`dot-${s.key}`}
              cx={xf(last.t)}
              cy={yf(last[s.key] ?? 0)}
              r="2.5"
              fill={s.color}
              opacity="0.8"
            />
          );
        })}
      </g>
    </svg>
  );
}
