/**
 * /analyze: catalytic geometry across a finished run's replicas (kind
 * `analyze`, `caterva analyze DIR`), called a result only when the
 * replicas agree.
 *
 * Every verdict is the one the command's report prints: a distance or an
 * angle is "held" or "moved" only once its replicas are consistent, and
 * every later section says "not yet a result" while the distances do not
 * show the runs converged. Beside each section are the thresholds those
 * verdicts were judged against, as the library holds them; the page
 * judges nothing itself.
 *
 * Replicas are compared side by side: a distance or an angle as each
 * replica's mean and error on one axis with the crystal value, the
 * flexibility as RMSF along the chain per replica, the occupancies and
 * populations as one bar per replica. Sections a newer engine adds arrive
 * under `extra` and are drawn by their shape.
 */
import { useState } from "react";
import { Link } from "wouter";

import type { AnalyzeRequest, AnalyzeResult, DistanceRow, SourcedValue } from "@/api/types";
import { useRun } from "@/api/useRun";
import { useRunAddress } from "@/lib/runAddress";
import { Disclosure } from "@/components/forms/Disclosure";
import { Field, fieldError } from "@/components/forms/Field";
import { Segmented } from "@/components/forms/Segmented";
import { Value } from "@/components/provenance/Value";
import { MarkdownReport, TextReport } from "@/components/report/Report";
import { Screen, Section } from "@/components/screen/Screen";
import { EmptyState } from "@/components/states/States";
import { DataTable } from "@/components/table/DataTable";
import { seriesColor } from "@/components/charts/theme";
import { useCapabilities } from "@/lib/queries";

import { ExtraSections } from "./structure/Extra";
import { PathField, RunScreen, text, useParam, useRefill, Verdict, WrittenPath } from "./structure/kit";
import { type ForestRow, ReplicaForest } from "./structure/ReplicaForest";
import { RmsfChart } from "./structure/RmsfChart";
import type { AngleView, FaceView, FlexibilityView, HbondView, ReplicaView, RotamerView, SiteView, WaterView } from "./structure/views";
import "./structure/structure.css";

type Mode = NonNullable<AnalyzeRequest["mode"]>;

const MODES: { mode: Mode; label: string; what: string }[] = [
  { mode: "native", label: "Native", what: "Caterva reads every replica's md.xtc itself; no GROMACS needed." },
  { mode: "gromacs", label: "GROMACS", what: "gmx measures, through the analyze.sh the command writes. No hydrogen bonds or water on this route." },
  { mode: "no_run", label: "From .xvg", what: "Reads the .xvg files a previous analyze.sh run left." },
  { mode: "script_only", label: "Script only", what: "Plans and writes analyze.sh and chi1.ndx; measures nothing." },
];

export default function AnalyzeScreen() {
  const reopened = useParam("run");
  const run = useRun("analyze", reopened);
  useRunAddress("/analyze", run.run, reopened);
  const caps = useCapabilities();
  const [directory, setDirectory] = useState(useParam("directory") ?? "");
  const [mode, setMode] = useState<Mode>("native");
  useRefill(reopened, run.run, (r) => {
    setDirectory(text(r.directory));
    if (MODES.some((m) => m.mode === r.mode)) setMode(r.mode as Mode);
  });
  const gromacs = caps.data?.gromacs;
  const what = MODES.find((m) => m.mode === mode)!;

  const request = (): AnalyzeRequest => {
    const r: AnalyzeRequest = { directory: directory.trim() };
    if (mode !== "native") r.mode = mode;
    return r;
  };

  return (
    <Screen title="Analyze" purpose="Catalytic geometry and active-site flexibility across replicas, called a result only when they agree.">
      <RunScreen
        kind="analyze"
        id="analyze"
        formLabel="Analyze a finished run"
        action="Analyze"
        canSubmit={Boolean(directory.trim())}
        onSubmit={() => void run.submit(request())}
        run={run}
        firstSize={26}
        form={
          <>
            <PathField
              label="A finished caterva md folder"
              value={directory}
              onChange={setDirectory}
              kind="directory"
              purpose="Choose a caterva md folder whose replicas have run"
              placeholder="/path/to/md-setup"
              hint="Its replicas are every rep*/ with an md.xtc. The command writes analyze.sh, chi1.ndx and ANALYSIS.md into it."
              error={fieldError(run.requestError, "directory")}
            />
            <Field label="How to measure" error={fieldError(run.requestError, "mode")} hint={
              mode === "gromacs" && gromacs && !gromacs.found ? `GROMACS is not found here: ${gromacs.reason ?? "no gmx"}.` : what.what
            }>
              <Segmented<Mode>
                label="How to measure"
                value={mode}
                onChange={setMode}
                size="sm"
                options={MODES.map((m) => ({ value: m.mode, label: m.label, disabled: m.mode === "gromacs" && gromacs !== undefined && !gromacs.found }))}
              />
            </Field>
            <p className="field-hint">
              The catalytic residues come from M-CSA through caterva prepare, so a run needs the network.
            </p>
          </>
        }
        idle={
          <EmptyState title="Choose a finished run">
            <p className="st-prose">
              A folder the <Link href="/md">Dynamics</Link> screen wrote, after its run.sh has finished every replica. The
              distances between catalytic groups decide whether the runs converged; until they agree, nothing else is
              called a result.
            </p>
          </EmptyState>
        }
      >
        {(result) => <AnalyzeResultView result={result} />}
      </RunScreen>
    </Screen>
  );
}

/* ------------------------------------------------------------------ */
/* Pieces                                                              */
/* ------------------------------------------------------------------ */

function Thresholds({ values, lead = "judged against" }: { values: SourcedValue[] | undefined; lead?: string }) {
  if (!values?.length) return null;
  return (
    <p className="st-thresholds">
      <span>{lead}</span>
      {values.map((v) => (
        <span key={v.label ?? String(v.value)}>
          {v.label} <Value v={v} />
        </span>
      ))}
    </p>
  );
}

function MeanSpread({ mean, spread }: { mean: SourcedValue; spread: SourcedValue | null | undefined }) {
  return (
    <span className="st-inline">
      <Value v={mean} />
      {spread ? (
        <span className="muted st-inline">
          ± <Value v={spread} showUnit={false} />
        </span>
      ) : null}
    </span>
  );
}

function Change({ value, word }: { value: SourcedValue | null; word: string | null | undefined }) {
  if (!value) return <span className="muted">no crystal value</span>;
  return (
    <span className="st-inline">
      <Value v={value} />
      {word ? <Verdict word={word} /> : <span className="muted">not yet a result</span>}
    </span>
  );
}

/** A fraction of frames (0..1) as a bar and the value with its mark. */
export function Fraction({ v }: { v: SourcedValue | null | undefined }) {
  if (!v) return <span className="muted">none</span>;
  const f = typeof v.value === "number" ? Math.min(1, Math.max(0, v.value)) : 0;
  return (
    <span className="st-frac">
      <span className="st-frac-bar" aria-hidden="true">
        <span style={{ transform: `scaleX(${f})` }} />
      </span>
      <Value v={v} />
    </span>
  );
}

const WELL_ORDER = ["+60", "180", "-60"];

function Wells({ wells }: { wells: Record<string, SourcedValue> }) {
  const order = WELL_ORDER.filter((w) => w in wells);
  return (
    <span className="st-inline">
      <span className="st-wells" aria-hidden="true">
        {order.map((w, i) => (
          <span key={w} style={{ flexGrow: wells[w].value ?? 0, background: seriesColor(i) }} />
        ))}
      </span>
      {order.map((w) => (
        <span key={w} className="st-inline">
          <span className="muted font-mono">{w}</span>
          <Value v={wells[w]} />
        </span>
      ))}
    </span>
  );
}

function forestRows(rows: { label: string; crystal: SourcedValue | null; mean: SourcedValue; ci95?: SourcedValue | null; per_replica?: unknown[]; verdict: string; reasons?: string[] }[]): ForestRow[] {
  return rows.map((r) => ({
    label: r.label,
    crystal: r.crystal,
    mean: r.mean,
    ci95: r.ci95,
    replicas: ((r.per_replica ?? []) as ReplicaView[]).map((p) => ({ name: p.name, mean: p.mean, error: p.error })),
    verdict: r.verdict,
    reasons: r.reasons,
  }));
}

function replicaColumns<T extends { per_replica?: unknown[] }>(reps: string[]) {
  return reps.map((name) => ({
    key: `rep-${name}`,
    header: name,
    numeric: true,
    cell: (row: T) => {
      const p = ((row.per_replica ?? []) as ReplicaView[]).find((x) => x.name === name);
      return p ? (
        <span className="st-inline">
          <Value v={p.mean} />
          <span className="muted st-inline">
            ± <Value v={p.error} showUnit={false} />
          </span>
        </span>
      ) : (
        <span className="muted">none</span>
      );
    },
  }));
}

/* ------------------------------------------------------------------ */
/* The result                                                          */
/* ------------------------------------------------------------------ */

export function AnalyzeResultView({ result }: { result: AnalyzeResult }) {
  const reps = result.replicas ?? [];
  const sites = (result.catalytic ?? []) as unknown as SiteView[];
  const angles = result.angles as unknown as AngleView[];
  const flex = result.flexibility as unknown as FlexibilityView | null;
  const hbonds = result.hbonds as unknown as HbondView[] | null;
  const rotamers = result.rotamers as unknown as RotamerView[] | null;
  const faces = result.faces as unknown as FaceView[] | null;
  const water = result.water as unknown as WaterView[] | null;
  const t = result.thresholds ?? {};
  const consistent = result.distances.filter((d) => d.verdict === "consistent").length;

  if (result.measured === false) {
    return (
      <>
        <div className="st-lede">
          <h2 className="st-lede-title st-inline">
            <span className="font-mono">{result.pdb}</span> <Verdict word="script written, nothing measured" />
          </h2>
          <TextReport text={result.report_markdown} />
        </div>
        {result.written?.length ? <Written paths={result.written} /> : null}
      </>
    );
  }

  return (
    <>
      <div className="st-lede">
        <h2 className="st-lede-title st-inline">
          <span>
            <span className="font-mono">{result.pdb}</span>
            {result.chain ? (
              <>
                {" "}
                chain <span className="font-mono">{result.chain}</span>
              </>
            ) : null}
          </span>
          <Verdict word={result.all_consistent ? "consistent" : "not yet a result"} />
        </h2>
        <p className="st-lede-meta">
          <span>
            {reps.length ? (
              <>
                <span className="font-mono">{reps.length}</span> replica{reps.length === 1 ? "" : "s"}:{" "}
                <span className="font-mono">{reps.join(", ")}</span>
              </>
            ) : (
              "no finished replicas"
            )}
          </span>
          <span>
            measured {result.mode === "native" ? "natively" : `by the ${String(result.mode).replace("_", " ")} route`}
            {result.gmx ? (
              <>
                {" "}
                with <code className="font-mono">{result.gmx}</code>
              </>
            ) : null}
          </span>
          <span>
            <span className="font-mono">{consistent}</span> of <span className="font-mono">{result.distances.length}</span>{" "}
            catalytic distances consistent across replicas
          </span>
        </p>
        <p className="st-prose">Catalytic residues from {result.source}.</p>
        <Thresholds values={t.replicas} lead="a replica's mean and error are judged with" />
      </div>

      {sites.length ? (
        <Section title="What was measured" aside={countsLine(result.counts)}>
          <p className="st-inline">
            {sites.map((s) => (
              <span key={s.resnr} className="chip chip-mono" data-tone={s.functional ? "signal" : undefined} title={s.functional ? s.atoms.join(" ") : "Cα stand-in"}>
                {s.label}
                <span className="muted">{s.functional ? s.atoms.join(" ") : "Cα stand-in"}</span>
              </span>
            ))}
          </p>
          {result.notes?.length ? (
            <ul className="st-prose" style={{ paddingLeft: "1.1rem", marginTop: "0.5rem" }}>
              {result.notes.map((n) => (
                <li key={n}>{n}</li>
              ))}
            </ul>
          ) : null}
        </Section>
      ) : null}

      {result.distances.length ? (
        <Section title="Catalytic distances" aside="between functional-group centres; the crystal is the structure the run started from">
          <ReplicaForest title="Each replica, the crystal and the mean" rows={forestRows(result.distances)} unit={result.distances[0].mean.unit} replicas={reps} />
          <Thresholds values={t.distances} />
          <DistancesTable rows={result.distances} reps={reps} />
        </Section>
      ) : null}

      {angles.length ? (
        <Section title="Angles at the catalytic groups" aside={`${angles.length} angles between groups in contact in the crystal`}>
          <ReplicaForest title="Each replica, the crystal and the mean" rows={forestRows(angles.map((a) => ({ ...a, crystal: a.crystal })))} unit={angles[0].mean.unit} replicas={reps} />
          <Thresholds values={t.angles} />
          <DataTable
            caption="Angles"
            captionHidden
            rows={angles}
            rowKey={(a) => a.label}
            maxHeight="28rem"
            columns={[
              { key: "label", header: "angle", cell: (a) => <span className="font-mono">{a.label}</span> },
              { key: "crystal", header: "crystal", numeric: true, cell: (a) => <Value v={a.crystal} /> },
              { key: "mean", header: "mean of replicas", numeric: true, cell: (a) => <MeanSpread mean={a.mean} spread={a.spread} /> },
              { key: "ci", header: "95% CI", numeric: true, cell: (a) => (a.ci95 ? <Value v={a.ci95} /> : <span className="muted">none</span>) },
              { key: "change", header: "change", cell: (a) => <Change value={a.change} word={a.change_word} /> },
              ...replicaColumns<AngleView>(reps),
              { key: "verdict", header: "replicas", cell: (a) => <VerdictWithReasons word={a.verdict} reasons={a.reasons} /> },
            ]}
          />
        </Section>
      ) : null}

      {flex ? <Flexibility flex={flex} /> : null}

      {hbonds?.length ? (
        <Section title="Hydrogen bonds between catalytic residues" aside="fraction of frames bonded, per replica">
          <Thresholds values={t.hbonds} />
          <DataTable
            caption="Hydrogen bonds"
            captionHidden
            rows={hbonds.filter((h) => h.bonded)}
            rowKey={(h) => h.label}
            empty="No pair is bonded in any frame."
            columns={[
              { key: "label", header: "pair", cell: (h) => <span className="font-mono">{h.label}</span> },
              { key: "start", header: "bonds at start", numeric: true, cell: (h) => h.at_start },
              ...reps.map((name) => ({
                key: name,
                header: name,
                cell: (h: HbondView) => <Fraction v={h.per_replica.find((p) => p.replica === name)?.fraction} />,
              })),
              { key: "verdict", header: "verdict", cell: (h) => <Verdict word={h.reported} /> },
            ]}
          />
          {hbonds.some((h) => !h.bonded) ? (
            <p className="st-prose">{hbonds.filter((h) => !h.bonded).length} pairs never bonded in any frame of any replica.</p>
          ) : null}
        </Section>
      ) : null}

      {rotamers?.length ? (
        <Section title="Side-chain rotamers (chi1)" aside="the share of frames in each well, per replica">
          <Thresholds values={t.rotamers} />
          <DataTable
            caption="Rotamers"
            captionHidden
            rows={rotamers}
            rowKey={(r) => r.label}
            columns={[
              { key: "label", header: "residue", cell: (r) => <span className="font-mono">{r.label}</span> },
              {
                key: "start",
                header: "chi1 at start",
                cell: (r) => (
                  <span className="st-inline">
                    <Value v={r.at_start} /> <span className="muted">{r.start_well} well</span>
                  </span>
                ),
              },
              ...reps.map((name) => ({
                key: name,
                header: `${name}: wells`,
                cell: (r: RotamerView) => {
                  const p = r.per_replica.find((x) => x.replica === name);
                  return p ? <Wells wells={p.wells} /> : <span className="muted">none</span>;
                },
              })),
              { key: "verdict", header: "verdict", cell: (r) => <Verdict word={r.reported} /> },
            ]}
          />
        </Section>
      ) : null}

      {faces?.length ? (
        <Section title="Which face of the vertex its partners are on" aside="fraction of frames on the crystal's face, per replica">
          <Thresholds values={t.faces} />
          <DataTable
            caption="Faces"
            captionHidden
            rows={faces}
            rowKey={(f) => f.label}
            maxHeight="28rem"
            columns={[
              { key: "label", header: "vertex", cell: (f) => <span className="font-mono">{f.label}</span> },
              { key: "flat", header: "out of flat, crystal", numeric: true, cell: (f) => <Value v={f.crystal_out_of_flat} /> },
              { key: "face", header: "crystal face", cell: (f) => f.crystal_face },
              ...reps.map((name) => ({
                key: name,
                header: name,
                cell: (f: FaceView) => <Fraction v={f.per_replica.find((p) => p.replica === name)?.kept} />,
              })),
              { key: "verdict", header: "verdict", cell: (f) => <Verdict word={f.reported} /> },
            ]}
          />
        </Section>
      ) : null}

      {water?.length ? (
        <Section title="Water at the catalytic residues" aside="frames with a water within reach, and the mean count, per replica">
          <Thresholds values={t.water} />
          <DataTable
            caption="Water"
            captionHidden
            rows={water}
            rowKey={(w) => w.label}
            columns={[
              { key: "label", header: "residue", cell: (w) => <span className="font-mono">{w.label}</span> },
              {
                key: "atoms",
                header: "atoms",
                cell: (w) => (
                  <span className="font-mono muted">
                    {w.atoms.join(" ")}
                    {w.stand_in ? " (stand-in)" : ""}
                  </span>
                ),
              },
              { key: "start", header: "at start", numeric: true, cell: (w) => w.at_start },
              ...reps.map((name) => ({
                key: name,
                header: name,
                cell: (w: WaterView) => {
                  const p = w.per_replica.find((x) => x.replica === name);
                  return p?.fraction && p.mean ? (
                    <span className="st-inline">
                      <Fraction v={p.fraction} />
                      <span className="muted st-inline">
                        mean <Value v={p.mean} />
                      </span>
                    </span>
                  ) : (
                    <span className="muted">none</span>
                  );
                },
              })),
              { key: "verdict", header: "verdict", cell: (w) => <Verdict word={w.reported} /> },
            ]}
          />
        </Section>
      ) : null}

      {result.extra ? <ExtraSections extra={result.extra} /> : null}

      {result.written?.length ? <Written paths={result.written} /> : null}

      <Disclosure title="The report the terminal prints (ANALYSIS.md)">
        <MarkdownReport source={result.report_markdown} />
      </Disclosure>
    </>
  );
}

function VerdictWithReasons({ word, reasons }: { word: string; reasons?: string[] }) {
  return (
    <span className="grid gap-0.5">
      <Verdict word={word} />
      {reasons?.length ? <span className="field-hint">{reasons.join("; ")}</span> : null}
    </span>
  );
}

function Written({ paths }: { paths: string[] }) {
  return (
    <Section title="Written into the run's folder" aside="never served by the studio">
      <ul className="st-files" style={{ gridTemplateColumns: "1fr" }}>
        {paths.map((w) => (
          <li key={w}>
            <WrittenPath path={w} />
          </li>
        ))}
      </ul>
    </Section>
  );
}

function Flexibility({ flex }: { flex: FlexibilityView }) {
  return (
    <Section
      title="Active-site flexibility"
      aside={
        <span className="st-inline">
          pocket: <span className="font-mono">{flex.pocket_residues}</span> residues within <Value v={flex.pocket_radius} />;
          rest: <span className="font-mono">{flex.rest_residues}</span>
        </span>
      }
    >
      {flex.rmsf ? <RmsfChart profile={flex.rmsf} /> : null}
      <DataTable
        caption="Flexibility per replica"
        captionHidden
        rows={flex.per_replica}
        rowKey={(r) => r.replica}
        empty="Not measurable: RMSF needs more than one frame per replica."
        columns={[
          { key: "replica", header: "replica", cell: (r) => <span className="font-mono">{r.replica}</span> },
          { key: "pocket", header: "pocket Cα RMSF", numeric: true, cell: (r) => <Value v={r.pocket} /> },
          { key: "rest", header: "rest Cα RMSF", numeric: true, cell: (r) => <Value v={r.rest} /> },
          { key: "ratio", header: "pocket / rest", numeric: true, cell: (r) => (r.ratio ? <Value v={r.ratio} /> : <span className="muted">none</span>) },
        ]}
      />
      {flex.ratio_mean ? (
        <p className="st-inline st-prose">
          Pocket / rest across replicas: <MeanSpread mean={flex.ratio_mean} spread={flex.ratio_sd} />
          {flex.is_result ? null : <Verdict word="not yet a result" />}
        </p>
      ) : null}
    </Section>
  );
}

function countsLine(counts: Record<string, number> | undefined): string | null {
  if (!counts) return null;
  const parts = [
    counts.distances !== undefined ? `${counts.distances} distances` : null,
    counts.angles !== undefined ? `${counts.angles} angles` : null,
    counts.faces !== undefined ? `${counts.faces} faces` : null,
    counts.water_sites !== undefined ? `water at ${counts.water_sites} residues` : null,
  ].filter(Boolean);
  return parts.join(", ");
}

function DistancesTable({ rows, reps }: { rows: DistanceRow[]; reps: string[] }) {
  return (
    <DataTable
      caption="Catalytic distances"
      captionHidden
      rows={rows}
      rowKey={(d) => d.label}
      columns={[
        { key: "label", header: "pair", cell: (d) => <span className="font-mono">{d.label}</span> },
        { key: "crystal", header: "crystal", numeric: true, cell: (d) => (d.crystal ? <Value v={d.crystal} /> : <span className="muted">none</span>) },
        { key: "mean", header: "mean of replicas", numeric: true, cell: (d) => <MeanSpread mean={d.mean} spread={d.spread} /> },
        { key: "ci", header: "95% CI", numeric: true, cell: (d) => (d.ci95 ? <Value v={d.ci95} /> : <span className="muted">none</span>) },
        { key: "change", header: "change", cell: (d) => <Change value={d.drift} word={d.change} /> },
        ...replicaColumns<DistanceRow>(reps),
        { key: "verdict", header: "replicas", cell: (d) => <VerdictWithReasons word={d.verdict} reasons={d.reasons} /> },
      ]}
    />
  );
}
