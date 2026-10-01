/**
 * /prepare: what is wrong with a PDB entry before it is simulated, each
 * defect placed against the catalytic residues (kind `prepare`,
 * `caterva prepare ENTRY`).
 *
 * Exit 4 ("every chain has at least one blocking defect") is a finding,
 * not a failure: the screen leads with the blocking findings and says which
 * chains a faithful setup cannot start from. Findings are listed in the
 * report's order: by severity (blocks, decide, note), then nearest the
 * active site first, findings with no distance last.
 */
import { type FormEvent, useMemo, useState } from "react";
import { Link } from "wouter";

import type { FindingRow, PrepareRequest, PrepareResult } from "@/api/types";
import { useRun } from "@/api/useRun";
import { Value } from "@/components/provenance/Value";
import { Screen } from "@/components/screen/Screen";
import { EmptyState } from "@/components/states/States";

import { EntryView } from "./structure/EntryView";
import {
  CheckField,
  CommandLine,
  NumberField,
  Part,
  PathField,
  PrimaryButton,
  RunArea,
  Table,
  TerminalReport,
  Verdict,
  fieldError,
  parsed,
  td,
} from "./structure/kit";
import { useParam } from "./structure/useCoordinates";
import type { CatalyticRowView, ChargeRowView } from "./structure/views";
import "./structure/structure.css";

const FIELDS = ["entry", "ph", "no_cache"];
const PDB_ID = /^[0-9][A-Za-z0-9]{3}$/;
const SEVERITY_TITLE: Record<string, string> = {
  blocks: "Blocks a faithful setup",
  decide: "Choices to make and record",
  note: "Worth knowing",
};

export default function PrepareScreen() {
  const run = useRun("prepare", useParam("run"));
  const [entry, setEntry] = useState(useParam("entry") ?? "");
  const [ph, setPh] = useState("");
  const [noCache, setNoCache] = useState(false);
  const err = run.requestError;
  const busy = run.status === "queued" || run.status === "running";

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const r: PrepareRequest = { entry: entry.trim() };
    const p = parsed(ph);
    if (p !== undefined) r.ph = p;
    if (noCache) r.no_cache = true;
    void run.submit(r);
  };

  return (
    <Screen title="Prepare" purpose="Audit a PDB entry before simulating it, defects ranked by distance to the active site.">
      <div className="grid gap-8 xl:grid-cols-[18rem_minmax(0,1fr)]">
        <form onSubmit={submit} className="grid content-start gap-4" aria-label="Audit an entry">
          <PathField
            id="prepare-entry"
            label="PDB id or mmCIF file"
            value={entry}
            onChange={setEntry}
            kind="file"
            purpose="Choose an mmCIF file to audit"
            extensions={["cif", "mmcif"]}
            placeholder="1I10, or /path/to/entry.cif"
            hint="A local file must be an absolute path to a .cif or .mmcif file."
            error={fieldError(err, "entry")}
          />
          <NumberField
            id="prepare-ph"
            label="Assay pH"
            value={ph}
            onChange={setPh}
            placeholder="not given"
            hint="Given, the audit judges each titratable residue near the active site at this pH."
            error={fieldError(err, "ph")}
          />
          <CheckField id="prepare-no-cache" label="Fetch everything fresh" checked={noCache} onChange={setNoCache} />
          <div>
            <PrimaryButton busy={busy} disabled={!entry.trim()}>
              Audit
            </PrimaryButton>
          </div>
        </form>

        <div className="grid min-w-0 content-start gap-8">
          {run.status === "idle" && !err ? (
            <EmptyState title="Audit an entry before you simulate it">
              <p className="m-0 max-w-[60ch] text-muted">
                Sequence differences from UniProt, chain breaks, truncated side chains, alternate conformations,
                non-standard residues and the biological assembly, each placed by its distance to the catalytic
                residues M-CSA records for the enzyme. Find an entry on the Structures screen.
              </p>
            </EmptyState>
          ) : null}
          <RunArea view={run} waiting="Reading the entry" hasResult={run.result !== null} fieldErrors={FIELDS}>
            {run.result ? <PrepareResultView result={run.result} entry={String(run.run?.request.entry ?? "")} /> : null}
          </RunArea>
          <CommandLine run={run.run} />
        </div>
      </div>
    </Screen>
  );
}

function rankFindings(findings: FindingRow[]): FindingRow[] {
  const order = ["blocks", "decide", "note"];
  return [...findings].sort(
    (a, b) =>
      order.indexOf(a.severity) - order.indexOf(b.severity) ||
      (a.distance?.value ?? Infinity) - (b.distance?.value ?? Infinity) ||
      (a.chain ?? "").localeCompare(b.chain ?? ""),
  );
}

export function PrepareResultView({ result, entry }: { result: PrepareResult; entry: string }) {
  const [chain, setChain] = useState<string>("all");
  const findings = useMemo(
    () => rankFindings(result.findings).filter((f) => chain === "all" || f.chain === null || f.chain === chain),
    [result, chain],
  );
  const clean = result.clean_chains ?? [];
  const catalytic = result.catalytic as unknown as CatalyticRowView[];
  const protonation = result.protonation as unknown as ChargeRowView[] | null;
  const isPdbId = PDB_ID.test(entry.trim());

  return (
    <div className="grid gap-8">
      <div className="grid gap-2">
        <p className="m-0 font-display text-[1.35rem] leading-snug">
          {clean.length ? (
            <>
              <span className="font-mono text-[1.15rem]">{result.pdb_id}</span>: a setup can start from chain
              {clean.length > 1 ? "s" : ""} <span className="font-mono">{clean.join(", ")}</span>
            </>
          ) : (
            <>
              <span className="font-mono text-[1.15rem]">{result.pdb_id}</span>: every chain has at least one blocking
              defect
            </>
          )}
        </p>
        <p className="m-0 flex flex-wrap items-baseline gap-x-3 gap-y-1 text-[13px] text-muted">
          <span>{result.method.toLowerCase()}</span>
          {result.resolution ? (
            <span className="text-fg">
              <Value v={result.resolution} />
            </span>
          ) : null}
          {result.r_free ? (
            <span>
              R-free{" "}
              <span className="text-fg">
                <Value v={result.r_free} />
              </span>
            </span>
          ) : null}
          {result.entry_citation ? (
            <span>
              {result.entry_citation.url ? (
                <a href={result.entry_citation.url} target="_blank" rel="noreferrer noopener">
                  {result.entry_citation.text}
                </a>
              ) : (
                result.entry_citation.text
              )}
            </span>
          ) : null}
        </p>
        {clean.length && isPdbId ? (
          <p className="m-0 flex flex-wrap gap-2">
            {clean.map((c) => (
              <Link
                key={c}
                className="btn-quiet no-underline"
                href={`/md?pdb=${encodeURIComponent(result.pdb_id)}&chain=${encodeURIComponent(c)}`}
              >
                Write an MD setup for chain {c}
              </Link>
            ))}
          </p>
        ) : null}
      </div>

      <Part title="Chains" aside={result.active_site_radius ? <>near the site: within <Value v={result.active_site_radius} /></> : null}>
        <Table head={["chain", "blocking findings", "findings near the site", "catalytic residues intact"]} caption="Chains">
          {result.chain_summary.map((s) => (
            <tr key={s.chain}>
              <td className={`${td} font-mono`}>{s.chain}</td>
              <td className={`${td} font-mono tabular-nums`}>{s.blocks}</td>
              <td className={`${td} font-mono tabular-nums`}>{s.near_site}</td>
              <td className={td}>{s.catalytic_intact ? "yes" : <Verdict word="no" />}</td>
            </tr>
          ))}
        </Table>
      </Part>

      <Part
        title={`Findings (${result.findings.length})`}
        aside={
          result.chains.length > 1 ? (
            <label className="inline-flex items-center gap-2">
              Chain
              <select
                className="rounded-[3px] border border-rule bg-surface px-1.5 py-0.5 font-mono text-[12.5px] text-fg"
                value={chain}
                onChange={(e) => setChain(e.target.value)}
              >
                <option value="all">all</option>
                {result.chains.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </label>
          ) : null
        }
      >
        {(["blocks", "decide", "note"] as const).map((sev) => {
          const rows = findings.filter((f) => f.severity === sev);
          if (!rows.length) return null;
          return (
            <div key={sev} className="grid gap-2">
              <h3 className="m-0 font-sans text-[13.5px] font-semibold">
                {SEVERITY_TITLE[sev]} <span className="font-mono text-muted tabular-nums">({rows.length})</span>
              </h3>
              <Table head={["chain", "where", "to the active site", "finding", "from"]} caption={SEVERITY_TITLE[sev]}>
                {rows.map((f, i) => (
                  <tr key={`${f.chain}-${f.residues.join(",")}-${f.check ?? ""}-${i}`}>
                    <td className={`${td} font-mono`}>{f.chain ?? ""}</td>
                    <td className={`${td} font-mono text-[12.5px]`}>{f.residues.join(", ")}</td>
                    <td className={`${td} whitespace-nowrap`}>
                      {f.distance ? <Value v={f.distance} /> : <span className="text-muted">no distance</span>}
                      {f.catalytic ? <span className="ml-1.5"><Verdict word="catalytic residue" /></span> : null}
                    </td>
                    <td className={`${td} max-w-[44rem] text-[13px]`}>
                      {f.check ? <span className="font-semibold">{f.check}: </span> : null}
                      {f.what}
                    </td>
                    <td className={`${td} font-mono text-[12px] text-muted`}>{f.source}</td>
                  </tr>
                ))}
              </Table>
            </div>
          );
        })}
      </Part>

      <Part title="Catalytic residues" aside="M-CSA's reference residues, carried onto each chain by global alignment">
        {catalytic.length ? (
          <Table head={["chain", "residue", "reference", "role", "conserved"]} caption="Catalytic residues">
            {catalytic.map((c) => (
              <tr key={`${c.chain}-${c.resseq}-${c.reference}`}>
                <td className={`${td} font-mono`}>{c.chain}</td>
                <td className={`${td} font-mono`}>
                  {(c.found ?? "-").charAt(0)}
                  {(c.found ?? "").slice(1).toLowerCase()}
                  {c.resseq}
                </td>
                <td className={`${td} font-mono text-[12.5px]`}>{c.reference}</td>
                <td className={`${td} text-[13px]`}>{c.roles}</td>
                <td className={td}>{c.conserved ? "yes" : <Verdict word={`no, ${c.expected} expected`} />}</td>
              </tr>
            ))}
          </Table>
        ) : (
          <p className="m-0 text-[13.5px] text-muted">
            {result.not_checked.find((n) => n.startsWith("catalytic residues")) ?? "None placed."}
          </p>
        )}
      </Part>

      {protonation ? (
        <Part
          title="Protonation at the active site"
          aside={result.ph ? <>judged at <Value v={result.ph} /></> : null}
        >
          {protonation.length ? (
            <Table
              head={["residue", "to the active site", "typical pKa", "fraction protonated", "at this pH", "state"]}
              caption="Protonation"
            >
              {protonation.map((p) => (
                <tr key={`${p.chain}-${p.resseq}`}>
                  <td className={`${td} font-mono`}>{p.residue}</td>
                  <td className={td}>
                    <Value v={p.distance} />
                  </td>
                  <td className={`${td} whitespace-nowrap`}>
                    {p.pka ? (
                      <>
                        <Value v={p.pka} />
                        {p.pka_sd ? (
                          <span className="text-muted">
                            {" "}
                            ± <Value v={p.pka_sd} />
                          </span>
                        ) : null}
                      </>
                    ) : (
                      <span className="text-muted">not in the survey</span>
                    )}
                  </td>
                  <td className={`${td} whitespace-nowrap`}>{p.protonated ? <Value v={p.protonated} /> : null}</td>
                  <td className={`${td} text-[13px]`}>{p.at_ph}</td>
                  <td className={td}>{p.emphasised ? <Verdict word={p.state} /> : <span className="text-[13px]">{p.state}</span>}</td>
                </tr>
              ))}
            </Table>
          ) : (
            <p className="m-0 text-[13.5px] text-muted">No titratable residue within the active-site radius.</p>
          )}
        </Part>
      ) : null}

      <Part title="Not checked">
        <ul className="m-0 grid gap-1 pl-5 text-[13.5px]">
          {result.not_checked.map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      </Part>

      {isPdbId ? (
        <Part title={`PDB ${result.pdb_id} in 3D`}>
          <EntryView pdbId={result.pdb_id} />
        </Part>
      ) : null}

      <TerminalReport text={result.report_markdown} markdown />
    </div>
  );
}
