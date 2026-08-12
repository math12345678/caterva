/* ============================================================
   terrium — tiny DOM / SVG construction helpers
   ============================================================ */

const SVG_NS = 'http://www.w3.org/2000/svg';

/** Create an SVG element with attributes and children. */
export function s(tag, attrs = {}, children = []) {
  const el = document.createElementNS(SVG_NS, tag);
  // Stroke-only architecture: an open <path> must never inherit SVG's
  // default black fill. CSS-declared fills still take precedence over
  // this presentation attribute.
  if ((tag === 'path' || tag === 'polyline') && !('fill' in attrs)) {
    el.setAttribute('fill', 'none');
  }
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined || v === false) continue;
    if (k === 'class') el.setAttribute('class', v);
    else if (k === 'text') el.textContent = v;
    else if (k === 'style') el.setAttribute('style', v);
    // `dataset` is spelled the same way here as in h(). SVGElement.dataset is
    // writable, but assigning the object wholesale is not — without this branch
    // the key falls through to setAttribute and writes the literal attribute
    // dataset="[object Object]", so every data-* hook silently disappears.
    else if (k === 'dataset') {
      for (const [dk, dv] of Object.entries(v)) {
        if (dv === null || dv === undefined || dv === false) continue;
        el.dataset[dk] = String(dv);
      }
    }
    else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, String(v));
  }
  for (const c of [].concat(children)) {
    if (c) el.appendChild(c);
  }
  return el;
}

/** Create an HTML element. */
export function h(tag, attrs = {}, children = []) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k === 'text') el.textContent = v;
    else if (k === 'html') el.innerHTML = v;
    /* Nullish entries are dropped rather than assigned, matching the way a
       nullish attribute is skipped above. Object.assign would stringify them
       into data-tone="null", which then matches [data-tone] selectors and
       styles an element for a state it is not in. */
    else if (k === 'dataset') {
      for (const [dk, dv] of Object.entries(v)) {
        if (dv === null || dv === undefined || dv === false) continue;
        el.dataset[dk] = String(dv);
      }
    }
    else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, String(v));
  }
  for (const c of [].concat(children)) {
    if (c === null || c === undefined) continue;
    el.appendChild(typeof c === 'string' ? document.createTextNode(c) : c);
  }
  return el;
}

export const qs = (sel, root = document) => root.querySelector(sel);
export const qsa = (sel, root = document) => Array.from(root.querySelectorAll(sel));

/** Measure a path's length once it is in the DOM, and prime dash animation. */
export function primeDash(pathEl) {
  try {
    const len = pathEl.getTotalLength();
    pathEl.style.setProperty('--len', `${Math.ceil(len)}`);
    return len;
  } catch {
    pathEl.style.setProperty('--len', '400');
    return 400;
  }
}

export const prefersReducedMotion = () =>
  window.matchMedia('(prefers-reduced-motion: reduce)').matches;

/** Reveal-on-scroll observer, shared across sections. */
export function observeReveals(root = document) {
  const items = qsa('[data-reveal]', root);
  if (!items.length) return;
  if (prefersReducedMotion() || !('IntersectionObserver' in window)) {
    items.forEach((el) => el.classList.add('is-revealed'));
    return;
  }
  const io = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add('is-revealed');
          io.unobserve(entry.target);
        }
      });
    },
    { rootMargin: '0px 0px -12% 0px', threshold: 0.08 }
  );
  items.forEach((el) => io.observe(el));
}

/** Pause CSS animations when the tab is hidden (performance). */
export function installVisibilityGuard() {
  const onChange = () => {
    document.documentElement.classList.toggle('is-tab-hidden', document.hidden);
  };
  document.addEventListener('visibilitychange', onChange);
  onChange();
}

/** Focus trap helper for the inspector / dialogs. */
export function trapFocus(container, event) {
  const focusables = qsa(
    'a[href], button:not([disabled]), input:not([disabled]), textarea, select, [tabindex]:not([tabindex="-1"])',
    container
  ).filter((el) => el.offsetParent !== null);
  if (!focusables.length) return;
  const first = focusables[0];
  const last = focusables[focusables.length - 1];
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
}
