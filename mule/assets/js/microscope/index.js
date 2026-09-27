/* ============================================================
   caterva — EVIDENCE MICROSCOPE

   One parameter, six depths. The reader descends and the value
   stops being a number.

   The interaction is a deep zoom, not an accordion: exactly one
   level occupies the stage at a time, the outgoing level scales up
   and dissolves as though it were being passed through, and the
   incoming level scales up from inside it. The levels the reader
   has already passed remain on a depth gauge, so descent is
   navigable rather than merely animated.
   ============================================================ */

import { qs, qsa, h, prefersReducedMotion } from '../lib/dom.js';
import { LEVELS, PARAM, DISCLAIMER } from '../config/microscope.js';
import { buildFigure } from './figures.js';

export class Microscope {
  constructor(root) {
    this.root = root;
    this.stageEl = qs('[data-mi-stage]', root);
    this.fieldEl = qs('[data-mi-field]', root);
    this.gaugeEl = qs('[data-mi-gauge]', root);
    this.liveEl = qs('[data-mi-live]', root);
    this.seedEl = qs('[data-mi-seed]', root);

    this.depth = -1;      // -1 = closed, showing only the floating parameter
    this.busy = false;
  }

  mount() {
    if (!this.stageEl) return null;
    this.buildGauge();
    this.wire();
    return this;
  }

  /* ---------- the depth gauge ----------
     Six stops, always visible, always jumpable. A deep-zoom interface
     that can only be walked one step at a time is a slideshow. */
  buildGauge() {
    if (!this.gaugeEl) return;
    this.gaugeEl.replaceChildren(...LEVELS.map((l, i) =>
      h('button', {
        class: 'mi-gauge__stop',
        type: 'button',
        dataset: { miGo: String(i) },
        'aria-pressed': 'false'
      }, [
        h('span', { class: 'mono mi-gauge__i', text: l.index }),
        h('span', { class: 'mi-gauge__k', text: l.key }),
        h('span', { class: 'mi-gauge__tick', 'aria-hidden': 'true' })
      ])
    ));
  }

  syncGauge() {
    qsa('[data-mi-go]', this.gaugeEl).forEach((b) => {
      const i = Number(b.dataset.miGo);
      const on = i === this.depth;
      b.classList.toggle('is-active', on);
      b.classList.toggle('is-passed', i < this.depth);
      b.setAttribute('aria-pressed', on ? 'true' : 'false');
    });
  }

  /* ---------- one level's panel ---------- */
  panel(level) {
    const rows = level.rows
      ? h('dl', { class: 'mi-rows' }, level.rows.flatMap((r) => [
          h('dt', { class: 'label label--micro mi-rows__k', text: r.k }),
          h('dd', {
            class: `mi-rows__v${r.mono ? ' mono' : ''}`,
            dataset: { tone: r.tone || null },
            text: r.v
          })
        ]))
      : null;

    return h('article', {
      class: 'mi-level',
      dataset: { miLevel: level.id, fig: level.figure }
    }, [
      h('div', { class: 'mi-level__meta' }, [
        h('span', { class: 'mono mi-level__i', text: `${level.index} / 06` }),
        h('span', { class: 'label label--micro mi-level__k', text: level.key })
      ]),
      h('div', { class: 'mi-level__grid' }, [
        h('div', { class: 'mi-level__fig' }, [buildFigure(level)]),
        h('div', { class: 'mi-level__text' }, [
          h('h3', { class: 'mi-level__t display', text: level.title }),
          h('p', { class: 'mi-level__lede', text: level.lede }),
          rows
        ].filter(Boolean))
      ]),
      h('div', { class: 'mi-level__acts' }, [
        level.descend
          ? h('button', {
              class: 'ctrl ctrl--primary',
              type: 'button',
              dataset: { miDown: '' },
              text: level.descend
            })
          : h('p', { class: 'mi-level__end mono', text: 'DEEPEST LEVEL / FULL CUSTODY SHOWN' }),
        this.depth > 0
          ? h('button', { class: 'ctrl ctrl--quiet', type: 'button', dataset: { miUp: '' }, text: 'Back up' })
          : null,
        h('button', { class: 'ctrl ctrl--quiet', type: 'button', dataset: { miClose: '' }, text: 'Close' })
      ].filter(Boolean))
    ]);
  }

  /* ---------- descent ----------
     The outgoing panel is kept in the DOM for the length of the
     transition so the two levels overlap: the new one has to appear to
     come out of the old one, which cannot happen if the old one is
     removed first. */
  goTo(i, { announce = true, focus = true } = {}) {
    const next = Math.max(0, Math.min(LEVELS.length - 1, i));
    if (next === this.depth) return;
    const dir = next > this.depth ? 'in' : 'out';
    const prevPanel = qs('.mi-level', this.stageEl);
    this.depth = next;
    const level = LEVELS[next];

    const panel = this.panel(level);
    panel.dataset.enter = dir;
    this.stageEl.appendChild(panel);
    this.root.classList.add('is-open');
    if (this.seedEl) this.seedEl.setAttribute('aria-hidden', 'true');

    const fast = prefersReducedMotion();
    if (prevPanel) {
      prevPanel.dataset.exit = dir;
      prevPanel.classList.remove('is-in');
      setTimeout(() => prevPanel.remove(), fast ? 10 : 520);
    }
    requestAnimationFrame(() => panel.classList.add('is-in'));

    this.root.dataset.miDepth = level.id;
    this.syncGauge();
    this.sizeField(panel);
    if (announce) {
      this.announce(`Level ${level.index} of 06. ${level.key}. ${level.title}. ${level.lede}`);
    }
    /* Focus the descent control so a keyboard reader can hold Enter and
       fall through all six levels without hunting for the button.

       Only when the descent was this section's own doing. A global mode
       change also drives this method — FAILURE opens the scope boundary —
       and a section three screens away stealing focus from the dock broke
       the dock's own keyboard contract: arrowing to FAILURE moved focus into
       the microscope, so the next arrow press went nowhere and Escape no
       longer closed the panel. A section may respond to a mode; it may not
       take the caret away from the control that published it. */
    if (focus) {
      const target = qs('[data-mi-down]', panel) || qs('[data-mi-up]', panel);
      if (target) setTimeout(() => target.focus({ preventScroll: true }), fast ? 10 : 260);
    }
  }

  close() {
    /* Read before anything is torn down: returning focus to the seed is only
       correct if the caret was inside the microscope to begin with. OBSERVE
       mode closes this section globally, and doing that while the reader is
       using the dock would drag them here from wherever they actually are. */
    const held = this.root.contains(document.activeElement);
    const prevPanel = qs('.mi-level', this.stageEl);
    if (prevPanel) {
      prevPanel.dataset.exit = 'out';
      prevPanel.classList.remove('is-in');
      setTimeout(() => prevPanel.remove(), prefersReducedMotion() ? 10 : 480);
    }
    this.depth = -1;
    this.root.classList.remove('is-open');
    delete this.root.dataset.miDepth;
    // Give the field back to the seed, which needs only its own quiet space.
    this.watch?.disconnect();
    if (this.fieldEl) this.fieldEl.style.removeProperty('--mi-h');
    if (this.seedEl) {
      this.seedEl.removeAttribute('aria-hidden');
      /* The panel that had focus is being removed, so the caret has to be put
         somewhere deliberate — but only if it was ours to move. */
      if (held) {
        const btn = qs('[data-mi-open]', this.seedEl);
        if (btn) btn.focus({ preventScroll: true });
      }
    }
    this.syncGauge();
    this.announce('Microscope closed. The parameter is shown as a bare value again.');
  }

  announce(text) {
    if (this.liveEl) this.liveEl.textContent = text;
  }

  /* ---------- fitting the field to the level ----------
     Levels have to stay absolutely positioned — the outgoing and incoming
     panels occupying one space is what makes this a zoom rather than a
     list — which means the field has nothing in normal flow to grow
     against. The deepest levels are the tallest (the verification gate,
     then the eight-field record), so a fixed field clips exactly the
     controls the reader needs to keep descending.

     Measured from the children's offsetHeight, deliberately, on two
     counts. getBoundingClientRect reports the *transformed* box, and a
     level is measured while it is still scaled to 0.82 by the entry
     transform — that under-reports every level by a fifth and clips the
     tallest ones anyway. And panel.scrollHeight is no better: the grid is
     centred, so content taller than the box overflows above and below,
     and scrollHeight only sees the half below the fold. */
  measure(panel) {
    const cs = getComputedStyle(panel);
    const gap = parseFloat(cs.rowGap) || 0;
    const kids = Array.from(panel.children);
    const content = kids.reduce((t, el) => t + el.offsetHeight, 0)
      + gap * Math.max(0, kids.length - 1);
    const frame = parseFloat(cs.paddingTop) + parseFloat(cs.paddingBottom)
      + parseFloat(cs.borderTopWidth) + parseFloat(cs.borderBottomWidth);
    return Math.ceil(content + frame);
  }

  sizeField(panel) {
    if (!this.fieldEl || !panel) return;
    this.watch?.disconnect();

    const apply = () => {
      if (!panel.isConnected) return;
      const h = this.measure(panel);
      // Only ever grow toward the mounted level; a one-pixel reflow should
      // not retrigger the field's own height transition.
      const cur = parseFloat(this.fieldEl.style.getPropertyValue('--mi-h')) || 0;
      if (Math.abs(h - cur) > 1) this.fieldEl.style.setProperty('--mi-h', `${h}px`);
    };
    apply();

    /* The figures contain SVG that settles its own aspect ratio a frame
       late, and a webfont can land later still. Watching the panel is more
       honest than guessing at a number of frames. */
    if ('ResizeObserver' in window) {
      this.watch = new ResizeObserver(() => apply());
      Array.from(panel.children).forEach((el) => this.watch.observe(el));
    } else {
      requestAnimationFrame(apply);
    }
  }

  /** Re-fit on resize: every figure is fluid, so a narrower field reflows
      the text and changes the height the level needs. */
  refit() {
    const panel = qs('.mi-level', this.stageEl);
    if (panel) this.sizeField(panel);
    else if (this.fieldEl) this.fieldEl.style.removeProperty('--mi-h');
  }

  /* ---------- wiring ---------- */
  wire() {
    qs('[data-mi-open]', this.root)?.addEventListener('click', () => this.goTo(0));

    /* Delegated: level panels are created and destroyed on every step, so
       per-panel listeners would be bound and orphaned constantly. */
    this.stageEl.addEventListener('click', (e) => {
      if (e.target.closest('[data-mi-down]')) this.goTo(this.depth + 1);
      else if (e.target.closest('[data-mi-up]')) this.goTo(this.depth - 1);
      else if (e.target.closest('[data-mi-close]')) this.close();
    });

    this.gaugeEl?.addEventListener('click', (e) => {
      const btn = e.target.closest('[data-mi-go]');
      if (btn) this.goTo(Number(btn.dataset.miGo));
    });

    let rt = 0;
    window.addEventListener('resize', () => {
      clearTimeout(rt);
      rt = setTimeout(() => this.refit(), 140);
    });

    /* Arrow keys walk the depth once the reader is inside, because that is
       what the gauge looks like it should do. */
    this.root.addEventListener('keydown', (e) => {
      if (this.depth < 0) return;
      if (e.key === 'Escape') { this.close(); return; }
      if (e.key === 'ArrowDown' || e.key === 'ArrowRight') { e.preventDefault(); this.goTo(this.depth + 1); }
      else if (e.key === 'ArrowUp' || e.key === 'ArrowLeft') { e.preventDefault(); this.goTo(this.depth - 1); }
    });
  }

  /* ---------- global SYSTEM MODE ----------
     The microscope is a reading instrument, so it does not run and it does
     not fail. What the modes change is which depth is worth being at:
     FAILURE opens the two levels where this parameter's limits are
     actually visible — the scope boundary that the temperature condition
     falls outside of, and the check that let it through as illustrative
     rather than supported. OBSERVE closes it back to the bare value,
     which is the section's own argument: a number with nothing shown. */
  applyMode(mode) {
    this.root.dataset.mode = mode;
    if (mode === 'failure') {
      /* Level 04, the scope boundary — the one place the undeclared
         temperature condition is drawn rather than described. */
      /* focus:false — see goTo. The reader is at the dock, not here. */
      if (this.depth < 3) this.goTo(3, { focus: false });
    } else if (mode === 'observe') {
      if (this.depth >= 0) this.close();
    }
  }
}

export function initMicroscope() {
  const root = qs('[data-microscope]');
  if (!root) return null;
  const mi = new Microscope(root).mount();
  if (mi) {
    import('../modes/index.js').then(({ systemMode }) => {
      systemMode.register('microscope', (mode) => mi.applyMode(mode));
    });
  }
  return mi;
}

export { PARAM, DISCLAIMER };
