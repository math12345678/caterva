/**
 * /structure: an enzyme's experimental structures in the PDB, grouped by
 * protein, each with its method, resolution, bound molecules and citation,
 * and the chosen entry in 3D with the catalytic residues `caterva prepare`
 * places on it.
 *
 * One run of `caterva structure` (kind `structure`). When the EC number is
 * several proteins the command refuses to pick one and says so; the screen
 * shows that refusal with the protein table, and choosing a protein asks
 * the same question again with its gene (or accession), as the command's
 * own hint says to.
 */
import { type FormEvent, useEffect, useMemo, useState } from "react";
import { Link } from "wouter";

import type { StructureRequest, StructureResult, StructureRow } from "@/api/types";
import { useRun } from "@/api/useRun";
import { Value } from "@/components/provenance/Value";
import { EmptyState } from "@/components/states/States";
import { Screen } from "@/components/screen/Screen";

import { EntryView } from "./structure/EntryView";
import {
  ArtifactButton,
  CheckField,
  CommandLine,
  NumberField,
  Part,
  PrimaryButton,
  RunArea,
  Table,
  TerminalReport,
  TextField,
  fieldError,
  parsed,
  td,
} from "./structure/kit";
import { useParam } from "./structure/useCoordinates";
import "./structure/structure.css";

const FIELDS = ["subject", "organism", "gene", "uniprot", "ligand", "top", "chimerax"];

export default function StructureScreen() {
  const runParam = useParam("run");
  const run = useRun("structure", runParam);
  const [form, setForm] = useState({
    subject: useParam("subject") ?? "",
    organism: useParam("organism") ?? "",
    gene: "",
    uniprot: "",
    ligand: "",
    top: "",
    chimerax: false,
  });
  const set = (key: keyof typeof form) => (v: string | boolean) => setForm((f) => ({ ...f, [key]: v }));

  const request = (f: typeof form): StructureRequest => {
    const r: StructureRequest = { subject: f.subject.trim() };
    for (const key of ["organism", "gene", "uniprot", "ligand"] as const) if (f[key].trim()) r[key] = f[key].trim();
    const top = parsed(f.top);
    if (top !== undefined) r.top = top;
    if (f.chimerax) r.chimerax = true;
    return r;
  };
  const submit = (e?: FormEvent) => {
    e?.preventDefault();
    void run.submit(request(form));
  };
  const choose = (gene: string | null, accession: string) => {
    const next = { ...form, gene: gene ?? "", uniprot: gene ? "" : accession };
    setForm(next);
    void run.submit(request(next));
  };

  const busy = run.status === "queued" || run.status === "running";
  const err = run.requestError;

  return (
    <Screen
      title="Structures"
      purpose="An enzyme's experimental structures in the PDB, grouped by protein, each with its method, resolution and citation."
    >
      <div className="grid gap-8 xl:grid-cols-[18rem_minmax(0,1fr)]">
        <form onSubmit={submit} className="grid content-start gap-4" aria-label="Search the PDB">
          <TextField
            id="structure-subject"
            label="EC number"
            value={form.subject}
            onChange={set("subject")}
            placeholder="1.1.1.27"
            mono
            autoFocus
            error={fieldError(err, "subject")}
          />
          <TextField
            id="structure-organism"
            label="Organism"
            value={form.organism}
            onChange={set("organism")}
            placeholder="human, Homo sapiens, E. coli"
            hint="Latin or common name; left out, every organism."
            error={fieldError(err, "organism")}
          />
          <div className="grid grid-cols-2 gap-3">
            <TextField id="structure-gene" label="Gene" value={form.gene} onChange={set("gene")} placeholder="LDHA" mono error={fieldError(err, "gene")} />
            <TextField
              id="structure-uniprot"
              label="UniProt"
              value={form.uniprot}
              onChange={set("uniprot")}
              placeholder="P00338"
              mono
              error={fieldError(err, "uniprot")}
            />
          </div>
          <TextField
            id="structure-ligand"
            label="Prefer entries with"
            value={form.ligand}
            onChange={set("ligand")}
            placeholder="oxamate or OXM"
            hint="A ligand id or name; entries holding it rank first."
            error={fieldError(err, "ligand")}
          />
          <NumberField
            id="structure-top"
            label="Entries in the report"
            value={form.top}
            onChange={set("top")}
            placeholder="10"
            step="1"
            hint="The table below holds every ranked entry either way."
            error={fieldError(err, "top")}
          />
          <CheckField
            id="structure-chimerax"
            label="Write a ChimeraX script for the top entry"
            checked={form.chimerax}
            onChange={set("chimerax")}
          />
          <div>
            <PrimaryButton busy={busy} disabled={!form.subject.trim()}>
              Search
            </PrimaryButton>
          </div>
        </form>

        <div className="grid content-start gap-8 min-w-0">
          {run.status === "idle" && !err ? (
            <EmptyState title="Name an enzyme by its EC number">
              <p className="m-0 max-w-[60ch] text-muted">
                The search reads UniProt for the proteins with that EC number and the RCSB for their entries. When the
                number covers several proteins (LDH in human is LDHA, LDHB, LDHC and more), it lists them and asks you
                to choose one by gene.
              </p>
            </EmptyState>
          ) : null}
          <RunArea view={run} waiting="Searching UniProt and the PDB" hasResult={run.result !== null} fieldErrors={FIELDS}>
            {run.result ? <StructureResultView result={run.result} runId={run.run?.id ?? null} onChoose={choose} busy={busy} /> : null}
          </RunArea>
          <CommandLine run={run.run} />
        </div>
      </div>
    </Screen>
  );
}

export function StructureResultView({
  result,
  runId,
  onChoose,
  busy = false,
}: {
  result: StructureResult;
  runId: string | null;
  onChoose?: (gene: string | null, accession: string) => void;
  busy?: boolean;
}) {
  const top = result.top ?? 10;
  const [all, setAll] = useState(false);
  const [open, setOpen] = useState<string | null>(result.entries[0]?.pdb_id ?? null);
  useEffect(() => setOpen(result.entries[0]?.pdb_id ?? null), [result]);
  const shown = useMemo(() => (all ? result.entries : result.entries.slice(0, top)), [all, result, top]);
  const chosen = result.proteins.find((p) => p.chosen) ?? null;

  return (
    <div className="grid gap-8">
      <div className="grid gap-1">
        <p className="m-0 font-display text-[1.35rem] leading-snug">
          EC <span className="font-mono text-[1.15rem]">{result.ec}</span>
          {result.organism ? <> in <em>{result.organism}</em></> : null}
          {chosen ? (
            <>
              {": "}
              {chosen.gene ?? chosen.accession}, <span className="font-mono tabular-nums">{result.total}</span>{" "}
              {result.total === 1 ? "entry" : "entries"}
            </>
          ) : null}
        </p>
        {result.organism_note ? <p className="m-0 text-[13px] text-muted">{result.organism_note}</p> : null}
      </div>

      <Part title="Proteins with this EC number" aside={chosen ? null : "choose one to see its entries"}>
        <Table head={["protein", "gene", "UniProt", "organism", "entries", ""]} caption="Proteins">
          {result.proteins.map((p) => (
            <tr key={p.accession} aria-current={p.chosen ? "true" : undefined}>
              <td className={td}>{p.name}</td>
              <td className={`${td} font-mono`}>{p.gene ?? ""}</td>
              <td className={`${td} font-mono`}>
                {p.url ? (
                  <a href={p.url} target="_blank" rel="noreferrer noopener">
                    {p.accession}
                  </a>
                ) : (
                  p.accession
                )}
              </td>
              <td className={`${td} italic`}>{p.organism}</td>
              <td className={`${td} font-mono tabular-nums`}>{p.entries}</td>
              <td className={`${td} text-right`}>
                {p.chosen ? (
                  <span className="text-[12.5px] text-muted">chosen</span>
                ) : onChoose && p.entries > 0 ? (
                  <button type="button" className="btn-quiet" disabled={busy} onClick={() => onChoose(p.gene, p.accession)}>
                    Choose
                  </button>
                ) : null}
              </td>
            </tr>
          ))}
        </Table>
      </Part>

      {result.entries.length > 0 ? (
        <Part
          title="Entries, best first"
          aside={
            <>
              ranked by ligand bound, method, then resolution
              {result.entries.length > top ? (
                <>
                  {" · "}
                  <button type="button" className="btn-quiet" onClick={() => setAll((a) => !a)}>
                    {all ? `Show the top ${top}` : `Show all ${result.entries.length}`}
                  </button>
                </>
              ) : null}
            </>
          }
        >
          <EntriesTable rows={shown} ligand={result.ligand} open={open} onOpen={setOpen} />
        </Part>
      ) : null}

      {open ? (
        <Part
          title={`PDB ${open}`}
          aside={
            <span className="inline-flex flex-wrap gap-2">
              <Link className="btn-quiet no-underline" href={`/prepare?entry=${encodeURIComponent(open)}`}>
                Audit this entry
              </Link>
              <Link className="btn-quiet no-underline" href={`/md?pdb=${encodeURIComponent(open)}`}>
                Write an MD setup
              </Link>
            </span>
          }
        >
          <EntryView key={open} pdbId={open} />
        </Part>
      ) : null}

      {result.chimerax_artifact && runId ? (
        <p className="m-0 flex flex-wrap items-baseline gap-3 text-[13.5px]">
          <ArtifactButton runId={runId} name={result.chimerax_artifact} label="Download the ChimeraX script" />
          <span className="text-muted">
            for the top entry; open it with <code className="font-mono">chimerax {result.chimerax_artifact}</code>
          </span>
        </p>
      ) : null}

      {result.sources?.length ? (
        <p className="m-0 text-[12.5px] text-muted">
          Read from:{" "}
          {result.sources.map((s, i) => (
            <span key={s.text}>
              {i ? "; " : ""}
              {s.url ? (
                <a href={s.url} target="_blank" rel="noreferrer noopener">
                  {s.text}
                </a>
              ) : (
                s.text
              )}
            </span>
          ))}
          .
        </p>
      ) : null}

      <TerminalReport text={result.report_markdown} markdown />
    </div>
  );
}

function EntriesTable({
  rows,
  ligand,
  open,
  onOpen,
}: {
  rows: StructureRow[];
  ligand: string | null;
  open: string | null;
  onOpen: (id: string) => void;
}) {
  return (
    <Table
      caption="PDB entries"
      head={["entry", "title", "method", "resolution", "bound", ...(ligand ? [`holds ${ligand}`] : []), "primary citation"]}
    >
      {rows.map((s) => (
        <tr
          key={s.pdb_id}
          data-selectable
          aria-selected={open === s.pdb_id}
          onClick={() => onOpen(s.pdb_id)}
        >
          <td className={`${td} whitespace-nowrap`}>
            <button
              type="button"
              className="font-mono text-[13.5px] text-[var(--signal-deep)] underline-offset-2 hover:underline"
              aria-label={`Open PDB ${s.pdb_id} in 3D`}
              onClick={(e) => {
                e.stopPropagation();
                onOpen(s.pdb_id);
              }}
            >
              {s.pdb_id}
            </button>
          </td>
          <td className={`${td} max-w-[28rem]`}>
            <span className="line-clamp-2">{sentenceCase(s.title)}</span>
          </td>
          <td className={`${td} whitespace-nowrap text-muted`}>{s.method.toLowerCase()}</td>
          <td className={`${td} whitespace-nowrap`} onClick={(e) => e.stopPropagation()}>
            {s.resolution ? <Value v={s.resolution} /> : <span className="text-muted">none given</span>}
          </td>
          <td className={`${td} text-[12.5px]`}>
            {s.bound.length ? (
              s.bound.map((b) => (
                <span key={`${b.component}-${b.role}`} className="mr-2 inline-block whitespace-nowrap" title={`${b.name}, ${b.role}`}>
                  <span className="font-mono">{b.component}</span> <span className="text-muted">{b.role}</span>
                </span>
              ))
            ) : (
              <span className="text-muted">nothing</span>
            )}
          </td>
          {ligand ? <td className={td}>{s.binds_ligand ? "yes" : "no"}</td> : null}
          <td className={`${td} text-[12.5px]`} onClick={(e) => e.stopPropagation()}>
            {s.citation.url ? (
              <a href={s.citation.url} target="_blank" rel="noreferrer noopener">
                {s.citation.text}
              </a>
            ) : (
              s.citation.text
            )}
          </td>
        </tr>
      ))}
    </Table>
  );
}

function sentenceCase(title: string): string {
  if (title !== title.toUpperCase()) return title;
  const lower = title.toLowerCase();
  return lower.charAt(0).toUpperCase() + lower.slice(1);
}
