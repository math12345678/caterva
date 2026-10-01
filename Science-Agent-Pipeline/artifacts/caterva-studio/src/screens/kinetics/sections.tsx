/**
 * A figure for each compose analysis that has something to draw, read from
 * the section's own report object (`StructuredSection.data`, the library's
 * dataclasses serialised by the adapter without rounding).
 *
 * Every point drawn is a number the library computed and returned; the page
 * plots it and changes nothing. A log axis is only a way of drawing (fold
 * changes over sixteen decades, samples drawn log-uniformly); a value that
 * a log axis cannot place (zero, negative) is said to be left out, and the
 * table under every figure lists every value as the library returned it.
 * A section whose data is not in the shape below draws no figure: its text
 * is still shown, so nothing is lost by a figure declining.
 */
import { useMemo } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from "recharts";

import type { StructuredSection } from "@/api/types";
import { ChartFrame } from "@/components/charts/ChartFrame";
import { AXIS, GRID, seriesColor, seriesDash, tick } from "@/components/charts/theme";
import { TimeCourseChart } from "@/components/charts/TimeCourseChart";
import { DataTable } from "@/components/table/DataTable";
import { formatNumber } from "@/lib/format";

type Json = Record<string, unknown>;

function obj(v: unknown): Json | null {
  return v && typeof v === "object" && !Array.isArray(v) ? (v as Json) : null;
}
function arr(v: unknown): unknown[] {
  return Array.isArray(v) ? v : [];
}
function numOrNull(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}
function str(v: unknown): string {
  return typeof v === "string" ? v : "";
}
function fmt(v: number | null): string {
  return v === null ? "none" : formatNumber(v);
}

// ------------------------------------------------------------ robustness

interface Sample {
  i: number;
  x: number | null;
  y: number | null;
  held: boolean;
  reason: string;
  values: Record<string, number | null>;
}

export function robustnessSamples(data: Json | null): { varied: string[]; samples: Sample[]; conclusion: string } | null {
  const report = obj(data?.report);
  if (!report) return null;
  const varied = arr(report.varied).map(str).filter(Boolean);
  const raw = arr(report.evaluated).length ? arr(report.evaluated) : arr(report.samples);
  if (!varied.length || !raw.length) return null;
  const samples = raw.map((s, i) => {
    const o = obj(s) ?? {};
    const values: Record<string, number | null> = {};
    const vals = obj(o.values) ?? {};
    for (const k of varied) values[k] = numOrNull(vals[k]);
    return {
      i: i + 1,
      x: values[varied[0]] ?? null,
      y: varied[1] ? (values[varied[1]] ?? null) : i + 1,
      held: o.held === true,
      reason: str(o.reason),
      values,
    };
  });
  return { varied, samples, conclusion: str(report.conclusion) };
}

function RobustnessFigure({ data }: { data: Json | null }) {
  const parsed = useMemo(() => robustnessSamples(data), [data]);
  if (!parsed) return null;
  const { varied, samples, conclusion } = parsed;
  const two = varied.length >= 2;
  const plot = (held: boolean) => samples.filter((s) => s.held === held && s.x !== null && s.x > 0 && s.y !== null && (!two || s.y > 0));
  const held = plot(true);
  const failed = plot(false);
  const omitted = samples.length - held.length - failed.length;
  const heldCount = samples.filter((s) => s.held).length;
  return (
    <ChartFrame
      title={`Did "${conclusion}" hold in each draw?`}
      caption={`${samples.length} draws of the placeholder constants${two ? `, ${varied[0]} against ${varied[1]}` : ` of ${varied[0]}`}, both axes logarithmic; ${heldCount} held, ${samples.length - heldCount} did not.${varied.length > 2 ? ` ${varied.length - 2} more constant(s) were varied and are in the table.` : ""}${omitted ? ` ${omitted} draw(s) a log axis cannot place are in the table only.` : ""}`}
      legend={[
        { label: "held", index: 0 },
        { label: "did not hold", index: 2 },
      ]}
      height={260}
      table={
        <DataTable
          caption="Every draw"
          captionHidden
          rows={samples}
          rowKey={(s) => String(s.i)}
          columns={[
            { key: "i", header: "Draw", numeric: true, cell: (s) => s.i, sortValue: (s) => s.i },
            ...varied.map((k) => ({
              key: k,
              header: k,
              numeric: true,
              cell: (s: Sample) => fmt(s.values[k]),
              sortValue: (s: Sample) => s.values[k],
            })),
            { key: "held", header: "Held", cell: (s) => (s.held ? "yes" : `no${s.reason ? `: ${s.reason}` : ""}`), sortValue: (s) => (s.held ? 1 : 0) },
          ]}
        />
      }
    >
      <ResponsiveContainer width="100%" height="100%">
        <ScatterChart margin={{ top: 8, right: 16, bottom: 22, left: 8 }}>
          <CartesianGrid {...GRID} />
          <XAxis
            dataKey="x"
            type="number"
            scale="log"
            domain={["auto", "auto"]}
            tickFormatter={tick}
            {...AXIS}
            name={varied[0]}
            label={{ value: varied[0], position: "insideBottom", offset: -12 }}
          />
          <YAxis
            dataKey="y"
            type="number"
            scale={two ? "log" : "linear"}
            domain={["auto", "auto"]}
            tickFormatter={tick}
            {...AXIS}
            width={60}
            name={two ? varied[1] : "draw"}
            label={{ value: two ? varied[1] : "draw", angle: -90, position: "insideLeft" }}
          />
          <ZAxis range={[36, 36]} />
          <Tooltip cursor={{ stroke: "var(--rule-strong)" }} isAnimationActive={false} formatter={(v: number) => formatNumber(v)} />
          <Scatter name="held" data={held} fill={seriesColor(0)} isAnimationActive={false} />
          <Scatter name="did not hold" data={failed} fill="none" stroke={seriesColor(2)} strokeWidth={1.5} isAnimationActive={false} />
        </ScatterChart>
      </ResponsiveContainer>
    </ChartFrame>
  );
}

// ------------------------------------------------------------ knockouts

interface Effect {
  key: string;
  kind: string;
  target: string;
  description: string;
  control: number | null;
  perturbed: number | null;
  fold: number | null;
  note: string;
}

export function perturbationEffects(data: Json | null): { readout: string; effects: Effect[] } | null {
  const block = obj(data?.screen) ?? obj(data?.comparison);
  if (!block) return null;
  const list = arr(block.ranked).length ? arr(block.ranked) : arr(block.effects);
  const effects = list.map((e, i) => {
    const o = obj(e) ?? {};
    const p = obj(o.perturbation) ?? {};
    return {
      key: `${i}`,
      kind: str(p.kind),
      target: str(p.target),
      description: str(p.description),
      control: numOrNull(o.control),
      perturbed: numOrNull(o.perturbed),
      fold: numOrNull(o.fold_change),
      note: str(o.note),
    };
  });
  if (!effects.length) return null;
  return { readout: str(block.readout) || str(data?.readout), effects };
}

function PerturbationFigure({ data }: { data: Json | null }) {
  const parsed = useMemo(() => perturbationEffects(data), [data]);
  if (!parsed) return null;
  const { readout, effects } = parsed;
  const plotted = effects.filter((e) => e.fold !== null && e.fold > 0).map((e) => ({ ...e, label: `${e.kind} ${e.target}` }));
  return (
    <ChartFrame
      title={`What each perturbation does to ${readout}`}
      caption={`Fold change of the ${readout} steady state against the unperturbed model, logarithmic axis, ranked as the screen ranked them.${effects.length - plotted.length ? ` ${effects.length - plotted.length} without a positive fold change are in the table only.` : ""}`}
      height={Math.max(140, 36 + plotted.length * 26)}
      table={
        <DataTable
          caption="Every perturbation"
          captionHidden
          rows={effects}
          rowKey={(e) => e.key}
          columns={[
            { key: "p", header: "Perturbation", cell: (e) => `${e.kind} ${e.target}` },
            { key: "c", header: `${readout}, control`, numeric: true, cell: (e) => fmt(e.control), sortValue: (e) => e.control },
            { key: "x", header: `${readout}, perturbed`, numeric: true, cell: (e) => fmt(e.perturbed), sortValue: (e) => e.perturbed },
            { key: "f", header: "Fold change", numeric: true, cell: (e) => fmt(e.fold), sortValue: (e) => e.fold },
            { key: "d", header: "What was done", cell: (e) => e.description },
          ]}
        />
      }
    >
      <ResponsiveContainer width="100%" height="100%">
        <ScatterChart margin={{ top: 8, right: 16, bottom: 22, left: 8 }}>
          <CartesianGrid {...GRID} horizontal={false} />
          <XAxis dataKey="fold" type="number" scale="log" domain={["auto", "auto"]} tickFormatter={tick} {...AXIS} label={{ value: "fold change", position: "insideBottom", offset: -12 }} />
          <YAxis dataKey="label" type="category" {...AXIS} width={170} interval={0} allowDuplicatedCategory={false} />
          <ZAxis range={[44, 44]} />
          <Tooltip isAnimationActive={false} formatter={(v: number) => formatNumber(v)} />
          <Scatter data={plotted} fill={seriesColor(0)} isAnimationActive={false} />
        </ScatterChart>
      </ResponsiveContainer>
    </ChartFrame>
  );
}

// ------------------------------------------------------------ design

interface Gain {
  key: string;
  description: string;
  protocol: string;
  novelty: number | null;
  informative: boolean;
}

export function designGains(data: Json | null): Gain[] | null {
  const report = obj(data?.report);
  if (!report) return null;
  const ranked = arr(report.ranked);
  if (!ranked.length) return null;
  return ranked.map((g, i) => {
    const o = obj(g) ?? {};
    const ob = obj(o.observation) ?? {};
    return {
      key: str(ob.key) || String(i),
      description: str(ob.description),
      protocol: str(ob.protocol),
      novelty: numOrNull(o.novelty),
      informative: o.informative === true,
    };
  });
}

function DesignFigure({ data }: { data: Json | null }) {
  const gains = useMemo(() => designGains(data), [data]);
  if (!gains) return null;
  const rows = gains.filter((g) => g.novelty !== null);
  return (
    <ChartFrame
      title="What each measurement would add"
      caption="The novelty the design module gave each candidate observation, in its own ranking order. Hollow bars are the observations it judged uninformative."
      height={Math.max(140, 36 + rows.length * 28)}
      table={
        <DataTable
          caption="Every candidate observation"
          captionHidden
          rows={gains}
          rowKey={(g) => g.key}
          columns={[
            { key: "k", header: "Observation", cell: (g) => <span className="font-mono">{g.key}</span> },
            { key: "o", header: "What it is", cell: (g) => g.description },
            { key: "n", header: "Novelty", numeric: true, cell: (g) => fmt(g.novelty), sortValue: (g) => g.novelty },
            { key: "i", header: "Informative", cell: (g) => (g.informative ? "yes" : "no") },
            { key: "p", header: "Protocol", cell: (g) => g.protocol },
          ]}
        />
      }
    >
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={rows} layout="vertical" margin={{ top: 8, right: 16, bottom: 22, left: 8 }}>
          <CartesianGrid {...GRID} horizontal={false} />
          <XAxis type="number" dataKey="novelty" tickFormatter={tick} {...AXIS} label={{ value: "novelty", position: "insideBottom", offset: -12 }} />
          <YAxis type="category" dataKey="key" {...AXIS} width={190} interval={0} />
          <Tooltip isAnimationActive={false} formatter={(v: number) => formatNumber(v)} cursor={{ fill: "var(--surface-raised)" }} />
          <Bar dataKey="novelty" isAnimationActive={false} barSize={14}>
            {rows.map((g) => (
              <Cell key={g.key} fill={g.informative ? seriesColor(0) : "transparent"} stroke={seriesColor(0)} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </ChartFrame>
  );
}

// ------------------------------------------------------------ identifiability

function IdentifiabilityFigure({ data }: { data: Json | null }) {
  const report = obj(data?.report);
  const values = arr(report?.singular_values).map(numOrNull);
  const params = arr(report?.parameters).map(str);
  if (!report || !values.length) return null;
  const threshold = numOrNull(report.threshold);
  const rows = values.map((v, i) => ({ i: i + 1, v }));
  const plotted = rows.filter((r) => r.v !== null && r.v > 0);
  return (
    <ChartFrame
      title="How many directions a measurement can pin down"
      caption={`Singular values of the sensitivity matrix, logarithmic axis; ${numOrNull(report.rank) ?? "an unstated number"} of ${params.length} constant direction(s) sit above the threshold${threshold !== null ? ` of ${formatNumber(threshold)}` : ""}.${rows.length - plotted.length ? ` ${rows.length - plotted.length} at zero, which a log axis cannot place, are in the table.` : ""}`}
      height={200}
      table={
        <DataTable
          caption="Singular values"
          captionHidden
          rows={rows}
          rowKey={(r) => String(r.i)}
          columns={[
            { key: "i", header: "Direction", numeric: true, cell: (r) => r.i },
            { key: "v", header: "Singular value", numeric: true, cell: (r) => fmt(r.v) },
          ]}
        />
      }
    >
      <ResponsiveContainer width="100%" height="100%">
        <ScatterChart margin={{ top: 8, right: 16, bottom: 22, left: 8 }}>
          <CartesianGrid {...GRID} />
          <XAxis dataKey="i" type="number" domain={[0, rows.length + 1]} allowDecimals={false} {...AXIS} label={{ value: "direction", position: "insideBottom", offset: -12 }} />
          <YAxis dataKey="v" type="number" scale="log" domain={["auto", "auto"]} tickFormatter={tick} {...AXIS} width={60} />
          <ZAxis range={[44, 44]} />
          <Tooltip isAnimationActive={false} formatter={(v: number) => formatNumber(v)} />
          <Scatter data={plotted} fill={seriesColor(0)} isAnimationActive={false} />
        </ScatterChart>
      </ResponsiveContainer>
    </ChartFrame>
  );
}

// ------------------------------------------------------------ stochastic

export function stochasticRun(data: Json | null): { times: (number | null)[]; counts: Record<string, (number | null)[]>; seed: number | null; events: number | null; ended: string; volume: number | null } | null {
  const run = obj(data?.run);
  if (!run) return null;
  const times = arr(run.times).map(numOrNull);
  const countsRaw = obj(run.counts) ?? {};
  const counts: Record<string, (number | null)[]> = {};
  for (const [k, v] of Object.entries(countsRaw)) counts[k] = arr(v).map(numOrNull);
  if (!times.length || !Object.keys(counts).length) return null;
  return { times, counts, seed: numOrNull(run.seed), events: numOrNull(run.events), ended: str(run.ended), volume: numOrNull(data?.volume_l) };
}

function StochasticFigure({ data }: { data: Json | null }) {
  const run = useMemo(() => stochasticRun(data), [data]);
  if (!run) return null;
  return (
    <TimeCourseChart
      title="One exact stochastic trajectory"
      caption={`Molecule counts, one step per event: ${run.events ?? "an unstated number of"} events in ${run.volume !== null ? `${formatNumber(run.volume)} L` : "the stated volume"}, seed ${run.seed ?? "not recorded"}; ${run.ended}.`}
      times={run.times}
      series={run.counts}
      timeUnit="s"
      unit="molecules"
      step
      height={260}
    />
  );
}

// ------------------------------------------------------------ findings and theorems

function Findings({ data }: { data: Json | null }) {
  const report = obj(data?.report);
  const findings = arr(report?.findings).map((f) => obj(f) ?? {});
  if (!findings.length) return null;
  return (
    <ul className="k-findings" aria-label="Findings">
      {findings.map((f, i) => (
        <li key={i} data-severity={str(f.severity)}>
          <span className="chip chip-mono" data-tone={f.agreed === true || str(f.severity) === "agree" ? "signal" : "caution"}>
            {str(f.check) || str(f.kind) || "finding"} {str(f.severity)}
          </span>
          <span className="k-finding-subject font-mono">{str(f.subject)}</span>
          <span className="k-finding-detail">{str(f.detail) || str(f.message)}</span>
        </li>
      ))}
    </ul>
  );
}

function Theorems({ data }: { data: Json | null }) {
  if (!data) return null;
  const theorems = Object.values(data)
    .map(obj)
    .filter((t): t is Json => t !== null && typeof t.theorem === "string");
  if (!theorems.length) return null;
  return (
    <div className="k-theorems">
      {theorems.map((t) => (
        <div key={str(t.theorem)} className="k-theorem">
          <p className="k-theorem-name">
            {str(t.theorem)}: <strong>{t.applies === true ? "applies" : "does not apply"}</strong>
          </p>
          <ul>
            {arr(t.hypotheses)
              .map((h) => obj(h) ?? {})
              .map((h) => (
                <li key={str(h.name)} data-holds={h.holds === true ? "true" : "false"}>
                  <span aria-hidden="true">{h.holds === true ? "✓" : "✗"}</span>
                  <span className="sr-only">{h.holds === true ? "holds" : "does not hold"}</span> {str(h.name)}
                  <span className="muted">: {str(h.detail)}</span>
                </li>
              ))}
          </ul>
        </div>
      ))}
    </div>
  );
}

/** The figure for one section, or nothing when it has nothing to draw. */
export function SectionFigure({ section }: { section: StructuredSection }) {
  const data = section.data;
  switch (section.key) {
    case "robustness":
      return <RobustnessFigure data={data} />;
    case "perturbations":
      return <PerturbationFigure data={data} />;
    case "design":
      return <DesignFigure data={data} />;
    case "identifiability":
      return <IdentifiabilityFigure data={data} />;
    case "stochastic":
      return <StochasticFigure data={data} />;
    case "validate":
    case "scale":
      return <Findings data={data} />;
    case "crnt":
      return <Theorems data={data} />;
    default:
      return null;
  }
}

// ------------------------------------------------------------ sweeps

export function sweepSeries(sweep: Record<string, unknown>): { parameter: string; rows: Json[]; names: string[] } | null {
  const parameter = str(sweep.parameter);
  const points = arr(sweep.points).map((p) => obj(p) ?? {});
  if (!parameter || !points.length) return null;
  const names = new Set<string>();
  const rows = points.map((p) => {
    const row: Json = { x: numOrNull(p.value), behaviour: str(p.behaviour) };
    const report = obj(p.report);
    const stable = arr(report?.stable_points).map((s) => obj(s) ?? {});
    stable.forEach((s, i) => {
      const state = obj(s.state) ?? {};
      for (const [sp, v] of Object.entries(state)) {
        const name = i === 0 ? sp : `${sp}, stable state ${i + 1}`;
        names.add(name);
        row[name] = numOrNull(v);
      }
    });
    return row;
  });
  return { parameter, rows, names: [...names] };
}

export function SweepFigure({ sweep, unit }: { sweep: Record<string, unknown>; unit: string }) {
  const parsed = useMemo(() => sweepSeries(sweep), [sweep]);
  if (!parsed) return null;
  const { parameter, rows, names } = parsed;
  const behaviours = [...new Set(rows.map((r) => str(r.behaviour)).filter(Boolean))];
  return (
    <ChartFrame
      title={`Stable steady states as ${parameter} is swept`}
      caption={`${rows.length} values of ${parameter}, logarithmic axis; at each, the stable steady states the search found. ${behaviours.length === 1 ? `Behaviour at every value: ${behaviours[0]}.` : `Behaviours seen: ${behaviours.join("; ")}.`}`}
      legend={names.map((n, i) => ({ label: n, index: i }))}
      height={260}
      table={
        <DataTable
          caption={`Sweep of ${parameter}`}
          captionHidden
          rows={rows}
          rowKey={(_, i) => String(i)}
          columns={[
            { key: "x", header: parameter, numeric: true, cell: (r) => fmt(numOrNull(r.x)) },
            ...names.map((n) => ({ key: n, header: `${n} (${unit})`, numeric: true, cell: (r: Json) => fmt(numOrNull(r[n])) })),
            { key: "b", header: "Behaviour", cell: (r: Json) => str(r.behaviour) },
          ]}
        />
      }
    >
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={rows.filter((r) => typeof r.x === "number" && (r.x as number) > 0)} margin={{ top: 8, right: 16, bottom: 22, left: 8 }}>
          <CartesianGrid {...GRID} vertical={false} />
          <XAxis dataKey="x" type="number" scale="log" domain={["auto", "auto"]} tickFormatter={tick} {...AXIS} label={{ value: parameter, position: "insideBottom", offset: -12 }} />
          <YAxis tickFormatter={tick} {...AXIS} width={56} label={{ value: unit, angle: -90, position: "insideLeft" }} />
          <Tooltip isAnimationActive={false} formatter={(v: number) => formatNumber(v)} labelFormatter={(v: number) => `${parameter} = ${formatNumber(v)}`} />
          {names.map((n, i) => (
            <Line key={n} dataKey={n} name={n} stroke={seriesColor(i)} strokeDasharray={seriesDash(i)} strokeWidth={1.75} dot={{ r: 2 }} connectNulls={false} isAnimationActive={false} />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </ChartFrame>
  );
}
