/**
 * The 3D structure viewer: an entry's alpha-carbon trace with the
 * highlighted residues' side chains (an active site) and its ligands,
 * depth-cued, on a 2D canvas.
 *
 * Drag to rotate, scroll or pinch to zoom; with the canvas focused, the
 * arrow keys rotate, + and - zoom, 0 resets, ] and [ step through the
 * highlighted residues (every residue when none is highlighted), Escape
 * clears the selection. Clicking a residue selects it and tells the
 * screen (`onSelect`), which shows what it knows about it.
 *
 * Frames are drawn only when something changed (a drag, a zoom, a theme
 * switch, a resize), never on an idle loop. After a drag the model keeps
 * turning briefly and slows to a stop; with prefers-reduced-motion it does
 * not, and nothing moves unless the reader moves it.
 *
 * The page never sees a coordinate it did not get from the server: the
 * atoms are the entry's mmCIF, first model, as the structure endpoint
 * parsed it (CONTRACT.md 7), and the citation shown is the entry's.
 */
import { RotateCcw } from "lucide-react";
import { type KeyboardEvent, type PointerEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { CoordinatesResponse } from "@/api/types";
import { Citation } from "@/components/provenance/Citation";
import { formatCount } from "@/lib/format";
import { useReducedMotion } from "@/lib/motion";

import { prepareFrame } from "./frame";
import { type Camera, dragRotate, fitScale, identity, type Mat3, pick, rotationX, rotationY, multiply } from "./geometry";
import { buildModel, type Residue, type ResidueRef, residueKey, residueLabel } from "./model";
import { type Palette, paintFrame } from "./paint";

const KEY_STEP = (7.5 * Math.PI) / 180;
const FINE_STEP = (1.5 * Math.PI) / 180;
const PICK_PX = 12;
const MIN_ZOOM = 0.35;
const MAX_ZOOM = 14;

function readPalette(el: Element): Palette {
  const s = getComputedStyle(el);
  const v = (name: string, fallback: string) => s.getPropertyValue(name).trim() || fallback;
  return {
    background: v("--surface", "Canvas"),
    trace: v("--fg", "CanvasText"),
    sidechain: v("--signal", "CanvasText"),
    ligand: v("--caution", "CanvasText"),
    selection: v("--focus", "CanvasText"),
    hover: v("--fg-soft", "CanvasText"),
  };
}

export interface MoleculeViewerProps {
  coordinates: CoordinatesResponse;
  /** Residues whose side chains are drawn: an active site, catalytic residues. */
  highlight?: readonly ResidueRef[];
  selected?: ResidueRef | null;
  onSelect?: (residue: Residue | null) => void;
  height?: number;
}

export function MoleculeViewer({ coordinates, highlight = [], selected = null, onSelect, height = 420 }: MoleculeViewerProps) {
  const highlightKey = highlight.map(residueKey).join(",");
  const model = useMemo(
    () => buildModel(coordinates.atoms, highlight),
    // `highlight` is compared by its residues, not by array identity.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [coordinates, highlightKey],
  );
  const reduced = useReducedMotion();
  const wrap = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const rotation = useRef<Mat3>(identity());
  const zoom = useRef(1);
  const size = useRef({ width: 0, height: 0, dpr: 1 });
  const projected = useRef(new Float32Array(model.count * 3));
  const palette = useRef<Palette | null>(null);
  const frameRequest = useRef(0);
  const velocity = useRef({ x: 0, y: 0 });
  const drag = useRef<{ x: number; y: number; startX: number; startY: number; t: number; moved: boolean } | null>(null);
  const timing = useRef({ avg: 0 });
  const [hovered, setHovered] = useState<{ index: number; x: number; y: number } | null>(null);
  const [announce, setAnnounce] = useState("");

  const selectedIndex = useMemo(() => {
    if (!selected) return -1;
    return model.residues.findIndex((r) => !r.hetero && r.chain === selected.chain && r.resseq === selected.resseq);
  }, [model, selected]);

  const camera = useCallback((): Camera => {
    const { width, height: h } = size.current;
    const base = fitScale(model.radius, width, h);
    return { rotation: rotation.current, distance: model.radius * 4 + 10, width, height: h, scale: base * zoom.current };
  }, [model]);

  const anchorOf = useCallback(
    (index: number): number => {
      const r = model.residues[index];
      return r.ca !== -1 ? r.ca : r.atoms[0];
    },
    [model],
  );

  const draw = useCallback(() => {
    frameRequest.current = 0;
    const c = canvas.current;
    if (!c || size.current.width === 0) return;
    const ctx = c.getContext("2d");
    if (!ctx) return;
    if (!palette.current && wrap.current) palette.current = readPalette(wrap.current);
    const t0 = performance.now();
    if (projected.current.length !== model.count * 3) projected.current = new Float32Array(model.count * 3);
    const frame = prepareFrame(model, camera(), projected.current);
    const p = projected.current;
    const at = (index: number) => {
      const a = anchorOf(index);
      return { x: p[a * 3], y: p[a * 3 + 1] };
    };
    paintFrame(ctx, frame, palette.current as Palette, size.current, {
      selected: selectedIndex >= 0 ? [at(selectedIndex)] : [],
      hovered: hovered && hovered.index !== selectedIndex ? at(hovered.index) : null,
    });
    const ms = performance.now() - t0;
    timing.current.avg = timing.current.avg ? timing.current.avg * 0.9 + ms * 0.1 : ms;
    c.dataset.frameMs = timing.current.avg.toFixed(2);
  }, [model, camera, anchorOf, selectedIndex, hovered]);

  // The pending frame always draws with the latest state, whenever it was asked for.
  const drawRef = useRef(draw);
  drawRef.current = draw;
  const invalidate = useCallback(() => {
    if (frameRequest.current) return;
    frameRequest.current = requestAnimationFrame(() => drawRef.current());
  }, []);

  useEffect(() => {
    invalidate();
  }, [draw, invalidate]);

  useEffect(
    () => () => {
      if (frameRequest.current) cancelAnimationFrame(frameRequest.current);
    },
    [],
  );

  // A new entry starts from the file's orientation, fitted.
  useEffect(() => {
    rotation.current = identity();
    zoom.current = 1;
    velocity.current = { x: 0, y: 0 };
  }, [model]);

  // Size the backing store to the element and the display's pixel ratio.
  useEffect(() => {
    const c = canvas.current;
    if (!c || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(() => {
      const rect = c.getBoundingClientRect();
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      size.current = { width: rect.width, height: rect.height, dpr };
      c.width = Math.max(1, Math.round(rect.width * dpr));
      c.height = Math.max(1, Math.round(rect.height * dpr));
      invalidate();
    });
    ro.observe(c);
    return () => ro.disconnect();
  }, [invalidate]);

  // Repaint in the new colours when the theme changes.
  useEffect(() => {
    const refresh = () => {
      palette.current = null;
      invalidate();
    };
    const mo = new MutationObserver(refresh);
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    const mq = typeof window.matchMedia === "function" ? window.matchMedia("(prefers-color-scheme: dark)") : null;
    mq?.addEventListener("change", refresh);
    return () => {
      mo.disconnect();
      mq?.removeEventListener("change", refresh);
    };
  }, [invalidate]);

  // The wheel listener must not be passive, or the page scrolls instead of the model zooming.
  useEffect(() => {
    const c = canvas.current;
    if (!c) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const factor = Math.exp(-e.deltaY * (e.deltaMode === 1 ? 0.05 : 0.0015));
      zoom.current = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, zoom.current * factor));
      invalidate();
    };
    c.addEventListener("wheel", onWheel, { passive: false });
    return () => c.removeEventListener("wheel", onWheel);
  }, [invalidate]);

  const coast = useCallback(() => {
    const v = velocity.current;
    if (reduced || drag.current || (Math.abs(v.x) < 0.05 && Math.abs(v.y) < 0.05)) return;
    rotation.current = dragRotate(rotation.current, v.x, v.y);
    v.x *= 0.92;
    v.y *= 0.92;
    drawRef.current();
    requestAnimationFrame(coast);
  }, [reduced]);

  const pickAt = useCallback(
    (clientX: number, clientY: number): number => {
      const c = canvas.current;
      if (!c) return -1;
      const rect = c.getBoundingClientRect();
      const atom = pick(projected.current, model.pickable, clientX - rect.left, clientY - rect.top, PICK_PX);
      return atom === -1 ? -1 : model.residueOf[atom];
    },
    [model],
  );

  const choose = useCallback(
    (index: number) => {
      const r = index >= 0 ? model.residues[index] : null;
      onSelect?.(r);
      setAnnounce(r ? `Selected ${residueLabel(r)}` : "Selection cleared");
      invalidate();
    },
    [model, onSelect, invalidate],
  );

  const onPointerDown = (e: PointerEvent<HTMLCanvasElement>) => {
    e.currentTarget.setPointerCapture(e.pointerId);
    velocity.current = { x: 0, y: 0 };
    drag.current = { x: e.clientX, y: e.clientY, startX: e.clientX, startY: e.clientY, t: performance.now(), moved: false };
  };
  const onPointerMove = (e: PointerEvent<HTMLCanvasElement>) => {
    const d = drag.current;
    if (d) {
      const dx = e.clientX - d.x;
      const dy = e.clientY - d.y;
      if (Math.abs(e.clientX - d.startX) + Math.abs(e.clientY - d.startY) > 4) d.moved = true;
      rotation.current = dragRotate(rotation.current, dx, dy);
      const now = performance.now();
      const dt = Math.max(1, now - d.t);
      velocity.current = { x: (dx / dt) * 16, y: (dy / dt) * 16 };
      d.x = e.clientX;
      d.y = e.clientY;
      d.t = now;
      invalidate();
      return;
    }
    const index = pickAt(e.clientX, e.clientY);
    if (index === -1) {
      if (hovered) setHovered(null);
      return;
    }
    const rect = e.currentTarget.getBoundingClientRect();
    setHovered({ index, x: e.clientX - rect.left, y: e.clientY - rect.top });
  };
  const onPointerUp = (e: PointerEvent<HTMLCanvasElement>) => {
    const d = drag.current;
    drag.current = null;
    if (!d) return;
    if (!d.moved) {
      choose(pickAt(e.clientX, e.clientY));
      return;
    }
    // A drag that stopped before release does not coast.
    if (performance.now() - d.t > 80) velocity.current = { x: 0, y: 0 };
    requestAnimationFrame(coast);
  };

  const order = useMemo(() => {
    const hl = [...model.highlighted].sort((a, b) => a - b);
    if (hl.length) return hl;
    return model.residues.map((r, i) => (r.ca !== -1 ? i : -1)).filter((i) => i !== -1);
  }, [model]);

  const onKeyDown = (e: KeyboardEvent<HTMLCanvasElement>) => {
    const step = e.shiftKey ? FINE_STEP : KEY_STEP;
    let handled = true;
    switch (e.key) {
      case "ArrowLeft":
        rotation.current = multiply(rotationY(-step), rotation.current);
        break;
      case "ArrowRight":
        rotation.current = multiply(rotationY(step), rotation.current);
        break;
      case "ArrowUp":
        rotation.current = multiply(rotationX(-step), rotation.current);
        break;
      case "ArrowDown":
        rotation.current = multiply(rotationX(step), rotation.current);
        break;
      case "+":
      case "=":
        zoom.current = Math.min(MAX_ZOOM, zoom.current * 1.2);
        break;
      case "-":
      case "_":
        zoom.current = Math.max(MIN_ZOOM, zoom.current / 1.2);
        break;
      case "0":
        rotation.current = identity();
        zoom.current = 1;
        break;
      case "]":
      case "[": {
        if (!order.length) break;
        const at = order.indexOf(selectedIndex);
        const next =
          at === -1 ? (e.key === "]" ? 0 : order.length - 1) : (at + (e.key === "]" ? 1 : order.length - 1)) % order.length;
        choose(order[next]);
        break;
      }
      case "Escape":
        if (selectedIndex === -1) handled = false;
        else choose(-1);
        break;
      default:
        handled = false;
    }
    if (handled) {
      e.preventDefault();
      invalidate();
    }
  };

  const reset = () => {
    rotation.current = identity();
    zoom.current = 1;
    velocity.current = { x: 0, y: 0 };
    invalidate();
  };

  const polymer = model.residues.filter((r) => !r.hetero).length;
  const selectedResidue = selectedIndex >= 0 ? model.residues[selectedIndex] : null;
  const hoveredResidue = hovered ? model.residues[hovered.index] : null;

  return (
    <div className="viewer" ref={wrap} style={{ height }}>
      <div className="viewer-stage">
        <canvas
          ref={canvas}
          className="viewer-canvas"
          tabIndex={0}
          role="application"
          aria-roledescription="structure viewer"
          aria-label={`${coordinates.pdb_id}: alpha-carbon trace of ${formatCount(polymer)} residues${
            model.highlighted.size ? `, ${model.highlighted.size} highlighted with side chains` : ""
          }. Arrow keys rotate, plus and minus zoom, 0 resets, ] and [ step through residues.`}
          data-reduced-motion={reduced ? "true" : undefined}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerCancel={() => {
            drag.current = null;
          }}
          onPointerLeave={() => setHovered(null)}
          onKeyDown={onKeyDown}
        />
        {hoveredResidue && hovered ? (
          <span className="viewer-hover" style={{ left: hovered.x, top: hovered.y }} aria-hidden="true">
            {residueLabel(hoveredResidue)}
          </span>
        ) : null}
      </div>
      <div className="viewer-bar">
        <Citation citation={coordinates.citation} />
        <span className="font-mono muted">
          {formatCount(coordinates.count)} atoms · {formatCount(polymer)} residues · chain{model.chains.length === 1 ? "" : "s"}{" "}
          {model.chains.join(" ")}
          {coordinates.truncated ? " · polymer and ligand atoms only" : ""}
        </span>
        <span className="viewer-selected" aria-live="polite">
          {selectedResidue ? <span className="font-mono">{residueLabel(selectedResidue)}</span> : null}
          <span className="sr-only">{announce}</span>
        </span>
        <button type="button" className="btn btn-sm btn-quiet" onClick={reset}>
          <RotateCcw size={12} aria-hidden="true" />
          Reset view
        </button>
      </div>
    </div>
  );
}
