/**
 * Which residues a finding or a catalytic site is about, and what the
 * tools said about one residue, gathered from what the server sent: the
 * catalytic residues `caterva prepare` places (M-CSA's, carried over by
 * alignment), the audit's findings at it, and, on Prepare, its row of the
 * protonation table.
 *
 * Nothing here measures anything. A finding names its residues as the
 * audit wrote them ("54", "163-164", or none for an entry-wide note); a
 * residue range that is not modelled has no atoms, so the viewer is
 * pointed at the residues either side of the gap, which are in the file,
 * and the page says that is what it shows.
 */
import type { CatalyticSite, FindingRow } from "@/api/types";
import type { ResidueRef } from "@/components/molecule/model";

import type { ChargeRowView } from "./views";

export function refKey(r: ResidueRef): string {
  return `${r.chain}:${r.resseq}`;
}

const RANGE = /^(-?\d+)[A-Z]?(?:-(-?\d+)[A-Z]?)?$/;

/** The residues a finding names, in its chain; a long unmodelled stretch is represented by its two ends. */
export function findingResidues(f: FindingRow): ResidueRef[] {
  if (!f.chain) return [];
  const out: ResidueRef[] = [];
  for (const text of f.residues) {
    const m = RANGE.exec(text.trim());
    if (!m) continue;
    const start = Number(m[1]);
    const end = m[2] === undefined ? start : Number(m[2]);
    if (end - start > 24) {
      out.push({ chain: f.chain, resseq: start }, { chain: f.chain, resseq: end });
      continue;
    }
    for (let r = start; r <= end; r++) out.push({ chain: f.chain, resseq: r });
  }
  return out;
}

/** Whether a finding is about residues that are not in the model (unmodelled, a chain break). */
export function isUnmodelled(f: FindingRow): boolean {
  return f.check === "unmodelled residues" || /not modelled/.test(f.what);
}

/**
 * Where to look in the viewer for a finding: its own residues, or for an
 * unmodelled stretch the residues just before and after it, which the file
 * does hold.
 */
export function findingFocus(f: FindingRow): { refs: ResidueRef[]; flanking: boolean } {
  const refs = findingResidues(f);
  if (!refs.length || !isUnmodelled(f)) return { refs, flanking: false };
  const nums = refs.map((r) => r.resseq);
  const chain = refs[0].chain;
  return {
    refs: [
      { chain, resseq: Math.min(...nums) - 1 },
      { chain, resseq: Math.max(...nums) + 1 },
    ],
    flanking: true,
  };
}

export function siteRef(s: { chain: string; resseq: string | number }): ResidueRef {
  return { chain: s.chain, resseq: Number(s.resseq) };
}

export interface Known {
  catalytic: CatalyticSite | null;
  findings: FindingRow[];
  charge: ChargeRowView | null;
}

/** Everything the server said about one residue. */
export function knownAbout(
  ref: ResidueRef,
  {
    catalytic = [],
    findings = [],
    charges = [],
  }: { catalytic?: readonly CatalyticSite[]; findings?: readonly FindingRow[]; charges?: readonly ChargeRowView[] },
): Known {
  const key = refKey(ref);
  return {
    catalytic: catalytic.find((c) => refKey(siteRef(c)) === key) ?? null,
    findings: findings.filter((f) => findingResidues(f).some((r) => refKey(r) === key)),
    charge: charges.find((c) => refKey(siteRef(c)) === key) ?? null,
  };
}

const SEVERITY_ORDER = ["blocks", "decide", "note"];

/**
 * The audit's findings in the report's order: by severity (blocks, decide,
 * note), then nearest the active site first, findings with no distance
 * last. The distance compared is the one the server sent.
 */
export function rankFindings(findings: readonly FindingRow[]): FindingRow[] {
  return [...findings].sort(
    (a, b) =>
      SEVERITY_ORDER.indexOf(a.severity) - SEVERITY_ORDER.indexOf(b.severity) ||
      (a.distance?.value ?? Infinity) - (b.distance?.value ?? Infinity) ||
      (a.chain ?? "").localeCompare(b.chain ?? ""),
  );
}
