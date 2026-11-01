/**
 * One frame, prepared without touching a canvas: every segment and point
 * projected and sorted into depth slabs, far to near. Painting is then a
 * handful of paths per slab (paint.ts), one stroke style each, which is
 * what keeps a 7,657-atom entry (1I10, four LDH chains, in the test
 * fixtures) well inside a 60 fps frame: the cost is the projection of the
 * atoms drawn (CAs, highlighted side chains, ligands), not the atom count.
 *
 * Depth cue: a slab's depth sets its line width and how far its colour is
 * mixed towards the background, so the near side of the fold reads in
 * front of the far side without lighting.
 */
import { type Camera, projectAll } from "./geometry";
import type { MoleculeModel } from "./model";

export const SLABS = 8;

export interface Slab {
  /** 0 farthest .. 1 nearest. */
  depth: number;
  /** x1, y1, x2, y2 per trace segment. */
  trace: number[];
  /** x1, y1, x2, y2 per side-chain bond. */
  bonds: number[];
  /** x, y per marked atom of a highlighted residue. */
  sidechainAtoms: number[];
  /** x, y per ligand atom. */
  ligandAtoms: number[];
}

export interface Frame {
  slabs: Slab[];
  projected: Float32Array;
  /** Wall-clock milliseconds spent preparing, for the viewer's own measurement. */
  prepareMs: number;
}

function slabIndex(z: number, radius: number): number {
  const t = (z + radius) / (2 * radius || 1);
  return Math.max(0, Math.min(SLABS - 1, Math.floor(t * SLABS)));
}

/**
 * Project what is drawn and bin it. `projected` is reused between frames
 * (length 3 x atom count); only the atoms that are drawn are written.
 */
export function prepareFrame(model: MoleculeModel, cam: Camera, projected: Float32Array): Frame {
  const t0 = typeof performance !== "undefined" ? performance.now() : 0;
  // Project only the atoms that are drawn or picked: CAs and marked atoms.
  const drawn = model.pickable;
  const one = new Float32Array(3);
  const out = new Float32Array(3);
  for (let k = 0; k < drawn.length; k++) {
    const i = drawn[k];
    one[0] = model.xyz[i * 3];
    one[1] = model.xyz[i * 3 + 1];
    one[2] = model.xyz[i * 3 + 2];
    projectAll(one, 1, cam, out);
    projected[i * 3] = out[0];
    projected[i * 3 + 1] = out[1];
    projected[i * 3 + 2] = out[2];
  }
  const slabs: Slab[] = Array.from({ length: SLABS }, (_, s) => ({
    depth: s / (SLABS - 1),
    trace: [],
    bonds: [],
    sidechainAtoms: [],
    ligandAtoms: [],
  }));
  const R = model.radius;
  const pushSegment = (list: "trace" | "bonds", a: number, b: number) => {
    const ax = projected[a * 3];
    const bx = projected[b * 3];
    if (Number.isNaN(ax) || Number.isNaN(bx)) return;
    const z = (projected[a * 3 + 2] + projected[b * 3 + 2]) / 2;
    slabs[slabIndex(z, R)][list].push(ax, projected[a * 3 + 1], bx, projected[b * 3 + 1]);
  };
  for (let k = 0; k < model.trace.length; k += 2) pushSegment("trace", model.trace[k], model.trace[k + 1]);
  for (let k = 0; k < model.sidechainBonds.length; k += 2)
    pushSegment("bonds", model.sidechainBonds[k], model.sidechainBonds[k + 1]);
  for (let k = 0; k < model.markedAtoms.length; k++) {
    const i = model.markedAtoms[k];
    const x = projected[i * 3];
    if (Number.isNaN(x)) continue;
    const slab = slabs[slabIndex(projected[i * 3 + 2], R)];
    const list = model.highlighted.has(model.residueOf[i]) ? slab.sidechainAtoms : slab.ligandAtoms;
    list.push(x, projected[i * 3 + 1]);
  }
  const t1 = typeof performance !== "undefined" ? performance.now() : 0;
  return { slabs, projected, prepareMs: t1 - t0 };
}
