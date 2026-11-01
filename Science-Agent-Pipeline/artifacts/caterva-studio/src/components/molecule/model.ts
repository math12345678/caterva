/**
 * From the structure endpoint's atoms (CoordinatesResponse, columnar, in
 * angstroms as the mmCIF gives them) to what the viewer draws: residues,
 * the alpha-carbon trace of each chain, the side chains of the residues a
 * screen highlights (an active site), and ligands.
 *
 * Nothing here moves an atom. Coordinates are only centred on their
 * centroid (a translation, so rotation turns the model about its middle);
 * bonds within a highlighted side chain are inferred by distance, the
 * convention every viewer without a topology uses, and are drawing only:
 * no number on the page comes from them.
 */
import type { AtomColumns } from "@/api/types";

export interface ResidueRef {
  chain: string;
  resseq: number;
}

export interface Residue extends ResidueRef {
  resname: string;
  hetero: boolean;
  /** Index of the residue's CA atom, or -1 (a ligand, a truncated residue). */
  ca: number;
  /** Indices of every atom of the residue. */
  atoms: number[];
}

export interface MoleculeModel {
  /** Centred coordinates, xyz interleaved. */
  xyz: Float32Array;
  count: number;
  /** The centroid that was subtracted, in the file's coordinates. */
  centroid: [number, number, number];
  /** Radius of the sphere about the centroid holding every atom. */
  radius: number;
  residues: Residue[];
  /** Residue index of each atom. */
  residueOf: Int32Array;
  chains: string[];
  /** Pairs of atom indices: consecutive CAs of a chain closer than TRACE_BREAK. */
  trace: Uint32Array;
  /** Pairs of atom indices: bonds inside highlighted residues (and their CA to the trace). */
  sidechainBonds: Uint32Array;
  /** Atoms drawn as points: highlighted side-chain atoms and ligand atoms. */
  markedAtoms: Uint32Array;
  /** Atoms a click can land on: every CA, every marked atom. */
  pickable: Uint32Array;
  /** Residue indices that are highlighted. */
  highlighted: Set<number>;
  /** Ligand residue indices (hetero, not water). */
  ligands: number[];
}

/** Two CAs further apart than this are not consecutive in the chain (a gap in the model). */
export const TRACE_BREAK = 4.3;
const BOND_MAX = 1.95;
const BACKBONE = new Set(["N", "C", "O", "OXT"]);
const WATER = new Set(["HOH", "WAT", "DOD", "H2O"]);

export function residueKey(r: ResidueRef): string {
  return `${r.chain}:${r.resseq}`;
}

export function buildModel(atoms: AtomColumns, highlight: readonly ResidueRef[] = []): MoleculeModel {
  const n = atoms.x.length;
  let sx = 0;
  let sy = 0;
  let sz = 0;
  for (let i = 0; i < n; i++) {
    sx += atoms.x[i];
    sy += atoms.y[i];
    sz += atoms.z[i];
  }
  const centroid: [number, number, number] = n ? [sx / n, sy / n, sz / n] : [0, 0, 0];
  const xyz = new Float32Array(n * 3);
  let r2 = 0;
  for (let i = 0; i < n; i++) {
    const x = atoms.x[i] - centroid[0];
    const y = atoms.y[i] - centroid[1];
    const z = atoms.z[i] - centroid[2];
    xyz[i * 3] = x;
    xyz[i * 3 + 1] = y;
    xyz[i * 3 + 2] = z;
    r2 = Math.max(r2, x * x + y * y + z * z);
  }

  // Residues, in file order; an atom joins the residue of the same chain and number.
  const residues: Residue[] = [];
  const byKey = new Map<string, number>();
  const residueOf = new Int32Array(n);
  const chains: string[] = [];
  for (let i = 0; i < n; i++) {
    const ref = { chain: atoms.chain[i], resseq: atoms.resseq[i] };
    const key = `${ref.chain}:${ref.resseq}:${atoms.hetero[i] ? "H" : "P"}`;
    let r = byKey.get(key);
    if (r === undefined) {
      r = residues.length;
      byKey.set(key, r);
      residues.push({ ...ref, resname: atoms.resname[i], hetero: atoms.hetero[i], ca: -1, atoms: [] });
      if (!chains.includes(ref.chain)) chains.push(ref.chain);
    }
    residueOf[i] = r;
    residues[r].atoms.push(i);
    // An alternate location repeats an atom name; the first is the one drawn.
    if (!atoms.hetero[i] && atoms.atom_name[i] === "CA" && residues[r].ca === -1) residues[r].ca = i;
  }

  const dist = (a: number, b: number) =>
    Math.hypot(xyz[a * 3] - xyz[b * 3], xyz[a * 3 + 1] - xyz[b * 3 + 1], xyz[a * 3 + 2] - xyz[b * 3 + 2]);

  // The trace: consecutive polymer residues of one chain, joined CA to CA unless there is a gap.
  const trace: number[] = [];
  const pickable: number[] = [];
  let prev: Residue | null = null;
  for (const r of residues) {
    if (r.hetero || r.ca === -1) continue;
    pickable.push(r.ca);
    if (prev && prev.chain === r.chain && dist(prev.ca, r.ca) <= TRACE_BREAK) trace.push(prev.ca, r.ca);
    prev = r;
  }

  const wanted = new Set(highlight.map(residueKey));
  const highlighted = new Set<number>();
  const bonds: number[] = [];
  const marked: number[] = [];
  const ligands: number[] = [];
  residues.forEach((r, index) => {
    const isLigand = r.hetero && !WATER.has(r.resname);
    const isHighlighted = !r.hetero && wanted.has(residueKey(r));
    if (!isLigand && !isHighlighted) return;
    if (isLigand) ligands.push(index);
    if (isHighlighted) highlighted.add(index);
    // Heavy atoms of the side chain (CA included, as its root), or the whole ligand.
    const drawn = r.atoms.filter(
      (i) => atoms.element[i] !== "H" && atoms.element[i] !== "D" && (isLigand || !BACKBONE.has(atoms.atom_name[i])),
    );
    for (const i of drawn) {
      if (i !== r.ca) {
        marked.push(i);
        pickable.push(i);
      }
    }
    for (let a = 0; a < drawn.length; a++) {
      for (let b = a + 1; b < drawn.length; b++) {
        if (dist(drawn[a], drawn[b]) <= BOND_MAX) bonds.push(drawn[a], drawn[b]);
      }
    }
  });

  return {
    xyz,
    count: n,
    centroid,
    radius: Math.sqrt(r2),
    residues,
    residueOf,
    chains,
    trace: Uint32Array.from(trace),
    sidechainBonds: Uint32Array.from(bonds),
    markedAtoms: Uint32Array.from(marked),
    pickable: Uint32Array.from(pickable),
    highlighted,
    ligands,
  };
}

/** "HIS 195 (chain A)", the way a residue is named on screen. */
export function residueLabel(r: Pick<Residue, "resname" | "resseq" | "chain">): string {
  return `${r.resname} ${r.resseq} (chain ${r.chain})`;
}
