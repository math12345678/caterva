/**
 * One PDB entry in 3D, and what the tools know about the residue chosen in
 * it. Used by Structures (an entry chosen from the search) and Prepare (the
 * audited entry, a finding chosen in its table).
 *
 * The viewer is the foundation's (src/components/molecule): the entry's
 * atoms from GET /api/structure/{id}/coordinates, its alpha-carbon trace,
 * and the side chains of the residues highlighted here, which are the
 * catalytic residues `caterva prepare` places (M-CSA's, carried over by
 * alignment) and, on Prepare, the residues of the finding being looked at.
 * The page picks no "active site" of its own.
 *
 * Choosing a residue (a click in the viewer, ] and [ on the focused
 * canvas, or a button in the list beside it) shows what the server said
 * about it: its catalytic role and the reference residue it was carried
 * from, every audit finding at it, and on Prepare its protonation at the
 * assay pH, each number with its provenance.
 */
import { useEffect, useMemo, useState } from "react";

import { ApiRequestError } from "@/api/client";
import type { CoordinatesResponse, FindingRow } from "@/api/types";
import { MoleculeViewer } from "@/components/molecule/MoleculeViewer";
import { type Residue, type ResidueRef, residueLabel } from "@/components/molecule/model";
import { Citation } from "@/components/provenance/Citation";
import { Value } from "@/components/provenance/Value";
import { Loading } from "@/components/states/Loading";
import { ErrorState } from "@/components/states/States";

import { residueName, sentenceCase, Verdict } from "./kit";
import { knownAbout, refKey, siteRef } from "./residues";
import { useCoordinates } from "./useCoordinates";
import type { ChargeRowView } from "./views";

export interface EntryFocus {
  refs: ResidueRef[];
  /** The refs are the residues either side of an unmodelled stretch, not the stretch itself. */
  flanking: boolean;
  /** What the focus is, in words, for the panel ("Cys54->Thr at residue 54"). */
  what: string;
}

export function EntryView({
  pdbId,
  focus = null,
  findings,
  charges,
}: {
  pdbId: string;
  focus?: EntryFocus | null;
  /** The audit's findings to show per residue; the coordinates' own (no pH) when not given. */
  findings?: readonly FindingRow[];
  charges?: readonly ChargeRowView[];
}) {
  const coords = useCoordinates(pdbId);
  if (coords.isPending) {
    return (
      <div className="st-entry-loading">
        <Loading label={`Reading PDB ${pdbId}: its atoms, fetched and cached as caterva prepare fetches them, and the audit's catalytic residues`} />
      </div>
    );
  }
  if (coords.isError) {
    const error = coords.error instanceof ApiRequestError ? coords.error.error : coords.error;
    return <ErrorState error={error} title={`PDB ${pdbId} could not be drawn`} inset />;
  }
  return <Entry coords={coords.data} focus={focus} findings={findings ?? coords.data.findings ?? []} charges={charges ?? []} />;
}

export function Entry({
  coords,
  focus = null,
  findings,
  charges = [],
  height = 440,
}: {
  coords: CoordinatesResponse;
  focus?: EntryFocus | null;
  findings: readonly FindingRow[];
  charges?: readonly ChargeRowView[];
  height?: number;
}) {
  const catalytic = useMemo(() => coords.catalytic ?? [], [coords]);
  const present = useMemo(() => {
    const keys = new Set<string>();
    for (let i = 0; i < coords.atoms.x.length; i++) {
      if (!coords.atoms.hetero[i]) keys.add(`${coords.atoms.chain[i]}:${coords.atoms.resseq[i]}`);
    }
    return keys;
  }, [coords]);
  const focusRefs = useMemo(() => (focus?.refs ?? []).filter((r) => present.has(refKey(r))), [focus, present]);
  const highlight = useMemo(() => {
    const seen = new Map<string, ResidueRef>();
    for (const c of catalytic) seen.set(refKey(siteRef(c)), siteRef(c));
    for (const r of focusRefs) seen.set(refKey(r), r);
    return [...seen.values()];
  }, [catalytic, focusRefs]);

  const [selected, setSelected] = useState<Residue | ResidueRef | null>(null);
  useEffect(() => setSelected(focusRefs[0] ?? null), [focusRefs]);

  const resname = (r: ResidueRef): string | null => {
    if ("resname" in r) return (r as Residue).resname;
    const i = coords.atoms.chain.findIndex((c, k) => c === r.chain && coords.atoms.resseq[k] === r.resseq && !coords.atoms.hetero[k]);
    return i === -1 ? null : coords.atoms.resname[i];
  };

  return (
    <div className="st-entry">
      <div className="st-side" style={{ gap: "0.625rem" }}>
        <MoleculeViewer coordinates={coords} highlight={highlight} selected={selected} onSelect={setSelected} height={height} />
        <p className="st-lede-meta">
          {coords.title ? <span>{sentenceCase(coords.title)}</span> : null}
          {coords.method ? <span>{coords.method.toLowerCase()}</span> : null}
          {coords.resolution ? <Value v={coords.resolution} /> : null}
        </p>
        {coords.catalytic_reference ? <ReferenceLine coords={coords} /> : null}
        {coords.truncated && coords.omitted ? <p className="st-prose">Left out of the view: {coords.omitted}.</p> : null}
      </div>
      <div className="st-side">
        {focus ? (
          <section className="st-known" aria-label="The finding being looked at">
            <p className="st-prose" style={{ color: "var(--fg)" }}>{focus.what}</p>
            {focus.flanking ? (
              <p className="st-prose">
                These residues are not in the model, so the view shows the residues either side of the gap
                {focusRefs.length ? `: ${focusRefs.map((r) => residueName(resname(r), r.resseq)).join(" and ")}` : ", and neither is in the file either"}.
              </p>
            ) : focus.refs.length && !focusRefs.length ? (
              <p className="st-prose">None of its residues has atoms in this file.</p>
            ) : null}
          </section>
        ) : null}
        <div className="st-side" style={{ gap: "0.375rem" }}>
          <h3 className="st-side-title">Catalytic residues, as caterva prepare places them</h3>
          {catalytic.length ? (
            <ul className="st-residues">
              {catalytic.map((c) => {
                const ref = siteRef(c);
                const on = selected !== null && refKey(selected) === refKey(ref);
                return (
                  <li key={refKey(ref)}>
                    <button
                      type="button"
                      className="st-residue"
                      aria-pressed={on}
                      onClick={() => setSelected(on ? null : ref)}
                      disabled={!present.has(refKey(ref))}
                    >
                      <span className="st-residue-name">
                        {c.chain} {residueName(c.resname, c.resseq)}
                      </span>
                      <span className="st-residue-what" title={c.roles}>
                        {c.roles}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          ) : (
            <p className="st-prose">{coords.catalytic_reason ?? "The audit placed none on this entry."}</p>
          )}
        </div>
        {selected ? (
          <KnownPanel
            residue={selected}
            resname={resname(selected)}
            known={knownAbout(selected, { catalytic, findings, charges })}
            onClear={() => setSelected(null)}
          />
        ) : (
          <p className="st-prose">
            Choose a residue in the view or the list to see what the tools found at it. With the view focused,{" "}
            <kbd className="kbd">]</kbd> and <kbd className="kbd">[</kbd> step through the highlighted residues.
          </p>
        )}
      </div>
    </div>
  );
}

function ReferenceLine({ coords }: { coords: CoordinatesResponse }) {
  const ref = coords.catalytic_reference!;
  return (
    <p className="st-prose">
      Catalytic residues from M-CSA entry <span className="font-mono">{ref.mcsa_id}</span> ({ref.enzyme}, reference{" "}
      <span className="font-mono">{ref.uniprot}</span>), chosen by {ref.how}; sequence identity to chain{" "}
      {coords.chains?.[0] ?? "?"} <Value v={ref.identity} />, carried onto each chain by global alignment.{" "}
      <Citation citation={ref.citation} />
      {ref.rejected.length ? <> Not used: {ref.rejected.join("; ")}.</> : null}
    </p>
  );
}

function KnownPanel({
  residue,
  resname,
  known,
  onClear,
}: {
  residue: ResidueRef | Residue;
  resname: string | null;
  known: ReturnType<typeof knownAbout>;
  onClear: () => void;
}) {
  const hetero = "hetero" in residue && (residue as Residue).hetero;
  const { catalytic, findings, charge } = known;
  const nothing = !catalytic && !findings.length && !charge;
  return (
    <section className="st-known" aria-label="What the tools know about this residue">
      <div className="st-known-head">
        <h3 className="st-known-name">
          {"resname" in residue ? residueLabel(residue as Residue) : `${residueName(resname, residue.resseq)} (chain ${residue.chain})`}
        </h3>
        <button type="button" className="btn btn-sm btn-quiet" onClick={onClear}>
          Clear
        </button>
      </div>
      {hetero ? <p className="st-prose">A bound molecule, ion or cofactor, as the entry names it. The audit judges residues of the chains only.</p> : null}
      {catalytic ? (
        <div className="grid gap-1">
          <p className="st-prose" style={{ color: "var(--fg)" }}>
            Catalytic: {catalytic.roles}
          </p>
          <p className="st-prose">
            Carried from {catalytic.reference}
            {catalytic.conserved ? "; the same residue type here." : null}
          </p>
          {!catalytic.conserved ? <Verdict word={`not conserved: ${catalytic.expected} expected`} /> : null}
        </div>
      ) : null}
      {findings.length ? (
        <ul aria-label="Audit findings at this residue">
          {findings.map((f, i) => (
            <li key={i}>
              <Verdict word={f.severity === "blocks" ? "blocks a faithful setup" : f.severity === "decide" ? "a choice to make" : "worth knowing"} />{" "}
              {f.check ? <b>{f.check}: </b> : null}
              {f.what}
              {f.distance ? (
                <>
                  {" "}
                  <Value v={f.distance} />
                </>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
      {charge ? (
        <div className="grid gap-1 text-[13px]">
          <p className="st-prose" style={{ color: "var(--fg)" }}>
            {charge.state}
          </p>
          <p className="st-inline">
            {charge.pka ? (
              <span>
                typical pKa <Value v={charge.pka} />
              </span>
            ) : null}
            {charge.protonated ? (
              <span>
                protonated <Value v={charge.protonated} />
              </span>
            ) : null}
            <span>
              <Value v={charge.distance} />
            </span>
          </p>
        </div>
      ) : null}
      {nothing && !hetero ? <p className="st-prose">The audit found nothing at this residue, and it is not one of the catalytic residues.</p> : null}
    </section>
  );
}
