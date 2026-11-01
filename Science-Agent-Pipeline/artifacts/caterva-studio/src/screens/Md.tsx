/**
 * /md: molecular dynamics, as the four questions the tools answer.
 *
 * - Setup (kind `md.setup`, `caterva md --pdb ... --out ...`): writes the
 *   GROMACS inputs into a folder and lists every parameter with where it
 *   came from: measured (the assay behind a cited constant, the PDB entry),
 *   chosen (by you in this form, or a stated default of the command), or a
 *   cited method. It never runs the simulation; GROMACS runs `run.sh` for
 *   hours, and the screen gives the exact commands for that and after.
 * - Convergence (`md.summarise`, `caterva md --summarise DIR`): whether
 *   the replicas of a finished run agree, block-averaged.
 * - Free energy (`fep.status`) and ligand pose (`complex.check`): read runs
 *   built and run outside the studio; setting them up needs your ligand
 *   topology and days of compute, so this version leaves that to the
 *   command line and shows the commands.
 *
 * Folders are chosen with the native panel inside Caterva.app and typed in
 * a browser (a page cannot learn a folder's path); the server checks every
 * path by CONTRACT.md 15 and a refusal lands under the field.
 */
import { type KeyboardEvent, type ReactNode, useId, useMemo, useState } from "react";
import { Link } from "wouter";

import { isCompleteEc, subjectFields } from "@/api/enzymes";
import type {
  ComplexCheckResult,
  ConvergenceResult,
  FepStatusResult,
  MdParameterRow,
  MdSetupRequest,
  MdSetupResult,
  SourcedValue,
} from "@/api/types";
import { useRun } from "@/api/useRun";
import { EnzymeFinder } from "@/components/enzyme/EnzymeFinder";
import { Disclosure } from "@/components/forms/Disclosure";
import { Field, fieldError, NumberInput, parseNumber, TextInput } from "@/components/forms/Field";
import { Citation } from "@/components/provenance/Citation";
import { ProvenanceMark, provenanceLabel } from "@/components/provenance/ProvenanceMark";
import { Value } from "@/components/provenance/Value";
import { CommandSlab, MarkdownReport, TextReport } from "@/components/report/Report";
import { Screen, Section } from "@/components/screen/Screen";
import { EmptyState } from "@/components/states/States";
import { DataTable } from "@/components/table/DataTable";
import { useCapabilities } from "@/lib/queries";

import { Linkified, Own, PathField, RunScreen, text, useParam, useRefill, Verdict, WrittenPath } from "./structure/kit";
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
  const asked = useParam("tab") as Tab | null;
  const initial = fromRun ?? asked;
  const [tab, setTab] = useState<Tab>(initial && TABS.some((t) => t.key === initial) ? initial : "setup");
  const [summariseDir, setSummariseDir] = useState(useParam("directory") ?? "");
  const base = useId();

  const onKey = (e: KeyboardEvent<HTMLDivElement>) => {
    const i = TABS.findIndex((t) => t.key === tab);
    const next =
      e.key === "ArrowRight" ? i + 1 : e.key === "ArrowLeft" ? i - 1 : e.key === "Home" ? 0 : e.key === "End" ? TABS.length - 1 : null;
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
      <div className="st-tabs" role="tablist" aria-label="What to do" onKeyDown={onKey}>
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
        <div key={t.key} id={`${base}-${t.key}`} role="tabpanel" aria-labelledby={`${base}-${t.key}-tab`} hidden={tab !== t.key}>
          {t.key === "setup" ? (
            <SetupPanel
              active={tab === "setup"}
              runId={fromRun === "setup" ? runId : null}
              onSummarise={(dir) => {
                setSummariseDir(dir);
                setTab("convergence");
              }}
            />
          ) : t.key === "convergence" ? (
            <ConvergencePanel
              active={tab === "convergence"}
              runId={fromRun === "convergence" ? runId : null}
              directory={summariseDir}
              setDirectory={setSummariseDir}
            />
          ) : t.key === "fep" ? (
            <FepPanel active={tab === "fep"} runId={fromRun === "fep" ? runId : null} />
          ) : (
            <ComplexPanel active={tab === "complex"} runId={fromRun === "complex" ? runId : null} />
          )}
        </div>
      ))}
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

interface SetupForm {
  pdb: string;
  chain: string;
  out: string;
  /** The chosen enzyme's EC number; the request carries nothing else. */
  subject: string;
  /** A name a link or an older run carried, to start the finder from; never sent. */
  subjectSeed: string;
  organism: string;
  substrate: string;
  temperature_k: string;
  ph: string;
  ns: string;
  ionic_strength_m: string;
  seed: string;
  replicas: string;
}

/** The request for the form; a number the page cannot read is sent as typed, so the server names it. */
export function setupRequest(f: SetupForm): MdSetupRequest {
  const r: MdSetupRequest = { pdb: f.pdb.trim() };
  for (const k of ["chain", "out", "organism", "substrate"] as const) if (f[k].trim()) r[k] = f[k].trim();
  if (isCompleteEc(f.subject)) r.subject = f.subject.trim();
  for (const k of ["temperature_k", "ph", "ns", "ionic_strength_m", "seed", "replicas"] as const) {
    if (f[k].trim()) r[k] = (parseNumber(f[k]) ?? f[k].trim()) as number;
  }
  return r;
}

function GromacsLine() {
  const caps = useCapabilities();
  const g = caps.data?.gromacs;
  if (!g) return null;
  return (
    <p className="field-hint">
      {g.found ? (
        <>
          GROMACS {g.version ?? ""} found at <code className="font-mono">{g.path}</code>; it runs the setup outside the
          studio.
        </>
      ) : (
        <>GROMACS is not found here ({g.reason ?? "no gmx"}). The setup is still written; running it needs GROMACS.</>
      )}
    </p>
  );
}

function SetupPanel({ runId, onSummarise, active }: { runId: string | null; onSummarise: (dir: string) => void; active: boolean }) {
  const run = useRun("md.setup", runId);
  const [f, setF] = useState<SetupForm>({
    pdb: useParam("pdb") ?? "",
    chain: useParam("chain") ?? "",
    out: "",
    subject: "",
    subjectSeed: "",
    organism: "",
    substrate: "",
    temperature_k: "",
    ph: "",
    ns: "",
    ionic_strength_m: "",
    seed: "",
    replicas: "",
  });
  const set = (k: keyof SetupForm) => (v: string) => setF((s) => ({ ...s, [k]: v }));
  useRefill(runId, run.run, (r) => {
    const out = text(r.out);
    // The default folder is the run's own; asking again writes a new run's.
    const own = run.run && out.includes(`/runs/${run.run.id}/`);
    setF({
      pdb: text(r.pdb), chain: text(r.chain), out: own ? "" : out, ...subjectFields(text(r.subject)), organism: text(r.organism),
      substrate: text(r.substrate), temperature_k: text(r.temperature_k), ph: text(r.ph), ns: text(r.ns),
      ionic_strength_m: text(r.ionic_strength_m), seed: text(r.seed), replicas: text(r.replicas),
    });
  });
  const err = (field: string) => fieldError(run.requestError, field);
  const num = (k: keyof SetupForm, label: string, unit?: string, hint?: string) => (
    <Field label={label} optional error={err(k)} hint={hint}>
      <NumberInput unit={unit} value={f[k]} onChange={(e) => set(k)(e.target.value)} />
    </Field>
  );

  return (
    <RunScreen
      kind="md.setup"
      id="md-setup"
      active={active}
      formLabel="Write a GROMACS setup"
      action="Write setup"
      canSubmit={Boolean(f.pdb.trim())}
      blockedReason="Enter a PDB entry first."
      onSubmit={() => void run.submit(setupRequest(f))}
      onChooseEnzyme={(ec) => setF((s) => ({ ...s, subject: ec, subjectSeed: "" }))}
      run={run}
      form={
        <>
          <p className="field-hint">Writes the inputs and a script into a folder. It does not run the simulation.</p>
          <div className="st-row-chain">
            <Field label="PDB entry" error={err("pdb")} hint="As 1AKI.">
              <TextInput mono value={f.pdb} onChange={(e) => set("pdb")(e.target.value)} />
            </Field>
            <Field label="Chain" optional error={err("chain")}>
              <TextInput mono value={f.chain} placeholder="all" onChange={(e) => set("chain")(e.target.value)} />
            </Field>
          </div>
          <PathField
            label="Folder to write into"
            optional
            value={f.out}
            onChange={set("out")}
            kind="directory"
            purpose="Choose a folder for the GROMACS setup"
            placeholder="kept with the run"
            hint="New, empty, or a previous caterva md setup. Left empty, the studio keeps the files with the run."
            error={err("out")}
          />
          <fieldset className="st-fieldset">
            <legend>Conditions from the measured kinetics</legend>
            <EnzymeFinder
              optional
              value={f.subject}
              onChange={(ec) => setF((s) => ({ ...s, subject: ec, subjectSeed: "" }))}
              organism={f.organism}
              seed={f.subjectSeed}
              error={err("subject")}
            />
            <div className="st-row2">
              <Field label="Organism" optional error={err("organism")}>
                <TextInput value={f.organism} onChange={(e) => set("organism")(e.target.value)} />
              </Field>
              <Field label="Substrate" optional error={err("substrate")}>
                <TextInput value={f.substrate} onChange={(e) => set("substrate")(e.target.value)} />
              </Field>
            </div>
            <p className="field-hint">
              With an enzyme and a substrate, the temperature and pH are the assay's behind the cited Km, and the setup
              says which paper.
            </p>
          </fieldset>
          <fieldset className="st-fieldset">
            <legend>Or choose them</legend>
            <div className="st-row2">
              {num("temperature_k", "Temperature", "K")}
              {num("ph", "pH")}
              {num("ns", "Production", "ns")}
              {num("ionic_strength_m", "NaCl", "M")}
              {num("replicas", "Replicas")}
              {num("seed", "Seed")}
            </div>
            <p className="field-hint">Empty fields take the command's stated defaults, and the result marks each one as a default.</p>
          </fieldset>
          <GromacsLine />
        </>
      }
      idle={
        <EmptyState title="Choose a PDB entry">
          <p className="st-prose">
            Find one on <Link href="/structure">Structures</Link> and audit it on <Link href="/prepare">Prepare</Link>{" "}
            first: a chain with no blocking defect is the place to start. Every parameter written says whether it was
            measured, chosen or taken from a cited method.
          </p>
        </EmptyState>
      }
    >
      {(result) => <SetupResultView result={result} onSummarise={onSummarise} />}
    </RunScreen>
  );
}

/** The SourcedValue the result carries for a parameter row, where it carries one. */
function valueOfRow(result: MdSetupResult, row: MdParameterRow): SourcedValue | null {
  switch (row.name) {
    case "temperature":
      return result.temperature;
    case "pH (protonation)":
      return result.ph;
    case "production length":
      return result.ns ?? null;
    case "ionic strength":
      return result.ionic_strength ?? null;
    default:
      return null;
  }
}

function Origin({ row, value }: { row: MdParameterRow; value: SourcedValue | null }) {
  if (value) {
    return (
      <span className="st-inline" style={{ flexWrap: "nowrap", whiteSpace: "nowrap" }}>
        <ProvenanceMark provenance={value.provenance} decorative />
        {provenanceLabel(value.provenance)}
      </span>
    );
  }
  if (row.origin === "chosen") {
    const p = { kind: "chosen" as const, by: row.by ?? "default" };
    return (
      <span className="st-inline" style={{ flexWrap: "nowrap", whiteSpace: "nowrap" }}>
        <ProvenanceMark provenance={p} decorative />
        {provenanceLabel(p)}
      </span>
    );
  }
  if (row.origin === "measured") {
    return (
      <span className="st-inline">
        <ProvenanceMark provenance={{ kind: "measured" }} decorative />
        measured
      </span>
    );
  }
  return <span className="chip">cited method</span>;
}

export function SetupResultView({ result, onSummarise }: { result: MdSetupResult; onSummarise?: (dir: string) => void }) {
  const out = result.out_dir;
  const counts = useMemo(() => {
    const c = { measured: 0, chosen: 0, method: 0 };
    for (const p of result.parameters) {
      // As the origin column shows it: a value the result carries says whose it is.
      const kind = valueOfRow(result, p)?.provenance.kind ?? p.origin;
      if (kind in c) c[kind as keyof typeof c] += 1;
    }
    return c;
  }, [result]);
  return (
    <>
      <div className="st-lede">
        <h2 className="st-lede-title">
          <span className="font-mono">{result.pdb}</span>
          {result.chain ? (
            <>
              {" "}
              chain <span className="font-mono">{result.chain}</span>
            </>
          ) : null}
          : <span className="font-mono">{result.files.length}</span> files written
        </h2>
        <WrittenPath path={out} />
        {result.note ? <p className="st-prose" style={{ color: "var(--fg)" }}>{result.note}</p> : null}
      </div>

      <dl className="dl">
        <dt>Temperature</dt>
        <dd>
          <Value v={result.temperature} />
        </dd>
        <dt>pH</dt>
        <dd>{result.ph ? <Value v={result.ph} /> : <span className="muted">not stated; GROMACS assigns standard states</span>}</dd>
        {result.ns ? (
          <>
            <dt>Production</dt>
            <dd>
              <Value v={result.ns} />
            </dd>
          </>
        ) : null}
        {result.ionic_strength ? (
          <>
            <dt>NaCl</dt>
            <dd>
              <Value v={result.ionic_strength} />
            </dd>
          </>
        ) : null}
        {result.replicas !== undefined ? (
          <>
            <dt>Replicas</dt>
            <dd>
              <span className="font-mono">{result.replicas}</span>
              {result.seeds?.length ? (
                <span className="muted">
                  {" "}
                  velocity seeds <span className="font-mono">{result.seeds.join(", ")}</span>
                </span>
              ) : null}
            </dd>
          </>
        ) : null}
      </dl>

      <Section title="Run it" aside="GROMACS, for hours, outside the studio">
        <div className="grid gap-3">
          <CommandSlab argv={["bash", `${out}/run.sh`]} title="1. Run every replica (GMX=/path/to/gmx chooses a GROMACS)" />
          <CommandSlab argv={["caterva", "md", "--summarise", out]} title="2. Then, whether the replicas converged" />
          <CommandSlab argv={["caterva", "analyze", out]} title="3. And the catalytic geometry across them" />
          <p className="st-inline">
            {onSummarise ? (
              <button type="button" className="btn btn-sm" onClick={() => onSummarise(out)}>
                Check convergence here once it has run
              </button>
            ) : null}
            <Link className="btn btn-sm" href={`/analyze?directory=${encodeURIComponent(out)}`}>
              Analyze it here once it has run
            </Link>
          </p>
        </div>
      </Section>

      <Section
        title="Every parameter, and where it came from"
        aside={`${counts.measured} measured, ${counts.chosen} chosen, ${counts.method} cited methods`}
      >
        <DataTable
          caption="Parameters"
          captionHidden
          rows={result.parameters}
          rowKey={(p) => p.name}
          maxHeight="40rem"
          columns={[
            { key: "name", header: "parameter", cell: (p) => p.name },
            {
              key: "value",
              header: "value",
              cell: (p) => {
                const v = valueOfRow(result, p);
                return v ? (
                  <Own>
                    <Value v={v} />
                  </Own>
                ) : (
                  <span className="font-mono">{p.value}</span>
                );
              },
            },
            {
              key: "origin",
              header: "origin",
              width: "10.5rem",
              sortValue: (p) => p.origin,
              cell: (p) => <Origin row={p} value={valueOfRow(result, p)} />,
            },
            {
              key: "source",
              header: "source",
              cell: (p) =>
                p.citation ? (
                  <span className="st-what">
                    <Citation citation={p.citation} />
                    {p.source.length > p.citation.text.length && p.source.startsWith(p.citation.text) ? (
                      <span className="muted">{p.source.slice(p.citation.text.length)}</span>
                    ) : null}
                  </span>
                ) : (
                  <span className="st-what">
                    <Linkified text={p.source} />
                  </span>
                ),
            },
          ]}
        />
      </Section>

      <Section title="Files written" aside="never served by the studio; open them where they are">
        <ul className="st-files">
          {result.files.map((name) => (
            <li key={name}>{name}</li>
          ))}
        </ul>
      </Section>

      {result.provenance_markdown ? (
        <Disclosure title="PROVENANCE.md, as written">
          <MarkdownReport source={result.provenance_markdown} />
        </Disclosure>
      ) : null}
      <Disclosure title="What the terminal prints">
        <TextReport text={result.report_text} />
      </Disclosure>
    </>
  );
}

/* ------------------------------------------------------------------ */
/* Convergence                                                         */
/* ------------------------------------------------------------------ */

function ConvergencePanel({
  runId,
  directory,
  setDirectory,
  active,
}: {
  runId: string | null;
  directory: string;
  setDirectory: (d: string) => void;
  active: boolean;
}) {
  const run = useRun("md.summarise", runId);
  useRefill(runId, run.run, (r) => setDirectory(text(r.directory)));
  return (
    <RunScreen
      kind="md.summarise"
      id="md-summarise"
      active={active}
      formLabel="Summarise replicas"
      action="Summarise"
      canSubmit={Boolean(directory.trim())}
      blockedReason="Choose the setup folder first."
      onSubmit={() => void run.submit({ directory: directory.trim() })}
      run={run}
      form={
        <PathField
          label="A finished setup's folder"
          value={directory}
          onChange={setDirectory}
          kind="directory"
          purpose="Choose a caterva md folder that has run"
          placeholder="/path/to/md-setup"
          hint="The command reads each rep*/rmsd.xvg and writes CONVERGENCE.md there."
          error={fieldError(run.requestError, "directory")}
        />
      }
      idle={
        <EmptyState title="Whether the replicas agree">
          <p className="st-prose">
            Each replica's backbone RMSD is block-averaged, the first part discarded as relaxation, and the replica means
            compared. One replica is one sample: nothing it shows can be told apart from chance.
          </p>
        </EmptyState>
      }
    >
      {(result) => <ConvergenceView result={result} />}
    </RunScreen>
  );
}

export function ConvergenceView({ result }: { result: ConvergenceResult }) {
  return (
    <>
      <div className="st-lede">
        <h2 className="st-lede-title st-inline">
          {result.quantity} <Verdict word={result.verdict} />
        </h2>
        {result.reasons?.length ? (
          <ul className="st-prose" style={{ paddingLeft: "1.1rem" }}>
            {result.reasons.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
        ) : null}
      </div>
      <dl className="dl">
        {result.mean ? (
          <>
            <dt>Mean of the replicas</dt>
            <dd>
              <Value v={result.mean} />
            </dd>
          </>
        ) : null}
        {result.spread ? (
          <>
            <dt>Spread (SD)</dt>
            <dd>
              <Value v={result.spread} />
            </dd>
          </>
        ) : null}
        {result.ci95 ? (
          <>
            <dt>95% CI half-width</dt>
            <dd>
              <Value v={result.ci95} />
            </dd>
          </>
        ) : null}
      </dl>
      <DataTable
        caption="Replicas"
        rows={result.replicas}
        rowKey={(r) => r.name}
        columns={[
          { key: "name", header: "replica", cell: (r) => <span className="font-mono">{r.name}</span> },
          { key: "mean", header: "mean", numeric: true, cell: (r) => <Value v={r.mean} /> },
          { key: "error", header: "block-averaged error", numeric: true, cell: (r) => <Value v={r.error} /> },
          {
            key: "kept",
            header: "frames kept",
            numeric: true,
            cell: (r) => (r.kept !== undefined && r.frames !== undefined ? `${r.kept} of ${r.frames}` : ""),
          },
          {
            key: "samples",
            header: "independent samples",
            numeric: true,
            cell: (r) => (r.effective_samples ? <Value v={r.effective_samples} /> : null),
          },
          { key: "verdict", header: "verdict", cell: (r) => <Verdict word={r.verdict} /> },
        ]}
      />
      {result.written ? (
        <p className="st-inline st-prose">
          Written: <WrittenPath path={result.written} />
        </p>
      ) : null}
      <Disclosure title="The report the terminal prints">
        <MarkdownReport source={result.report_markdown} />
      </Disclosure>
    </>
  );
}

/* ------------------------------------------------------------------ */
/* Free energy and pose: read only                                     */
/* ------------------------------------------------------------------ */

function FepPanel({ runId, active }: { runId: string | null; active: boolean }) {
  const run = useRun("fep.status", runId);
  const [dir, setDir] = useState("");
  useRefill(runId, run.run, (r) => setDir(text(r.directory)));
  return (
    <RunScreen
      kind="fep.status"
      id="fep-status"
      active={active}
      formLabel="Read a free-energy run"
      action="Read status"
      canSubmit={Boolean(dir.trim())}
      blockedReason="Choose the free-energy folder first."
      onSubmit={() => void run.submit({ directory: dir.trim() })}
      run={run}
      form={
        <PathField
          label="A caterva fep folder"
          value={dir}
          onChange={setDir}
          kind="directory"
          purpose="Choose a folder caterva fep wrote"
          placeholder="/path/to/fep-run"
          error={fieldError(run.requestError, "directory")}
        />
      }
      idle={
        <div className="grid gap-4">
          <p className="st-prose">
            The studio reads a binding free-energy run; it does not set one up or run it. Building the complex needs your
            ligand topology, and the alchemical legs take hours to days of GROMACS. In a terminal:
          </p>
          <CommandSlab
            title="Build, check, set up, then read"
            argv={["caterva", "complex", "--pdb", "PDB", "--ligand", "RES", "--ligand-itp", "LIGAND.itp", "--ligand-coords", "LIGAND.gro", "--out", "COMPLEX_DIR"]}
          />
          <CommandSlab argv={["caterva", "complex", "--check", "COMPLEX_DIR", "--ligand", "RES"]} title="Did the ligand keep its pose" />
          <CommandSlab
            argv={["caterva", "fep", "--ec", "EC", "--inhibitor", "NAME", "--complex", "EQUILIBRATED.gro", "--topology", "TOPOLOGY.top", "--ligand", "RES", "--ligand-itp", "LIGAND.itp", "--out", "FEP_DIR"]}
            title="Set up the legs"
          />
          <p className="st-prose">
            This tab runs <code className="font-mono">caterva fep --summarise FEP_DIR</code>: each replica's two legs, the
            cycle closed, and the verdict against the measured Ki band.
          </p>
        </div>
      }
    >
      {(result) => <FepStatusView result={result} />}
    </RunScreen>
  );
}

export function FepStatusView({ result }: { result: FepStatusResult }) {
  return (
    <>
      <div className="st-lede">
        <h2 className="st-lede-title">
          {result.compound} on <em>{result.organism}</em>
          {result.state ? <span className="muted">, {result.state} enzyme</span> : null}
        </h2>
      </div>
      <dl className="dl">
        {result.temperature_k ? (
          <>
            <dt>Temperature</dt>
            <dd>
              <Value v={result.temperature_k} />
            </dd>
          </>
        ) : null}
        {result.restraint_correction ? (
          <>
            <dt>Restraint correction</dt>
            <dd>
              <Value v={result.restraint_correction} />
            </dd>
          </>
        ) : null}
        {result.band_low && result.band_high ? (
          <>
            <dt>Measured band</dt>
            <dd className="st-inline">
              <Value v={result.band_low} /> to <Value v={result.band_high} />
            </dd>
          </>
        ) : null}
        {result.computed ? (
          <>
            <dt>Computed ΔG°bind</dt>
            <dd className="st-inline">
              <Value v={result.computed} />
              {result.sigma ? (
                <>
                  ± <Value v={result.sigma} />
                </>
              ) : null}
            </dd>
          </>
        ) : null}
      </dl>
      {result.verdict ? (
        <div className="grid gap-1">
          <p className="st-inline">
            <Verdict word={result.verdict.word} /> <span className="st-prose">{result.verdict.detail}</span>
          </p>
          <p className="st-inline st-prose">
            gap <Value v={result.verdict.gap_kcal} />, as a Ki error <Value v={result.verdict.ki_fold} />
          </p>
        </div>
      ) : result.not_a_result ? (
        <p className="st-inline st-prose">
          <Verdict word="not a result" /> {result.not_a_result.replace(/^NOT A RESULT:\s*/, "")}
        </p>
      ) : null}
      {result.replicas.length ? (
        <DataTable
          caption="Replicas"
          rows={result.replicas}
          rowKey={(r) => String(r.rep)}
          columns={[
            { key: "rep", header: "replica", cell: (r) => <span className="font-mono">rep{r.rep}</span> },
            {
              key: "complex",
              header: "complex leg",
              numeric: true,
              cell: (r) => (
                <span className="st-inline">
                  <Value v={r.complex_kj} />
                  {r.complex_err_kj ? (
                    <>
                      ± <Value v={r.complex_err_kj} showUnit={false} />
                    </>
                  ) : null}
                </span>
              ),
            },
            {
              key: "solvent",
              header: "solvent leg",
              numeric: true,
              cell: (r) => (
                <span className="st-inline">
                  <Value v={r.solvent_kj} />
                  {r.solvent_err_kj ? (
                    <>
                      ± <Value v={r.solvent_err_kj} showUnit={false} />
                    </>
                  ) : null}
                </span>
              ),
            },
            { key: "dg", header: "ΔG°bind", numeric: true, cell: (r) => <Value v={r.dg_kcal} /> },
          ]}
        />
      ) : null}
      {result.warnings.length || result.caveats?.length ? (
        <ul className="st-prose" style={{ paddingLeft: "1.1rem" }}>
          {result.caveats?.map((c) => <li key={`c-${c}`}>{c}</li>)}
          {result.warnings.map((w) => (
            <li key={`w-${w}`} style={{ color: "var(--caution)" }}>
              {w}
            </li>
          ))}
        </ul>
      ) : null}
      {result.references?.length ? <p className="st-prose">Target band from {result.references.join(", ")}.</p> : null}
      <Disclosure title="What the terminal prints">
        <TextReport text={result.report_text} />
      </Disclosure>
    </>
  );
}

function ComplexPanel({ runId, active }: { runId: string | null; active: boolean }) {
  const run = useRun("complex.check", runId);
  const [dir, setDir] = useState("");
  const [ligand, setLigand] = useState("");
  useRefill(runId, run.run, (r) => {
    setDir(text(r.directory));
    setLigand(text(r.ligand));
  });
  return (
    <RunScreen
      kind="complex.check"
      id="complex-check"
      active={active}
      formLabel="Check a ligand's pose"
      action="Check the pose"
      canSubmit={Boolean(dir.trim() && ligand.trim())}
      blockedReason="Choose the complex folder and name the ligand first."
      onSubmit={() => void run.submit({ directory: dir.trim(), ligand: ligand.trim() })}
      run={run}
      form={
        <>
          <PathField
            label="A caterva complex folder"
            value={dir}
            onChange={setDir}
            kind="directory"
            purpose="Choose a folder caterva complex built and equilibrated"
            placeholder="/path/to/complex"
            error={fieldError(run.requestError, "directory")}
          />
          <Field label="Ligand residue name" error={fieldError(run.requestError, "ligand")} hint="As the topology names it, as BNZ.">
            <TextInput mono value={ligand} onChange={(e) => setLigand(e.target.value)} />
          </Field>
        </>
      }
      idle={
        <p className="st-prose">
          After equilibration, did the ligand keep the pose the crystal gave it? A pose it left is one the free-energy
          restraints would hold it to wrongly. The complex itself is built in a terminal with{" "}
          <code className="font-mono">caterva complex</code>.
        </p>
      }
    >
      {(result) => <ComplexCheckView result={result} />}
    </RunScreen>
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
    <>
      <h2 className="st-lede-title st-inline">
        {result.ligand ?? "The ligand"} <Verdict word={result.kept ? "kept" : "left its pose"} />
      </h2>
      <dl className="dl">
        {Object.entries(result.values).map(([key, v]): ReactNode => (
          <Term key={key} label={POSE_LABEL[key] ?? v.label ?? key} v={v} />
        ))}
      </dl>
      {result.ca_atoms !== undefined ? (
        <p className="st-prose">
          Superposed on <span className="font-mono">{result.ca_atoms}</span> C-alpha atoms
          {result.frames ? (
            <>
              ; <span className="font-mono">{result.frames}</span> frames of npt.xtc read
            </>
          ) : null}
          .
        </p>
      ) : null}
      <Disclosure title="What the terminal prints">
        <TextReport text={result.report_text} />
      </Disclosure>
    </>
  );
}

function Term({ label, v }: { label: string; v: SourcedValue }) {
  return (
    <>
      <dt>{label}</dt>
      <dd>
        <Value v={v} />
      </dd>
    </>
  );
}
