/* ============================================================
   caterva — atlas controller

   Owns interaction and state. Reads topology from config/atlas.js,
   shapes from atlas/render.js, framing from atlas/camera.js.

   Three architecture states, exclusive:
     view      the map at rest, inspectable
     run       the illustrative pipeline plays through it
     failure   the safe-failure paths come forward

   Selection and tracing are orthogonal to state: a reader can
   inspect a module while a run is playing, and the run does not
   fight them for the camera.
   ============================================================ */

import { qs, qsa, h, prefersReducedMotion, trapFocus } from '../lib/dom.js';
import {
  NODE, REGION, ROUTES, FAILURES, ATLAS_RUN, ZOOM, tracePath
} from '../config/atlas.js';
import { ATLAS_RECORDS, BADGE, SOURCE_BADGE, REGION_BRIEF } from '../config/atlasRecords.js';
import { STATUS } from '../config/architecture.js';
import { buildAtlas } from './render.js';
import { AtlasCamera } from './camera.js';

const ROUTE = Object.fromEntries([...ROUTES, ...FAILURES].map((r) => [r.id, r]));

export class Atlas {
  constructor(root) {
    this.root = root;
    this.stage = qs('[data-atlas-stage]', root);
    this.panel = qs('[data-atlas-panel]', root);
    this.logEl = qs('[data-atlas-log]', root);
    this.captionEl = qs('[data-atlas-caption]', root);
    this.liveEl = qs('[data-atlas-live]', root);
    this.state = 'view';
    this.selected = null;
    this.traced = null;
    this.timers = [];
    this.runToken = 0;
    /* What the readout returns to when a transient hover ends. Held as state
       rather than hardcoded at each pointerleave: descending into a region
       animates the camera, which slides lanes under a stationary pointer and
       fires their leave handler a second later — and a leave handler that
       restores a fixed string would wipe the region line the click had just
       written, making the readout contradict the view. */
    this.resting = 'SYSTEM MAP / ILLUSTRATIVE V1 ARCHITECTURE';
  }

  mount() {
    if (!this.stage) return;
    this.svg = buildAtlas();
    this.stage.appendChild(this.svg);

    this.camera = new AtlasCamera(this.svg, this.stage);
    this.camera.onLevel = (id) => this.syncZoomButtons(id);
    this.camera.install();
    this.camera.goLevel('system', true);

    this.wireNodes();
    this.wireRegions();
    this.wireLanes();
    this.wireControls();
    this.wirePanel();
    /* After wiring, not before: syncZoomButtons now also sets which of the
       plates and the modules are in the tab order, and it cannot do that for
       plates that have not been marked operable yet. */
    this.syncZoomButtons('system');
    this.log('SYSTEM MAP READY / ILLUSTRATIVE V1 ARCHITECTURE', { hold: true });
    return this;
  }

  /* ---------- logging + screen-reader announcements ----------
     `hold: true` also makes the line the one the readout returns to after a
     transient hover. Used for anything the reader chose — a region, a run
     state — as opposed to what happened to be under the cursor. */
  log(text, { hold = false } = {}) {
    if (hold) this.resting = text;
    if (this.logEl) this.logEl.textContent = text;
  }

  /** Return the readout to whatever the reader last chose. */
  rest() {
    this.log(this.selected
      ? `INSPECTING / ${NODE[this.selected].label.toUpperCase()}`
      : this.resting);
  }

  announce(text) {
    /* The map is an image to assistive tech; every state change has to be
       stated in words or the whole feature is silent. */
    if (this.liveEl) this.liveEl.textContent = text;
  }

  clearTimers() {
    this.timers.forEach(clearTimeout);
    this.timers = [];
  }

  after(ms, fn) {
    this.timers.push(setTimeout(fn, ms));
  }

  /* ---------- nodes ---------- */
  wireNodes() {
    qsa('.atl-node', this.svg).forEach((el) => {
      const id = el.dataset.node;
      el.setAttribute('aria-label', this.nodeAria(id));

      el.addEventListener('click', () => {
        if (this.stage.dataset.dragged) return;   // that was a pan
        this.select(id);
      });
      el.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          this.select(id);
        }
      });
      /* Hover traces the path; it does not select. Two different questions —
         "what is this" and "what does it touch" — deserve two gestures. */
      el.addEventListener('pointerenter', (e) => {
        if (e.pointerType === 'touch') return;
        this.trace(id);
        /* Hovering a module names it. Not held: this is what happens to be
           under the cursor, so it must give the line back on leave. */
        if (!this.selected) this.log(`${NODE[id].label.toUpperCase()} / ${NODE[id].sub.toUpperCase()}`);
      });
      el.addEventListener('pointerleave', () => { this.untrace(); this.rest(); });
      el.addEventListener('focus', () => this.trace(id));
      el.addEventListener('blur', () => { this.untrace(); this.rest(); });
    });
  }

  /* ---------- region plates ----------
     At SYSTEM zoom the plates are the only thing drawn, and individual
     modules are deliberately not hit-testable there — that view is about
     regions, not parts. Which left the opening state of the map with
     nothing to click: the first thing a visitor tries on a system diagram
     is one of the seven big labelled blocks, and it did nothing.

     A plate click descends into that region. It is the same gesture as the
     zoom buttons, aimed at the thing under the pointer instead. */
  wireRegions() {
    qsa('.atl-region', this.svg).forEach((el) => {
      const r = REGION[el.dataset.region];
      if (!r) return;

      /* The plate is a graphic, so it has to be told it is operable — for
         the pointer, for the keyboard, and for a screen reader. */
      el.setAttribute('role', 'button');
      el.setAttribute('tabindex', '0');
      el.setAttribute('aria-label',
        `${r.word}. ${REGION_BRIEF[r.id] || r.note}. Open this region.`);
      el.classList.add('is-operable');

      const line = `${r.word} / ${r.note.toUpperCase()}`;

      const open = () => {
        if (this.stage.dataset.dragged) return;   // that was a pan
        /* Framing the region's own box, not a fixed zoom level. An earlier
           version called goLevel('layers') first and then frameBox, which
           started two camera animations in the same tick and hardcoded a
           scale that a narrow region does not want: the camera settles at
           whichever authored level actually matches the resulting width, and
           the level callback syncs the buttons and the tab order to it. Below
           SYSTEM the modules inside are hit-testable, so descending is also
           what makes them clickable — which is why LAYERS is passed as a
           floor. Inference alone cannot guarantee it: on a very wide stage the
           fitted width clamps and reads as SYSTEM, leaving the reader inside a
           region whose modules are still inert. */
        this.camera.frameBox(r.box, 140, 'layers');
        /* Held: this is the reader's choice, so a lane sliding under a
           stationary pointer as the camera travels must restore this line
           rather than the generic one. */
        this.log(line, { hold: true });
        this.announce(`${r.word}. ${REGION_BRIEF[r.id] || r.note}`);
      };

      el.addEventListener('click', open);
      el.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(); }
      });
      el.addEventListener('pointerenter', (e) => {
        if (e.pointerType === 'touch') return;
        this.log(line);
      });
      el.addEventListener('pointerleave', () => this.rest());
      el.addEventListener('focus', () => this.log(line));
      el.addEventListener('blur', () => this.rest());
    });
  }

  nodeAria(id) {
    const n = NODE[id];
    const rec = ATLAS_RECORDS[id];
    if (!n) return '';
    const st = STATUS[n.status];
    const parts = [n.label, REGION[n.region]?.word, st ? st.word : ''];
    if (rec) parts.push(rec.role);
    return parts.filter(Boolean).join('. ') + '. Activate to inspect.';
  }

  select(id) {
    const n = NODE[id];
    const rec = ATLAS_RECORDS[id];
    if (!n || !rec) return;
    this.selected = id;
    qsa('.atl-node', this.svg).forEach((el) => {
      el.classList.toggle('is-selected', el.dataset.node === id);
    });
    this.root.classList.add('is-inspecting');
    this.renderRecord(id, n, rec);
    this.trace(id, true);
    /* Bring the module into view, but only when the reader is already
       zoomed out far enough that it is a speck. Yanking the camera on a
       reader who has framed something themselves is the rudest thing an
       interactive map can do. Floored at AGENTS: a single module is the
       tightest thing on the map, and having inspected one the reader is
       unambiguously below the region scale. */
    if (this.camera.view.w > 2000) this.camera.frameBox(n.box, 300, 'agents');
    this.announce(`${n.label} selected. ${rec.role}`);
    this.log(`INSPECTING / ${n.label.toUpperCase()}`);
  }

  renderRecord(id, node, rec) {
    if (!this.panel) return;
    const st = STATUS[node.status];
    const region = REGION[node.region];
    const isSource = rec.kind === 'source';

    const field = (label, value, cls = '') =>
      h('div', { class: `atl-rec__field ${cls}`.trim() }, [
        h('span', { class: 'label label--micro', text: label }),
        h('p', { text: value })
      ]);

    const related = (rec.related || [])
      .filter((rid) => NODE[rid])
      .map((rid) =>
        h('button', {
          class: 'atl-rec__rel',
          type: 'button',
          dataset: { goto: rid },
          text: NODE[rid].label
        })
      );

    const body = h('div', { class: 'atl-rec' }, [
      h('div', { class: 'atl-rec__head' }, [
        h('span', { class: 'label label--micro atl-rec__coord', text: `${region.coord} / ${node.coord}` }),
        h('button', { class: 'atl-rec__close', type: 'button', dataset: { atlasClose: '' }, text: '\u2715', 'aria-label': 'Close inspector' })
      ]),
      h('p', { class: 'label atl-rec__region', text: region.word }),
      h('h3', { class: 'atl-rec__title', text: rec.label }),
      h('p', {
        class: `atl-rec__status atl-rec__status--${node.status}`,
        dataset: { status: node.status }
      }, [
        h('span', { class: 'atl-rec__glyph', text: st.glyph }),
        h('span', { text: st.word })
      ]),
      h('p', { class: 'atl-rec__role', text: rec.role }),
      h('div', { class: 'atl-rec__flow' }, [
        field('RECEIVES', rec.receives),
        h('div', { class: 'atl-rec__rule' }),
        field('PRODUCES', rec.produces)
      ]),
      field('VERIFIES / TRANSFORMS', rec.acts, 'atl-rec__acts'),
      /* Failure behaviour is given its own emphatic block rather than being
         one more row. It is the field that makes the architecture credible,
         and burying it in a list would waste it. */
      h('div', { class: 'atl-rec__failure' }, [
        h('span', { class: 'label label--micro', text: 'WHEN IT CANNOT PROCEED' }),
        h('p', { text: rec.failure })
      ]),
      related.length
        ? h('div', { class: 'atl-rec__related' }, [
            h('span', { class: 'label label--micro', text: 'RELATED COMPONENTS' }),
            h('div', { class: 'atl-rec__rels' }, related)
          ])
        : null,
      h('p', { class: 'atl-rec__badge', text: isSource ? SOURCE_BADGE : BADGE })
    ].filter(Boolean));

    this.panel.replaceChildren(body);
    this.panel.hidden = false;
    this.panel.classList.add('is-open');
    this.panel.scrollTop = 0;
  }

  wirePanel() {
    if (!this.panel) return;
    this.panel.addEventListener('click', (e) => {
      if (e.target.closest('[data-atlas-close]')) { this.deselect(); return; }
      const rel = e.target.closest('[data-goto]');
      if (rel) this.select(rel.dataset.goto);
    });
    this.panel.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') { this.deselect(); return; }
      /* The panel is a non-modal drawer, so focus is contained rather than
         trapped hard — Tab cycles inside it while it is open, and Escape
         returns to the map. */
      trapFocus(this.panel, e);
    });
    this.root.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && this.selected) this.deselect();
    });
  }

  deselect() {
    const prev = this.selected;
    this.selected = null;
    this.root.classList.remove('is-inspecting');
    if (this.panel) {
      this.panel.classList.remove('is-open');
      this.panel.hidden = true;
    }
    qsa('.atl-node.is-selected', this.svg).forEach((el) => el.classList.remove('is-selected'));
    this.untrace(true);
    /* Back to whatever the reader was looking at before they inspected —
       usually a region they descended into, which is still on screen. */
    this.rest();
    this.announce('Inspector closed.');
    const el = prev && qs(`[data-node="${prev}"]`, this.svg);
    if (el) el.focus({ preventScroll: true });
  }

  /* ---------- tracing ---------- */
  trace(id, sticky = false) {
    const { nodes, routes } = tracePath(id);
    /* In global TRACE mode every hover is sticky: the path stays lit after
       the pointer leaves so the reader can look away from the map at the
       drawer without the answer disappearing. */
    this.traced = (sticky || this.sticky) ? id : this.traced;
    this.svg.classList.add('is-tracing');
    qsa('.atl-node', this.svg).forEach((el) => {
      el.classList.toggle('is-lit', nodes.includes(el.dataset.node));
      el.classList.toggle('is-focus', el.dataset.node === id);
    });
    qsa('.atl-lane', this.svg).forEach((el) => {
      el.classList.toggle('is-lit', routes.includes(el.dataset.route));
    });
  }

  untrace(force = false) {
    if (this.traced && !force) {
      /* A selected module keeps its path lit, so the drawer and the map
         are describing the same thing while the reader reads. */
      this.trace(this.traced, true);
      return;
    }
    if (force) this.traced = null;
    this.svg.classList.remove('is-tracing');
    qsa('.atl-node', this.svg).forEach((el) => el.classList.remove('is-lit', 'is-focus'));
    qsa('.atl-lane', this.svg).forEach((el) => el.classList.remove('is-lit'));
  }

  /* ---------- lanes ---------- */
  wireLanes() {
    qsa('.atl-lane', this.svg).forEach((el) => {
      const r = ROUTE[el.dataset.route];
      if (!r) return;
      const hit = qs('.atl-lane__hit', el);
      const show = () => {
        el.classList.add('is-hover');
        this.highlightRoute(r);
        this.log(`${r.word} / ${r.info.toUpperCase()}`);
      };
      const hide = () => {
        el.classList.remove('is-hover');
        this.untrace();
        this.rest();
      };
      hit.addEventListener('pointerenter', (e) => {
        if (e.pointerType === 'touch') return;
        show();
      });
      hit.addEventListener('pointerleave', hide);
    });
  }

  /** Hovering a route lights the whole chain it belongs to, both directions. */
  highlightRoute(route) {
    const up = tracePath(route.from);
    const down = tracePath(route.to);
    const nodes = new Set([...up.nodes, ...down.nodes]);
    const routes = new Set([...up.routes, ...down.routes, route.id]);
    this.svg.classList.add('is-tracing');
    qsa('.atl-node', this.svg).forEach((el) => {
      el.classList.toggle('is-lit', nodes.has(el.dataset.node));
    });
    qsa('.atl-lane', this.svg).forEach((el) => {
      el.classList.toggle('is-lit', routes.has(el.dataset.route));
    });
  }

  /* ---------- controls ---------- */
  wireControls() {
    qsa('[data-atlas-zoom]', this.root).forEach((btn) => {
      btn.addEventListener('click', () => {
        const z = this.camera.goLevel(btn.dataset.atlasZoom);
        this.syncZoomButtons(z.id);
        if (this.captionEl) this.captionEl.textContent = z.caption;
        this.announce(`${z.word} view. ${z.caption}`);
      });
    });

    qsa('[data-atlas-state]', this.root).forEach((btn) => {
      btn.addEventListener('click', () => this.setState(btn.dataset.atlasState));
    });

    qsa('[data-atlas-region]', this.root).forEach((btn) => {
      btn.addEventListener('click', () => {
        const r = REGION[btn.dataset.atlasRegion];
        if (!r) return;
        /* Same floor as clicking the plate itself: a jump is a descent. */
        this.camera.frameBox(r.box, 140, 'layers');
        this.log(`${r.word} / ${r.note.toUpperCase()}`, { hold: true });
        this.announce(`${r.word}. ${REGION_BRIEF[r.id] || ''}`);
      });
    });
  }

  syncZoomButtons(id) {
    qsa('[data-atlas-zoom]', this.root).forEach((b) => {
      const on = b.dataset.atlasZoom === id;
      b.classList.toggle('is-active', on);
      b.setAttribute('aria-pressed', on ? 'true' : 'false');
    });

    /* The two scales offer different targets, and the tab order has to say
       so. At SYSTEM the plates are the operable things and the modules are
       not hit-testable; below it that reverses. Leaving both in the order
       would give a keyboard reader seven focus stops that do nothing at the
       scale they are at. */
    const regions = id === 'system';
    qsa('.atl-region.is-operable', this.svg).forEach((el) => {
      el.setAttribute('tabindex', regions ? '0' : '-1');
      el.setAttribute('aria-hidden', regions ? 'false' : 'true');
    });
    qsa('.atl-node', this.svg).forEach((el) => {
      el.setAttribute('tabindex', regions ? '-1' : '0');
      el.setAttribute('aria-hidden', regions ? 'true' : 'false');
    });
    const z = ZOOM.find((l) => l.id === id);
    if (z && this.captionEl) this.captionEl.textContent = z.caption;
  }

  /* ---------- architecture states ---------- */
  setState(next) {
    if (!next) return;
    this.clearTimers();
    this.runToken += 1;
    this.state = next;
    this.root.dataset.atlasState = next;
    qsa('[data-atlas-state]', this.root).forEach((b) => {
      const on = b.dataset.atlasState === next;
      b.classList.toggle('is-active', on);
      b.setAttribute('aria-pressed', on ? 'true' : 'false');
    });
    this.resetRunMarks();

    if (next === 'view') {
      this.camera.goLevel('system');
      this.log('SYSTEM MAP / ILLUSTRATIVE V1 ARCHITECTURE', { hold: true });
      this.announce('Architecture view. The map at rest.');
    } else if (next === 'run') {
      this.playRun();
    } else if (next === 'failure') {
      this.showFailures();
    }
  }

  resetRunMarks() {
    qsa('.atl-node', this.svg).forEach((el) => el.classList.remove('is-active', 'is-done'));
    qsa('.atl-lane', this.svg).forEach((el) => el.classList.remove('is-running', 'is-carried'));
  }

  /** The illustrative pipeline, played across the map. */
  playRun() {
    const token = this.runToken;
    this.camera.goLevel('layers');
    this.log('RUNNING ILLUSTRATIVE PIPELINE', { hold: true });
    this.announce('Running the illustrative pipeline across the system map.');

    /* Under reduced motion the run resolves to its finished state instead of
       animating. The information is the point; the sequence is the flourish. */
    if (prefersReducedMotion()) {
      ATLAS_RUN.forEach((beat) => {
        if (beat.node) qs(`[data-node="${beat.node}"]`, this.svg)?.classList.add('is-done');
        if (beat.route) qs(`[data-route="${beat.route}"]`, this.svg)?.classList.add('is-carried');
      });
      this.log('ILLUSTRATIVE RUN COMPLETE / RECORD PRODUCED', { hold: true });
      this.announce('Illustrative run complete. All nine stages finished and the record was produced.');
      return;
    }

    ATLAS_RUN.forEach((beat) => {
      this.after(beat.at, () => {
        if (token !== this.runToken) return;
        if (beat.route) {
          const lane = qs(`[data-route="${beat.route}"]`, this.svg);
          if (lane) {
            lane.classList.add('is-running');
            this.after(900, () => {
              lane.classList.remove('is-running');
              lane.classList.add('is-carried');
            });
          }
        }
        if (beat.node) {
          const el = qs(`[data-node="${beat.node}"]`, this.svg);
          if (el) {
            el.classList.add('is-active');
            this.after(1100, () => {
              el.classList.remove('is-active');
              el.classList.add('is-done');
            });
          }
        }
        if (beat.log) this.log(beat.log);
      });
    });

    const last = ATLAS_RUN[ATLAS_RUN.length - 1].at;
    this.after(last + 900, () => {
      if (token !== this.runToken) return;
      this.log('ILLUSTRATIVE RUN COMPLETE / RECORD PRODUCED', { hold: true });
      this.announce('Illustrative run complete. The record was produced with one disclosed assumption.');
    });
  }

  /** Failure mode: the five safe-failure paths, revealed in sequence. */
  showFailures() {
    const token = this.runToken;
    this.camera.goLevel('layers');
    this.log('SHOWING FAILURE PATHS / HOW CATERVA DECLINES', { hold: true });
    this.announce(
      'Failure paths shown. Five ways the system declines safely: ' +
      FAILURES.map((f) => `${f.word}, ${f.consequence}`).join(' ')
    );

    const step = prefersReducedMotion() ? 0 : 620;
    FAILURES.forEach((f, i) => {
      this.after(i * step, () => {
        if (token !== this.runToken) return;
        const lane = qs(`[data-route="${f.id}"]`, this.svg);
        if (lane) lane.classList.add('is-carried');
        qs(`[data-node="${f.to}"]`, this.svg)?.classList.add('is-done');
        if (!prefersReducedMotion()) this.log(`${f.index} ${f.word} / ${f.consequence.toUpperCase()}`);
      });
    });
  }

  /* ---------- global SYSTEM MODE ----------
     The dock owns no behaviour; it asks. The atlas already had three
     states of its own, so most of the work here is mapping the four
     global modes onto them and back — which is deliberate: two controls
     that disagree about what the map is doing would be worse than one
     control fewer.

     TRACE is the exception. It has no equivalent atlas state, because it
     is not something the map *does* — it is a change in what hovering
     means. In trace mode a path stays lit after the pointer leaves, so
     the reader can read the drawer and the route at the same time
     without holding the mouse still. */
  applyMode(mode) {
    this.mode = mode;
    this.root.dataset.mode = mode;

    if (mode === 'trace') {
      /* Nothing is playing; hovering is the whole interaction. Which is
         why the camera has to come down to the layers level: at the system
         level individual modules are deliberately not hit-testable — that
         view shows regions, not parts — so trace mode there would be a
         mode whose only interaction is unavailable. */
      this.setState('view');
      this.camera.goLevel('layers');
      this.syncZoomButtons('layers');
      this.log('TRACE / HOVER ANY MODULE TO FOLLOW ITS PATH', { hold: true });
      return;
    }
    if (mode === 'run') { this.setState('run'); return; }
    if (mode === 'failure') { this.setState('failure'); return; }

    /* observe */
    this.untrace(true);
    this.setState('view');
    this.log('OBSERVE / SYSTEM AT REST', { hold: true });
  }

  /** True while hovering should leave the path lit behind it. */
  get sticky() {
    return this.mode === 'trace';
  }
}

export function initAtlas() {
  const root = qs('[data-atlas]');
  if (!root) return null;
  const atlas = new Atlas(root).mount();
  /* Registered rather than imported by the dock: the atlas mounts lazily,
     so the dock cannot hold a reference to it at boot. */
  if (atlas) {
    import('../modes/index.js').then(({ systemMode }) => {
      systemMode.register('atlas', (mode) => atlas.applyMode(mode));
    });
  }
  return atlas;
}
