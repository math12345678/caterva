/* ============================================================
   caterva — choreography
   Maps run-state to the rendered architecture. Every class here
   corresponds to a pipeline event, never to decoration.
   ============================================================ */

import { qs, qsa, prefersReducedMotion } from '../lib/dom.js';
import {
  STAGES, RAIL, FRAMES, STAGE, ARRAY_MODULES, EVIDENCE, PARAMETERS,
  SENTINELS, QUESTION_CHAMBER, MOBILE_JOURNEY, MOBILE_STATION
} from '../config/architecture.js';

/** Narrow viewports walk the architecture as close upright stations. */
const isNarrow = () => window.matchMedia('(max-width: 48rem)').matches;
const STATION = Object.fromEntries(MOBILE_JOURNEY.map((m) => [m.id, m]));

const STAGE_IDS = STAGES.map((st) => st.id);
const reached = (idx, id) => idx >= STAGE_IDS.indexOf(id);

/** Sentinel visual state per run position. */
function sentinelState(sen, idx) {
  const own = STAGE_IDS.indexOf(sen.activeAt);
  if (idx > own) return sen.result.status === 'review' ? 'review' : 'resolved';
  if (idx === own) return sen.result.status === 'review' ? 'review' : 'resolved';
  if (idx === own - 1) return 'scanning';
  return 'idle';
}

export class Choreographer {
  constructor({ svg, stageEl, railEl, logEl, vaultLineEl }) {
    this.svg = svg;
    this.stageEl = stageEl;
    this.railEl = railEl;
    this.logEl = logEl;
    this.vaultLineEl = vaultLineEl;
    this.camera = qs('.camera', svg);
    this.currentFrame = null;
    this.viewBox = null;
    this.camRaf = null;
    this.buildRail();
    this.resetCamera();

    // Re-fit framing on resize so the composition is never cropped.
    let rt;
    window.addEventListener('resize', () => {
      clearTimeout(rt);
      rt = setTimeout(() => {
        if (this.currentFrame) this.moveCamera(this.currentFrame, true);
      }, 140);
    });
  }

  /* ---------- progress rail ---------- */
  buildRail() {
    this.railEl.replaceChildren(
      ...RAIL.map((step) => {
        const el = document.createElement('div');
        el.className = 'rail-step';
        el.setAttribute('role', 'listitem');
        el.dataset.rail = step.id;
        el.dataset.state = 'pending';
        el.innerHTML =
          `<span class="rail-step__pip" aria-hidden="true"></span>` +
          `<span class="rail-step__label">${step.label}</span>`;
        return el;
      })
    );
  }

  updateRail(idx) {
    const currentRail = STAGES[idx]?.rail;
    const railOrder = RAIL.map((r) => r.id);
    const currentPos = railOrder.indexOf(currentRail);
    qsa('.rail-step', this.railEl).forEach((el) => {
      const pos = railOrder.indexOf(el.dataset.rail);
      let state = 'pending';
      if (currentPos >= 0) {
        if (pos < currentPos) state = 'done';
        else if (pos === currentPos) state = 'current';
      }
      el.dataset.state = state;
      el.setAttribute('aria-current', state === 'current' ? 'step' : 'false');
    });
  }

  /* ---------- camera ----------
     The cathedral is far taller than any viewport, so framing is done
     by animating the SVG viewBox. Each frame is fitted to the container's
     real aspect ratio so nothing is ever cropped unintentionally.
  ---------------------------------------------------------------- */
  fitFrame(f) {
    const rect = this.svg.getBoundingClientRect();
    const aspect = (rect.width || 16) / (rect.height || 9);
    let w = f.w;
    let h = f.h;
    if (w / h < aspect) w = h * aspect;
    else h = w / aspect;
    const cx = f.x + f.w / 2;
    const cy = f.y + f.h / 2;
    return { x: cx - w / 2, y: cy - h / 2, w, h };
  }

  /** Wide framing cannot render 8px instrument text legibly, so annotation
      swaps to monumental tier titles. See .tier-title in cathedral.css. */
  setLod(frameId) {
    this.svg.dataset.lod = frameId === 'full' ? 'wide' : 'close';
  }

  /** Depth parallax. The distant layer lags the camera by a fraction of its
      vertical travel, which is what makes the monument read as sitting in a
      space rather than being drawn on one plane. Desktop only — the CSS gates
      the transform, so this property is simply ignored elsewhere. */
  setParallax(vb) {
    const centre = vb.y + vb.h / 2;
    const offset = (centre - STAGE.h / 2) * 0.055;
    this.svg.style.setProperty('--parallax', `${offset.toFixed(1)}px`);
  }

  moveCamera(frameId, immediate = false) {
    const f = FRAMES[frameId] || STATION[frameId]?.frame || this.adhoc?.[frameId] || FRAMES.full;
    if (frameId === this.currentFrame && !immediate) return;
    this.currentFrame = frameId;
    this.setLod(frameId);
    const target = this.fitFrame(f);

    if (immediate || prefersReducedMotion()) {
      this.viewBox = target;
      this.svg.setAttribute('viewBox', `${target.x} ${target.y} ${target.w} ${target.h}`);
      this.setParallax(target);
      return;
    }

    const from = this.viewBox || this.fitFrame(FRAMES.full);
    const start = performance.now();
    // The phone itinerary has eleven stops where the desktop has six frames,
    // but the run's stages are the same 1300-1900ms apart. At the desktop's
    // 1400ms a move is always cut off by the next one, so the camera drifts
    // continuously and never arrives — measured at 14.9s of movement in a 19s
    // run, including one unbroken 7s pan across the whole vault. A shorter
    // flight arrives with time to spare, so each station is still while its
    // state resolves. Stillness at the stop, not slowness in transit, is what
    // makes the sequence read as deliberate.
    const dur = isNarrow() ? 620 : 1400;
    const ease = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);

    if (this.camRaf) cancelAnimationFrame(this.camRaf);
    const tick = (now) => {
      const t = Math.min(1, (now - start) / dur);
      const e = ease(t);
      const vb = {
        x: from.x + (target.x - from.x) * e,
        y: from.y + (target.y - from.y) * e,
        w: from.w + (target.w - from.w) * e,
        h: from.h + (target.h - from.h) * e
      };
      this.viewBox = vb;
      this.svg.setAttribute('viewBox', `${vb.x} ${vb.y} ${vb.w} ${vb.h}`);
      this.setParallax(vb);
      if (t < 1) this.camRaf = requestAnimationFrame(tick);
    };
    this.camRaf = requestAnimationFrame(tick);
  }

  /** Re-fit the current frame to the container's present size. Used when the
      inspector reserves part of the drawing field, and by the resize handler. */
  refit() {
    if (this.currentFrame) this.moveCamera(this.currentFrame, true);
  }

  /* ---------- framing a single object ----------
     On a phone the bottom sheet leaves a shallow band of architecture above
     it, and the object being inspected is very often not in that band: the
     record was measured framing the vault while the sheet described a
     sentinel 500 units above the visible edge, so the promise that the
     structure stays visible behind the sheet was not kept.

     So inspecting an object on a phone moves the camera to that object. The
     frame is derived from the node's own bounding box in stage units, padded
     so the object reads as sitting inside architecture rather than filling
     the band alone. */
  frameNode(id) {
    const el = qs(`[data-node="${id}"]`, this.svg);
    if (!el || typeof el.getBBox !== 'function') return false;
    let bb;
    try { bb = el.getBBox(); } catch { return false; }
    if (!bb || !bb.width || !bb.height) return false;

    // Enough context that the object is legibly part of a structure, and a
    // floor on the frame so a small node is not magnified past its detail.
    const pad = 120;
    const w = Math.max(bb.width + pad * 2, 430);
    const h = Math.max(bb.height + pad * 2, 220);
    const cx = bb.x + bb.width / 2;
    const cy = bb.y + bb.height / 2;

    this.returnFrame = this.returnFrame || this.currentFrame;
    this.adhoc = this.adhoc || {};
    this.adhoc.inspect = { x: cx - w / 2, y: cy - h / 2, w, h };
    // Force the move even if the id matches, because the geometry has changed.
    this.currentFrame = null;
    this.moveCamera('inspect');
    return true;
  }

  /** Return to whatever the run was framing before the inspection. */
  releaseNodeFrame() {
    if (!this.returnFrame) return;
    const back = this.returnFrame;
    this.returnFrame = null;
    this.currentFrame = null;
    this.moveCamera(back);
  }

  resetCamera() {
    if (this.camRaf) cancelAnimationFrame(this.camRaf);
    this.currentFrame = 'full';
    this.setLod('full');
    this.viewBox = this.fitFrame(FRAMES.full);
    const vb = this.viewBox;
    this.svg.setAttribute('viewBox', `${vb.x} ${vb.y} ${vb.w} ${vb.h}`);
    this.setParallax(vb);
  }

  /* ---------- main state application ---------- */
  apply(idx, question) {
    const svg = this.svg;
    const stage = this.stageEl;

    // --- question chamber ---
    const chamber = qs('[data-node="question-chamber"]', svg);
    if (chamber) {
      chamber.dataset.state = reached(idx, 'questionAccepted')
        ? (reached(idx, 'modelSelected') ? 'locked' : 'active')
        : 'dormant';
    }

    // Quantities lifted out of the sentence. The interpretation step is the
    // hard part of the pipeline; showing it keeps the run honest.
    svg.classList.toggle('is-parsed', reached(idx, 'conceptsIsolated'));

    // --- interpretation array ---
    ARRAY_MODULES.forEach((mod) => {
      const el = qs(`[data-module="${mod.id}"]`, svg);
      if (!el) return;
      const own = STAGE_IDS.indexOf(mod.activeAt);
      el.dataset.state = idx > own ? 'locked' : idx === own ? 'active' : 'dormant';
    });

    // --- evidence objects: routed travel then dock ---
    const evLive = reached(idx, 'literatureRetrieved');
    svg.classList.toggle('is-evidence-live', evLive);
    EVIDENCE.forEach((ev, i) => {
      const el = qs(`[data-evidence="${ev.id}"]`, svg);
      if (!el) return;
      const carrier = qs('.ev-carrier', el);
      el.classList.toggle('is-live', evLive);
      if (evLive) {
        const docked = reached(idx, 'configurationBuilt') || prefersReducedMotion();
        if (docked) {
          carrier.style.transitionDelay = `${i * 150}ms`;
          carrier.setAttribute('transform', `translate(${ev.dock.x} ${ev.dock.y})`);
          el.classList.add('is-docked');
        } else {
          carrier.setAttribute('transform', `translate(${ev.origin.x} ${ev.origin.y})`);
          el.classList.remove('is-docked');
        }
      } else {
        carrier.setAttribute('transform', `translate(${ev.origin.x} ${ev.origin.y})`);
        el.classList.remove('is-docked');
      }
    });

    // --- configuration assembly: parameters snap into berths ---
    const configured = reached(idx, 'configurationBuilt');
    svg.classList.toggle('is-configured', configured);
    PARAMETERS.forEach((p, i) => {
      const el = qs(`[data-param="${p.id}"]`, svg);
      if (!el) return;
      if (configured) {
        const param = qs('.param', el);
        param.style.transitionDelay = `${i * 110}ms`;
        el.classList.add('is-filled');
      } else {
        el.classList.remove('is-filled');
        const param = qs('.param', el);
        param.style.transitionDelay = '0ms';
      }
    });

    // --- spine flow: active while the system is working ---
    const flowing = reached(idx, 'questionAccepted') && !reached(idx, 'recordReleased');
    svg.classList.toggle('is-flowing', flowing);

    // --- simulation core ---
    svg.classList.toggle('is-executed', reached(idx, 'simulationExecuted'));
    svg.classList.toggle('is-envelope-shown', reached(idx, 'correctnessChecked'));

    // --- vault + sentinels ---
    svg.classList.toggle('is-verifying', reached(idx, 'simulationExecuted'));
    svg.classList.toggle('is-traced', reached(idx, 'hallucinationChecked'));
    svg.classList.toggle('is-critiqued', reached(idx, 'critiqueCompleted'));
    svg.classList.toggle('is-verified', reached(idx, 'polishCompleted'));
    SENTINELS.forEach((sen) => {
      const el = qs(`[data-sentinel="${sen.id}"]`, svg);
      if (el) el.dataset.state = sentinelState(sen, idx);
    });

    const vaultNode = qs('.vault-node', svg);
    if (vaultNode) vaultNode.dataset.state = reached(idx, 'polishCompleted') ? 'locked' : reached(idx, 'simulationExecuted') ? 'active' : 'dormant';
    const asmNode = qs('.assembly-node', svg);
    if (asmNode) asmNode.dataset.state = configured ? 'locked' : 'dormant';

    // --- record release ---
    svg.classList.toggle('is-released', reached(idx, 'recordReleased'));

    // --- teal bloom, only at completion moments ---
    if (reached(idx, 'polishCompleted') && !this._bloomed) {
      this._bloomed = true;
      const bloom = qs('.bloom', svg);
      if (bloom && !prefersReducedMotion()) {
        bloom.classList.add('is-firing');
        setTimeout(() => bloom.classList.remove('is-firing'), 1600);
      }
    }
    if (idx < STAGE_IDS.indexOf('polishCompleted')) this._bloomed = false;

    // --- vault statement appears at the intellectual centre ---
    const showLine = reached(idx, 'simulationExecuted') && !reached(idx, 'recordReleased');
    this.vaultLineEl.classList.toggle('is-shown', showLine);

    // --- HUD ---
    this.updateRail(idx);
    const st = STAGES[idx];
    if (st) this.logEl.textContent = st.log;
    stage.dataset.stage = st ? st.id : 'idle';

    // --- camera framing ---
    // Reduced motion: hold the whole architecture in view and let the
    // state changes themselves carry the narrative.
    // Narrow viewports follow the mobile itinerary instead, so each
    // station arrives close enough to read.
    if (prefersReducedMotion()) {
      if (isNarrow() && st) {
        const station = MOBILE_STATION[st.id];
        if (station) this.moveCamera(station, true);
      } else if (this.currentFrame !== 'full') {
        this.resetCamera();
      }
    } else if (isNarrow()) {
      const station = st ? MOBILE_STATION[st.id] : null;
      this.moveCamera(station || 'full');
    } else {
      this.moveCamera(st?.camera || 'full');
    }
  }

  /** Completed composition: pull back to the full architecture.
      On a phone the whole is unreadable, so we rest on the record the
      run just produced and let the journey control do the travelling. */
  settle() {
    if (isNarrow()) {
      this.moveCamera('m-record', prefersReducedMotion());
      return;
    }
    if (!prefersReducedMotion()) {
      setTimeout(() => this.moveCamera('full'), 900);
    }
  }

  reset() {
    this._bloomed = false;
    this.resetCamera();
    const chamber = qs('[data-node="question-chamber"]', this.svg);
    if (chamber) chamber.dataset.state = 'dormant';
  }
}

export { QUESTION_CHAMBER };
