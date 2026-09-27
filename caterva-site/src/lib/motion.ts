/**
 * Motion primitives.
 *
 * Every animation on the site routes through one of these, so timing and
 * easing stay consistent and `prefers-reduced-motion` is honoured in exactly
 * one place rather than being re-remembered per component.
 */

import { useEffect, useRef, useState, useCallback } from 'react';

export const EASE_OUT = 'cubic-bezier(0.16, 1, 0.3, 1)';
export const EASE_IN_OUT = 'cubic-bezier(0.65, 0, 0.35, 1)';

export function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)');
    const sync = () => setReduced(mq.matches);
    sync();
    mq.addEventListener('change', sync);
    return () => mq.removeEventListener('change', sync);
  }, []);
  return reduced;
}

/** Fires once when the element first enters the viewport. */
export function useInView<T extends HTMLElement>(
  rootMargin = '-12% 0px -12% 0px',
): [React.RefObject<T>, boolean] {
  const ref = useRef<T>(null);
  const [seen, setSeen] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el || seen) return;
    if (typeof IntersectionObserver === 'undefined') {
      setSeen(true);
      return;
    }
    const io = new IntersectionObserver(
      ([e]) => {
        if (e.isIntersecting) {
          setSeen(true);
          io.disconnect();
        }
      },
      { rootMargin, threshold: 0.01 },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [seen, rootMargin]);

  return [ref, seen];
}

/** Eased count-up. Returns the target immediately under reduced motion. */
export function useCountUp(
  target: number,
  active: boolean,
  duration = 1100,
  decimals = 0,
): string {
  const reduced = useReducedMotion();
  const [v, setV] = useState(0);
  const raf = useRef<number>();

  useEffect(() => {
    if (!active) return;
    if (reduced) {
      setV(target);
      return;
    }
    const t0 = performance.now();
    const tick = (now: number) => {
      const k = Math.min(1, (now - t0) / duration);
      const eased = 1 - Math.pow(1 - k, 4);
      setV(target * eased);
      if (k < 1) raf.current = requestAnimationFrame(tick);
    };
    raf.current = requestAnimationFrame(tick);
    return () => {
      if (raf.current) cancelAnimationFrame(raf.current);
    };
  }, [target, active, duration, reduced]);

  return v.toFixed(decimals);
}

/** Character-by-character typing. */
export function useTypewriter(
  text: string,
  active: boolean,
  cps = 55,
  delay = 0,
): { shown: string; done: boolean } {
  const reduced = useReducedMotion();
  const [n, setN] = useState(0);
  const [done, setDone] = useState(false);

  useEffect(() => {
    if (!active) return;
    if (reduced) {
      setN(text.length);
      setDone(true);
      return;
    }
    setN(0);
    setDone(false);
    let id: number;
    let raf: number;
    const start = () => {
      const t0 = performance.now();
      const tick = (now: number) => {
        const k = Math.floor(((now - t0) / 1000) * cps);
        if (k >= text.length) {
          setN(text.length);
          setDone(true);
          return;
        }
        setN(k);
        raf = requestAnimationFrame(tick);
      };
      raf = requestAnimationFrame(tick);
    };
    id = window.setTimeout(start, delay);
    return () => {
      window.clearTimeout(id);
      if (raf) cancelAnimationFrame(raf);
    };
  }, [text, active, cps, delay, reduced]);

  return { shown: text.slice(0, n), done };
}

/** Scroll progress through an element, 0 at entry, 1 at exit. */
export function useScrollProgress<T extends HTMLElement>(): [
  React.RefObject<T>,
  number,
] {
  const ref = useRef<T>(null);
  const [p, setP] = useState(0);

  const onScroll = useCallback(() => {
    const el = ref.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    const vh = window.innerHeight;
    const total = r.height + vh;
    const seen = vh - r.top;
    setP(Math.max(0, Math.min(1, seen / total)));
  }, []);

  useEffect(() => {
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', onScroll);
    return () => {
      window.removeEventListener('scroll', onScroll);
      window.removeEventListener('resize', onScroll);
    };
  }, [onScroll]);

  return [ref, p];
}
