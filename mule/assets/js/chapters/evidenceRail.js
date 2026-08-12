/* ============================================================
   Chapter 01 — the evidence rail
   A single parameter's provenance, link by link, inspectable.
   ============================================================ */

import { h, qs, qsa } from '../lib/dom.js';

const LINKS = [
  {
    id: 'source',
    label: 'Source basis',
    form: 'sheet',
    title: 'Demo source / enzyme kinetics method',
    body: 'An illustrative literature record. It carries a scope: which enzyme, which conditions. The scope travels with the value.',
    status: 'supported'
  },
  {
    id: 'parameter',
    label: 'Parameter',
    form: 'plate',
    title: 'Km — 0.42 mM',
    body: 'The value is attached to its source rather than asserted. A parameter without support is labelled, not hidden.',
    status: 'supported'
  },
  {
    id: 'decision',
    label: 'Configuration decision',
    form: 'lattice',
    title: 'Docked into the parameter schema',
    body: 'The configuration agent records where the value came from and which conditions it assumes.',
    status: 'supported'
  },
  {
    id: 'model',
    label: 'Executed model',
    form: 'core',
    title: 'Local ODE runtime / illustrated',
    /* Was "executed as a browser-compatible numerical system", which is not
       what happens and contradicts two other places on this page: the compute
       router's own record says the browser runtime was insufficient for the
       integration, and manifest item 04 promises no browser execution where
       real compute is required. Terrium integrates ODEs through libroadrunner
       outside the browser; the rail now says that. */
    body: 'The schema is integrated by a real ODE solver outside the browser. Where the method cannot run there either, routing escalates instead of pretending.',
    status: 'user'
  },
  {
    id: 'verification',
    label: 'Verification event',
    form: 'sentinel',
    title: 'Traced by the hallucination check',
    body: 'The check follows the value back to its evidence object. Resolved links turn teal. Unresolved values stay amber.',
    status: 'supported'
  },
  {
    id: 'record',
    label: 'Final record',
    form: 'record',
    title: 'Carried into verified run / 0007',
    body: 'The trail survives presentation. Polish may format the record, but it may never remove a disclosure.',
    status: 'supported'
  }
];

const GLYPH = {
  supported: '\u25C6',
  user: '\u25A0',
  review: '\u25B2'
};

/** Small architectural mark per link — each form reads differently. */
function linkMark(form) {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', '0 0 34 34');
  svg.setAttribute('class', 'rail-mark');
  svg.setAttribute('aria-hidden', 'true');
  const paths = {
    sheet: '<path d="M8 6h13l5 5v17H8z"/><path d="M12 14h11M12 19h8" class="thin"/>',
    plate: '<path d="M5 11h24v12H5z"/><path d="M11 11v12M23 11v12" class="thin"/>',
    lattice: '<path d="M6 6h22v22H6z"/><path d="M13 6v22M20 6v22M6 13h22M6 20h22" class="thin"/>',
    core: '<path d="M17 4l13 13-13 13L4 17z"/><circle cx="17" cy="17" r="3.4" class="fill"/>',
    sentinel: '<path d="M17 4l11 6v10l-11 8-11-8V10z"/><circle cx="17" cy="15" r="2.6" class="fill"/>',
    record: '<path d="M6 5h22v24H6z"/><path d="M11 12h12M11 18h12M11 24h7" class="thin"/>'
  };
  svg.innerHTML = paths[form] || paths.plate;
  return svg;
}

export function initEvidenceRail() {
  const mount = qs('[data-evidence-rail]');
  const detail = qs('[data-rail-detail]');
  if (!mount || !detail) return;

  const render = (activeId) => {
    qsa('.rail-link', mount).forEach((el) => {
      const on = el.dataset.link === activeId;
      el.classList.toggle('is-active', on);
      el.setAttribute('aria-selected', on ? 'true' : 'false');
      el.tabIndex = on ? 0 : -1;
    });
    const link = LINKS.find((l) => l.id === activeId);
    detail.replaceChildren(
      h('p', { class: 'label label--micro', text: link.label }),
      h('h3', { class: 'rail-detail__title', text: link.title }),
      h('p', { class: 'rail-detail__body', text: link.body }),
      h('p', { class: 'rail-detail__status', dataset: { status: link.status } }, [
        h('span', { 'aria-hidden': 'true', text: GLYPH[link.status] }),
        h('span', { text: link.status === 'user' ? 'User-defined / example condition' : 'Illustrative source-supported example' })
      ])
    );
  };

  const items = LINKS.map((link, i) => {
    const btn = h('button', {
      class: 'rail-link',
      type: 'button',
      role: 'tab',
      dataset: { link: link.id },
      'aria-selected': 'false',
      tabindex: '-1'
    }, [
      h('span', { class: 'rail-link__index label label--micro', text: String(i + 1).padStart(2, '0') }),
      h('span', { class: 'rail-link__mark' }, [linkMark(link.form)]),
      h('span', { class: 'rail-link__label', text: link.label })
    ]);
    btn.addEventListener('click', () => render(link.id));
    btn.addEventListener('keydown', (e) => {
      const dirs = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 };
      if (dirs[e.key]) {
        e.preventDefault();
        const next = (i + dirs[e.key] + LINKS.length) % LINKS.length;
        render(LINKS[next].id);
        qs(`[data-link="${LINKS[next].id}"]`, mount)?.focus();
      }
    });
    return btn;
  });

  mount.setAttribute('role', 'tablist');
  mount.setAttribute('aria-label', 'Evidence provenance chain for parameter Km');
  // Conduits between links carry a staggered pulse: evidence moving along
  // a defined route, matching the cathedral's own visual vocabulary.
  const joint = (i) => h('span', {
    class: 'rail-joint', 'aria-hidden': 'true',
    style: `--flow-delay:${i * 260}ms`
  }, [h('span', { class: 'rail-pulse' })]);

  mount.replaceChildren(
    ...items.flatMap((el, i) => (i < items.length - 1 ? [el, joint(i)] : [el]))
  );

  render(LINKS[0].id);
}
