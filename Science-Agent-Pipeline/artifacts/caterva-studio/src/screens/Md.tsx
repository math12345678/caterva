/**
 * /md: molecular dynamics, as four questions the tools answer.
 *
 * - Setup (kind `md.setup`, `caterva md --pdb ... --out ...`): writes the
 *   GROMACS inputs into a folder and lists every parameter with where it
 *   came from. It does not run the simulation; GROMACS runs `run.sh`, for
 *   hours, and the screen says so and shows the command.
 * - Convergence (`md.summarise`, `caterva md --summarise DIR`): whether the
 *   replicas of a finished run agree, block-averaged.
 * - Free energy (`fep.status`, `caterva fep --summarise DIR`) and pose
 *   (`complex.check`, `caterva complex --check DIR --ligand RES`): read a
 *   run built and run outside the studio. Setting up a free-energy
 *   calculation needs your ligand topology and days of compute, so this
 *   version leaves it to the command line and shows the commands.
 */
import { useQuery } from "@tanstack/react-query";
import { type FormEvent, type KeyboardEvent, type ReactNode, useId, useState } from "react";

import { apiJson } from "@/api/client";
import type {
  Capabilities,
  ComplexCheckResult,
  ConvergenceResult,
  FepStatusResult,
  MdSetupRequest,
  MdSetupResult,
} from "@/api/types";
import { useRun } from "@/api/useRun";
import { Value } from "@/components/provenance/Value";
import { Screen } from "@/components/screen/Screen";
import { EmptyState } from "@/components/states/States";

import {
  CommandLine,
  NumberField,
  Part,
  PathField,
  PrimaryButton,
  RunArea,
  Table,
  TerminalReport,
  TextField,
  Verdict,
  WrittenPath,
  fieldError,
  parsed,
  td,
  Linkified,
} from "./structure/kit";
import { useParam } from "./structure/useCoordinates";
import "./structure/structure.css";

type Tab = "setup" | "convergence" | "fep" | "complex";
const TABS: { key: Tab; label: string }[] = [
  { key: "setup", label: "Setup" },
  { key: "convergence", label: "Convergence" },
  { key: "fep", label: "Free energy" },
  { key: "complex", label: "Ligand pose" },
];

export default function MdScreen() {
  const runId = useParam("run");
  const fromRun = runId ? tabOfRun(runId) : null;
  const initial = (useParam("tab") as Tab | null) ?? fromRun;
  const [tab, setTab] = useState<Tab>(initial && TABS.some((t) => t.key === initial) ? initial : "setup");
  const [summariseDir, setSummariseDir] = useState("");
  const base = useId();

  const onKey = (e: KeyboardEvent<HTMLDivElement>) => {
    const i = TABS.findIndex((t) => t.key === tab);
    const next = e.key === "ArrowRight" ? i + 1 : e.key === "ArrowLeft" ? i - 1 : null;
    if (next === null) return;
    e.preventDefault();
    const t = TABS[(next + TABS.length) % TABS.length];
    setTab(t.key);
    document.getElementById(`${base}-${t.key}-tab`)?.focus();
  };

  return (
    <Screen
      title="Dynamics"
      purpose="A GROMACS setup whose every parameter is measured, chosen or cited, and whether its replicas converged."
    >
      <div className="grid gap-6">
        <div className="str-tabs" role="tablist" aria-label="What to do" onKeyDown={onKey}>
          {TABS.map((t) => (
            <button
              key={t.key}
              id={`${base}-${t.key}-tab`}
              type="button"
              role="tab"
              aria-selected={tab === t.key}
              aria-controls={`${base}-${t.key}`}
              tabIndex={tab === t.key ? 0 : -1}
              onClick={() => setTab(t.key)}
            >
              {t.label}
            </button>
          ))}
        </div>
        {TABS.map((t) => (
          <div
            key={t.key}
            id={`${base}-${t.key}`}
            role="tabpanel"
            aria-labelledby={`${base}-${t.key}-tab`}
            hidden={tab !== t.key}
          >
            {t.key === "setup" ? (
              <SetupPanel
                runId={fromRun === "setup" ? runId : null}
                onSummarise={(dir) => {
                  setSummariseDir(dir);
                  setTab("convergence");
                }}
              />
            ) : t.key === "convergence" ? (
              <ConvergencePanel
                runId={fromRun === "convergence" ? runId : null}
                directory={summariseDir}
                setDirectory={setSummariseDir}
              />
            ) : t.key === "fep" ? (
              <FepPanel runId={fromRun === "fep" ? runId : null} />
            ) : (
              <ComplexPanel runId={fromRun === "complex" ? runId : null} />
            )}
          </div>
        ))}
      </div>
    </Screen>
  );
}

/** Which tab a run reopened from History belongs to, from the kind its id carries (routes.RUN_ID_PATTERN). */
export function tabOfRun(id: string): Tab | null {
  const kind = /^[0-9]{8}-[0-9]{6}-([a-z]+(?:-[a-z]+)?)-[0-9a-f]{8}$/.exec(id)?.[1];
  return kind === "md-setup"
    ? "setup"
    : kind === "md-summarise"
      ? "convergence"
      : kind === "fep-status"
        ? "fep"
        : kind === "complex-check"
          ? "complex"
          : null;
}

/* ------------------------------------------------------------------ */
/* Setup                                                               */
/* ------------------------------------------------------------------ */

const SETUP_FIELDS = ["pdb", "chain", "out", "subject", "organism", "substrate", "temperature_k", "ph", "ns",
  "ionic_strength_m", "seed", "replicas"];

function useGromacs() {
  return useQuery({
    queryKey: ["capabilities"],
    queryFn: () => apiJson<Capabilities>("/api/capabilities"),
    select: (c) => c.gromacs,
  });
}

function SetupPanel({ runId, onSummarise }: { runId: string | null; onSummarise: (dir: string) => void }) {
  const run = useRun("md.setup", runId);
  const gromacs = useGromacs();
  const [f, setF] = useState({
    pdb: useParam("pdb") ?? "",
    chain: useParam("chain") ?? "",
    out: "",
    subject: "",
    organism: "",
    substrate: "",
    temperature_k: "",
    ph: "",
    ns: "",
    ionic_strength_m: "",
    seed: "",
    replicas: "",
  });
  const set = (k: keyof typeof f) => (v: string) => setF((s) => ({ ...s, [k]: v }));
  const err = run.requestError;
  const busy = run.status === "queued" || run.status === "running";

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const r: MdSetupRequest = { pdb: f.pdb.trim() };
    for (const k of ["chain", "out", "subject", "organism", "substrate"] as const) if (f[k].trim()) r[k] = f[k].trim();
    for (const k of ["temperature_k", "ph", "ns", "ionic_strength_m", "seed", "replicas"] as const) {
      const n = parsed(f[k]);
      if (n !== undefined) r[k] = n;
    }
    void run.submit(r);
  };

  return (
    <div className="grid gap-8 xl:grid-cols-[19rem_minmax(0,1fr)]">
      <form onSubmit={submit} className="grid content-start gap-4" aria-label="Write a GROMACS setup">
        <p className="m-0 text-[13px] leading-snug text-muted">
          Writes the inputs and a script; it does not run the simulation.
        </p>
        <div className="grid grid-cols-[1fr_6rem] gap-3">
          <TextField id="md-pdb" label="PDB entry" value={f.pdb} onChange={set("pdb")} placeholder="1AKI" mono error={fieldError(err, "pdb")} />
          <TextField id="md-chain" label="Chain" value={f.chain} onChange={set("chain")} placeholder="all" mono error={fieldError(err, "chain")} />
        </div>
        <PathField
          id="md-out"
          label="Folder to write into"
          value={f.out}
          onChange={set("out")}
          kind="directory"
          purpose="Choose a folder for the GROMACS setup"
          placeholder="the run's own folder"
          hint="New or empty, or a previous caterva md setup. Left empty, the studio keeps it with the run."
          error={fieldError(err, "out")}
        />
        <fieldset className="grid gap-3 border-0 border-t border-rule p-0 pt-3">
          <legend className="pr-2 text-[13px] font-semibold">Conditions from the measured kinetics</legend>
          <TextField id="md-subject" label="EC number" value={f.subject} onChange={set("subject")} placeholder="1.1.1.27" mono error={fieldError(err, "subject")} />
          <div className="grid grid-cols-2 gap-3">
            <TextField id="md-organism" label="Organism" value={f.organism} onChange={set("organism")} placeholder="human" error={fieldError(err, "organism")} />
            <TextField id="md-substrate" label="Substrate" value={f.substrate} onChange={set("substrate")} placeholder="pyruvate" error={fieldError(err, "substrate")} />
          </div>
          <p className="m-0 text-[12.5px] leading-snug text-muted">
            With an EC number and a substrate, the temperature and pH are the assay's behind the cited Km.
          </p>
        </fieldset>
        <fieldset className="grid grid-cols-2 gap-3 border-0 border-t border-rule p-0 pt-3">
          <legend className="pr-2 text-[13px] font-semibold">Or set them</legend>
          <NumberField id="md-temperature" label="Temperature, K" value={f.temperature_k} onChange={set("temperature_k")} placeholder="298.15" error={fieldError(err, "temperature_k")} />
          <NumberField id="md-ph" label="pH" value={f.ph} onChange={set("ph")} placeholder="not stated" error={fieldError(err, "ph")} />
          <NumberField id="md-ns" label="Production, ns" value={f.ns} onChange={set("ns")} placeholder="10" error={fieldError(err, "ns")} />
          <NumberField id="md-ionic" label="NaCl, M" value={f.ionic_strength_m} onChange={set("ionic_strength_m")} placeholder="0.15" error={fieldError(err, "ionic_strength_m")} />
          <NumberField id="md-replicas" label="Replicas" value={f.replicas} onChange={set("replicas")} placeholder="3" step="1" error={fieldError(err, "replicas")} />
          <NumberField id="md-seed" label="Seed" value={f.seed} onChange={set("seed")} placeholder="20260927" step="1" error={fieldError(err, "seed")} />
        </fieldset>
        <div>
          <PrimaryButton busy={busy} disabled={!f.pdb.trim()}>
            Write setup
          </PrimaryButton>
        </div>
        <p className="m-0 text-[12.5px] text-muted">
          {gromacs.data
            ? gromacs.data.found
              ? `GROMACS found: ${gromacs.data.version ?? ""} at ${gromacs.data.path ?? ""}.`
              : `GROMACS not found here (${gromacs.data.reason ?? "no gmx"}). The setup is still written; running it needs GROMACS.`
            : null}
        </p>
      </form>

      <div className="grid min-w-0 content-start gap-8">
        {run.status === "idle" && !err ? (
          <EmptyState title="Choose a PDB entry">
            <p className="m-0 max-w-[60ch] text-muted">
              Find one on the Structures screen and audit it on Prepare first; a chain with no blocking defect is the
              place to start. Every parameter written will say whether it was measured, chosen or taken from a cited
              method.
            </p>
          </EmptyState>
        ) : null}
        <RunArea view={run} waiting="Writing the setup" hasResult={run.result !== null} fieldErrors={SETUP_FIELDS}>
          {run.result ? <SetupResultView result={run.result} onSummarise={onSummarise} /> : null}
        </RunArea>
        <CommandLine run={run.run} />
      </div>
    </div>
  );
}

const ORIGIN_WORD: Record<string, string> = {
  measured: "measured",
  chosen: "chosen",
  method: "cited method",
};

export function SetupResultView({ result, onSummarise }: { result: MdSetupResult; onSummarise?: (dir: string) => void }) {
  return (
    <div className="grid gap-8">
      <div className="grid gap-2">
        <p className="m-0 font-display text-[1.35rem] leading-snug">
          <span className="font-mono text-[1.15rem]">{result.pdb}</span>
          {result.chain ? <> chain <span className="font-mono">{result.chain}</span></> : null}: {result.files.length} files
          written
        </p>
        <WrittenPath path={result.out_dir} />
        {result.note ? <p className="m-0 max-w-[75ch] text-[13.5px]">{result.note}</p> : null}
      </div>

      <dl className="m-0 grid grid-cols-[repeat(auto-fit,minmax(11rem,1fr))] gap-x-8 gap-y-3">
        <Term label="Temperature">
          <Value v={result.temperature} />
        </Term>
        <Term label="pH">{result.ph ? <Value v={result.ph} /> : <span className="text-muted">not stated; standard states</span>}</Term>
        {result.ns ? (
          <Term label="Production">
            <Value v={result.ns} />
          </Term>
        ) : null}
        {result.ionic_strength ? (
          <Term label="NaCl">
            <Value v={result.ionic_strength} />
          </Term>
        ) : null}
        {result.replicas !== undefined ? (
          <Term label="Replicas">
            <span className="font-mono tabular-nums">{result.replicas}</span>
            {result.seeds?.length ? (
              <span className="text-[12.5px] text-muted"> seeds <span className="font-mono">{result.seeds.join(", ")}</span></span>
            ) : null}
          </Term>
        ) : null}
      </dl>

      <Part title="Run it" aside="GROMACS, for hours; outside the studio">
        <pre className="command-slab m-0">{`bash ${shellPath(result.out_dir)}/run.sh\ncaterva md --summarise ${shellPath(result.out_dir)}`}</pre>
        {onSummarise ? (
          <p className="m-0">
            <button type="button" className="btn-quiet" onClick={() => onSummarise(result.out_dir)}>
              Check convergence once it has run
            </button>
          </p>
        ) : null}
      </Part>

      <Part title="Every parameter, and where it came from" aside={`${result.parameters.length} parameters`}>
        <Table head={["parameter", "value", "origin", "source"]} caption="Parameters">
          {result.parameters.map((p) => (
            <tr key={p.name}>
              <td className={`${td} whitespace-nowrap`}>{p.name}</td>
              <td className={`${td} font-mono text-[12.5px]`}>{p.value}</td>
              <td className={`${td} whitespace-nowrap`}>
                <OriginTag origin={p.origin} />
              </td>
              <td className={`${td} max-w-[36rem] text-[13px]`}>
                <Linkified text={p.source} />
              </td>
            </tr>
          ))}
        </Table>
      </Part>

      <Part title="Files written" aside="never served by the studio; open them where they are">
        <ul className="m-0 grid grid-cols-[repeat(auto-fill,minmax(10rem,1fr))] gap-x-6 gap-y-0.5 p-0 font-mono text-[12.5px]">
          {result.files.map((name) => (
            <li key={name} className="list-none">
              {name}
            </li>
          ))}
        </ul>
      </Part>

      {result.provenance_markdown ? (
        <TerminalReport text={result.provenance_markdown} markdown title="PROVENANCE.md, as written" />
      ) : null}
      <TerminalReport text={result.report_text} markdown={false} />
    </div>
  );
}

function OriginTag({ origin }: { origin: string }) {
  const word = ORIGIN_WORD[origin] ?? origin;
  const tone = origin === "measured" ? "text-[var(--signal-deep)]" : origin === "method" ? "text-fg" : "text-caution";
  return <span className={`font-mono text-[12px] ${tone}`}>{word}</span>;
}

function shellPath(path: string): string {
  return /^[A-Za-z0-9_@%+=:,./-]+$/.test(path) ? path : `'${path.replace(/'/g, `'\\''`)}'`;
}

function Term({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid gap-0.5">
      <dt className="text-[12px] text-muted">{label}</dt>
      <dd className="m-0 text-[15px]">{children}</dd>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Convergence                                                         */
/* ------------------------------------------------------------------ */

function ConvergencePanel({
  runId,
  directory,
  setDirectory,
}: {
  runId: string | null;
  directory: string;
  setDirectory: (d: string) => void;
}) {
  const run = useRun("md.summarise", runId);
  const err = run.requestError;
  const busy = run.status === "queued" || run.status === "running";
  return (
    <div className="grid gap-8 xl:grid-cols-[19rem_minmax(0,1fr)]">
      <form
        className="grid content-start gap-4"
        aria-label="Summarise replicas"
        onSubmit={(e) => {
          e.preventDefault();
          void run.submit({ directory: directory.trim() });
        }}
      >
        <PathField
          id="md-summarise-dir"
          label="A finished setup's folder"
          value={directory}
          onChange={setDirectory}
          kind="directory"
          purpose="Choose a caterva md folder that has run"
          placeholder="/path/to/md-setup"
          hint="The command reads each rep*/rmsd.xvg and writes CONVERGENCE.md there."
          error={fieldError(err, "directory")}
        />
        <div>
          <PrimaryButton busy={busy} disabled={!directory.trim()}>
            Summarise
          </PrimaryButton>
        </div>
      </form>
      <div className="grid min-w-0 content-start gap-6">
        {run.status === "idle" && !err ? (
          <EmptyState title="Whether the replicas agree">
            <p className="m-0 max-w-[60ch] text-muted">
              Each replica's backbone RMSD is block-averaged, the first part discarded as relaxation, and the replica
              means compared. One replica is one sample: nothing it shows can be told apart from chance.
            </p>
          </EmptyState>
        ) : null}
        <RunArea view={run} waiting="Reading the replicas" hasResult={run.result !== null} fieldErrors={["directory"]}>
          {run.result ? <ConvergenceView result={run.result} /> : null}
        </RunArea>
        <CommandLine run={run.run} />
      </div>
    </div>
  );
}

export function ConvergenceView({ result }: { result: ConvergenceResult }) {
  return (
    <div className="grid gap-6">
      <p className="m-0 flex flex-wrap items-baseline gap-3 font-display text-[1.25rem]">
        {result.quantity}: <Verdict word={result.verdict} />
      </p>
      <dl className="m-0 grid grid-cols-[repeat(auto-fit,minmax(10rem,1fr))] gap-x-8 gap-y-3">
        {result.mean ? (
          <Term label="Mean of the replicas">
            <Value v={result.mean} />
          </Term>
        ) : null}
        {result.spread ? (
          <Term label="Spread (SD)">
            <Value v={result.spread} />
          </Term>
        ) : null}
        {result.ci95 ? (
          <Term label="95% CI half-width">
            <Value v={result.ci95} />
          </Term>
        ) : null}
      </dl>
      {result.reasons?.length ? (
        <ul className="m-0 grid gap-1 pl-5 text-[13.5px]">
          {result.reasons.map((r) => (
            <li key={r}>{r}</li>
          ))}
        </ul>
      ) : null}
      <Table head={["replica", "mean", "block-averaged error", "frames kept", "independent samples", "error"]} caption="Replicas">
        {result.replicas.map((r) => (
          <tr key={r.name}>
            <td className={`${td} font-mono`}>{r.name}</td>
            <td className={td}>
              <Value v={r.mean} />
            </td>
            <td className={td}>
              <Value v={r.error} />
            </td>
            <td className={`${td} font-mono tabular-nums`}>
              {r.kept !== undefined && r.frames !== undefined ? `${r.kept} of ${r.frames}` : ""}
            </td>
            <td className={td}>{r.effective_samples ? <Value v={r.effective_samples} /> : null}</td>
            <td className={td}>
              <Verdict word={r.verdict} />
            </td>
          </tr>
        ))}
      </Table>
      {result.written ? (
        <p className="m-0 text-[13px] text-muted">
          Written: <WrittenPath path={result.written} />
        </p>
      ) : null}
      <TerminalReport text={result.report_markdown} markdown />
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Free energy and pose: read only                                     */
/* ------------------------------------------------------------------ */

function NotFromHere({ children }: { children: ReactNode }) {
  return (
    <div className="grid max-w-[75ch] gap-2 text-[13.5px]">
      <p className="m-0">{children}</p>
    </div>
  );
}

function FepPanel({ runId }: { runId: string | null }) {
  const run = useRun("fep.status", runId);
  const [dir, setDir] = useState("");
  const err = run.requestError;
  const busy = run.status === "queued" || run.status === "running";
  return (
    <div className="grid gap-8 xl:grid-cols-[19rem_minmax(0,1fr)]">
      <form
        className="grid content-start gap-4"
        aria-label="Read a free-energy run"
        onSubmit={(e) => {
          e.preventDefault();
          void run.submit({ directory: dir.trim() });
        }}
      >
        <PathField
          id="fep-dir"
          label="A caterva fep folder"
          value={dir}
          onChange={setDir}
          kind="directory"
          purpose="Choose a folder caterva fep wrote"
          placeholder="/path/to/fep-run"
          error={fieldError(err, "directory")}
        />
        <div>
          <PrimaryButton busy={busy} disabled={!dir.trim()}>
            Read status
          </PrimaryButton>
        </div>
      </form>
      <div className="grid min-w-0 content-start gap-6">
        {run.status === "idle" && !err ? (
          <div className="grid gap-4">
            <NotFromHere>
              The studio reads a binding free-energy run; it does not set one up or run it. Building the complex needs
              your ligand topology, and the alchemical legs take hours to days of GROMACS on a workstation or cluster.
              In a terminal:
            </NotFromHere>
            <pre className="command-slab m-0">{[
              "caterva complex --pdb PDB --ligand RES --ligand-itp LIGAND.itp \\",
              "    --ligand-coords LIGAND.gro --out COMPLEX_DIR",
              "caterva complex --check COMPLEX_DIR --ligand RES",
              "caterva fep --ec EC --inhibitor NAME --complex EQUILIBRATED.gro \\",
              "    --topology TOPOLOGY.top --ligand RES --ligand-itp LIGAND.itp --out FEP_DIR",
              "caterva fep --summarise FEP_DIR",
            ].join("\n")}</pre>
            <p className="m-0 text-[13px] text-muted">
              The last line is what this tab runs: each replica's two legs, the cycle closed, and the verdict against
              the measured Ki band.
            </p>
          </div>
        ) : null}
        <RunArea view={run} waiting="Reading the legs" hasResult={run.result !== null} fieldErrors={["directory"]}>
          {run.result ? <FepStatusView result={run.result} /> : null}
        </RunArea>
        <CommandLine run={run.run} />
      </div>
    </div>
  );
}

export function FepStatusView({ result }: { result: FepStatusResult }) {
  return (
    <div className="grid gap-6">
      <p className="m-0 font-display text-[1.25rem] leading-snug">
        {result.compound} on <em>{result.organism}</em>
        {result.state ? <span className="text-muted">, {result.state} enzyme</span> : null}
      </p>
      <dl className="m-0 grid grid-cols-[repeat(auto-fit,minmax(11rem,1fr))] gap-x-8 gap-y-3">
        {result.temperature_k ? (
          <Term label="Temperature">
            <Value v={result.temperature_k} />
          </Term>
        ) : null}
        {result.restraint_correction ? (
          <Term label="Restraint correction">
            <Value v={result.restraint_correction} />
          </Term>
        ) : null}
        {result.band_low && result.band_high ? (
          <Term label="Measured band">
            <Value v={result.band_low} /> <span className="text-muted">to</span> <Value v={result.band_high} />
          </Term>
        ) : null}
        {result.computed ? (
          <Term label="Computed ΔG°bind">
            <Value v={result.computed} />
            {result.sigma ? (
              <span className="text-muted">
                {" "}
                ± <Value v={result.sigma} />
              </span>
            ) : null}
          </Term>
        ) : null}
      </dl>
      {result.verdict ? (
        <div className="grid gap-1">
          <p className="m-0 flex flex-wrap items-baseline gap-3">
            <Verdict word={result.verdict.word} />
            <span className="text-[13.5px]">{result.verdict.detail}</span>
          </p>
          <p className="m-0 text-[13px] text-muted">
            gap <Value v={result.verdict.gap_kcal} />, as a Ki error <Value v={result.verdict.ki_fold} />
          </p>
        </div>
      ) : result.not_a_result ? (
        <p className="m-0 max-w-[75ch] text-[13.5px]">
          <Verdict word="not a result" /> {result.not_a_result.replace(/^NOT A RESULT:\s*/, "")}
        </p>
      ) : null}
      {result.replicas.length ? (
        <Table head={["replica", "complex leg", "solvent leg", "ΔG°bind"]} caption="Replicas">
          {result.replicas.map((r) => (
            <tr key={r.rep}>
              <td className={`${td} font-mono`}>rep{r.rep}</td>
              <td className={td}>
                <Value v={r.complex_kj} />
                {r.complex_err_kj ? (
                  <span className="text-muted">
                    {" "}
                    ± <Value v={r.complex_err_kj} showUnit={false} />
                  </span>
                ) : null}
              </td>
              <td className={td}>
                <Value v={r.solvent_kj} />
                {r.solvent_err_kj ? (
                  <span className="text-muted">
                    {" "}
                    ± <Value v={r.solvent_err_kj} showUnit={false} />
                  </span>
                ) : null}
              </td>
              <td className={td}>
                <Value v={r.dg_kcal} />
              </td>
            </tr>
          ))}
        </Table>
      ) : null}
      {result.warnings.length || result.caveats?.length ? (
        <ul className="m-0 grid gap-1 pl-5 text-[13px]">
          {result.caveats?.map((c) => <li key={`c-${c}`}>{c}</li>)}
          {result.warnings.map((w) => (
            <li key={`w-${w}`} className="text-caution">
              {w}
            </li>
          ))}
        </ul>
      ) : null}
      {result.references?.length ? (
        <p className="m-0 text-[12.5px] text-muted">Target band from {result.references.join(", ")}.</p>
      ) : null}
      <TerminalReport text={result.report_text} markdown={false} />
    </div>
  );
}

function ComplexPanel({ runId }: { runId: string | null }) {
  const run = useRun("complex.check", runId);
  const [dir, setDir] = useState("");
  const [ligand, setLigand] = useState("");
  const err = run.requestError;
  const busy = run.status === "queued" || run.status === "running";
  return (
    <div className="grid gap-8 xl:grid-cols-[19rem_minmax(0,1fr)]">
      <form
        className="grid content-start gap-4"
        aria-label="Check a ligand's pose"
        onSubmit={(e) => {
          e.preventDefault();
          void run.submit({ directory: dir.trim(), ligand: ligand.trim() });
        }}
      >
        <PathField
          id="complex-dir"
          label="A caterva complex folder"
          value={dir}
          onChange={setDir}
          kind="directory"
          purpose="Choose a folder caterva complex built and equilibrated"
          placeholder="/path/to/complex"
          error={fieldError(err, "directory")}
        />
        <TextField id="complex-ligand" label="Ligand residue name" value={ligand} onChange={setLigand} placeholder="BNZ" mono error={fieldError(err, "ligand")} />
        <div>
          <PrimaryButton busy={busy} disabled={!dir.trim() || !ligand.trim()}>
            Check the pose
          </PrimaryButton>
        </div>
      </form>
      <div className="grid min-w-0 content-start gap-6">
        {run.status === "idle" && !err ? (
          <NotFromHere>
            After equilibration, did the ligand keep the pose the crystal gave it? A pose it left is one the free-energy
            restraints would hold it to wrongly. The complex itself is built in a terminal with{" "}
            <code className="font-mono">caterva complex</code>.
          </NotFromHere>
        ) : null}
        <RunArea view={run} waiting="Superposing the complex" hasResult={run.result !== null} fieldErrors={["directory", "ligand"]}>
          {run.result ? <ComplexCheckView result={run.result} /> : null}
        </RunArea>
        <CommandLine run={run.run} />
      </div>
    </div>
  );
}

const POSE_LABEL: Record<string, string> = {
  ligand_rmsd: "Ligand RMSD after equilibration",
  ca_rmsd: "Protein C-alpha RMSD",
  centroid_shift: "Ligand centroid moved",
  kept_threshold: "Kept within",
  worst_rmsd: "Worst frame of npt.xtc",
  worst_time: "at",
  max_centroid_shift: "Largest centroid shift",
};

export function ComplexCheckView({ result }: { result: ComplexCheckResult }) {
  return (
    <div className="grid gap-6">
      <p className="m-0 flex flex-wrap items-baseline gap-3 font-display text-[1.25rem]">
        {result.ligand ?? "The ligand"}: <Verdict word={result.kept ? "kept" : "left its pose"} />
      </p>
      <dl className="m-0 grid grid-cols-[repeat(auto-fit,minmax(12rem,1fr))] gap-x-8 gap-y-3">
        {Object.entries(result.values).map(([key, v]) => (
          <Term key={key} label={POSE_LABEL[key] ?? v.label ?? key}>
            <Value v={v} />
          </Term>
        ))}
      </dl>
      {result.ca_atoms !== undefined ? (
        <p className="m-0 text-[13px] text-muted">
          Superposed on <span className="font-mono tabular-nums">{result.ca_atoms}</span> C-alpha atoms
          {result.frames ? (
            <>
              ; <span className="font-mono tabular-nums">{result.frames}</span> frames of npt.xtc read
            </>
          ) : null}
          .
        </p>
      ) : null}
      <TerminalReport text={result.report_text} markdown={false} />
    </div>
  );
}
