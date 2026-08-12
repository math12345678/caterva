/* ============================================================
   terrium — atlas camera

   viewBox animation, pointer panning, wheel and pinch zoom.
   The camera owns three published facts about itself:

     data-lod        which zoom level's detail is allowed to draw
     --atl-scale     how magnified the map currently is, so strokes
                     and type can be kept optically constant
     --atl-px, --atl-py   parallax offsets for the depth planes

   Everything visual reads those; nothing else needs the camera.
   ============================================================ */

import { ATLAS, ZOOM } from '../config/atlas.js';
import { prefersReducedMotion } from '../lib/dom.js';

const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
const easeInOut = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);

/* Zoom bounds expressed as viewBox width. Narrower box = closer in.
   The floor stops the reader zooming past legibility into a single
   stroke; the ceiling is the whole plate with a small margin. */
const MIN_W = 620;
const MAX_W = ATLAS.w * 1.06;

export class AtlasCamera {
  constructor(svg, host) {
    this.svg = svg;
    this.host = host;
    this.view = { ...ZOOM[0].frame };
    this.target = { ...this.view };
    this.raf = null;
    this.level = 'system';
    this.onLevel = null;
    /* Publish the level immediately. setLevel() short-circuits when the level
       is unchanged, so without this the attribute every level-of-detail rule
       keys off is simply absent on first paint, and the map opens showing all
       thirty module labels at once — the node cloud it exists to avoid. */
    this.host.dataset.lod = this.level;
    this.apply();
  }

  /* --- fitting -------------------------------------------------
     A frame is authored as a region of interest, not as a viewBox.
     With preserveAspectRatio="meet" the browser letterboxes, which
     means the authored frame is a *minimum* — so it must be grown
     on the short axis to match the viewport, or the map drifts off
     centre on wide screens. */
  fit(frame) {
    const r = this.host.getBoundingClientRect();
    const va = r.width / Math.max(1, r.height);
    if (!Number.isFinite(va) || va <= 0) return { ...frame };
    const fa = frame.w / frame.h;
    const out = { ...frame };
    if (fa < va) {
      const w = frame.h * va;
      out.x = frame.x - (w - frame.w) / 2;
      out.w = w;
    } else {
      const h = frame.w / va;
      out.y = frame.y - (h - frame.h) / 2;
      out.h = h;
    }
    return out;
  }

  apply() {
    const v = this.view;
    this.svg.setAttribute('viewBox', `${v.x} ${v.y} ${v.w} ${v.h}`);

    /* Optical compensation. Zooming a viewBox scales strokes and glyphs
       with it, so a hairline becomes a bar and 10px type becomes a
       headline. Publishing the scale lets CSS divide it back out, which
       is what keeps the notation looking drawn rather than blown up. */
    const scale = ZOOM[0].frame.w / Math.max(1, v.w);
    this.host.style.setProperty('--atl-scale', String(Math.round(scale * 1000) / 1000));

    /* Parallax from the camera centre, in fractions of the plate. Kept
       small: depth should be felt, not noticed. Disabled entirely under
       reduced motion, where drifting planes are the problem. */
    if (!prefersReducedMotion()) {
      const cx = (v.x + v.w / 2) / ATLAS.w - 0.5;
      const cy = (v.y + v.h / 2) / ATLAS.h - 0.5;
      this.host.style.setProperty('--atl-px', `${(-cx * 46).toFixed(2)}px`);
      this.host.style.setProperty('--atl-py', `${(-cy * 30).toFixed(2)}px`);
    }
  }

  /** Nearest authored zoom level for the current width — drives LOD.
   *
   *  The comparison is against each level's FITTED width, not its authored
   *  one. fit() grows a frame on its short axis to match the stage, so on a
   *  wide, short stage the authored numbers and the live viewBox are in
   *  different spaces: at 1728x1117 the LAYERS frame fits to 3491 units,
   *  which is nearer SYSTEM's authored 3680 than LAYERS' own authored 2560.
   *  Inferring from authored widths therefore reported `system` for a reader
   *  who had just pressed LAYERS — the button lit, the camera moved, and the
   *  level-of-detail rules kept the module labels hidden and the region jump
   *  list switched off, so the map appeared to ignore the press. It was
   *  correct at 1440x900 and below, which is why it survived earlier passes.
   */
  levelForWidth(w) {
    let best = ZOOM[0], bestD = Infinity;
    for (const z of ZOOM) {
      const fw = clamp(this.fit(z.frame).w, MIN_W, MAX_W);
      const d = Math.abs(Math.log(fw / w));
      if (d < bestD) { bestD = d; best = z; }
    }
    return best;
  }

  setLevel(id, { silent = false } = {}) {
    if (this.level === id) return;
    this.level = id;
    this.host.dataset.lod = id;
    if (!silent && this.onLevel) this.onLevel(id);
  }

  /** Animate to a frame. `immediate` snaps, used on resize and boot.
   *  `level` names the destination when the caller already knows it. */
  moveTo(frame, immediate = false, level = null) {
    /* Keep the frame AS AUTHORED, separately from the fitted result. fit()
       grows a frame on its short axis to match the viewport, so re-fitting an
       already-fitted frame compounds that growth — on every resize event the
       camera would creep outward until the architecture was a speck in the
       middle of empty substrate. refit() reads this, not `target`. */
    this.authored = { ...frame };
    const fitted = this.fit(frame);
    fitted.w = clamp(fitted.w, MIN_W, MAX_W);
    this.target = fitted;

    /* A named destination is taken at its word; only a free gesture has to
       have its level guessed from the resulting width. On a very wide stage
       the guess cannot succeed even in fitted space: at 2560x1440 both SYSTEM
       and LAYERS grow past MAX_W and clamp to the same 4028 units, so the two
       levels become genuinely indistinguishable by width and LAYERS reported
       `system`. Width is the right inference for a wheel or a pinch, where
       there is no intent to consult — but when the reader has pressed a
       button labelled LAYERS, the level is already known and inferring it
       can only lose information. */
    this.setLevel(level || this.levelForWidth(fitted.w).id);

    if (immediate || prefersReducedMotion()) {
      this.view = { ...fitted };
      this.apply();
      return;
    }

    const from = { ...this.view };
    const t0 = performance.now();
    /* Longer travel for longer distance: a jump across the plate that
       takes the same time as a nudge reads as a cut, and the reader
       loses their place on the map. */
    const span = Math.abs(from.x - fitted.x) + Math.abs(from.w - fitted.w);
    const dur = clamp(760 + span * 0.22, 760, 1750);

    cancelAnimationFrame(this.raf);
    const step = (now) => {
      const t = clamp((now - t0) / dur, 0, 1);
      const e = easeInOut(t);
      this.view = {
        x: from.x + (fitted.x - from.x) * e,
        y: from.y + (fitted.y - from.y) * e,
        w: from.w + (fitted.w - from.w) * e,
        h: from.h + (fitted.h - from.h) * e
      };
      this.apply();
      if (t < 1) this.raf = requestAnimationFrame(step);
    };
    this.raf = requestAnimationFrame(step);
  }

  /** Go to a named zoom level. */
  goLevel(id, immediate = false) {
    const z = ZOOM.find((l) => l.id === id) || ZOOM[0];
    /* Pass the level through: this is the one caller that knows it for
       certain, and the width it produces may not identify it. */
    this.moveTo(z.frame, immediate, z.id);
    return z;
  }

  /** Frame a box with padding, clamped so the camera cannot leave the plate.
   *
   *  `atLeast` names the shallowest level the result is allowed to be read as.
   *  Descending into a region is the caller that needs it: the level is what
   *  makes the modules inside hit-testable, and on a very wide stage a single
   *  region can fit to a width that clamps against MAX_W and is therefore
   *  indistinguishable from SYSTEM. At 2560x1440 clicking the Trust Layer
   *  plate zoomed in correctly and then reported `system`, so the reader
   *  arrived inside a region with its modules still inert and the seven region
   *  plates still holding the tab order — a descent that visibly happened and
   *  functionally did not.
   */
  frameBox(box, pad = 220, atLeast = null) {
    const w = Math.max(box.w + pad * 2, MIN_W);
    const h = Math.max(box.h + pad * 2, 380);
    const cx = box.x + box.w / 2;
    const cy = box.y + box.h / 2;
    let level = null;
    if (atLeast) {
      const inferred = this.levelForWidth(clamp(this.fit({ x: cx - w / 2, y: cy - h / 2, w, h }).w, MIN_W, MAX_W)).id;
      /* Take whichever is deeper — the floor is a floor, not an override: a
         region tight enough to warrant AGENTS must still be allowed to say so. */
      const order = ZOOM.map((z) => z.id);
      level = order.indexOf(inferred) >= order.indexOf(atLeast) ? inferred : atLeast;
    }
    this.moveTo({ x: cx - w / 2, y: cy - h / 2, w, h }, false, level);
  }

  /** Re-fit after a resize, without animating. */
  refit() {
    /* Only an authored frame can be safely re-fitted. After a free pan or a
       wheel zoom there is no authored frame to return to — the reader put the
       camera where it is, and snapping them back to the last button they
       pressed would discard their navigation. In that case the view is simply
       left alone; it is still valid, just no longer a named frame. */
    if (!this.authored) return;
    const fitted = this.fit(this.authored);
    fitted.w = clamp(fitted.w, MIN_W, MAX_W);
    this.target = fitted;
    this.view = { ...fitted };
    this.apply();
  }

  /* --- panning -------------------------------------------------
     Pointer events only, so mouse, pen and touch share one path.
     Panning converts screen pixels to atlas units through the live
     viewBox, which is what makes the drag feel pinned to the map at
     every zoom level rather than accelerating as you zoom in. */
  installPan() {
    const svg = this.svg;
    let dragging = false, id = null, sx = 0, sy = 0, start = null, moved = 0, captured = false;

    const unitsPerPx = () => {
      const r = this.host.getBoundingClientRect();
      return this.view.w / Math.max(1, r.width);
    };

    svg.addEventListener('pointerdown', (e) => {
      if (e.button !== undefined && e.button !== 0) return;
      /* Never steal the gesture from a module: the primary interaction is
         inspection, and a map that swallows clicks feels broken. */
      if (e.target.closest('.atl-node')) return;
      dragging = true; id = e.pointerId; moved = 0; captured = false;
      sx = e.clientX; sy = e.clientY;
      start = { ...this.view };
      cancelAnimationFrame(this.raf);
      /* Capture is deliberately NOT taken here. A captured pointer sends its
         click to the capture element, so grabbing the pointer on every press
         retargeted every click to the <svg> itself — which silently broke the
         region plates, whose whole job at SYSTEM zoom is to be clicked. They
         hovered correctly and reported the right elementFromPoint, so the
         failure looked like a missing handler rather than a stolen event.
         Capture is taken below, on the first move past the drag threshold,
         where it is actually needed: to keep receiving moves if the pointer
         leaves the frame mid-pan. A press that never moves stays an ordinary
         click on whatever is underneath it. */
    });

    svg.addEventListener('pointermove', (e) => {
      if (!dragging || e.pointerId !== id) return;
      const k = unitsPerPx();
      const dx = (e.clientX - sx) * k;
      const dy = (e.clientY - sy) * k;
      moved = Math.max(moved, Math.abs(e.clientX - sx) + Math.abs(e.clientY - sy));
      /* Past the threshold this is a pan, not a click. Now take the pointer,
         and now show the grabbing cursor — both of which would be wrong on a
         press that turns out to be a plain click. */
      if (!captured && moved > 6) {
        captured = true;
        this.host.classList.add('is-panning');
        try { svg.setPointerCapture(id); } catch { /* capture is a nicety */ }
      }
      this.view = {
        x: clamp(start.x - dx, -600, ATLAS.w - this.view.w + 600),
        y: clamp(start.y - dy, -500, ATLAS.h - this.view.h + 500),
        w: start.w, h: start.h
      };
      this.target = { ...this.view };
      this.authored = null;   // the reader owns the camera now
      this.apply();
    });

    const end = (e) => {
      if (!dragging || (e && e.pointerId !== id)) return;
      dragging = false;
      captured = false;
      this.host.classList.remove('is-panning');
      /* A drag that ended on a module must not also open it. */
      if (moved > 6) this.host.dataset.dragged = '1';
      else delete this.host.dataset.dragged;
      setTimeout(() => { delete this.host.dataset.dragged; }, 80);
    };
    svg.addEventListener('pointerup', end);
    svg.addEventListener('pointercancel', end);
    svg.addEventListener('lostpointercapture', end);
  }

  /* --- wheel zoom ----------------------------------------------
     Zoom toward the cursor, not the centre. Zooming to centre forces
     the reader to zoom-then-pan repeatedly to reach anything, which is
     the difference between a map and a slideshow. */
  installWheel() {
    this.svg.addEventListener('wheel', (e) => {
      /* Only claim the wheel when the reader is deliberately zooming.
         Otherwise the atlas would trap the page scroll and the visitor
         could not get past the section — a genuinely hostile pattern. */
      const zoomIntent = e.ctrlKey || e.metaKey || this.host.classList.contains('is-engaged');
      if (!zoomIntent) return;
      e.preventDefault();
      cancelAnimationFrame(this.raf);

      const r = this.host.getBoundingClientRect();
      const fx = clamp((e.clientX - r.left) / Math.max(1, r.width), 0, 1);
      const fy = clamp((e.clientY - r.top) / Math.max(1, r.height), 0, 1);
      const ax = this.view.x + fx * this.view.w;
      const ay = this.view.y + fy * this.view.h;

      const k = Math.exp(e.deltaY * 0.0016);
      const w = clamp(this.view.w * k, MIN_W, MAX_W);
      const h = w * (this.view.h / this.view.w);

      this.view = { x: ax - fx * w, y: ay - fy * h, w, h };
      this.target = { ...this.view };
      this.authored = null;
      this.setLevel(this.levelForWidth(w).id);
      this.apply();
    }, { passive: false });
  }

  /* --- pinch ---------------------------------------------------
     Two-finger scale on touch. Kept separate from pan so a pinch is
     never interpreted as a drag mid-gesture. */
  installPinch() {
    const pts = new Map();
    let base = null;
    const svg = this.svg;

    const spread = () => {
      const [a, b] = [...pts.values()];
      return Math.hypot(b.x - a.x, b.y - a.y);
    };

    svg.addEventListener('pointerdown', (e) => {
      if (e.pointerType !== 'touch') return;
      pts.set(e.pointerId, { x: e.clientX, y: e.clientY });
      if (pts.size === 2) base = { d: spread(), view: { ...this.view } };
    });
    svg.addEventListener('pointermove', (e) => {
      if (e.pointerType !== 'touch' || !pts.has(e.pointerId)) return;
      pts.set(e.pointerId, { x: e.clientX, y: e.clientY });
      if (pts.size !== 2 || !base) return;
      e.preventDefault();
      const k = base.d / Math.max(1, spread());
      const w = clamp(base.view.w * k, MIN_W, MAX_W);
      const h = w * (base.view.h / base.view.w);
      const cx = base.view.x + base.view.w / 2;
      const cy = base.view.y + base.view.h / 2;
      this.view = { x: cx - w / 2, y: cy - h / 2, w, h };
      this.target = { ...this.view };
      this.authored = null;
      this.setLevel(this.levelForWidth(w).id);
      this.apply();
    }, { passive: false });
    const drop = (e) => {
      pts.delete(e.pointerId);
      if (pts.size < 2) base = null;
    };
    svg.addEventListener('pointerup', drop);
    svg.addEventListener('pointercancel', drop);
  }

  install() {
    this.installPan();
    this.installWheel();
    this.installPinch();
    window.addEventListener('resize', () => this.refit());
  }
}
