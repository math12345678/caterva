/* ============================================================
   caterva — chapter seams

   The chapters were separated by a hairline border and a large
   pad, which made them read as four unrelated sections stacked in
   a column. They are not: each one is the previous one continuing.
   So the boundary between them carries structure that leaves the
   section above and becomes the section below.

     cathedral -> evidence   one source artifact leaves the spine
                             and opens into a provenance trail
     evidence  -> trust      the trail folds inward and closes
                             into the vault ring
     trust     -> execution  the output curve extends and divides
                             into three compute environments

   Drawn in the same hairline vocabulary as the cathedral, at a
   scale that never competes with either neighbour. Non-uniform
   scaling is deliberate: these are lane drawings, so horizontal
   stretch is correct, and non-scaling strokes keep the weight
   identical to the architecture above.
   ============================================================ */

import { s, qs, prefersReducedMotion } from '../lib/dom.js';

const W = 1600;
const H = 200;

function frame(kind) {
  const svg = s('svg', {
    class: 'seam-svg',
    viewBox: `0 0 ${W} ${H}`,
    /* Uniform scaling. Stretching to fill was distorting the geometry badly
       enough to change what it said: at 1.75x anisotropy the vault ring became a
       flat lozenge with none of the enclosure's proportions, and the fan curves
       lost their fall. These shapes quote the architecture above, so they have to
       keep its proportions. Void margins either side are correct — the seam is a
       centred join, not a full-bleed band. */
    preserveAspectRatio: 'xMidYMid meet',
    'aria-hidden': 'true',
    focusable: 'false'
  });
  svg.dataset.seam = kind;
  return svg;
}

/** A single artifact detaches from the spine and opens into a trail. */
function seamEvidence() {
  const svg = frame('evidence');
  const cx = W / 2;

  // the spine continuing out of the monument above
  svg.appendChild(s('path', { class: 'seam-line seam-line--spine', d: `M ${cx} 0 L ${cx} 74` }));

  // the artifact itself, mid-departure
  const art = s('g', { class: 'seam-artifact' });
  art.appendChild(s('path', { class: 'seam-solid', d: `M ${cx - 15} 66 L ${cx + 9} 66 L ${cx + 15} 72 L ${cx + 15} 88 L ${cx - 15} 88 Z` }));
  art.appendChild(s('path', { class: 'seam-hair', d: `M ${cx - 9} 74 L ${cx + 5} 74 M ${cx - 9} 80 L ${cx} 80` }));
  svg.appendChild(art);

  // opening into a provenance trail: four links fanning to the rail below
  [-3, -1, 1, 3].forEach((k, i) => {
    const x2 = cx + k * 210;
    svg.appendChild(s('path', {
      class: 'seam-line',
      d: `M ${cx} 90 C ${cx} 132, ${x2} 128, ${x2} 178`,
      style: `--seam-i:${i}`
    }));
    svg.appendChild(s('circle', { class: 'seam-node', cx: x2, cy: 176, r: 3, style: `--seam-i:${i}` }));
  });

  return svg;
}

/** The trail folds inward and closes into the vault ring. */
function seamTrust() {
  const svg = frame('trust');
  const cx = W / 2;

  [-3, -1, 1, 3].forEach((k, i) => {
    const x1 = cx + k * 210;
    svg.appendChild(s('circle', { class: 'seam-node', cx: x1, cy: 14, r: 3, style: `--seam-i:${i}` }));
    svg.appendChild(s('path', {
      class: 'seam-line',
      d: `M ${x1} 18 C ${x1} 66, ${cx} 74, ${cx} 112`,
      style: `--seam-i:${i}`
    }));
  });

  /* The ring the trail closes into. Centred at 152 with a 40 minor radius so its
     lower edge lands at 192, inside the 200-unit frame: at ry 42 about y 168 it
     was cut off by the viewBox and the fold appeared to end in nothing, which is
     the opposite of the intended reading. */
  const ring = s('g', { class: 'seam-ring' });
  const pts = [];
  const n = 16;
  for (let i = 0; i <= n; i += 1) {
    const a = (i / n) * Math.PI * 2 - Math.PI / 2;
    pts.push(`${(cx + Math.cos(a) * 104).toFixed(1)} ${(152 + Math.sin(a) * 40).toFixed(1)}`);
  }
  ring.appendChild(s('path', { class: 'seam-line', d: `M ${pts.join(' L ')} Z` }));
  // inner ring, so the enclosure reads as the vault's own wall thickness
  const inner = [];
  for (let i = 0; i <= n; i += 1) {
    const a = (i / n) * Math.PI * 2 - Math.PI / 2 + Math.PI / n;
    inner.push(`${(cx + Math.cos(a) * 78).toFixed(1)} ${(152 + Math.sin(a) * 30).toFixed(1)}`);
  }
  ring.appendChild(s('path', { class: 'seam-line', d: `M ${inner.join(' L ')} Z`, opacity: 0.55 }));
  svg.appendChild(ring);

  return svg;
}

/** The output curve extends and divides into three runtimes. */
function seamExecution() {
  const svg = frame('execution');
  const cx = W / 2;

  /* The saturating curve continuing out of the core above. It enters at the
     left, flattens toward its plateau, and the division happens at the plateau
     — which is the honest place for it, because that is where the output is
     finished and the only remaining question is where it can run. */
  const tail = cx + 40;
  svg.appendChild(s('path', {
    class: 'seam-line seam-line--curve',
    d: `M ${cx - 460} 10 C ${cx - 330} 12, ${cx - 250} 58, ${cx - 120} 66`
      + ` C ${cx - 40} 70, ${cx - 10} 72, ${tail} 72`
  }));

  /* Dividing into three lanes. All three branches leave the same point at the
     plateau and open symmetrically about it, so nothing doubles back across the
     curve it came from. */
  [-1, 0, 1].forEach((k, i) => {
    const x2 = cx + k * 400;
    svg.appendChild(s('path', {
      class: 'seam-line',
      d: `M ${tail} 74 C ${tail + 30} 112, ${x2} 116, ${x2} 168`,
      style: `--seam-i:${i}`
    }));
    svg.appendChild(s('path', {
      class: 'seam-line seam-line--lane',
      d: `M ${x2 - 84} 172 L ${x2 + 84} 172`,
      style: `--seam-i:${i}`
    }));
  });

  return svg;
}

const BUILDERS = {
  evidence: seamEvidence,
  trust: seamTrust,
  execution: seamExecution
};

/** Mount each seam above the chapter it introduces and draw it on approach. */
export function initSeams() {
  const targets = [
    ['#evidence', 'evidence'],
    ['#separation', 'trust'],
    ['#execution', 'execution']
  ];

  targets.forEach(([sel, kind]) => {
    const section = qs(sel);
    if (!section) return;
    const wrap = document.createElement('div');
    wrap.className = 'seam';
    wrap.dataset.seamFor = kind;
    wrap.appendChild(BUILDERS[kind]());
    section.parentNode.insertBefore(wrap, section);
    // The section no longer needs its own top border; the seam carries it.
    section.classList.add('chapter--seamed');

    if (prefersReducedMotion() || !('IntersectionObserver' in window)) {
      wrap.classList.add('is-drawn');
      return;
    }
    const io = new IntersectionObserver((entries) => {
      entries.forEach((e) => {
        if (e.isIntersecting) {
          wrap.classList.add('is-drawn');
          io.disconnect();
        }
      });
    }, { threshold: 0.25 });
    io.observe(wrap);
  });
}
