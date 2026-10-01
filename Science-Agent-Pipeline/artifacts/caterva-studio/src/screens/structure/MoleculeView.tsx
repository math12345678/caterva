/**
 * The 3D view of a PDB entry: every atom of the first model as a dot, the
 * catalytic residues `caterva prepare` placed in the signal colour, bound
 * ligands in the caution colour, waters hidden unless asked for.
 *
 * Dots, not cartoons: a cartoon is a secondary-structure assignment the
 * page would have to compute and the tools do not, while the atoms are
 * exactly what the file holds. The dotted look is also the mark's.
 *
 * Keyboard first: the canvas takes focus; arrow keys turn it, + and - zoom,
 * 0 resets, and each catalytic residue in the list beside it is a button
 * that centres the view on it. Without WebGL (some virtual machines, tests)
 * the view says so and the residue list still stands.
 */
import { Canvas, useThree } from "@react-three/fiber";
import { type KeyboardEvent, type PointerEvent, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";

import type { CoordinatesResponse } from "@/api/types";

import { type ViewerModel, type ViewerPalette, buildModel, readPalette, residueName } from "./model";

const RADIUS = { polymer: 0.5, ligand: 0.62, water: 0.32, catalytic: 0.85 } as const;
const STEP = Math.PI / 18;

export function webglAvailable(): boolean {
  if (typeof document === "undefined") return false;
  if (typeof navigator !== "undefined" && /jsdom/i.test(navigator.userAgent)) return false;
  try {
    const canvas = document.createElement("canvas");
    return Boolean(canvas.getContext("webgl2") ?? canvas.getContext("webgl"));
  } catch {
    return false;
  }
}

/** The page's tokens as WebGL colours, re-read when the theme changes. */
function usePalette(): ViewerPalette {
  const [palette, setPalette] = useState<ViewerPalette>(() => readPalette());
  useEffect(() => {
    const update = () => setPalette(readPalette());
    const media = window.matchMedia?.("(prefers-color-scheme: dark)");
    media?.addEventListener?.("change", update);
    const observer = new MutationObserver(update);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme", "class"] });
    return () => {
      media?.removeEventListener?.("change", update);
      observer.disconnect();
    };
  }, []);
  return palette;
}

function Atoms({ model, palette, selected }: { model: ViewerModel; palette: ViewerPalette; selected: string | null }) {
  const mesh = useRef<THREE.InstancedMesh>(null);
  const invalidate = useThree((s) => s.invalidate);
  const count = model.roles.length;
  const geometry = useMemo(() => new THREE.IcosahedronGeometry(1, count > 20000 ? 0 : 1), [count]);
  const chainIndex = useMemo(() => {
    const order = new Map<string, number>();
    for (const c of model.chains) if (!order.has(c)) order.set(c, order.size);
    return order;
  }, [model]);

  useLayoutEffect(() => {
    const m = mesh.current;
    if (!m) return;
    const selectedAtoms = new Set(model.sites.find((s) => s.key === selected)?.atoms ?? []);
    const matrix = new THREE.Matrix4();
    const colour = new THREE.Color();
    for (let k = 0; k < count; k++) {
      const role = model.roles[k];
      const r = selectedAtoms.has(k) ? RADIUS.catalytic * 1.25 : RADIUS[role];
      matrix.makeScale(r, r, r);
      matrix.setPosition(model.positions[k * 3], model.positions[k * 3 + 1], model.positions[k * 3 + 2]);
      m.setMatrixAt(k, matrix);
      const rgb =
        role === "catalytic"
          ? palette.catalytic
          : role === "ligand"
            ? palette.ligand
            : role === "water"
              ? palette.water
              : (chainIndex.get(model.chains[k]) ?? 0) % 2 === 0
                ? palette.polymer
                : palette.polymerAlt;
      colour.setRGB(rgb[0], rgb[1], rgb[2], THREE.SRGBColorSpace);
      m.setColorAt(k, colour);
    }
    m.instanceMatrix.needsUpdate = true;
    if (m.instanceColor) m.instanceColor.needsUpdate = true;
    m.computeBoundingSphere();
    invalidate();
  }, [model, palette, selected, count, chainIndex, invalidate]);

  return (
    <instancedMesh ref={mesh} args={[geometry, undefined, count]}>
      <meshLambertMaterial />
    </instancedMesh>
  );
}

function Scene({
  model,
  palette,
  selected,
  rotation,
  distance,
}: {
  model: ViewerModel;
  palette: ViewerPalette;
  selected: string | null;
  rotation: THREE.Quaternion;
  distance: number;
}) {
  const { camera, invalidate, scene } = useThree();
  const centre = model.sites.find((s) => s.key === selected)?.centre ?? null;
  useEffect(() => {
    scene.background = new THREE.Color().setRGB(...palette.surface, THREE.SRGBColorSpace);
    invalidate();
  }, [palette, scene, invalidate]);
  useEffect(() => {
    camera.position.set(0, 0, distance);
    camera.lookAt(0, 0, 0);
    camera.updateProjectionMatrix();
    invalidate();
  }, [camera, distance, invalidate]);
  useEffect(() => invalidate(), [rotation, centre, invalidate]);
  return (
    <>
      <ambientLight intensity={1.4} />
      <directionalLight position={[1, 1.5, 2]} intensity={1.6} />
      <group quaternion={rotation}>
        <group position={centre ? [-centre[0], -centre[1], -centre[2]] : [0, 0, 0]}>
          <Atoms model={model} palette={palette} selected={selected} />
        </group>
      </group>
    </>
  );
}

export function MoleculeView({
  coords,
  selected,
  onSelect,
  height = 440,
}: {
  coords: CoordinatesResponse;
  selected: string | null;
  onSelect: (key: string | null) => void;
  height?: number;
}) {
  const [showWater, setShowWater] = useState(false);
  const model = useMemo(() => buildModel(coords, { showWater }), [coords, showWater]);
  const palette = usePalette();
  const [rotation, setRotation] = useState(() => new THREE.Quaternion());
  const home = model.extent * 2.7;
  const [distance, setDistance] = useState(home);
  const drag = useRef<{ x: number; y: number } | null>(null);
  const canDraw = useMemo(webglAvailable, []);

  useEffect(() => setDistance(selected ? Math.min(home, 26) : home), [selected, home]);

  const turn = (dx: number, dy: number) => {
    const q = new THREE.Quaternion()
      .setFromAxisAngle(new THREE.Vector3(0, 1, 0), dx)
      .multiply(new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(1, 0, 0), dy));
    setRotation((r) => q.multiply(r).normalize());
  };
  const zoom = (factor: number) => setDistance((d) => Math.min(home * 3, Math.max(8, d * factor)));

  const onKey = (e: KeyboardEvent<HTMLDivElement>) => {
    const keys: Record<string, () => void> = {
      ArrowLeft: () => turn(-STEP, 0),
      ArrowRight: () => turn(STEP, 0),
      ArrowUp: () => turn(0, -STEP),
      ArrowDown: () => turn(0, STEP),
      "+": () => zoom(0.85),
      "=": () => zoom(0.85),
      "-": () => zoom(1 / 0.85),
      "0": () => {
        setRotation(new THREE.Quaternion());
        onSelect(null);
        setDistance(home);
      },
    };
    const act = keys[e.key];
    if (act) {
      e.preventDefault();
      act();
    }
  };
  const onPointerDown = (e: PointerEvent<HTMLDivElement>) => {
    drag.current = { x: e.clientX, y: e.clientY };
    e.currentTarget.setPointerCapture(e.pointerId);
  };
  const onPointerMove = (e: PointerEvent<HTMLDivElement>) => {
    if (!drag.current) return;
    const dx = e.clientX - drag.current.x;
    const dy = e.clientY - drag.current.y;
    drag.current = { x: e.clientX, y: e.clientY };
    turn(dx * 0.008, dy * 0.008);
  };
  const onPointerUp = () => {
    drag.current = null;
  };

  const shownSites = model.sites;
  const missing = shownSites.filter((s) => s.atoms.length === 0);

  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_15rem]">
      <figure className="m-0 grid gap-2">
        {canDraw ? (
          <div
            className="viewer-canvas relative overflow-hidden rounded-[3px] border border-rule"
            style={{ height }}
            tabIndex={0}
            role="application"
            aria-roledescription="3D structure view"
            aria-label={`PDB ${coords.pdb_id}: ${model.roles.length} atoms. Arrow keys turn it, plus and minus zoom, 0 resets.`}
            onKeyDown={onKey}
            onPointerDown={onPointerDown}
            onPointerMove={onPointerMove}
            onPointerUp={onPointerUp}
            onPointerCancel={onPointerUp}
            onWheel={(e) => zoom(e.deltaY > 0 ? 1.08 : 1 / 1.08)}
          >
            <Canvas frameloop="demand" dpr={[1, 2]} camera={{ fov: 35, near: 0.5, far: 4000, position: [0, 0, home] }}>
              <Scene model={model} palette={palette} selected={selected} rotation={rotation} distance={distance} />
            </Canvas>
          </div>
        ) : (
          <div
            className="grid place-items-center rounded-[3px] border border-dashed border-rule p-6 text-center text-[13.5px] text-muted"
            style={{ minHeight: 160 }}
          >
            This browser gives the page no WebGL, so the {model.roles.length} atoms cannot be drawn here. The catalytic
            residues are listed beside it.
          </div>
        )}
        <figcaption className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 text-[12.5px] text-muted">
          <span>
            <span className="font-mono tabular-nums">{model.roles.length}</span> atoms of model 1, as the mmCIF gives
            them{coords.truncated && coords.omitted ? `; left out: ${coords.omitted}` : ""}.
          </span>
          {model.hiddenWater > 0 || showWater ? (
            <label className="inline-flex items-center gap-1.5">
              <input
                type="checkbox"
                className="accent-[var(--signal-deep)]"
                checked={showWater}
                onChange={(e) => setShowWater(e.target.checked)}
              />
              Show waters
              {!showWater ? (
                <span className="font-mono tabular-nums">({model.hiddenWater})</span>
              ) : null}
            </label>
          ) : null}
        </figcaption>
        <ul className="m-0 flex list-none flex-wrap gap-x-4 gap-y-1 p-0 text-[12.5px] text-muted" aria-label="Key">
          <li className="inline-flex items-center gap-1.5">
            <Dot colour="var(--signal)" /> catalytic residue (caterva prepare)
          </li>
          <li className="inline-flex items-center gap-1.5">
            <Dot colour="var(--caution)" /> bound ligand, ion or cofactor
          </li>
          <li className="inline-flex items-center gap-1.5">
            <Dot colour="var(--muted)" /> protein, chains in alternating tints
          </li>
        </ul>
      </figure>

      <div className="grid content-start gap-2">
        <h3 className="m-0 font-sans text-[13px] font-semibold">Catalytic residues</h3>
        {shownSites.length === 0 ? (
          <p className="m-0 text-[13px] text-muted">{coords.catalytic_reason ?? "None placed on this entry."}</p>
        ) : (
          <ul className="m-0 grid list-none gap-0.5 p-0">
            {shownSites.map((s) => (
              <li key={s.key}>
                <button
                  type="button"
                  aria-pressed={selected === s.key}
                  disabled={s.atoms.length === 0}
                  onClick={() => onSelect(selected === s.key ? null : s.key)}
                  className={
                    "grid w-full grid-cols-[auto_1fr] items-baseline gap-x-2 rounded-[3px] px-2 py-1 text-left text-[13px] " +
                    "hover:bg-surface-raised disabled:cursor-default disabled:opacity-60 aria-pressed:bg-surface-raised"
                  }
                >
                  <span className="font-mono tabular-nums">
                    {s.site.chain}·{residueName(s.site.resname, s.site.resseq)}
                  </span>
                  <span className="truncate text-muted" title={s.site.roles}>
                    {s.site.roles}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
        {missing.length > 0 ? (
          <p className="m-0 text-[12.5px] text-muted">
            {missing.length} of them have no atoms in this file (unmodelled or not conserved).
          </p>
        ) : null}
      </div>
    </div>
  );
}

function Dot({ colour }: { colour: string }) {
  return <span aria-hidden="true" className="inline-block size-2.5 rounded-full" style={{ background: colour }} />;
}
