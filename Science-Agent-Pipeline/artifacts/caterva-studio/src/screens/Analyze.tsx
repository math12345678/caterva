/**
 * /analyze: catalytic geometry across a finished run's replicas (kind
 * `analyze`, `caterva analyze DIR`), called a result only when the
 * replicas agree.
 *
 * Every verdict is the one the command's report prints: a distance or
 * angle is "held" or "moved" only once its replicas are consistent, and
 * every later section carries "not yet a result" while the distances do
 * not show the runs converged. The screen sets those words as they come;
 * it judges nothing itself. Sections a newer engine adds arrive under
 * `extra` and are drawn generically rather than dropped.
 */
import { useQuery } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";

import { apiJson } from "@/api/client";
import type { AnalyzeRequest, AnalyzeResult, Capabilities, DistanceRow, SourcedValue } from "@/api/types";
import { useRun } from "@/api/useRun";
import { Value } from "@/components/provenance/Value";
import { Screen } from "@/components/screen/Screen";
import { EmptyState } from "@/components/states/States";

import {
  CommandLine,
  Part,
  PathField,
  PrimaryButton,
  RunArea,
  Table,
  TerminalReport,
  Verdict,
  WrittenPath,
  fieldError,
  td,
} from "./structure/kit";
import { useParam } from "./structure/useCoordinates";
import {
  type AngleView,
  type FaceView,
  type FlexibilityView,
  type HbondView,
  type RotamerView,
  type SiteView,
  type WaterView,
} from "./structure/views";
import "./structure/structure.css";

type Mode = NonNullable<AnalyzeRequest["mode"]>;

const MODES: { mode: Mode; label: string; what: string }[] = [
  { mode: "native", label: "Native", what: "Caterva reads every replica's md.xtc itself. No GROMACS needed." },
  { mode: "gromacs", label: "GROMACS", what: "gmx measures, through the analyze.sh the command writes." },
  { mode: "no_run", label: "From .xvg files", what: "Reads the .xvg files a previous analyze.sh run left." },
  { mode: "script_only", label: "Script only", what: "Plans and writes analyze.sh and chi1.ndx; measures nothing." },
];

export default function AnalyzeScreen() {
  const run = useRun("analyze", useParam("run"));
  const [directory, setDirectory] = useState(useParam("directory") ?? "");
  const [mode, setMode] = useState<Mode>("native");
  const gromacs = useQuery({
    queryKey: ["capabilities"],
    queryFn: () => apiJson<Capabilities>("/api/capabilities"),
    select: (c) => c.gromacs,
  });
  const err = run.requestError;
  const busy = run.status === "queued" || run.status === "running";

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const r: AnalyzeRequest = { directory: directory.trim() };
    if (mode !== "native") r.mode = mode;
    void run.submit(r);
  };

  return (
    <Screen
      title="Analyze"
      purpose="Catalytic geometry and active-site flexibility across replicas, called a result only when they agree."
    >
      <div className="grid gap-8 xl:grid-cols-[19rem_minmax(0,1fr)]">
        <form onSubmit={submit} className="grid content-start gap-4" aria-label="Analyze a finished run">
          <PathField
            id="analyze-dir"
            label="A finished caterva md folder"
            value={directory}
            onChange={setDirectory}
            kind="directory"
            purpose="Choose a caterva md folder whose replicas have run"
            placeholder="/path/to/md-setup"
            hint="The command writes analyze.sh, chi1.ndx and ANALYSIS.md into it."
            error={fieldError(err, "directory")}
          />
          <fieldset className="grid gap-1.5 border-0 p-0">
            <legend className="mb-1 text-[13px] font-semibold">How to measure</legend>
            {MODES.map((m) => {
              const off = m.mode === "gromacs" && gromacs.data !== undefined && !gromacs.data.found;
              return (
                <label key={m.mode} className={`grid grid-cols-[auto_1fr] gap-x-2 text-[13.5px] ${off ? "opacity-60" : ""}`}>
                  <input
                    type="radio"
                    name="analyze-mode"
                    className="mt-1 accent-[var(--signal-deep)]"
                    value={m.mode}
                    checked={mode === m.mode}
                    disabled={off}
                    onChange={() => setMode(m.mode)}
                  />
                  <span>
                    {m.label}
                    <span className="block text-[12.5px] leading-snug text-muted">
                      {off ? `GROMACS not found here: ${gromacs.data?.reason ?? "no gmx"}` : m.what}
                    </span>
                  </span>
                </label>
              );
            })}
          </fieldset>
          {fieldError(err, "mode") ? <p className="m-0 text-[12.5px] text-danger">{fieldError(err, "mode")}</p> : null}
          <p className="m-0 text-[12.5px] leading-snug text-muted">
            The catalytic residues come from M-CSA through caterva prepare, so this needs the network.
          </p>
          <div>
            <PrimaryButton busy={busy} disabled={!directory.trim()}>
              Analyze
            </PrimaryButton>
          </div>
        </form>

        <div className="grid min-w-0 content-start gap-8">
          {run.status === "idle" && !err ? (
            <EmptyState title="Choose a finished run">
              <p className="m-0 max-w-[60ch] text-muted">
                A folder the Dynamics screen wrote, after its run.sh has finished every replica. The distances between
                catalytic groups decide whether the runs converged; until they agree, nothing else is called a result.
              </p>
            </EmptyState>
          ) : null}
          <RunArea view={run} waiting="Reading the replicas" hasResult={run.result !== null} fieldErrors={["directory", "mode"]}>
            {run.result ? <AnalyzeResultView result={run.result} /> : null}
          </RunArea>
          <CommandLine run={run.run} />
        </div>
      </div>
    </Screen>
  );
}

function ChangeCell({ value, word }: { value: SourcedValue | null; word: string | null | undefined }) {
  if (!value) return <span className="text-muted">no crystal value</span>;
  return (
    <span className="inline-flex flex-wrap items-baseline gap-1.5">
      <Value v={value} />
      {word ? <Verdict word={word} /> : <span className="text-[12px] text-muted">not yet a result</span>}
    </span>
  );
}

function MeanCell({ mean, spread }: { mean: SourcedValue; spread: SourcedValue | null | undefined }) {
  return (
    <span className="whitespace-nowrap">
      <Value v={mean} />
      {spread ? (
        <span className="text-muted">
          {" "}
          ± <Value v={spread} showUnit={false} />
        </span>
      ) : null}
    </span>
  );
}

function Reasons({ reasons }: { reasons: string[] | undefined }) {
  if (!reasons?.length) return null;
  return <span className="block text-[12px] leading-snug text-muted">{reasons.join("; ")}</span>;
}

export function AnalyzeResultView({ result }: { result: AnalyzeResult }) {
  const reps = result.replicas ?? [];
  const sites = (result.catalytic ?? []) as unknown as SiteView[];
  const angles = result.angles as unknown as AngleView[];
  const flex = result.flexibility as unknown as FlexibilityView | null;
  const hbonds = result.hbonds as unknown as HbondView[] | null;
  const rotamers = result.rotamers as unknown as RotamerView[] | null;
  const faces = result.faces as unknown as FaceView[] | null;
  const water = result.water as unknown as WaterView[] | null;
  const consistent = result.distances.filter((d) => d.verdict === "consistent").length;

  return (
    <div className="grid gap-8">
      <div className="grid gap-2">
        <p className="m-0 flex flex-wrap items-baseline gap-x-3 font-display text-[1.35rem] leading-snug">
          <span>
            <span className="font-mono text-[1.15rem]">{result.pdb}</span>
            {result.chain ? <> chain <span className="font-mono">{result.chain}</span></> : null}
          </span>
          {result.measured === false ? (
            <Verdict word="script written, nothing measured" />
          ) : result.all_consistent ? (
            <Verdict word="consistent" />
          ) : (
            <Verdict word="not yet a result" />
          )}
        </p>
        <p className="m-0 text-[13px] text-muted">
          {reps.length ? (
            <>
              <span className="font-mono tabular-nums">{reps.length}</span> replica{reps.length === 1 ? "" : "s"} (
              <span className="font-mono">{reps.join(", ")}</span>)
            </>
          ) : (
            "no finished replicas"
          )}
          {result.mode ? `, measured ${result.mode === "native" ? "natively" : `by the ${result.mode.replace("_", " ")} route`}` : null}
          {result.gmx ? <> with <code className="font-mono">{result.gmx}</code></> : null}
          {result.measured !== false ? (
            <>
              ; <span className="font-mono tabular-nums">{consistent}</span> of{" "}
              <span className="font-mono tabular-nums">{result.distances.length}</span> catalytic distances consistent
              across replicas
            </>
          ) : null}
          .
        </p>
        <p className="m-0 text-[13px] text-muted">Catalytic residues from {result.source}.</p>
      </div>

      {sites.length ? (
        <Part title="What was measured" aside={result.counts ? countsLine(result.counts) : null}>
          <ul className="m-0 flex list-none flex-wrap gap-x-5 gap-y-1 p-0 text-[13px]">
            {sites.map((s) => (
              <li key={s.resnr}>
                <span className="font-mono">{s.label}</span>{" "}
                <span className="text-muted">
                  {s.atoms.join(" ")}
                  {s.functional ? "" : " (Cα stand-in)"}
                </span>
              </li>
            ))}
          </ul>
          {result.notes?.length ? (
            <ul className="m-0 grid gap-1 pl-5 text-[13px] text-muted">
              {result.notes.map((n) => (
                <li key={n}>{n}</li>
              ))}
            </ul>
          ) : null}
        </Part>
      ) : null}

      {result.distances.length ? (
        <Part title="Catalytic distances" aside="between functional-group centres; the crystal is the starting structure">
          <DistancesTable rows={result.distances} />
        </Part>
      ) : null}

      {angles.length ? (
        <Part title="Angles at the catalytic groups">
          <Table head={["angle", "crystal", "simulated", "95% CI", "change", "replicas"]} caption="Angles">
            {angles.map((a) => (
              <tr key={a.label}>
                <td className={`${td} font-mono text-[12.5px]`}>{a.label}</td>
                <td className={td}>
                  <Value v={a.crystal} />
                </td>
                <td className={td}>
                  <MeanCell mean={a.mean} spread={a.spread} />
                </td>
                <td className={td}>{a.ci95 ? <Value v={a.ci95} /> : <span className="text-muted">n/a</span>}</td>
                <td className={td}>
                  <ChangeCell value={a.change} word={a.change_word} />
                </td>
                <td className={td}>
                  <Verdict word={a.verdict} />
                  <Reasons reasons={a.reasons} />
                </td>
              </tr>
            ))}
          </Table>
        </Part>
      ) : null}

      {flex ? (
        <Part
          title="Active-site flexibility"
          aside={
            <>
              pocket: <span className="font-mono tabular-nums">{flex.pocket_residues}</span> residues within{" "}
              <Value v={flex.pocket_radius} />; rest: <span className="font-mono tabular-nums">{flex.rest_residues}</span>
            </>
          }
        >
          <Table head={["replica", "pocket Cα RMSF", "rest Cα RMSF", "pocket / rest"]} caption="Flexibility">
            {flex.per_replica.map((r) => (
              <tr key={r.replica}>
                <td className={`${td} font-mono`}>{r.replica}</td>
                <td className={td}>
                  <Value v={r.pocket} />
                </td>
                <td className={td}>
                  <Value v={r.rest} />
                </td>
                <td className={td}>{r.ratio ? <Value v={r.ratio} /> : <span className="text-muted">n/a</span>}</td>
              </tr>
            ))}
          </Table>
          {flex.ratio_mean ? (
            <p className="m-0 text-[13.5px]">
              Pocket / rest across replicas: <MeanCell mean={flex.ratio_mean} spread={flex.ratio_sd} />
              {flex.is_result ? null : <span className="text-muted"> (not yet a result)</span>}
            </p>
          ) : null}
        </Part>
      ) : null}

      {hbonds?.length ? (
        <Part title="Hydrogen bonds between catalytic residues" aside="fraction of frames bonded, per replica">
          <Table head={["pair", "at start", ...reps, "verdict"]} caption="Hydrogen bonds">
            {hbonds
              .filter((h) => h.bonded)
              .map((h) => (
                <tr key={h.label}>
                  <td className={`${td} font-mono text-[12.5px]`}>{h.label}</td>
                  <td className={`${td} font-mono tabular-nums`}>{h.at_start}</td>
                  {h.per_replica.map((p) => (
                    <td key={p.replica} className={td}>
                      <Value v={p.fraction} />
                    </td>
                  ))}
                  <td className={td}>
                    <Verdict word={h.reported} />
                  </td>
                </tr>
              ))}
          </Table>
          {hbonds.some((h) => !h.bonded) ? (
            <p className="m-0 text-[12.5px] text-muted">
              {hbonds.filter((h) => !h.bonded).length} pairs never bonded in any frame.
            </p>
          ) : null}
        </Part>
      ) : null}

      {rotamers?.length ? (
        <Part title="Side-chain rotamers (chi1)" aside="fraction of frames in the starting well, per replica">
          <Table head={["residue", "chi1 at start", ...reps, "verdict"]} caption="Rotamers">
            {rotamers.map((r) => (
              <tr key={r.label}>
                <td className={`${td} font-mono text-[12.5px]`}>{r.label}</td>
                <td className={`${td} whitespace-nowrap`}>
                  <Value v={r.at_start} /> <span className="text-[12px] text-muted">{r.start_well}</span>
                </td>
                {r.per_replica.map((p) => (
                  <td key={p.replica} className={td}>
                    <Value v={p.kept} />
                  </td>
                ))}
                <td className={td}>
                  <Verdict word={r.reported} />
                </td>
              </tr>
            ))}
          </Table>
        </Part>
      ) : null}

      {faces?.length ? (
        <Part title="Which face of the vertex its partners are on">
          <Table head={["vertex", "out of flat, crystal", "crystal face", ...reps, "verdict"]} caption="Faces">
            {faces.map((f) => (
              <tr key={f.label}>
                <td className={`${td} font-mono text-[12.5px]`}>{f.label}</td>
                <td className={td}>
                  <Value v={f.crystal_out_of_flat} />
                </td>
                <td className={`${td} text-[13px]`}>{f.crystal_face}</td>
                {f.per_replica.map((p) => (
                  <td key={p.replica} className={td}>
                    {p.kept ? <Value v={p.kept} /> : <span className="text-muted">n/a</span>}
                  </td>
                ))}
                <td className={td}>
                  <Verdict word={f.reported} />
                </td>
              </tr>
            ))}
          </Table>
        </Part>
      ) : null}

      {water?.length ? (
        <Part title="Water at the catalytic residues" aside="mean waters within reach, and the fraction of frames with any">
          <Table head={["residue", "atoms", "at start", ...reps, "verdict"]} caption="Water">
            {water.map((w) => (
              <tr key={w.label}>
                <td className={`${td} font-mono text-[12.5px]`}>{w.label}</td>
                <td className={`${td} font-mono text-[12px] text-muted`}>
                  {w.atoms.join(" ")}
                  {w.stand_in ? " (stand-in)" : ""}
                </td>
                <td className={`${td} font-mono tabular-nums`}>{w.at_start}</td>
                {w.per_replica.map((p) => (
                  <td key={p.replica} className={`${td} whitespace-nowrap`}>
                    {p.mean && p.fraction ? (
                      <>
                        <Value v={p.mean} /> <span className="text-muted">(</span>
                        <Value v={p.fraction} />
                        <span className="text-muted">)</span>
                      </>
                    ) : (
                      <span className="text-muted">n/a</span>
                    )}
                  </td>
                ))}
                <td className={td}>
                  <Verdict word={w.reported} />
                </td>
              </tr>
            ))}
          </Table>
        </Part>
      ) : null}

      {result.extra && Object.keys(result.extra).length ? (
        <Part title="Sections this page does not draw yet">
          <p className="m-0 max-w-[75ch] text-[13.5px]">
            This run carries {Object.keys(result.extra).length === 1 ? "a section" : "sections"} from a newer engine:{" "}
            <span className="font-mono">{Object.keys(result.extra).join(", ")}</span>. Their numbers have no
            provenance marks here, so they are not drawn as numbers; the report below holds them as the terminal
            prints them, and the run's result.json holds them in full.
          </p>
        </Part>
      ) : null}

      {result.written?.length ? (
        <Part title="Written into the run's folder">
          <ul className="m-0 grid gap-0.5 p-0">
            {result.written.map((w) => (
              <li key={w} className="list-none">
                <WrittenPath path={w} />
              </li>
            ))}
          </ul>
        </Part>
      ) : null}

      <TerminalReport text={result.report_markdown} markdown={result.measured !== false} />
    </div>
  );
}

function countsLine(counts: Record<string, number>): string {
  const parts = [
    counts.distances !== undefined ? `${counts.distances} distances` : null,
    counts.angles !== undefined ? `${counts.angles} angles` : null,
    counts.faces !== undefined ? `${counts.faces} faces` : null,
    counts.water_sites !== undefined ? `water at ${counts.water_sites} residues` : null,
  ].filter(Boolean);
  return parts.join(", ");
}

function DistancesTable({ rows }: { rows: DistanceRow[] }) {
  return (
    <Table head={["pair", "crystal", "simulated", "95% CI", "change", "replicas"]} caption="Catalytic distances">
      {rows.map((d) => (
        <tr key={d.label}>
          <td className={`${td} font-mono text-[12.5px]`}>{d.label}</td>
          <td className={td}>{d.crystal ? <Value v={d.crystal} /> : <span className="text-muted">?</span>}</td>
          <td className={td}>
            <MeanCell mean={d.mean} spread={d.spread} />
          </td>
          <td className={td}>{d.ci95 ? <Value v={d.ci95} /> : <span className="text-muted">n/a</span>}</td>
          <td className={td}>
            <ChangeCell value={d.drift} word={d.change} />
          </td>
          <td className={td}>
            <Verdict word={d.verdict} />
            <Reasons reasons={d.reasons} />
          </td>
        </tr>
      ))}
    </Table>
  );
}
