/**
 * Painting a prepared frame on a 2D canvas, far slabs first.
 *
 * Colours come from the stylesheet's tokens (read by the viewer from
 * computed style, so a theme switch repaints in the new theme): the trace
 * in ink, highlighted side chains in signal, ligands in caution, the
 * selection ringed in the focus colour. Depth fades a slab towards the
 * background and thins its lines.
 */
import type { Frame } from "./frame";

export interface Palette {
  background: string;
  trace: string;
  sidechain: string;
  ligand: string;
  selection: string;
  hover: string;
}

export interface Marker {
  x: number;
  y: number;
}

function strokeSegments(ctx: CanvasRenderingContext2D, segs: number[]): void {
  if (!segs.length) return;
  ctx.beginPath();
  for (let k = 0; k < segs.length; k += 4) {
    ctx.moveTo(segs[k], segs[k + 1]);
    ctx.lineTo(segs[k + 2], segs[k + 3]);
  }
  ctx.stroke();
}

function fillDots(ctx: CanvasRenderingContext2D, pts: number[], r: number): void {
  if (!pts.length) return;
  ctx.beginPath();
  for (let k = 0; k < pts.length; k += 2) {
    ctx.moveTo(pts[k] + r, pts[k + 1]);
    ctx.arc(pts[k], pts[k + 1], r, 0, Math.PI * 2);
  }
  ctx.fill();
}

export function paintFrame(
  ctx: CanvasRenderingContext2D,
  frame: Frame,
  palette: Palette,
  size: { width: number; height: number; dpr: number },
  marks: { selected: Marker[]; hovered: Marker | null },
): void {
  const { width, height, dpr } = size;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.globalAlpha = 1;
  ctx.fillStyle = palette.background;
  ctx.fillRect(0, 0, width, height);
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  for (const slab of frame.slabs) {
    const d = slab.depth;
    ctx.globalAlpha = 0.22 + 0.78 * d;
    ctx.strokeStyle = palette.trace;
    ctx.lineWidth = 1.1 + 2.1 * d;
    strokeSegments(ctx, slab.trace);
    ctx.strokeStyle = palette.sidechain;
    ctx.lineWidth = 1.3 + 1.9 * d;
    strokeSegments(ctx, slab.bonds);
    ctx.fillStyle = palette.sidechain;
    fillDots(ctx, slab.sidechainAtoms, 1.4 + 1.6 * d);
    ctx.fillStyle = palette.ligand;
    fillDots(ctx, slab.ligandAtoms, 1.6 + 1.8 * d);
  }
  ctx.globalAlpha = 1;
  ctx.lineWidth = 2;
  ctx.strokeStyle = palette.selection;
  for (const m of marks.selected) {
    ctx.beginPath();
    ctx.arc(m.x, m.y, 9, 0, Math.PI * 2);
    ctx.stroke();
  }
  if (marks.hovered) {
    ctx.strokeStyle = palette.hover;
    ctx.lineWidth = 1.5;
    ctx.setLineDash([2, 3]);
    ctx.beginPath();
    ctx.arc(marks.hovered.x, marks.hovered.y, 7, 0, Math.PI * 2);
    ctx.stroke();
    ctx.setLineDash([]);
  }
}
