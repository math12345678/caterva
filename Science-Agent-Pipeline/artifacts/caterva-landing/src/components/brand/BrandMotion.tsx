import { useEffect, useRef } from "react";

/**
 * The mark, in motion: a swell travels around the C, the signal dot hands its
 * colour from the top of the C to its open end, the C steps aside and the
 * wordmark sets itself letter by letter; then it all returns. One 11 s loop,
 * drawn from the measured geometry in Mark.tsx, never a video.
 *
 * Reduced motion shows the finished lockup, still. Off screen or in a
 * hidden tab it stops drawing. Every frame is written straight to the DOM
 * from one requestAnimationFrame loop, so React does not re-render at 60 Hz.
 */

// [cx, cy, r] from the master artwork, in the order the swell visits them:
// the C's upper end (signal), round the back, to its open lower end.
const RING: ReadonlyArray<readonly [number, number, number]> = [
  [688.7, 309.3, 50.9], // 0: upper end, the signal dot in the mark
  [541.3, 242.6, 61.7],
  [386.5, 281.7, 44.2],
  [305.1, 403.8, 59.6],
  [297.4, 569.0, 44.2],
  [382.6, 697.4, 60.2],
  [542.5, 744.6, 53.5],
  [680.8, 684.5, 44.2], // 7: open end, the signal dot in the lockup
];
const VIEW = { x: 236, y: 172, w: 514, h: 634 };
const LETTERS = "caterva".split("");
const LOOP = 11; // seconds

const clamp = (x: number, a = 0, b = 1) => Math.min(b, Math.max(a, x));
const easeOutQuint = (t: number) => 1 - Math.pow(1 - clamp(t), 5);
const easeInOutCubic = (t: number) => {
  const x = clamp(t);
  return x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2;
};
const span = (t: number, a: number, b: number) => clamp((t - a) / (b - a));

/** Where the loop is, as the few numbers every element needs. */
function frame(t: number) {
  // The swell: two passes round the ring, one while centred at the start,
  // one on the way back, as in the reference.
  const swellA = span(t, 0.2, 2.6);
  const swellB = span(t, 8.9, 10.9);
  const swell = swellA > 0 && swellA < 1 ? swellA : swellB > 0 && swellB < 1 ? swellB : -1;
  // Centred mark -> lockup -> centred mark.
  const toLockup = easeInOutCubic(span(t, 2.4, 3.5));
  const toMark = easeInOutCubic(span(t, 8.0, 9.1));
  const lockup = toLockup * (1 - toMark);
  return { swell, lockup, t };
}

export interface Pose {
  /** Each ring dot's radius, in artwork units. */
  radii: number[];
  /** Which ring dot carries the signal colour (0 = upper end, 7 = open end). */
  signal: number;
  /** 0 = the mark alone, centred; 1 = the lockup. */
  lockup: number;
  /** The mark's scale: 1 alone, 0.5 in the lockup. */
  scale: number;
  /** Each letter's opacity and vertical offset (em). */
  letters: { opacity: number; rise: number }[];
}

/** Everything drawn at time t (seconds into the loop). Pure, so it is tested. */
export function pose(t: number): Pose {
  const f = frame(((t % LOOP) + LOOP) % LOOP);
  const radii = RING.map(([, , r], i) => {
    let s = 1;
    if (f.swell >= 0) {
      const p = f.swell * (RING.length + 1) - 0.5;
      const d = i - p;
      // Strong enough that neighbours meet, as in the reference animation.
      s += (i === 0 || i === 7 ? 1.15 : 0.85) * Math.exp(-(d * d) / 1.3);
    }
    return r * s;
  });
  const letters = LETTERS.map((_, i) => {
    const tt = f.t;
    const inT = easeOutQuint(span(tt, 3.2 + i * 0.13, 3.9 + i * 0.13));
    const k = LETTERS.length - 1 - i;
    const outT = easeInOutCubic(span(tt, 7.7 + k * 0.04, 8.2 + k * 0.04));
    return { opacity: inT * (1 - outT), rise: (1 - inT) * 0.45 - outT * 0.15 };
  });
  return { radii, signal: f.lockup > 0.5 ? 7 : 0, lockup: f.lockup, scale: 1 - 0.5 * f.lockup, letters };
}

export default function BrandMotion({ height = 170 }: { height?: number }) {
  const stage = useRef<HTMLDivElement>(null);
  const svg = useRef<SVGSVGElement>(null);
  const dots = useRef<(SVGCircleElement | null)[]>([]);
  const word = useRef<HTMLSpanElement>(null);
  const letters = useRef<(HTMLSpanElement | null)[]>([]);

  useEffect(() => {
    const root = stage.current!;
    const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    const markW = (height * VIEW.w) / VIEW.h;
    const small = 0.5; // the mark's scale in the lockup
    const gap = height * small * 0.55;

    const place = (lockup: number) => {
      const W = root.clientWidth;
      const textW = word.current?.offsetWidth ?? 0;
      const total = markW * small + gap + textW;
      const left = (W - total) / 2;
      const scale = 1 + (small - 1) * lockup; // = pose().scale
      const centreX = W / 2 + (left + (markW * small) / 2 - W / 2) * lockup;
      svg.current!.style.transform = `translate(${centreX - markW / 2}px, 0) scale(${scale})`;
      word.current!.style.transform = `translate(${left + markW * small + gap}px, -50%)`;
    };

    const draw = (t: number) => {
      const p = pose(t);
      place(p.lockup);
      p.radii.forEach((r, i) => {
        const c = dots.current[i];
        if (!c) return;
        c.setAttribute("r", String(r));
        c.style.fill = i === p.signal ? "var(--signal)" : "currentColor";
      });
      p.letters.forEach(({ opacity, rise }, i) => {
        const el = letters.current[i];
        if (!el) return;
        el.style.opacity = String(opacity);
        el.style.transform = `translateY(${rise}em)`;
      });
    };

    if (reduced) {
      draw(5.5); // the settled lockup
      const onResize = () => draw(5.5);
      window.addEventListener("resize", onResize);
      return () => window.removeEventListener("resize", onResize);
    }

    let raf = 0;
    let visible = true;
    let start = performance.now();
    let pausedAt = 0;
    const tick = (now: number) => {
      draw(((now - start) / 1000) % LOOP);
      raf = requestAnimationFrame(tick);
    };
    const run = () => {
      if (raf || !visible || document.hidden) return;
      start += performance.now() - pausedAt;
      raf = requestAnimationFrame(tick);
    };
    const stop = () => {
      if (!raf) return;
      cancelAnimationFrame(raf);
      raf = 0;
      pausedAt = performance.now();
    };
    const io =
      typeof IntersectionObserver === "undefined"
        ? null
        : new IntersectionObserver(([e]) => {
            visible = e.isIntersecting;
            visible ? run() : stop();
          });
    io?.observe(root);
    const onVis = () => (document.hidden ? stop() : run());
    document.addEventListener("visibilitychange", onVis);
    pausedAt = performance.now();
    draw(0);
    run();
    return () => {
      stop();
      io?.disconnect();
      document.removeEventListener("visibilitychange", onVis);
    };
  }, [height]);

  return (
    <div
      ref={stage}
      role="img"
      aria-label="caterva"
      className="relative w-full overflow-hidden text-fg select-none"
      style={{ height: height * 1.25 }}
      data-testid="brand-motion"
    >
      <svg
        ref={svg}
        aria-hidden
        viewBox={`${VIEW.x} ${VIEW.y} ${VIEW.w} ${VIEW.h}`}
        height={height}
        width={(height * VIEW.w) / VIEW.h}
        className="absolute left-0 overflow-visible"
        style={{ top: height * 0.125, transformOrigin: "50% 50%", willChange: "transform" }}
      >
        {RING.map(([cx, cy, r], i) => (
          <circle
            key={i}
            ref={(el) => (dots.current[i] = el)}
            cx={cx}
            cy={cy}
            r={r}
            fill={i === 0 ? "var(--signal)" : "currentColor"}
          />
        ))}
      </svg>
      <span
        ref={word}
        aria-hidden
        className="wordmark absolute left-0 top-1/2 leading-none whitespace-nowrap"
        style={{ fontSize: height * 0.5 * 0.72, willChange: "transform" }}
      >
        {LETTERS.map((l, i) => (
          <span
            key={i}
            ref={(el) => (letters.current[i] = el)}
            className="inline-block"
            style={{ opacity: 0 }}
          >
            {l}
          </span>
        ))}
      </span>
    </div>
  );
}
