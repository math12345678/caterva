/* ============================================================
   caterva — chapter bootstrapping
   Chapters below the fold initialise lazily so the first
   interaction is never delayed.
   ============================================================ */

import { qs, h, prefersReducedMotion } from '../lib/dom.js';
import { PIPELINE_TEXT } from '../config/architecture.js';
import { initSeams } from './seams.js';

function renderPipelineList() {
  const list = qs('[data-pipeline-list]');
  if (!list) return;
  list.replaceChildren(
    ...PIPELINE_TEXT.map((step, i) =>
      h('li', { class: 'pipeline-step' }, [
        h('span', { class: 'pipeline-step__n label label--micro', text: String(i + 1).padStart(2, '0') }),
        h('span', { class: 'pipeline-step__l', text: step })
      ])
    )
  );
}

/** Load a chapter module when its section approaches the viewport. */
function lazySection(selector, loader) {
  const el = qs(selector);
  if (!el) return;
  let done = false;
  const run = () => {
    if (done) return;
    done = true;
    loader();
  };
  if (prefersReducedMotion() || !('IntersectionObserver' in window)) {
    run();
    return;
  }
  const io = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          run();
          io.disconnect();
        }
      });
    },
    { rootMargin: '400px 0px' }
  );
  io.observe(el);
}

export function initChapters() {
  renderPipelineList();

  /* Seams are structure, not decoration, and they are what makes the page read
     as one continuous descent rather than four stacked sections. They mount
     immediately: lazy-loading them would leave visible gaps between chapters
     during the scroll that is precisely when they are needed. */
  initSeams();

  lazySection('#evidence', async () => {
    const { initEvidenceRail } = await import('./evidenceRail.js');
    initEvidenceRail();
  });

  lazySection('#trust', async () => {
    const { initExplodedVault } = await import('./explodedVault.js');
    initExplodedVault();
  });

  lazySection('#execution', async () => {
    const { initExecutionStrata } = await import('./executionStrata.js');
    initExecutionStrata();
  });

  initMastheadInversion();
}

/* ------------------------------------------------------------
   MASTHEAD OVER THE ARCHIVAL SHEET
   The whole page is dark except its last section, which is the pale
   record the architecture produces. The masthead is fixed, so over
   that section it was near-white type on near-white paper —
   measured at roughly 1.1:1, which is illegible. The record is the
   point of the invitation and must not be darkened to accommodate
   chrome, so the chrome inverts instead: the mark and the navigation
   take graphite while they are over paper.
   ------------------------------------------------------------ */
function initMastheadInversion() {
  const mast = qs('.masthead');
  const pilot = qs('#pilot');
  if (!mast || !pilot) return;

  /* Two states are not enough, and measuring proved it. The seam is a gradient
     from graphite into paper, so between the two ends there is a band of
     mid-grey — sampled at rgb(138,141,138) — and on mid-grey NEITHER colour
     works: light chrome falls to 2.7:1 and graphite chrome to 1.0:1 while the
     backdrop is still dark. Flipping earlier or later only moves the failure.

     So there are three states, and the middle one is honest about the fact
     that the backdrop is briefly unusable: while the masthead is crossing the
     seam it keeps its light type and carries a void scrim of its own. The
     scrim is the same graphite the sheet is rising out of, and it is gone by
     the time the reader is standing on the paper — so the artifact is never
     covered while it is being read.

     The scrim itself is now the resting state on every dark section rather
     than something this function switches on (see base.css: fixed chrome over
     unpainted sections was colliding with pale type all down the page). What
     these two classes still decide is the part only scroll position can know:
     `is-on-paper` inverts the type AND suppresses the scrim, and `is-crossing`
     marks the band where neither type colour works, so the light type and the
     scrim both have to be held through it. */
  const gradientBand = () => {
    // .pilot::before is the seam gradient; its height is the same clamp
    // expression, read back off the element so CSS stays the single source.
    const probe = getComputedStyle(pilot, '::before').height;
    const px = parseFloat(probe);
    return Number.isFinite(px) && px > 0 ? px : 160;
  };

  const set = () => {
    const p = pilot.getBoundingClientRect();
    const m = mast.getBoundingClientRect();
    const paperTop = p.top + gradientBand();

    // Fully past the gradient: opaque paper behind the whole bar.
    const onPaper = paperTop <= m.top && p.bottom >= m.bottom;
    // Overlapping the gradient at all: backdrop is indeterminate.
    const crossing = !onPaper && p.top < m.bottom + 24 && paperTop > m.top - 24 && p.bottom > m.top;

    mast.classList.toggle('is-on-paper', onPaper);
    mast.classList.toggle('is-crossing', crossing);
  };
  set();
  window.addEventListener('scroll', set, { passive: true });
  window.addEventListener('resize', set);
}
