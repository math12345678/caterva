/**
 * /prepare: what is wrong with a PDB entry before it is simulated, each
 * defect placed against the catalytic residues (kind `prepare`,
 * `caterva prepare ENTRY`).
 *
 * The findings are ranked as the report ranks them: what blocks a faithful
 * setup first, then the choices to make and record, then what is worth
 * knowing; within each, nearest the active site first, by the distance the
 * audit measured, and those with no distance last. Choosing a finding
 * (click, or Enter on its row) shows it in the viewer beside the table,
 * with what else the audit knows about its residues.
 *
 * Exit 4 ("every chain has at least one blocking defect") is a finding,
 * not a failure: the run's outcome says so above the result, and the
 * blocking findings lead.
 */
import { useId, useMemo, useState } from "react";
import { Link } from "wouter";

import type { FindingRow, PrepareRequest, PrepareResult } from "@/api/types";
import { useRun } from "@/api/useRun";
import { useRunAddress } from "@/lib/runAddress";
import { Checkbox, Field, fieldError, NumberInput, parseNumber, Select } from "@/components/forms/Field";
import { Disclosure } from "@/components/forms/Disclosure";
import { Citation } from "@/components/provenance/Citation";
import { Value } from "@/components/provenance/Value";
import { MarkdownReport } from "@/components/report/Report";
import { Screen, Section } from "@/components/screen/Screen";
import { EmptyState } from "@/components/states/States";
import { DataTable } from "@/components/table/DataTable";

import { type EntryFocus, EntryView } from "./structure/EntryView";
import { Own, PathField, residueName, RunScreen, text, useParam, useRefill, Verdict } from "./structure/kit";
import { findingFocus, rankFindings } from "./structure/residues";
import type { CatalyticRowView, ChargeRowView } from "./structure/views";
import "./structure/structure.css";

const PDB_ID = /^[0-9][A-Za-z0-9]{3}$/;
const SEVERITY_TITLE: Record<string, string> = {
  blocks: "Blocks a faithful setup",
  decide: "Choices to make and record",
  note: "Worth knowing",
};

export default function PrepareScreen() {
  const reopened = useParam("run");
  const run = useRun("prepare", reopened);
  useRunAddress("/prepare", run.run, reopened);
  const [entry, setEntry] = useState(useParam("entry") ?? "");
  const [ph, setPh] = useState("");
  const [noCache, setNoCache] = useState(false);
  useRefill(reopened, run.run, (r) => {
    setEntry(text(r.entry));
    setPh(text(r.ph));
    setNoCache(Boolean(r.no_cache));
  });
  const err = (field: string) => fieldError(run.requestError, field);

  const request = (): PrepareRequest => {
    const r: PrepareRequest = { entry: entry.trim() };
    if (ph.trim()) r.ph = (parseNumber(ph) ?? ph.trim()) as number;
    if (noCache) r.no_cache = true;
    return r;
  };

  return (
    <Screen title="Prepare" purpose="Audit a PDB entry before simulating it, every defect ranked by its distance to the active site.">
      <RunScreen
        kind="prepare"
        id="prepare"
        formLabel="Audit an entry"
        action="Audit"
        canSubmit={Boolean(entry.trim())}
        onSubmit={() => void run.submit(request())}
        run={run}
        firstSize={26}
        form={
          <>
            <PathField
              label="PDB id or mmCIF file"
              value={entry}
              onChange={setEntry}
              kind="file"
              purpose="Choose an mmCIF file to audit"
              extensions={["cif", "mmcif"]}
              hint="A PDB id, as 1I10, or the absolute path to a local .cif or .mmcif file."
              error={err("entry")}
            />
            <Field
              label="Assay pH"
              optional
              error={err("ph")}
              hint="Given, each titratable residue near the active site is judged at this pH."
            >
              <NumberInput value={ph} onChange={(e) => setPh(e.target.value)} />
            </Field>
            <Checkbox
              label="Fetch everything fresh"
              hint="caterva prepare --no-cache: ignore the copies kept from earlier audits."
              checked={noCache}
              onChange={setNoCache}
            />
          </>
        }
        idle={
          <EmptyState title="Audit an entry before you simulate it">
            <p className="st-prose">
              Sequence differences from UniProt, chain breaks, truncated side chains, alternate conformations,
              non-standard residues and the biological assembly, each placed by its distance to the catalytic residues
              M-CSA records for the enzyme. Find an entry on the <Link href="/structure">Structures</Link> screen.
            </p>
          </EmptyState>
        }
      >
        {(result) => <PrepareResultView result={result} entry={String(run.run?.request.entry ?? entry)} />}
      </RunScreen>
    </Screen>
  );
}

function findingKey(f: FindingRow, i: number): string {
  return `${f.severity}|${f.chain ?? ""}|${f.residues.join(",")}|${f.check ?? ""}|${i}`;
}

export function PrepareResultView({ result, entry }: { result: PrepareResult; entry: string }) {
  const [chain, setChain] = useState<string>("all");
  const ranked = useMemo(() => rankFindings(result.findings).map((f, i) => ({ f, key: findingKey(f, i) })), [result]);
  const shown = useMemo(
    () => ranked.filter(({ f }) => chain === "all" || f.chain === null || f.chain === chain),
    [ranked, chain],
  );
  const [picked, setPicked] = useState<string | null>(null);
  const viewerId = useId();
  const pick = (key: string) => {
    const next = key === picked ? null : key;
    setPicked(next);
    if (next) {
      const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
      document.getElementById(viewerId)?.scrollIntoView({ block: "nearest", behavior: reduced ? "auto" : "smooth" });
    }
  };
  const pickedRow = ranked.find((r) => r.key === picked)?.f ?? null;
  const focus = useMemo<EntryFocus | null>(() => {
    if (!pickedRow) return null;
    const { refs, flanking } = findingFocus(pickedRow);
    return { refs, flanking, what: `${pickedRow.check ? `${pickedRow.check}: ` : ""}${pickedRow.what}` };
  }, [pickedRow]);
  const clean = result.clean_chains ?? [];
  const catalytic = result.catalytic as unknown as CatalyticRowView[];
  const charges = (result.protonation ?? []) as unknown as ChargeRowView[];
  const isPdbId = PDB_ID.test(entry.trim());

  return (
    <>
      <div className="st-lede">
        <h2 className="st-lede-title">
          <span className="font-mono">{result.pdb_id}</span>
          {clean.length ? (
            <>
              : a setup can start from chain{clean.length > 1 ? "s" : ""} <span className="font-mono">{clean.join(", ")}</span>
            </>
          ) : (
            <>: every chain has at least one blocking defect</>
          )}
        </h2>
        <p className="st-lede-meta">
          <span>{result.method.toLowerCase()}</span>
          {result.resolution ? <Value v={result.resolution} /> : null}
          {result.r_free ? (
            <span className="st-inline">
              R-free <Value v={result.r_free} />
            </span>
          ) : null}
          {result.entry_citation ? <Citation citation={result.entry_citation} /> : null}
        </p>
        {clean.length && isPdbId ? (
          <p className="st-inline">
            {clean.map((c) => (
              <Link key={c} className="btn btn-sm" href={`/md?pdb=${encodeURIComponent(result.pdb_id)}&chain=${encodeURIComponent(c)}`}>
                Write an MD setup for chain {c}
              </Link>
            ))}
          </p>
        ) : null}
      </div>

      <Section
        title="Chains"
        aside={
          result.active_site_radius ? (
            <span className="st-inline">
              near the site: within <Value v={result.active_site_radius} />
            </span>
          ) : null
        }
      >
        <DataTable
          caption="Chains"
          captionHidden
          rows={result.chain_summary}
          rowKey={(s) => s.chain}
          columns={[
            { key: "chain", header: "chain", cell: (s) => <span className="font-mono">{s.chain}</span> },
            { key: "blocks", header: "blocking findings", numeric: true, cell: (s) => s.blocks, sortValue: (s) => s.blocks },
            { key: "near", header: "findings near the site", numeric: true, cell: (s) => s.near_site, sortValue: (s) => s.near_site },
            {
              key: "intact",
              header: "catalytic residues intact",
              cell: (s) => (s.catalytic_intact ? "yes" : <Verdict word="no" />),
            },
            {
              key: "clean",
              header: "a setup can start here",
              cell: (s) => (clean.includes(s.chain) ? <span className="chip" data-tone="signal">yes</span> : "no"),
            },
          ]}
        />
      </Section>

      <Section
        title={`Findings, nearest the active site first (${result.findings.length})`}
        aside={
          result.chains.length > 1 ? (
            <label className="st-inline">
              chain
              <Select value={chain} onChange={(e) => setChain(e.target.value)} aria-label="Show the findings of chain">
                <option value="all">all</option>
                {result.chains.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </Select>
            </label>
          ) : null
        }
      >
        <div className="st-findings">
          {(["blocks", "decide", "note"] as const).map((sev) => {
            const rows = shown.filter(({ f }) => f.severity === sev);
            if (!rows.length) return null;
            return (
              <div key={sev}>
                <h3 className="st-group-title">
                  {SEVERITY_TITLE[sev]} <span className="font-mono muted">{rows.length}</span>
                </h3>
                <DataTable
                  caption={SEVERITY_TITLE[sev]}
                  captionHidden
                  rows={rows}
                  rowKey={(r) => r.key}
                  selectedKey={picked}
                  onRowSelect={(r) => pick(r.key)}
                  maxHeight="22rem"
                  columns={[
                    {
                      key: "distance",
                      header: "to the active site",
                      headerText: "distance to the active site",
                      width: "9rem",
                      sortValue: (r) => r.f.distance?.value ?? null,
                      cell: ({ f }) =>
                        f.distance ? (
                          <Own>
                            <Value v={f.distance} />
                          </Own>
                        ) : (
                          <span className="muted">no distance</span>
                        ),
                    },
                    { key: "chain", header: "chain", cell: ({ f }) => <span className="font-mono">{f.chain ?? ""}</span> },
                    {
                      key: "where",
                      header: "where",
                      cell: ({ f }) => (
                        <span className="font-mono">
                          {f.residues.join(", ")}
                          {f.catalytic ? (
                            <>
                              {" "}
                              <Verdict word="catalytic residue" />
                            </>
                          ) : null}
                        </span>
                      ),
                    },
                    {
                      key: "what",
                      header: "finding",
                      cell: ({ f }) => (
                        <span className="st-what">
                          {f.check ? <b>{f.check}: </b> : null}
                          {f.what}
                        </span>
                      ),
                    },
                    { key: "source", header: "from", cell: ({ f }) => <span className="font-mono muted">{f.source}</span> },
                  ]}
                />
              </div>
            );
          })}
        </div>
      </Section>

      {isPdbId ? (
        <Section
          id={viewerId}
          title={`PDB ${result.pdb_id} in 3D`}
          aside={pickedRow ? "showing the chosen finding" : "choose a finding above to see it here"}
        >
          <EntryView pdbId={result.pdb_id} focus={focus} findings={result.findings} charges={charges} />
        </Section>
      ) : (
        <p className="st-prose">A local file is audited from disk; the 3D view draws entries the PDB serves.</p>
      )}

      <Section title="Catalytic residues" aside="M-CSA's reference residues, carried onto each chain by global alignment">
        {catalytic.length ? (
          <DataTable
            caption="Catalytic residues"
            captionHidden
            rows={catalytic}
            rowKey={(c) => `${c.chain}-${c.resseq}-${c.reference}`}
            columns={[
              { key: "chain", header: "chain", cell: (c) => <span className="font-mono">{c.chain}</span> },
              { key: "residue", header: "residue", cell: (c) => <span className="font-mono">{residueName(c.found ?? "-", c.resseq)}</span> },
              { key: "reference", header: "carried from", cell: (c) => <span className="font-mono">{c.reference}</span> },
              { key: "roles", header: "role", cell: (c) => c.roles },
              {
                key: "conserved",
                header: "conserved",
                cell: (c) => (c.conserved ? "yes" : <Verdict word={`no, ${c.expected} expected`} />),
              },
            ]}
          />
        ) : (
          <p className="st-prose">{result.not_checked.find((n) => n.startsWith("catalytic residues")) ?? "None placed."}</p>
        )}
      </Section>

      {result.protonation ? (
        <Section
          title="Protonation at the active site"
          aside={
            result.ph ? (
              <span className="st-inline">
                judged at <Value v={result.ph} />
              </span>
            ) : null
          }
        >
          <DataTable
            caption="Protonation"
            captionHidden
            rows={charges}
            rowKey={(p) => `${p.chain}-${p.resseq}`}
            empty="No titratable residue within the active-site radius."
            columns={[
              { key: "residue", header: "residue", cell: (p) => <span className="font-mono">{p.residue}</span> },
              {
                key: "distance",
                header: "to the active site",
                numeric: true,
                sortValue: (p) => p.distance.value,
                cell: (p) => <Value v={p.distance} />,
              },
              {
                key: "pka",
                header: "typical pKa",
                numeric: true,
                cell: (p) =>
                  p.pka ? (
                    <span className="st-inline">
                      <Value v={p.pka} />
                      {p.pka_sd ? (
                        <span className="muted st-inline">
                          ± <Value v={p.pka_sd} showUnit={false} />
                        </span>
                      ) : null}
                    </span>
                  ) : (
                    <span className="muted">not in the survey</span>
                  ),
              },
              {
                key: "protonated",
                header: "fraction protonated",
                numeric: true,
                cell: (p) => (p.protonated ? <Value v={p.protonated} /> : null),
              },
              { key: "at_ph", header: "at this pH", cell: (p) => p.at_ph },
              { key: "state", header: "state", cell: (p) => (p.emphasised ? <Verdict word={p.state} /> : p.state) },
            ]}
          />
        </Section>
      ) : null}

      <Section title="Not checked">
        <ul className="st-prose" style={{ paddingLeft: "1.1rem", display: "grid", gap: "0.25rem" }}>
          {result.not_checked.map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      </Section>

      <Disclosure title="The report the terminal prints">
        <MarkdownReport source={result.report_markdown} />
      </Disclosure>
    </>
  );
}
