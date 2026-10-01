/**
 * /structure: an enzyme's experimental structures in the PDB, grouped by
 * protein with each isoform kept apart, every entry with its method,
 * resolution, bound molecules and citation, and the chosen entry in 3D
 * with the catalytic residues `caterva prepare` places on it.
 *
 * One run of `caterva structure` (kind `structure`). The enzyme is an EC
 * number or a name; a name is looked up by the command, and one that names
 * several enzymes is refused with each candidate, which the screen offers
 * as a search. An EC number that is several proteins is refused too (the
 * command will not choose LDHA for you when you asked for LDH), and the
 * screen shows the protein table with a choice per protein, which asks the
 * same question again with that protein's gene, as the command's own hint
 * says to.
 */
import { ExternalLink } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "wouter";

import type { ProteinRow, StructureRequest, StructureResult, StructureRow } from "@/api/types";
import { useRun } from "@/api/useRun";
import { Checkbox, Field, fieldError, NumberInput, parseNumber, TextInput } from "@/components/forms/Field";
import { Disclosure } from "@/components/forms/Disclosure";
import { Citation } from "@/components/provenance/Citation";
import { Value } from "@/components/provenance/Value";
import { MarkdownReport } from "@/components/report/Report";
import { Screen, Section } from "@/components/screen/Screen";
import { EmptyState } from "@/components/states/States";
import { DataTable } from "@/components/table/DataTable";
import { useCapabilities } from "@/lib/queries";

import { EntryView } from "./structure/EntryView";
import { ArtifactButton, Own, RunScreen, sentenceCase, text, useParam, useRefill } from "./structure/kit";
import "./structure/structure.css";

interface Form {
  subject: string;
  organism: string;
  gene: string;
  uniprot: string;
  ligand: string;
  top: string;
  chimerax: boolean;
}

/** The request for a form. A number the page cannot read is sent as typed, so the server names it. */
export function structureRequest(f: Form): StructureRequest {
  const r: StructureRequest = { subject: f.subject.trim() };
  for (const key of ["organism", "gene", "uniprot", "ligand"] as const) if (f[key].trim()) r[key] = f[key].trim();
  if (f.top.trim()) r.top = (parseNumber(f.top) ?? f.top.trim()) as number;
  if (f.chimerax) r.chimerax = true;
  return r;
}

export default function StructureScreen() {
  const reopened = useParam("run");
  const run = useRun("structure", reopened);
  const caps = useCapabilities();
  const [form, setForm] = useState<Form>({
    subject: useParam("subject") ?? "",
    organism: useParam("organism") ?? "",
    gene: "",
    uniprot: "",
    ligand: "",
    top: "",
    chimerax: true,
  });
  const set = <K extends keyof Form>(key: K, value: Form[K]) => setForm((f) => ({ ...f, [key]: value }));
  useRefill(reopened, run.run, (r) =>
    setForm({
      subject: text(r.subject),
      organism: text(r.organism),
      gene: text(r.gene),
      uniprot: text(r.uniprot),
      ligand: text(r.ligand),
      top: text(r.top),
      chimerax: Boolean(r.chimerax),
    }),
  );
  const err = (field: string) => fieldError(run.requestError, field);
  const ask = (next: Form) => {
    setForm(next);
    void run.submit(structureRequest(next));
  };
  const literature = caps.data?.literature;

  return (
    <Screen
      title="Structures"
      purpose="An enzyme's experimental structures in the PDB, grouped by protein, each with its method, resolution, bound molecules and citation."
    >
      <RunScreen
        kind="structure"
        id="structure"
        formLabel="Search the PDB"
        action="Search"
        canSubmit={Boolean(form.subject.trim())}
        onSubmit={() => void run.submit(structureRequest(form))}
        run={run}
        form={
          <>
            <Field
              label="Enzyme"
              error={err("subject")}
              hint={
                literature && !literature.available
                  ? "An EC number. Looking up a name needs the literature layer, which this installation does not have."
                  : "An EC number (1.1.1.27) or a name (hexokinase). A name that is several enzymes is refused with each one named."
              }
            >
              <TextInput mono autoFocus value={form.subject} placeholder="1.1.1.27" onChange={(e) => set("subject", e.target.value)} />
            </Field>
            <Field label="Organism" optional error={err("organism")} hint="Latin or common name; left out, every organism.">
              <TextInput value={form.organism} placeholder="human" onChange={(e) => set("organism", e.target.value)} />
            </Field>
            <div className="st-row2">
              <Field label="Gene" optional error={err("gene")}>
                <TextInput mono value={form.gene} placeholder="LDHA" onChange={(e) => set("gene", e.target.value)} />
              </Field>
              <Field label="UniProt" optional error={err("uniprot")}>
                <TextInput mono value={form.uniprot} placeholder="P00338" onChange={(e) => set("uniprot", e.target.value)} />
              </Field>
            </div>
            <Field
              label="Prefer entries holding"
              optional
              error={err("ligand")}
              hint="A ligand id or name; entries with it bound rank first."
            >
              <TextInput value={form.ligand} placeholder="oxamate" onChange={(e) => set("ligand", e.target.value)} />
            </Field>
            <Field
              label="Entries in the report"
              optional
              error={err("top")}
              hint="The command's default is 10. The table holds every ranked entry either way."
            >
              <NumberInput value={form.top} onChange={(e) => set("top", e.target.value)} />
            </Field>
            <Checkbox
              label="Write the ChimeraX script for the top entry"
              hint="caterva structure --chimerax, kept with the run to download."
              checked={form.chimerax}
              onChange={(v) => set("chimerax", v)}
            />
          </>
        }
        idle={
          <EmptyState title="Name an enzyme">
            <p className="st-prose">
              The search reads UniProt for the proteins with that EC number and the RCSB for their entries. When the
              number covers several proteins (lactate dehydrogenase in human is LDHA, LDHB, LDHC and more) it lists
              them and asks you to choose one, because a structure belongs to one protein.
            </p>
          </EmptyState>
        }
      >
        {(result) => (
          <StructureResultView
            result={result}
            runId={run.run?.id ?? null}
            busy={run.status === "queued" || run.status === "running"}
            onChoose={(p) => ask({ ...form, gene: p.gene ?? "", uniprot: p.gene ? "" : p.accession })}
            onCandidate={(ec) => ask({ ...form, subject: ec, gene: "", uniprot: "" })}
          />
        )}
      </RunScreen>
    </Screen>
  );
}

export function StructureResultView({
  result,
  runId,
  onChoose,
  onCandidate,
  busy = false,
}: {
  result: StructureResult;
  runId: string | null;
  onChoose?: (protein: ProteinRow) => void;
  onCandidate?: (ec: string) => void;
  busy?: boolean;
}) {
  const [open, setOpen] = useState<string | null>(result.entries[0]?.pdb_id ?? null);
  useEffect(() => setOpen(result.entries[0]?.pdb_id ?? null), [result]);
  const chosen = result.proteins.find((p) => p.chosen) ?? null;

  if (result.candidates?.length) {
    return (
      <Section title="Which enzyme did you mean?" aside={`${result.candidates.length} EC numbers`}>
        <p className="st-prose">
          UniProt's reviewed entries file <q>{result.subject_name}</q> under each of these. Search one:
        </p>
        <div className="st-candidates">
          {result.candidates.map((ec) => (
            <button key={ec} type="button" className="btn font-mono" disabled={busy} onClick={() => onCandidate?.(ec)}>
              EC {ec}
            </button>
          ))}
        </div>
      </Section>
    );
  }

  return (
    <>
      <div className="st-lede">
        <h2 className="st-lede-title">
          EC <span className="font-mono">{result.ec}</span>
          {result.organism ? (
            <>
              {" "}
              in <em>{result.organism}</em>
            </>
          ) : null}
          {chosen ? (
            <>
              : {chosen.gene ?? chosen.accession}, <span className="font-mono">{result.total}</span>{" "}
              {result.total === 1 ? "entry" : "entries"}
            </>
          ) : null}
        </h2>
        {result.subject_name ? (
          <p className="st-prose">
            <q>{result.subject_name}</q> is EC {result.ec}: the one EC number UniProt's reviewed entries give that name.
          </p>
        ) : null}
        {result.organism_note ? <p className="st-prose">{result.organism_note}</p> : null}
      </div>

      <Section title="Proteins with this EC number" aside={chosen ? "isoforms kept apart" : "choose one to see its entries"}>
        <DataTable
          caption="Proteins"
          captionHidden
          rows={result.proteins}
          rowKey={(p) => p.accession}
          selectedKey={chosen?.accession ?? null}
          columns={[
            { key: "name", header: "protein", cell: (p) => p.name },
            { key: "gene", header: "gene", cell: (p) => <span className="font-mono">{p.gene ?? ""}</span> },
            {
              key: "accession",
              header: "UniProt",
              cell: (p) =>
                p.url ? (
                  <a className="font-mono" href={p.url} target="_blank" rel="noopener noreferrer">
                    {p.accession}
                  </a>
                ) : (
                  <span className="font-mono">{p.accession}</span>
                ),
            },
            { key: "entries", header: "entries", numeric: true, cell: (p) => p.entries, sortValue: (p) => p.entries },
            {
              key: "choose",
              header: "",
              align: "end",
              cell: (p) =>
                p.chosen ? (
                  <span className="chip" data-tone="signal">
                    chosen
                  </span>
                ) : onChoose && p.entries > 0 ? (
                  <button
                    type="button"
                    className="btn btn-sm"
                    disabled={busy}
                    aria-label={`Choose ${p.gene ?? p.accession}`}
                    onClick={() => onChoose(p)}
                  >
                    Choose
                  </button>
                ) : null,
            },
            ...(new Set(result.proteins.map((p) => p.organism)).size > 1
              ? [{ key: "organism", header: "organism", cell: (p: ProteinRow) => <em>{p.organism}</em> }]
              : []),
          ]}
        />
      </Section>

      {result.entries.length ? (
        <Section
          title="Entries, best evidence first"
          aside={`ranked by ${result.ligand ? `${result.ligand} bound, then ` : ""}method, then resolution; the report lists ${Math.min(result.top ?? 10, result.entries.length)}`}
        >
          <EntriesTable rows={result.entries} ligand={result.ligand} open={open} onOpen={setOpen} />
        </Section>
      ) : null}

      {open ? <OpenEntry pdbId={open} result={result} runId={runId} /> : null}

      {result.sources?.length ? (
        <p className="st-prose">
          Read from{" "}
          {result.sources.map((s, i) => (
            <span key={s.text}>
              {i ? "; " : ""}
              <Citation citation={s} />
            </span>
          ))}
          .
        </p>
      ) : null}

      {result.report_markdown ? (
        <Disclosure title="The report the terminal prints">
          <MarkdownReport source={result.report_markdown} />
        </Disclosure>
      ) : null}
    </>
  );
}

function OpenEntry({ pdbId, result, runId }: { pdbId: string; result: StructureResult; runId: string | null }) {
  const row = result.entries.find((e) => e.pdb_id === pdbId);
  const top = result.entries[0]?.pdb_id;
  return (
    <Section
      title={`PDB ${pdbId}`}
      aside={
        <span className="st-inline">
          <Link className="btn btn-sm" href={`/prepare?entry=${encodeURIComponent(pdbId)}`}>
            Audit this entry
          </Link>
          <Link className="btn btn-sm" href={`/md?pdb=${encodeURIComponent(pdbId)}`}>
            Write an MD setup
          </Link>
          {row?.entry_url ? (
            <a className="btn btn-sm btn-quiet" href={row.entry_url} target="_blank" rel="noopener noreferrer">
              RCSB <ExternalLink size={11} aria-hidden="true" />
            </a>
          ) : null}
        </span>
      }
    >
      {row ? (
        <p className="st-lede-meta" style={{ marginBottom: "0.75rem" }}>
          <Citation citation={row.citation} detailed />
        </p>
      ) : null}
      <EntryView key={pdbId} pdbId={pdbId} />
      {result.chimerax_artifact && runId ? (
        <p className="st-inline" style={{ marginTop: "1rem" }}>
          <ArtifactButton runId={runId} name={result.chimerax_artifact} label="Download the ChimeraX script" />
          <span className="st-prose">
            {pdbId === top ? "for this entry, the top one" : `for the top entry, ${top}`}; open it with{" "}
            <code className="font-mono">chimerax {result.chimerax_artifact}</code>
          </span>
        </p>
      ) : null}
    </Section>
  );
}

const ROLE_ORDER = ["ligand", "cofactor", "metal", "additive"];

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
  const columns = useMemo(
    () => [
      {
        key: "pdb",
        header: "entry",
        cell: (s: StructureRow) => (
          <span className="font-mono" aria-label={`PDB ${s.pdb_id}`}>
            {s.pdb_id}
          </span>
        ),
      },
      {
        key: "title",
        header: "title",
        cell: (s: StructureRow) => <span className="st-what">{sentenceCase(s.title)}</span>,
      },
      { key: "method", header: "method", cell: (s: StructureRow) => <span className="muted">{s.method.toLowerCase()}</span> },
      {
        key: "resolution",
        header: "resolution",
        headerText: "resolution",
        numeric: true,
        sortValue: (s: StructureRow) => s.resolution?.value ?? null,
        cell: (s: StructureRow) =>
          s.resolution ? (
            <Own>
              <Value v={s.resolution} />
            </Own>
          ) : (
            <span className="muted">none given</span>
          ),
      },
      {
        key: "bound",
        header: "bound",
        cell: (s: StructureRow) =>
          s.bound.length ? (
            <span className="st-inline">
              {[...s.bound]
                .sort((a, b) => ROLE_ORDER.indexOf(a.role) - ROLE_ORDER.indexOf(b.role))
                .map((b) => (
                  <span
                    key={`${b.component}-${b.role}`}
                    className="chip chip-mono"
                    data-tone={b.role === "additive" ? undefined : b.role === "ligand" ? "signal" : undefined}
                    title={`${b.name}, ${b.role}`}
                  >
                    {b.component}
                    <span className="muted">{b.role}</span>
                  </span>
                ))}
            </span>
          ) : (
            <span className="muted">nothing</span>
          ),
      },
      ...(ligand
        ? [
            {
              key: "holds",
              header: `holds ${ligand}`,
              cell: (s: StructureRow) => (s.binds_ligand ? "yes" : "no"),
            },
          ]
        : []),
      {
        key: "citation",
        header: "primary citation",
        cell: (s: StructureRow) => (
          <Own>
            <Citation citation={s.citation} />
          </Own>
        ),
      },
    ],
    [ligand],
  );
  return (
    <DataTable
      caption="PDB entries: Enter or a click opens one in 3D"
      captionHidden
      rows={rows}
      rowKey={(s) => s.pdb_id}
      columns={columns}
      selectedKey={open}
      onRowSelect={(s) => onOpen(s.pdb_id)}
      maxHeight="26rem"
    />
  );
}
