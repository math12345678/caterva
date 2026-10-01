/**
 * The molecule viewer's engine, on real coordinates: T4 lysozyme (1L63)
 * and human LDH (1I10, three chains, 7,657 atoms), both committed mmCIF
 * fixtures parsed into the CoordinatesResponse shape (fixtures/README.md).
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import ldh from "./fixtures/api/coordinates-1I10.json";
import lysozyme from "./fixtures/api/coordinates-1L63.json";
import type { CoordinatesResponse } from "@/api/types";
import { prepareFrame } from "@/components/molecule/frame";
import {
  type Camera,
  determinant,
  dragRotate,
  fitScale,
  identity,
  multiply,
  pick,
  project,
  projectAll,
  rotationX,
  rotationY,
} from "@/components/molecule/geometry";
import { buildModel, residueLabel, TRACE_BREAK } from "@/components/molecule/model";
import { MoleculeViewer } from "@/components/molecule/MoleculeViewer";

const T4L = lysozyme as CoordinatesResponse;
const LDH = ldh as CoordinatesResponse;
/** T4 lysozyme's catalytic pair. */
const ACTIVE_SITE = [
  { chain: "A", resseq: 11 },
  { chain: "A", resseq: 20 },
];

function camera(width = 800, height = 600, radius = 30): Camera {
  return { rotation: identity(), distance: radius * 4 + 10, width, height, scale: fitScale(radius, width, height) };
}

describe("rotation", () => {
  it("turns the front to the right for a positive yaw, and brings the top forward for a positive pitch", () => {
    const yaw = rotationY(Math.PI / 2);
    const front = [yaw[2], yaw[5], yaw[8]]; // the image of (0, 0, 1)
    expect(front[0]).toBeCloseTo(1);
    expect(front[2]).toBeCloseTo(0);
    const pitch = rotationX(Math.PI / 2);
    const top = [pitch[1], pitch[4], pitch[7]]; // the image of (0, 1, 0)
    expect(top[2]).toBeCloseTo(1);
  });

  it("stays a rotation after thousands of small drags (no shear, no scale)", () => {
    let m = identity();
    for (let i = 0; i < 5000; i++) m = dragRotate(m, Math.sin(i) * 7, Math.cos(i * 1.3) * 5);
    expect(determinant(m)).toBeCloseTo(1, 10);
    const t = multiply(m, new Float64Array([m[0], m[3], m[6], m[1], m[4], m[7], m[2], m[5], m[8]]));
    for (let r = 0; r < 3; r++) for (let c = 0; c < 3; c++) expect(t[r * 3 + c]).toBeCloseTo(r === c ? 1 : 0, 10);
  });
});

describe("projection", () => {
  it("puts the centre in the middle, x to the right and y up", () => {
    const cam = camera();
    expect(project([0, 0, 0], cam).slice(0, 2)).toEqual([400, 300]);
    const [rx] = project([10, 0, 0], cam);
    const [, uy] = project([0, 10, 0], cam);
    expect(rx).toBeGreaterThan(400);
    expect(uy).toBeLessThan(300);
  });

  it("draws the nearer of two equal offsets further from the centre (perspective)", () => {
    const cam = camera();
    const [near] = project([10, 0, 20], cam);
    const [far] = project([10, 0, -20], cam);
    expect(near - 400).toBeGreaterThan(far - 400);
  });

  it("fits the whole entry inside the canvas", () => {
    const model = buildModel(T4L.atoms);
    const cam = camera(640, 480, model.radius);
    const out = new Float32Array(model.count * 3);
    projectAll(model.xyz, model.count, cam, out);
    for (let i = 0; i < model.count; i++) {
      expect(out[i * 3]).toBeGreaterThanOrEqual(0);
      expect(out[i * 3]).toBeLessThanOrEqual(640);
      expect(out[i * 3 + 1]).toBeGreaterThanOrEqual(0);
      expect(out[i * 3 + 1]).toBeLessThanOrEqual(480);
    }
  });
});

describe("the model", () => {
  it("reads 1L63 as one chain of 162 residues, joined CA to CA", () => {
    const model = buildModel(T4L.atoms);
    expect(model.count).toBe(T4L.count);
    expect(model.chains).toEqual(["A"]);
    const polymer = model.residues.filter((r) => !r.hetero);
    expect(polymer).toHaveLength(162);
    expect(polymer.every((r) => r.ca !== -1)).toBe(true);
    expect(model.trace.length / 2).toBe(161);
    // Centred: the centroid of the centred coordinates is the origin.
    let sx = 0;
    for (let i = 0; i < model.count; i++) sx += model.xyz[i * 3];
    expect(Math.abs(sx / model.count)).toBeLessThan(1e-3);
  });

  it("breaks the trace where 1I10's chain G has a disordered stretch, and nowhere else", () => {
    const model = buildModel(LDH.atoms);
    const polymer = model.residues.filter((r) => !r.hetero && r.ca !== -1);
    expect(model.chains).toEqual(["A", "D", "G"]);
    const segments = model.trace.length / 2;
    const joins = polymer.length - model.chains.length;
    expect(joins - segments).toBe(1);
    // The one missing join: G 100 to G 107, the active-site loop the audit fixture describes.
    const joined = new Set<string>();
    for (let k = 0; k < model.trace.length; k += 2) joined.add(`${model.trace[k]}-${model.trace[k + 1]}`);
    const missing = polymer.slice(1).filter((r, i) => r.chain === polymer[i].chain && !joined.has(`${polymer[i].ca}-${r.ca}`));
    expect(missing.map((r) => `${r.chain}${r.resseq}`)).toEqual(["G107"]);
    expect(TRACE_BREAK).toBeLessThan(7.5);
  });

  it("draws the side chains of the highlighted residues, bonded by distance", () => {
    const model = buildModel(T4L.atoms, ACTIVE_SITE);
    expect([...model.highlighted].map((i) => residueLabel(model.residues[i]))).toEqual([
      "GLU 11 (chain A)",
      "ASP 20 (chain A)",
    ]);
    // Glu: CB CG CD OE1 OE2; Asp: CB CG OD1 OD2.
    expect(model.markedAtoms.length).toBe(9);
    // Glu: CA-CB CB-CG CG-CD CD-OE1 CD-OE2; Asp: CA-CB CB-CG CG-OD1 CG-OD2.
    expect(model.sidechainBonds.length / 2).toBe(9);
  });
});

describe("picking", () => {
  it("finds the residue under the pointer, after any rotation", () => {
    const model = buildModel(T4L.atoms, ACTIVE_SITE);
    const cam = { ...camera(800, 600, model.radius), rotation: dragRotate(identity(), 140, -60) };
    const projected = new Float32Array(model.count * 3);
    prepareFrame(model, cam, projected);
    const glu = model.residues.find((r) => r.resseq === 11)!;
    const at = pick(projected, model.pickable, projected[glu.ca * 3] + 2, projected[glu.ca * 3 + 1] - 1, 12);
    expect(at).not.toBe(-1);
    expect(model.residueOf[at]).toBe(model.residues.indexOf(glu));
    expect(pick(projected, model.pickable, -500, -500, 12)).toBe(-1);
  });

  it("prefers the nearer atom when two overlap on screen", () => {
    const projected = new Float32Array([100, 100, -5, 100, 100, 7]);
    expect(pick(projected, [0, 1], 100, 100, 10)).toBe(1);
  });
});

describe("a frame of a 7,657-atom entry", () => {
  it("sorts every segment into a depth slab, far to near", () => {
    const model = buildModel(LDH.atoms, [{ chain: "A", resseq: 193 }]);
    const projected = new Float32Array(model.count * 3);
    const frame = prepareFrame(model, camera(1200, 800, model.radius), projected);
    const total = frame.slabs.reduce((n, s) => n + s.trace.length / 4, 0);
    expect(total).toBe(model.trace.length / 2);
    const depths = frame.slabs.map((s) => s.depth);
    expect([...depths].sort((a, b) => a - b)).toEqual(depths);
  });

  it("is prepared well inside a 60 fps frame budget", () => {
    const model = buildModel(LDH.atoms, [{ chain: "A", resseq: 193 }]);
    const projected = new Float32Array(model.count * 3);
    let rotation = identity();
    const times: number[] = [];
    for (let i = 0; i < 60; i++) {
      rotation = dragRotate(rotation, 6, 2);
      const t0 = performance.now();
      prepareFrame(model, { ...camera(1200, 800, model.radius), rotation }, projected);
      times.push(performance.now() - t0);
    }
    times.sort((a, b) => a - b);
    const median = times[Math.floor(times.length / 2)];
    // Painting adds a few dozen canvas paths; the preparation must leave most of the 16.7 ms.
    expect(median).toBeLessThan(8);
  });
});

describe("<MoleculeViewer>", () => {
  it("names itself, steps through the highlighted residues with ] and clears with Escape", () => {
    const onSelect = vi.fn();
    render(<MoleculeViewer coordinates={T4L} highlight={ACTIVE_SITE} onSelect={onSelect} />);
    const canvas = screen.getByRole("application");
    expect(canvas).toHaveAccessibleName(/1L63: alpha-carbon trace of 162 residues, 2 highlighted with side chains/);
    fireEvent.keyDown(canvas, { key: "]" });
    expect(onSelect).toHaveBeenLastCalledWith(expect.objectContaining({ resname: "GLU", resseq: 11 }));
    expect(screen.getByText("Selected GLU 11 (chain A)")).toBeInTheDocument();
    fireEvent.keyDown(canvas, { key: "Escape" });
    // Nothing was selected by the parent (uncontrolled), so Escape has nothing to clear and is not taken.
    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("link", { name: /PDB 1L63/ })).toHaveAttribute("href", "https://www.rcsb.org/structure/1L63");
  });
});
