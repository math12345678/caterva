/* ============================================================
   caterva — SYSTEM MODE

   A single global control that changes the behaviour of the whole
   page. Four modes, and the difference between them has to be
   visible without reading the label:

     OBSERVE  nothing runs, ambient signal only
     TRACE    hovering anything reveals the path through it
     RUN      the kinetics pipeline plays on the map and console
     FAILURE  the system shows its refusals

   The dock owns no behaviour of its own. It publishes the mode to
   `documentElement[data-mode]` — which is what lets CSS across every
   stylesheet respond — and then asks each section's controller to do
   the part only that controller can do. Sections are registered
   rather than imported, because they mount lazily and the dock is
   present from boot: a section that has not been built yet simply
   has no adapter, and the mode still applies to everything else.
   ============================================================ */

import { getHost } from '../lib/host.js';
import { qs, qsa, h, prefersReducedMotion } from '../lib/dom.js';
import { MODES, MODE, DEFAULT_MODE, FAILURE_KINDS, DOCK } from '../config/modes.js';

export class SystemMode {
  constructor() {
    this.mode = null;
    this.adapters = new Map();
    this.root = null;
    this.liveEl = null;
    this.open = false;
  }

  /* ---------- the dock ----------
     Fixed in a corner and collapsed to a single readable strip until
     touched: a control that governs the whole page has to be reachable
     from anywhere, and a control that is reachable from anywhere must
     not sit on top of the thing it is governing. */
  build() {
    const list = h('div', { class: 'mode__list', role: 'radiogroup', 'aria-label': DOCK.label },
      MODES.map((m) => h('button', {
        class: 'mode__opt',
        type: 'button',
        role: 'radio',
        'aria-checked': 'false',
        dataset: { modeSet: m.id },
        title: `${m.word} — ${m.cue}`
      }, [
        h('span', { class: 'mono mode__i', text: m.index }),
        h('span', { class: 'mode__glyph', 'aria-hidden': 'true', text: m.glyph }),
        h('span', { class: 'mode__w', text: m.word }),
        h('span', { class: 'mode__cue', text: m.cue })
      ]))
    );

    const dock = h('aside', {
      class: 'mode',
      dataset: { modeDock: '' },
      'aria-label': 'System mode'
    }, [
      /* The collapsed face: label, current mode, and a pulse whose rhythm
         is itself the mode indicator. */
      h('button', {
        class: 'mode__face',
        type: 'button',
        dataset: { modeToggle: '' },
        'aria-expanded': 'false'
      }, [
        h('span', { class: 'mode__beacon', 'aria-hidden': 'true' }),
        h('span', { class: 'mode__face-txt' }, [
          h('span', { class: 'label label--micro mode__lbl', text: DOCK.label }),
          h('span', { class: 'mono mode__now', dataset: { modeNow: '' }, text: '' })
        ]),
        h('span', { class: 'mono mode__chev', 'aria-hidden': 'true', text: '\u2039' })
      ]),

      /* One wrapper inside the panel, deliberately: the collapse is a
         grid-template-rows: 0fr → 1fr animation, and that only sizes the
         first row. With the hint, list, legend and note as four direct
         children the other three rows stay auto-sized and the "collapsed"
         dock is still three hundred pixels tall. */
      h('div', { class: 'mode__panel', dataset: { modePanel: '' } }, [
        h('div', { class: 'mode__panel-in' }, [
        h('p', { class: 'mode__hint', text: DOCK.hint }),
        list,
        /* Failure mode is the only one that needs a legend, because it is
           the only one where the reader has to know what to go and look
           for. It is written into the dock rather than a tooltip. */
        h('div', { class: 'mode__kinds', dataset: { modeKinds: '' } }, [
          h('span', { class: 'label label--micro mode__kinds-l', text: 'Disclosing' }),
          h('ul', { class: 'mode__kinds-list' },
            FAILURE_KINDS.map((k) => h('li', { class: 'mode__kind', text: k })))
        ]),
        h('p', { class: 'mode__where', dataset: { modeWhere: '' }, text: '' })
        ])
      ])
    ]);

    getHost().appendChild(dock);
    this.root = dock;
    this.faceEl = qs('[data-mode-toggle]', dock);
    this.panelEl = qs('[data-mode-panel]', dock);
    this.nowEl = qs('[data-mode-now]', dock);
    this.whereEl = qs('[data-mode-where]', dock);

    this.liveEl = h('p', {
      class: 'visually-hidden',
      role: 'status',
      'aria-live': 'polite',
      dataset: { modeLive: '' }
    });
    getHost().appendChild(this.liveEl);

    this.publishHeight();
  }

  /* ---------- how much of the bottom edge the dock owns ----------
     On a phone the dock spans the full width of the bottom edge, which puts
     it directly on top of any chrome that is itself anchored to the bottom
     of a section. That is not hypothetical: following the navigation to
     #atlas left four of the seven region-jump buttons — the stated primary
     way around the map on a phone — under the dock and untappable.

     The dock cannot know which sections have bottom-anchored controls, and
     those sections must not have to know the dock's dimensions. So it
     publishes its resting height and nothing more; whether to reserve that
     space, and at which breakpoint, stays a question for CSS. Only the
     collapsed face counts: the expanded panel is a deliberate overlay the
     reader opened and will close. */
  publishHeight() {
    const face = this.faceEl;
    if (!face) return;
    const write = () => {
      const h0 = Math.round(face.getBoundingClientRect().height);
      if (h0 > 0) document.documentElement.style.setProperty('--dock-h', `${h0}px`);
    };
    write();
    // `'ResizeObserver' in window` narrows `window` itself, so the else
    // branch types it as `never` and `window.addEventListener` is an
    // error on a line that runs fine. Testing the property directly says
    // the same thing about the environment without narrowing the object.
    if (typeof ResizeObserver !== 'undefined') {
      new ResizeObserver(write).observe(face);
    } else {
      window.addEventListener('resize', write);
    }
  }

  /* ---------- registration ----------
     The heavy sections mount when they approach the viewport, which is
     long after the dock exists. Each one registers itself on arrival and
     is immediately handed the mode already in force, so a section built
     during RUN starts running instead of starting idle and looking
     broken. */
  register(name, adapter) {
    this.adapters.set(name, adapter);
    if (this.mode) this.applyTo(adapter, this.mode);
  }

  applyTo(adapter, mode) {
    try {
      adapter(mode);
    } catch (err) {
      /* One section failing to honour a mode must not leave the rest of
         the page stuck in the previous one. */
      console.warn('[caterva] mode adapter failed', err);
    }
  }

  /* ---------- switching ---------- */
  set(next, { announce = true, scroll = false, collapse = false } = {}) {
    const m = MODE[next];
    if (!m || next === this.mode) return;
    this.mode = next;

    /* Published on the document element, not on the dock: this is what
       lets every stylesheet — atlas, console, microscope, base — answer a
       mode change without any of them knowing the dock exists. */
    document.documentElement.dataset.mode = next;

    if (this.nowEl) this.nowEl.textContent = `${m.index} ${m.word}`;
    if (this.whereEl) this.whereEl.textContent = m.note;
    this.sync();

    this.adapters.forEach((adapter) => this.applyTo(adapter, next));

    if (announce) this.announce(m.say);

    /* A mode with a stage takes the reader to it, because a mode that
       visibly changes a section three screens away has not visibly
       changed anything. Requested explicitly, so restoring a mode on
       load never hijacks the scroll position. */
    if (scroll && m.stage) {
      const host = qs(m.stage);
      if (host) {
        host.scrollIntoView({
          behavior: prefersReducedMotion() ? 'auto' : 'smooth',
          block: 'start'
        });
        /* Collapse on the way, but only for a pointer selection: the panel
           is an overlay on the reading surface, so leaving it open while
           scrolling to the thing that just changed means the dock is
           covering the change. Keyboard callers pass collapse:false —
           closing the panel would take focus with it, and a reader arrowing
           through the four modes would be thrown out after one press. */
        if (collapse) this.setOpen(false);
      }
    }
  }

  sync() {
    qsa('[data-mode-set]', this.root).forEach((b) => {
      const on = b.dataset.modeSet === this.mode;
      b.classList.toggle('is-active', on);
      b.setAttribute('aria-checked', on ? 'true' : 'false');
      /* Only the active option stays in the tab order, which is how a
         radiogroup is meant to behave: one stop, arrows to move. */
      b.tabIndex = on ? 0 : -1;
    });
  }

  setOpen(on) {
    this.open = on;
    this.root.classList.toggle('is-open', on);
    this.faceEl.setAttribute('aria-expanded', on ? 'true' : 'false');
  }

  announce(text) {
    if (this.liveEl) this.liveEl.textContent = text;
  }

  wire() {
    this.faceEl.addEventListener('click', () => this.setOpen(!this.open));

    qs('[data-mode-panel]', this.root).addEventListener('click', (e) => {
      const btn = e.target.closest('[data-mode-set]');
      if (btn) this.set(btn.dataset.modeSet, { scroll: true, collapse: true });
    });

    /* Arrow keys move between modes and switch on arrival, which is the
       expected behaviour for a radiogroup and also the fastest way to feel
       the difference between the four. */
    this.root.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && this.open) { this.setOpen(false); this.faceEl.focus(); return; }
      const btn = e.target.closest('[data-mode-set]');
      if (!btn) return;
      const fwd = e.key === 'ArrowDown' || e.key === 'ArrowRight';
      const back = e.key === 'ArrowUp' || e.key === 'ArrowLeft';
      if (!fwd && !back) return;
      e.preventDefault();
      const i = MODES.findIndex((m) => m.id === btn.dataset.modeSet);
      const n = (i + (fwd ? 1 : MODES.length - 1)) % MODES.length;
      this.set(MODES[n].id, { scroll: true });
      qs(`[data-mode-set="${MODES[n].id}"]`, this.root)?.focus();
    });

    /* Number keys 1–4 anywhere on the page, because this is meant to read
       as an operating system's mode switch. Skipped while the reader is
       typing into the inquiry terminal. */
    document.addEventListener('keydown', (e) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      // `e.target` is an EventTarget, which has no tagName. It is an
      // element for every keydown this listener can see; the cast says so
      // rather than the properties being read off a type that lacks them.
      const t = /** @type {HTMLElement | null} */ (e.target);
      if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)) return;
      const i = ['1', '2', '3', '4'].indexOf(e.key);
      if (i < 0) return;
      /* The collapsed face already names the mode and the beacon already
         shows it, so there is nothing to open the panel for — and opening
         it would put it on top of the section being scrolled to. */
      this.set(MODES[i].id, { scroll: true, collapse: true });
    });

    /* Clicking away closes the panel; it is an overlay on the reading
       surface and should not have to be dismissed deliberately. */
    document.addEventListener('pointerdown', (e) => {
      if (this.open && !this.root.contains(e.target)) this.setOpen(false);
    });
  }

  mount() {
    this.build();
    this.wire();
    this.set(DEFAULT_MODE, { announce: false });
    return this;
  }
}

export const systemMode = new SystemMode();

export function initSystemMode() {
  return systemMode.mount();
}
