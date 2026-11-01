/**
 * The page background: a live Lennard-Jones molecular dynamics simulation.
 *
 * Bonds are drawn between particles inside the interaction cutoff, with
 * opacity falling off as the pair separates — so the lattice visibly forms,
 * strains and breaks as the system evolves. The cursor acts as a repulsive
 * body, which is the same pairwise force with the sign flipped.
 *
 * It runs at a deliberately low contrast. It is texture, not decoration, and
 * it should never compete with the text sitting on top of it.
 */

import { useEffect, useRef } from 'react';
import { createMD, step, CUTOFF, type MDState } from '../lib/md';
import { useReducedMotion } from '../lib/motion';

export default function AmbientLattice() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const stateRef = useRef<MDState | null>(null);
  const mouseRef = useRef({ x: -9999, y: -9999 });
  const rafRef = useRef<number>();
  const reduced = useReducedMotion();

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let w = 0;
    let h = 0;
    let dpr = 1;

    const resize = () => {
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      w = window.innerWidth;
      h = window.innerHeight;
      canvas.width = Math.floor(w * dpr);
      canvas.height = Math.floor(h * dpr);
      canvas.style.width = `${w}px`;
      canvas.style.height = `${h}px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

      // Density scales with area so a wide monitor doesn't look sparse and a
      // phone doesn't melt.
      const n = Math.max(34, Math.min(96, Math.round((w * h) / 26000)));
      stateRef.current = createMD(n, w, h, 42);
    };

    resize();
    window.addEventListener('resize', resize);

    const onMove = (e: PointerEvent) => {
      mouseRef.current.x = e.clientX;
      mouseRef.current.y = e.clientY;
    };
    const onLeave = () => {
      mouseRef.current.x = -9999;
      mouseRef.current.y = -9999;
    };
    window.addEventListener('pointermove', onMove, { passive: true });
    window.addEventListener('pointerleave', onLeave);

    const draw = () => {
      const s = stateRef.current;
      if (!s) return;

      if (!reduced) {
        // The cursor repels, using the same pair force with the sign flipped.
        const { x: mx, y: my } = mouseRef.current;
        if (mx > -9000) {
          for (let i = 0; i < s.n; i++) {
            const dx = s.pos[i * 2] - mx;
            const dy = s.pos[i * 2 + 1] - my;
            const r2 = dx * dx + dy * dy;
            if (r2 < 30000 && r2 > 1) {
              const f = Math.min(0.5, 900 / r2);
              s.vel[i * 2] += (dx / Math.sqrt(r2)) * f;
              s.vel[i * 2 + 1] += (dy / Math.sqrt(r2)) * f;
            }
          }
        }
        step(s, 0.9);
      }

      ctx.clearRect(0, 0, w, h);

      // Bonds first, so particles sit on top of them.
      const cut2 = CUTOFF * CUTOFF;
      ctx.lineWidth = 1;
      for (let i = 0; i < s.n; i++) {
        const xi = s.pos[i * 2];
        const yi = s.pos[i * 2 + 1];
        for (let j = i + 1; j < s.n; j++) {
          const dx = xi - s.pos[j * 2];
          const dy = yi - s.pos[j * 2 + 1];
          const r2 = dx * dx + dy * dy;
          if (r2 > cut2) continue;
          const t = 1 - Math.sqrt(r2) / CUTOFF;
          const a = t * t * 0.2;
          if (a < 0.006) continue;
          ctx.strokeStyle = `rgba(110,231,183,${a})`;
          ctx.beginPath();
          ctx.moveTo(xi, yi);
          ctx.lineTo(s.pos[j * 2], s.pos[j * 2 + 1]);
          ctx.stroke();
        }
      }

      for (let i = 0; i < s.n; i++) {
        const x = s.pos[i * 2];
        const y = s.pos[i * 2 + 1];
        const sp = Math.hypot(s.vel[i * 2], s.vel[i * 2 + 1]);
        const hot = Math.min(1, sp / 1.6);
        ctx.beginPath();
        ctx.arc(x, y, 1.35, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(${140 + hot * 90},${231},${183},${0.22 + hot * 0.4})`;
        ctx.fill();
      }

      rafRef.current = requestAnimationFrame(draw);
    };

    rafRef.current = requestAnimationFrame(draw);

    return () => {
      window.removeEventListener('resize', resize);
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerleave', onLeave);
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [reduced]);

  return (
    <div className="pointer-events-none fixed inset-0 z-0" aria-hidden="true">
      <canvas ref={canvasRef} className="block h-full w-full opacity-[0.55]" />
      {/* Vignette: pulls contrast out of the corners so text stays readable
          over the busiest part of the lattice. */}
      <div
        className="absolute inset-0"
        style={{
          background:
            'radial-gradient(ellipse 120% 80% at 50% 40%, transparent 0%, rgba(5,6,7,0.55) 55%, rgba(5,6,7,0.92) 100%)',
        }}
      />
    </div>
  );
}
