/* ============================================================
   caterva — inspection mode
   Any architecture node resolves to a readable record.
   Desktop: right-side panel. Mobile: full-width bottom sheet.
   ============================================================ */

import { h, qs, qsa, trapFocus } from '../lib/dom.js';
import { getInspectorRecord } from '../config/inspector.js';
import { STATUS } from '../config/architecture.js';

export class Inspector {
  constructor(root) {
    this.root = root;
    this.openId = null;
    this.lastTrigger = null;
    /* Set by main so the panel can ask the camera to re-fit after the drawing
       field narrows. Without this the viewBox keeps the old aspect ratio and the
       monument stretches for the duration of the inspection. */
    this.onReframe = null;
    /* Set by main. On a phone the sheet covers most of the screen, so the
       camera is asked to bring the inspected object into the band that is
       left; on release the run's own framing is restored. */
    this.onFrameNode = null;
    this.onReleaseFrame = null;
    this.el = this.build();
    root.appendChild(this.el);
    this.bind();
  }

  /** Reserve the panel's footprint in the drawing field, then re-fit the camera.
      Desktop reserves width on the right; the phone sheet reserves height at the
      bottom, published as a custom property so the CSS does not have to guess a
      sheet height that depends on how much the record says. */
  reserveSpace(on) {
    const cath = qs('.cathedral');
    if (!cath) return;
    cath.classList.toggle('is-inspecting', on);
    if (this.isSheet()) {
      const px = on ? Math.round(this.el.getBoundingClientRect().height) : 0;
      cath.style.setProperty('--sheet-height', `${px}px`);
    }
    // The inset animates for 520ms; refit at the end so the final framing is
    // measured against the container's settled size, not a mid-transition one.
    clearTimeout(this._reframeT);
    const refit = () => this.onReframe && this.onReframe();
    refit();
    this._reframeT = setTimeout(refit, 560);
  }

  build() {
    const panel = h('aside', {
      class: 'inspector',
      id: 'inspector',
      role: 'dialog',
      'aria-modal': 'false',
      'aria-labelledby': 'inspector-title',
      tabindex: '-1',
      hidden: 'hidden'
    }, [
      h('div', { class: 'inspector__grip', 'aria-hidden': 'true' }),
      h('header', { class: 'inspector__head' }, [
        h('span', { class: 'label label--micro', 'data-ins-eyebrow': '' }),
        h('button', {
          class: 'inspector__close',
          type: 'button',
          'aria-label': 'Close inspection panel',
          'data-ins-close': ''
        }, [h('span', { 'aria-hidden': 'true', text: '\u2715' })])
      ]),
      h('h3', { class: 'inspector__title', id: 'inspector-title', 'data-ins-title': '' }),
      h('p', { class: 'inspector__category', 'data-ins-category': '' }),
      h('p', { class: 'inspector__status', 'data-ins-status': '' }),
      h('p', { class: 'inspector__purpose', 'data-ins-purpose': '' }),

      /* Flow block. Inputs and outputs are the two halves of one idea, so they
         are set as a passage through the object rather than as two more rows in
         a list of fields. This is the part that makes a node feel like a piece
         of apparatus with something running through it. */
      h('div', { class: 'inspector__flow', 'data-ins-flow': '' }, [
        h('div', { class: 'ins-flow__row' }, [
          h('span', { class: 'label label--micro', text: 'IN' }),
          h('p', { 'data-ins-in': '' })
        ]),
        h('div', { class: 'ins-flow__rule', 'aria-hidden': 'true' }),
        h('div', { class: 'ins-flow__row' }, [
          h('span', { class: 'label label--micro', text: 'OUT' }),
          h('p', { 'data-ins-out': '' })
        ])
      ]),

      /* The illustrated event: what this object actually did in run 0007. */
      h('div', { class: 'inspector__event', 'data-ins-event-wrap': '' }, [
        h('span', { class: 'label label--micro', text: 'THIS RUN' }),
        h('p', { 'data-ins-event': '' })
      ]),

      h('dl', { class: 'inspector__fields', 'data-ins-fields': '' }),

      /* Position in the chain of custody. Every record carries it, because the
         claim of the product is that nothing floats free of the trail. */
      h('div', { class: 'inspector__trail', 'data-ins-trail-wrap': '' }, [
        h('span', { class: 'label label--micro', text: 'EVIDENCE TRAIL' }),
        h('p', { 'data-ins-trail': '' })
      ]),

      h('p', { class: 'inspector__note', 'data-ins-note': '' }),
      h('p', { class: 'inspector__foot disclaimer', 'data-ins-foot': '' })
    ]);
    return panel;
  }

  bind() {
    qs('[data-ins-close]', this.el).addEventListener('click', () => this.close());
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && this.openId) {
        e.preventDefault();
        this.close();
      }
      if (e.key === 'Tab' && this.openId && this.isSheet()) {
        trapFocus(this.el, e);
      }
    });
  }

  isSheet() {
    return window.matchMedia('(max-width: 68rem)').matches;
  }

  /** Open inspection for a node id, marking the selection in the SVG. */
  open(id, triggerEl, svg, fromKeyboard = false) {
    const record = getInspectorRecord(id);
    if (!record) return;

    this.openId = id;
    this.lastTrigger = triggerEl || null;

    qs('[data-ins-eyebrow]', this.el).textContent = record.eyebrow;
    qs('[data-ins-title]', this.el).textContent = record.title;
    qs('[data-ins-category]', this.el).textContent = record.category || '';

    const st = STATUS[record.status] || STATUS.pending;
    const statusEl = qs('[data-ins-status]', this.el);
    statusEl.innerHTML = '';
    statusEl.dataset.status = record.status;
    statusEl.append(
      h('span', { class: 'inspector__glyph', 'aria-hidden': 'true', text: st.glyph }),
      h('span', { text: st.word })
    );

    qs('[data-ins-purpose]', this.el).textContent = record.purpose || '';
    qs('[data-ins-in]', this.el).textContent = record.inputs || '\u2014';
    qs('[data-ins-out]', this.el).textContent = record.outputs || '\u2014';
    qs('[data-ins-event]', this.el).textContent = record.event || '';
    qs('[data-ins-trail]', this.el).textContent = record.trail || '';

    /* Scope is the only optional field, and it is only present on objects where
       a scope boundary is a real property: evidence and parameters. Structures
       do not get an empty row. */
    const fields = qs('[data-ins-fields]', this.el);
    if (record.scope) {
      fields.replaceChildren(
        h('dt', { class: 'label label--micro', text: 'SCOPE' }),
        h('dd', { text: record.scope })
      );
      fields.hidden = false;
    } else {
      fields.replaceChildren();
      fields.hidden = true;
    }

    qs('[data-ins-note]', this.el).textContent = record.note || '';
    qs('[data-ins-foot]', this.el).textContent =
      record.status === 'review'
        ? 'Illustrative demo / disclosed assumption / not an experimental result'
        : 'Illustrative demo / not an experimental result';

    this.el.hidden = false;
    // allow layout before transition
    requestAnimationFrame(() => this.el.classList.add('is-open'));

    this.lightPath(svg, id, record);
    if (this.isSheet()) {
      /* Measure the sheet only once it has been laid out with this record's
         content, then give the camera the reduced band and ask it to bring the
         object into it. Order matters: reserving first and framing second means
         the frame is fitted to the band that actually remains. */
      requestAnimationFrame(() => {
        this.reserveSpace(true);
        if (this.onFrameNode) this.onFrameNode(id);
      });
    } else {
      this.reserveSpace(true);
    }

    // Keyboard and pointer are treated differently: a keyboard user needs the
    // record announced and their next Tab to land inside it, so focus moves
    // into the panel. A mouse user keeps focus where they left it.
    if (this.isSheet()) {
      qs('[data-ins-close]', this.el).focus({ preventScroll: true });
    } else if (fromKeyboard) {
      this.el.focus({ preventScroll: true });
    }
  }

  /* ------------------------------------------------------------
     ACTIVE PATH

     Inspecting an object is not a lookup, it is a question about
     where that object sits in the run. So the panel is only half
     the answer: the other half is drawn in the architecture, which
     stays on screen and marks the selected node plus the nodes it
     is actually related to. Everything else recedes but is never
     hidden — losing the monument would lose the context that makes
     the record mean anything.
     ------------------------------------------------------------ */
  lightPath(svg, id, record) {
    if (!svg) return;
    svg.classList.add('is-inspecting');
    qsa('.is-selected, .in-path', svg).forEach((el) => {
      el.classList.remove('is-selected');
      el.classList.remove('in-path');
    });
    qsa('.has-selection', svg).forEach((el) => el.classList.remove('has-selection'));

    const target = qs(`[data-node="${id}"]`, svg);
    if (target) {
      target.classList.add('is-selected');
      target.closest('.tier')?.classList.add('has-selection');
    }

    // Related nodes are raised with the selection, and their tiers with them,
    // so a relationship that crosses tiers stays legible as one path.
    (record.path || []).forEach((nid) => {
      if (nid === id) return;
      const el = qs(`[data-node="${nid}"]`, svg);
      if (!el) return;
      el.classList.add('in-path');
      el.closest('.tier')?.classList.add('has-selection');
    });
  }

  close() {
    if (!this.openId) return;
    this.openId = null;
    this.el.classList.remove('is-open');
    const wasSheet = this.isSheet();
    this.reserveSpace(false);
    if (wasSheet && this.onReleaseFrame) this.onReleaseFrame();
    const svg = qs('.cath-svg');
    if (svg) {
      svg.classList.remove('is-inspecting');
      qsa('.is-selected, .in-path', svg).forEach((el) => {
        el.classList.remove('is-selected');
        el.classList.remove('in-path');
      });
      qsa('.has-selection', svg).forEach((el) => el.classList.remove('has-selection'));
    }
    const t = this.lastTrigger;
    setTimeout(() => {
      if (!this.openId) this.el.hidden = true;
    }, 420);
    if (t && typeof t.focus === 'function') t.focus({ preventScroll: true });
  }

  /** Wire every interactive node in the given SVG to the inspector. */
  attach(svg) {
    qsa('[data-node]', svg).forEach((node) => {
      const id = node.dataset.node;
      node.addEventListener('click', (e) => {
        e.stopPropagation();
        this.open(id, node, svg);
      });
      node.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ' || e.key === 'Spacebar') {
          e.preventDefault();
          this.open(id, node, svg, true);
        }
      });
    });
  }
}
