/**
 * What the structure viewer draws, worked out from a CoordinatesResponse
 * without any drawing: which atoms are shown, in which role, where the
 * catalytic residues are, and where the camera looks.
 *
 * Coordinates are the file's, in angstroms, as the server sent them; the
 * only arithmetic here is centring (subtracting the shown atoms' centroid)
 * so the molecule turns about its middle. Nothing is rounded and no atom is
 * invented or moved relative to another.
 *
 * The catalytic residues are the ones `caterva prepare` placed (M-CSA's
 * reference residues carried over by alignment); the viewer marks those and
 * no others. It does not pick an "active site" of its own.
 */
import type { CatalyticSite, CoordinatesResponse } from "@/api/types";

export type AtomRole = "polymer" | "ligand" | "water" | "catalytic";

export interface SiteMark {
  key: string;
  site: CatalyticSite;
  /** Indexes into the model's atoms. */
  atoms: number[];
  /** Centroid of the site's atoms, centred like every position. */
  centre: [number, number, number] | null;
}

export interface ViewerModel {
  /** x, y, z per shown atom, centred, angstroms. */
  positions: Float32Array;
  roles: AtomRole[];
  /** Index of the atom in the response's columns, per shown atom. */
  source: number[];
  /** Chain of each shown atom, for tinting chains apart. */
  chains: string[];
  sites: SiteMark[];
  /** Radius of the sphere about the origin that holds every shown atom. */
  extent: number;
  /** The centroid that was subtracted, in the file's frame. */
  origin: [number, number, number];
  hiddenWater: number;
}

const WATER = new Set(["HOH", "WAT", "DOD", "H2O", "SOL"]);

export function siteKey(chain: string, resseq: string | number): string {
  return `${chain}:${String(resseq)}`;
}

export function buildModel(coords: CoordinatesResponse, { showWater = false } = {}): ViewerModel {
  const a = coords.atoms;
  const catalytic = new Map<string, CatalyticSite>();
  for (const site of coords.catalytic ?? []) catalytic.set(siteKey(site.chain, site.resseq), site);

  const keep: number[] = [];
  const roles: AtomRole[] = [];
  let hiddenWater = 0;
  for (let i = 0; i < a.x.length; i++) {
    const water = WATER.has(a.resname[i]);
    if (water && !showWater) {
      hiddenWater += 1;
      continue;
    }
    keep.push(i);
    if (!a.hetero[i] && catalytic.has(siteKey(a.chain[i], a.resseq[i]))) roles.push("catalytic");
    else if (water) roles.push("water");
    else if (a.hetero[i]) roles.push("ligand");
    else roles.push("polymer");
  }

  let cx = 0;
  let cy = 0;
  let cz = 0;
  for (const i of keep) {
    cx += a.x[i];
    cy += a.y[i];
    cz += a.z[i];
  }
  const n = Math.max(keep.length, 1);
  const origin: [number, number, number] = [cx / n, cy / n, cz / n];

  const positions = new Float32Array(keep.length * 3);
  let extent = 0;
  keep.forEach((i, k) => {
    const x = a.x[i] - origin[0];
    const y = a.y[i] - origin[1];
    const z = a.z[i] - origin[2];
    positions[k * 3] = x;
    positions[k * 3 + 1] = y;
    positions[k * 3 + 2] = z;
    extent = Math.max(extent, Math.hypot(x, y, z));
  });

  const byKey = new Map<string, number[]>();
  keep.forEach((i, k) => {
    if (roles[k] !== "catalytic") return;
    const key = siteKey(a.chain[i], a.resseq[i]);
    const list = byKey.get(key) ?? [];
    list.push(k);
    byKey.set(key, list);
  });
  const sites: SiteMark[] = (coords.catalytic ?? []).map((site) => {
    const key = siteKey(site.chain, site.resseq);
    const atoms = byKey.get(key) ?? [];
    let centre: [number, number, number] | null = null;
    if (atoms.length) {
      const s = [0, 0, 0];
      for (const k of atoms) for (let d = 0; d < 3; d++) s[d] += positions[k * 3 + d];
      centre = [s[0] / atoms.length, s[1] / atoms.length, s[2] / atoms.length];
    }
    return { key, site, atoms, centre };
  });

  return {
    positions,
    roles,
    source: keep,
    chains: keep.map((i) => a.chain[i]),
    sites,
    extent: Math.max(extent, 1),
    origin,
    hiddenWater,
  };
}

/** A residue's name as people say it: "His192". */
export function residueName(resname: string | null, resseq: string | number): string {
  const r = resname ?? "?";
  return `${r.charAt(0)}${r.slice(1).toLowerCase()}${resseq}`;
}

/* ------------------------------------------------------------------ */
/* Theme colours for WebGL                                             */
/* ------------------------------------------------------------------ */

/**
 * sRGB (0..1 per channel) of a CSS `oklch(L C H)` value, by the OKLab
 * matrices (Ottosson 2020, https://bottosson.github.io/posts/oklab/). The
 * tokens are written in OKLCH and WebGL takes linear or sRGB triples, so
 * the viewer converts the same tokens the page uses rather than keeping a
 * second palette. Returns null for anything that is not oklch().
 */
export function oklchToSrgb(css: string): [number, number, number] | null {
  const m = /oklch\(\s*([\d.]+)(%?)\s+([\d.]+)\s+([\d.]+)(?:deg)?\s*(?:\/\s*[\d.%]+\s*)?\)/i.exec(css.trim());
  if (!m) return null;
  const L = Number(m[1]) / (m[2] === "%" ? 100 : 1);
  const C = Number(m[3]);
  const h = (Number(m[4]) * Math.PI) / 180;
  const A = C * Math.cos(h);
  const B = C * Math.sin(h);
  const l = (L + 0.3963377774 * A + 0.2158037573 * B) ** 3;
  const mm = (L - 0.1055613458 * A - 0.0638541728 * B) ** 3;
  const s = (L - 0.0894841775 * A - 1.291485548 * B) ** 3;
  const lin = [
    4.0767416621 * l - 3.3077115913 * mm + 0.2309699292 * s,
    -1.2684380046 * l + 2.6097574011 * mm - 0.3413193965 * s,
    -0.0041960863 * l - 0.7034186147 * mm + 1.707614701 * s,
  ];
  const enc = (c: number) => {
    const v = Math.min(1, Math.max(0, c));
    return v <= 0.0031308 ? 12.92 * v : 1.055 * v ** (1 / 2.4) - 0.055;
  };
  return [enc(lin[0]), enc(lin[1]), enc(lin[2])];
}

export interface ViewerPalette {
  surface: [number, number, number];
  polymer: [number, number, number];
  polymerAlt: [number, number, number];
  ligand: [number, number, number];
  water: [number, number, number];
  catalytic: [number, number, number];
}

const FALLBACK: ViewerPalette = {
  surface: [0.992, 0.973, 0.933],
  polymer: [0.42, 0.43, 0.47],
  polymerAlt: [0.62, 0.62, 0.64],
  ligand: [0.58, 0.4, 0.13],
  water: [0.75, 0.78, 0.8],
  catalytic: [0.36, 0.5, 0.55],
};

function mix(a: [number, number, number], b: [number, number, number], t: number): [number, number, number] {
  return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t];
}

/** The viewer's colours from the page's current tokens (both themes). */
export function readPalette(root: HTMLElement = document.documentElement): ViewerPalette {
  const style = getComputedStyle(root);
  const token = (name: string, fallback: [number, number, number]) =>
    oklchToSrgb(style.getPropertyValue(name)) ?? fallback;
  const surface = token("--surface", FALLBACK.surface);
  const fg = token("--fg", FALLBACK.polymer);
  const muted = token("--muted", FALLBACK.polymerAlt);
  return {
    surface,
    polymer: mix(fg, surface, 0.28),
    polymerAlt: mix(muted, surface, 0.35),
    ligand: token("--caution", FALLBACK.ligand),
    water: mix(muted, surface, 0.6),
    catalytic: token("--signal", FALLBACK.catalytic),
  };
}
