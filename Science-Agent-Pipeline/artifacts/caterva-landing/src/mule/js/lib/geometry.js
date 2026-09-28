/* ============================================================
   caterva — architectural geometry
   Faceted shells, routed pathways, and the illustrative curve.
   Nothing here is decorative: each generator maps to a structure.
   ============================================================ */

const fmt = (n) => Math.round(n * 100) / 100;

/**
 * Faceted vertical shell — a chamfered architectural silhouette.
 * `chamfer` cuts the corners so nothing reads as a rounded card.
 */
export function facetPath({ x, y, w, h }, chamfer = 14, opts = {}) {
  const { top = true, bottom = true } = opts;
  const c = Math.min(chamfer, w / 2, h / 2);
  const r = x + w;
  const b = y + h;
  const pts = [];
  if (top) {
    pts.push(`M ${fmt(x + c)} ${fmt(y)}`, `L ${fmt(r - c)} ${fmt(y)}`, `L ${fmt(r)} ${fmt(y + c)}`);
  } else {
    pts.push(`M ${fmt(x)} ${fmt(y)}`, `L ${fmt(r)} ${fmt(y)}`);
  }
  if (bottom) {
    pts.push(`L ${fmt(r)} ${fmt(b - c)}`, `L ${fmt(r - c)} ${fmt(b)}`, `L ${fmt(x + c)} ${fmt(b)}`, `L ${fmt(x)} ${fmt(b - c)}`);
  } else {
    pts.push(`L ${fmt(r)} ${fmt(b)}`, `L ${fmt(x)} ${fmt(b)}`);
  }
  pts.push('Z');
  return pts.join(' ');
}

/** Tapered chamber: narrows toward the bottom aperture. */
export function chamberPath({ x, y, w, h }, inset = 90) {
  const r = x + w;
  const b = y + h;
  const mid = x + w / 2;
  return [
    `M ${fmt(x)} ${fmt(y)}`,
    `L ${fmt(r)} ${fmt(y)}`,
    `L ${fmt(r - inset * 0.34)} ${fmt(b - 26)}`,
    `L ${fmt(mid + 16)} ${fmt(b)}`,
    `L ${fmt(mid - 16)} ${fmt(b)}`,
    `L ${fmt(x + inset * 0.34)} ${fmt(b - 26)}`,
    'Z'
  ].join(' ');
}

/** Polygonal ring of the vault: faceted ellipse. */
export function facetedEllipse(cx, cy, rx, ry, facets, phase = 0) {
  const pts = [];
  for (let i = 0; i < facets; i += 1) {
    const a = phase + (i / facets) * Math.PI * 2;
    pts.push(`${fmt(cx + Math.cos(a) * rx)} ${fmt(cy + Math.sin(a) * ry)}`);
  }
  return `M ${pts.join(' L ')} Z`;
}

/** Radial spokes between two faceted ellipses — the vault's structure. */
export function vaultSpokes(cx, cy, outer, inner, facets, phase = 0) {
  const out = [];
  for (let i = 0; i < facets; i += 1) {
    const a = phase + (i / facets) * Math.PI * 2;
    const x1 = cx + Math.cos(a) * inner.rx;
    const y1 = cy + Math.sin(a) * inner.ry;
    const x2 = cx + Math.cos(a) * outer.rx;
    const y2 = cy + Math.sin(a) * outer.ry;
    out.push(`M ${fmt(x1)} ${fmt(y1)} L ${fmt(x2)} ${fmt(y2)}`);
  }
  return out.join(' ');
}

/**
 * Routed pathway: orthogonal-with-chamfer route between two points.
 * Evidence travels along defined routes, never floats.
 */
export function routePath(from, to, opts = {}) {
  const { bend = 0.55, chamfer = 12 } = opts;
  const midY = from.y + (to.y - from.y) * bend;
  const dirX = Math.sign(to.x - from.x) || 1;
  const c = Math.min(chamfer, Math.abs(to.x - from.x) / 2 || chamfer, Math.abs(to.y - midY) / 2 || chamfer);
  if (Math.abs(to.x - from.x) < 2) {
    return `M ${fmt(from.x)} ${fmt(from.y)} L ${fmt(to.x)} ${fmt(to.y)}`;
  }
  return [
    `M ${fmt(from.x)} ${fmt(from.y)}`,
    `L ${fmt(from.x)} ${fmt(midY - c)}`,
    `L ${fmt(from.x + c * dirX)} ${fmt(midY)}`,
    `L ${fmt(to.x - c * dirX)} ${fmt(midY)}`,
    `L ${fmt(to.x)} ${fmt(midY + c)}`,
    `L ${fmt(to.x)} ${fmt(to.y)}`
  ].join(' ');
}

/** Simple elbow used for trace scans inside the vault. */
export function elbowPath(from, to) {
  const midX = from.x + (to.x - from.x) * 0.5;
  return `M ${fmt(from.x)} ${fmt(from.y)} L ${fmt(midX)} ${fmt(from.y)} L ${fmt(midX)} ${fmt(to.y)} L ${fmt(to.x)} ${fmt(to.y)}`;
}

/** Thin architectural fracture line — the critique disclosure. */
export function fracturePath(x, y, len, seed = 7) {
  let cx = x;
  let cy = y;
  const segs = [`M ${fmt(cx)} ${fmt(cy)}`];
  const steps = 7;
  for (let i = 1; i <= steps; i += 1) {
    const t = i / steps;
    cx = x + len * t;
    cy = y + Math.sin(t * 5.2 + seed) * 9 + t * 26;
    segs.push(`L ${fmt(cx)} ${fmt(cy)}`);
  }
  return segs.join(' ');
}

/* ------------------------------------------------------------
   Illustrative Michaelis–Menten shape.
   Shape demonstration only — not a scientific claim.
   ------------------------------------------------------------ */
export function kineticsSeries({ vmax, km, sMax, samples, jitter }) {
  const v = (sc) => (vmax * sc) / (km + sc);
  const curve = [];
  const steps = 72;
  for (let i = 0; i <= steps; i += 1) {
    const sc = (i / steps) * sMax;
    curve.push({ s: sc, v: v(sc) });
  }
  // Deterministic pseudo-jitter so plotted points read as measured, not random.
  const points = [];
  for (let i = 1; i <= samples; i += 1) {
    const sc = (i / (samples + 0.4)) * sMax;
    const wobble = Math.sin(i * 12.9898) * jitter;
    points.push({ s: sc, v: Math.max(0, Math.min(vmax * 1.04, v(sc) + wobble)) });
  }
  return { curve, points, vmax };
}

/** Map a series into an SVG plot box and emit a polyline path. */
export function plotToPath(series, plot, vmax) {
  const sMax = series[series.length - 1].s || 1;
  const pts = series.map((p) => {
    const px = plot.x + (p.s / sMax) * plot.w;
    const py = plot.y + plot.h - (p.v / (vmax * 1.12)) * plot.h;
    return `${fmt(px)} ${fmt(py)}`;
  });
  return `M ${pts.join(' L ')}`;
}

export function plotPoint(p, plot, sMax, vmax) {
  return {
    x: plot.x + (p.s / sMax) * plot.w,
    y: plot.y + plot.h - (p.v / (vmax * 1.12)) * plot.h
  };
}

/** Expected-behaviour envelope band around the curve. */
export function envelopePath(series, plot, vmax, spread = 0.075) {
  const sMax = series[series.length - 1].s || 1;
  const upper = [];
  const lower = [];
  series.forEach((p) => {
    const px = plot.x + (p.s / sMax) * plot.w;
    const base = p.v / (vmax * 1.12);
    const pad = spread * (0.42 + base * 0.75);
    upper.push(`${fmt(px)} ${fmt(plot.y + plot.h - Math.min(1, base + pad) * plot.h)}`);
    lower.unshift(`${fmt(px)} ${fmt(plot.y + plot.h - Math.max(0, base - pad) * plot.h)}`);
  });
  return `M ${upper.join(' L ')} L ${lower.join(' L ')} Z`;
}
