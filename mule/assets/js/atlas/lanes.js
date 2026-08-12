/* ============================================================
   terrium — atlas route lanes

   Routes are drawn as transit corridors: straight runs, chamfered
   turns, no bezier swoops. The chamfer is the same language the
   cathedral uses for its module silhouettes, which is what keeps
   the atlas reading as one drawing rather than two.
   ============================================================ */

const dist = (a, b) => Math.hypot(b[0] - a[0], b[1] - a[1]);

/** Point `d` along the segment a→b. */
function along(a, b, d) {
  const len = dist(a, b) || 1;
  const t = Math.min(d, len) / len;
  return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
}

/**
 * Polyline → path with chamfered corners.
 * The cut is clamped to half of each adjoining segment so short
 * runs degrade into a plain corner instead of overshooting and
 * turning the lane inside out.
 */
export function lanePath(points, chamfer = 18) {
  if (!points || points.length < 2) return '';
  const p = points;
  let d = `M ${p[0][0]} ${p[0][1]}`;
  for (let i = 1; i < p.length - 1; i++) {
    const prev = p[i - 1], cur = p[i], next = p[i + 1];
    const cut = Math.min(chamfer, dist(prev, cur) / 2, dist(cur, next) / 2);
    const inPt = along(cur, prev, cut);
    const outPt = along(cur, next, cut);
    d += ` L ${inPt[0]} ${inPt[1]} L ${outPt[0]} ${outPt[1]}`;
  }
  const last = p[p.length - 1];
  d += ` L ${last[0]} ${last[1]}`;
  return d;
}

/**
 * Where a route's payload label belongs: the midpoint of its longest
 * straight run. Labels on short connector stubs collide with the
 * modules at either end, and the longest run is also the part of the
 * lane a reader's eye follows, so the label lands where they are
 * already looking.
 */
export function labelAnchor(points) {
  let best = 0, bestLen = -1;
  for (let i = 0; i < points.length - 1; i++) {
    const len = dist(points[i], points[i + 1]);
    if (len > bestLen) { bestLen = len; best = i; }
  }
  const a = points[best], b = points[best + 1];
  const horizontal = Math.abs(b[0] - a[0]) >= Math.abs(b[1] - a[1]);
  return {
    x: (a[0] + b[0]) / 2,
    y: (a[1] + b[1]) / 2,
    horizontal,
    run: bestLen
  };
}

/**
 * A small open chevron at the arrival end, oriented along the final
 * segment. Open rather than filled: a solid arrowhead is the single
 * strongest signal that a drawing is a flowchart.
 */
export function arrivalChevron(points, size = 13) {
  const b = points[points.length - 1];
  const a = points[points.length - 2] || [b[0] - 1, b[1]];
  const ang = Math.atan2(b[1] - a[1], b[0] - a[0]);
  const wing = 2.5;
  const p1 = [b[0] - size * Math.cos(ang - Math.PI / wing), b[1] - size * Math.sin(ang - Math.PI / wing)];
  const p2 = [b[0] - size * Math.cos(ang + Math.PI / wing), b[1] - size * Math.sin(ang + Math.PI / wing)];
  return `M ${p1[0]} ${p1[1]} L ${b[0]} ${b[1]} L ${p2[0]} ${p2[1]}`;
}

/** Total run length, used to prime dash animations without a DOM read. */
export function laneLength(points) {
  let total = 0;
  for (let i = 0; i < points.length - 1; i++) total += dist(points[i], points[i + 1]);
  return Math.round(total);
}

/** Small square registration mark, used where a lane leaves a module. */
export function portMark(points, size = 7) {
  const [x, y] = points[0];
  return { x: x - size / 2, y: y - size / 2, w: size, h: size };
}
