import { useEffect, useRef } from "react";

interface Particle {
  x: number;
  y: number;
  vx: number;
  vy: number;
  size: number;
  alpha: number;
  pulse: number;
  pulseSpeed: number;
  life: number;
  maxLife: number;
  isShooting: boolean;
}

/** Detect low-end devices for performance scaling */
function isLowEndDevice(): boolean {
  if (typeof navigator === "undefined") return false;
  // Mobile devices with limited memory heuristics
  const mem = (navigator as Navigator & { deviceMemory?: number }).deviceMemory;
  if (mem !== undefined && mem <= 4) return true;
  // Check for reduced motion preference as proxy for low-power
  if (
    typeof window !== "undefined" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  )
    return true;
  // Small screen = likely mobile
  if (typeof window !== "undefined" && window.innerWidth < 768) return true;
  return false;
}

export default function AnimatedBackground() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const mouseRef = useRef({ x: -1000, y: -1000 });
  const particlesRef = useRef<Particle[]>([]);
  const pageVisibleRef = useRef(true);
  const lowEndRef = useRef(false);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d", { alpha: true });
    if (!ctx) return;

    // Detect low-end device once
    lowEndRef.current = isLowEndDevice();

    let animId = 0;
    let particles: Particle[] = [];
    let frameCount = 0;

    const resize = () => {
      canvas.width = window.innerWidth;
      canvas.height = window.innerHeight;
    };

    const init = () => {
      resize();
      particles = [];
      // Reduce particle count by ~40% on low-end devices
      const densityDivisor = lowEndRef.current ? 16000 : 7000;
      const count = Math.floor((canvas.width * canvas.height) / densityDivisor);
      for (let i = 0; i < count; i++) {
        particles.push(createParticle());
      }
      particlesRef.current = particles;
    };

    const createParticle = (): Particle => ({
      x: Math.random() * canvas.width,
      y: Math.random() * canvas.height,
      vx: (Math.random() - 0.5) * (lowEndRef.current ? 0.25 : 0.4),
      vy: (Math.random() - 0.5) * (lowEndRef.current ? 0.25 : 0.4),
      size: Math.random() * (lowEndRef.current ? 1.0 : 1.5) + 0.3,
      alpha: Math.random() * 0.4 + 0.1,
      pulse: Math.random() * Math.PI * 2,
      pulseSpeed: Math.random() * 0.02 + 0.005,
      life: 0,
      maxLife: Math.random() * 300 + 200,
      isShooting: false,
    });

    const spawnShootingStar = () => {
      const angle = Math.random() * Math.PI * 2;
      const speed = Math.random() * 4 + 3;
      const startX = canvas.width * 0.2 + Math.random() * canvas.width * 0.6;
      const p: Particle = {
        x: startX,
        y: -10,
        vx: Math.cos(angle) * speed,
        vy: Math.sin(angle) * speed * 0.5 + speed * 0.8,
        size: Math.random() * 1.5 + 1,
        alpha: 1,
        pulse: 0,
        pulseSpeed: 0,
        life: 0,
        maxLife: 60 + Math.random() * 40,
        isShooting: true,
      };
      particles.push(p);
    };

    init();

    const handleMouse = (e: MouseEvent) => {
      mouseRef.current.x = e.clientX;
      mouseRef.current.y = e.clientY;
    };

    window.addEventListener("mousemove", handleMouse);

    // Page Visibility API — pause rendering when tab is hidden
    const onVisibility = () => {
      pageVisibleRef.current = document.visibilityState === "visible";
    };
    document.addEventListener("visibilitychange", onVisibility);

    let starTimer = 0;

    const draw = () => {
      animId = requestAnimationFrame(draw);

      // Skip frame if page is hidden
      if (!pageVisibleRef.current) return;

      // Frame skipping: on low-end devices, render every 2nd frame; skip 1 of 3 on mid-range
      frameCount++;
      if (lowEndRef.current && frameCount % 3 !== 0) return;

      starTimer++;
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      const mx = mouseRef.current.x;
      const my = mouseRef.current.y;

      // cursor glow
      const glowGrad = ctx.createRadialGradient(mx, my, 0, mx, my, 200);
      glowGrad.addColorStop(0, "rgba(93,127,141, 0.06)");
      glowGrad.addColorStop(0.5, "rgba(93,127,141, 0.02)");
      glowGrad.addColorStop(1, "rgba(93,127,141, 0)");
      ctx.fillStyle = glowGrad;
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      if (starTimer > 300 + Math.random() * 400) {
        spawnShootingStar();
        starTimer = 0;
      }

      particles = particles.filter((p) => {
        p.x += p.vx;
        p.y += p.vy;
        p.pulse += p.pulseSpeed;
        p.life++;

        if (p.isShooting) {
          p.alpha -= 0.015;
          if (p.life > p.maxLife || p.alpha <= 0) return false;
          const tailLen = Math.min(p.life * 3, 40);
          const grad = ctx.createLinearGradient(
            p.x,
            p.y,
            p.x - p.vx * 3,
            p.y - p.vy * 3,
          );
          grad.addColorStop(0, `rgba(93,127,141, ${p.alpha * 0.8})`);
          grad.addColorStop(1, "rgba(93,127,141, 0)");
          ctx.beginPath();
          ctx.moveTo(p.x, p.y);
          ctx.lineTo(p.x - p.vx * tailLen, p.y - p.vy * tailLen);
          ctx.strokeStyle = grad;
          ctx.lineWidth = p.size;
          ctx.lineCap = "round";
          ctx.stroke();
          return true;
        }

        if (p.x < 0 || p.x > canvas.width) p.vx *= -1;
        if (p.y < 0 || p.y > canvas.height) p.vy *= -1;

        const dx = mx - p.x;
        const dy = my - p.y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        let mouseBoost = 1;
        if (dist < 150) {
          mouseBoost = 1 + (1 - dist / 150) * 0.5;
        }

        const pulseAlpha =
          p.alpha * (0.6 + 0.4 * Math.sin(p.pulse)) * mouseBoost;
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(93,127,141, ${pulseAlpha})`;
        ctx.fill();

        return true;
      });

      while (
        particles.length < Math.floor((canvas.width * canvas.height) / 7000)
      ) {
        particles.push(createParticle());
      }

      for (let i = 0; i < particles.length; i++) {
        for (let j = i + 1; j < particles.length; j++) {
          const a = particles[i];
          const b = particles[j];
          if (a.isShooting || b.isShooting) continue;
          const dx = a.x - b.x;
          const dy = a.y - b.y;
          const dist = Math.sqrt(dx * dx + dy * dy);

          const maxDist = 120;
          if (dist < maxDist) {
            const alpha = (1 - dist / maxDist) * 0.12;
            ctx.beginPath();
            ctx.moveTo(a.x, a.y);
            ctx.lineTo(b.x, b.y);
            ctx.strokeStyle = `rgba(93,127,141, ${alpha})`;
            ctx.lineWidth = 0.5;
            ctx.stroke();
          }
        }
      }

      const cx = canvas.width / 2;
      const cy = canvas.height / 2;
      const maxDist = Math.min(canvas.width, canvas.height) * 0.5;
      const grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, maxDist);
      grad.addColorStop(0, "rgba(93,127,141, 0.02)");
      grad.addColorStop(0.4, "rgba(93,127,141, 0.01)");
      grad.addColorStop(1, "transparent");
      ctx.fillStyle = grad;
      ctx.fillRect(0, 0, canvas.width, canvas.height);
    };

    draw();

    window.addEventListener("resize", () => {
      init();
    });

    return () => {
      cancelAnimationFrame(animId);
      window.removeEventListener("mousemove", handleMouse);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, []);

  return (
    <canvas ref={canvasRef} className="fixed inset-0 pointer-events-none z-0" />
  );
}
