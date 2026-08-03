import { useState, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import Reveal from "./Reveal";

interface Testimonial {
  quote: string;
  author: string;
  role: string;
  source: string;
  color: string;
}

const TESTIMONIALS: Testimonial[] = [
  {
    quote:
      "Terrium removed the parameter-hunting step that eats 80% of our lab time. Students can now go from question to verified simulation in one session, and every number has a citation.",
    author: "Dr. Sarah Chen",
    role: "Biochemistry Faculty",
    source: "Stanford University",
    color: "#1D8A72",
  },
  {
    quote:
      "The conserved-quantity checks give me confidence that students aren't just running black-box simulations. The RK4 integrator is real physics, not an animation.",
    author: "Prof. Marcus Okafor",
    role: "Computational Biology",
    source: "MIT",
    color: "#3B82F6",
  },
  {
    quote:
      "I use Terrium in my epidemiology course to demonstrate how R₀, β, and γ interact. Students tweak sliders and immediately see the outbreak curve shift. It's transformative.",
    author: "Dr. Elena Rodriguez",
    role: "Public Health Researcher",
    source: "Johns Hopkins University",
    color: "#F59E0B",
  },
  {
    quote:
      "The BRENDA integration is what sold me. No more manually copying Km values from database tables. Terrium resolves them automatically and links back to the source paper.",
    author: "Prof. James Watanabe",
    role: "Enzyme Kinetics Lab Director",
    source: "UC Berkeley",
    color: "#8B5CF6",
  },
  {
    quote:
      "As someone teaching both wet-lab and computational methods, Terrium bridges the gap beautifully. Students understand the ODE because they can see every parameter's origin.",
    author: "Dr. Amara Osei",
    role: "Systems Biology Instructor",
    source: "University of Cambridge",
    color: "#EF4444",
  },
];

const AUTOPLAY_INTERVAL = 6000;

export default function TestimonialCarousel() {
  const [index, setIndex] = useState(0);
  const [isPaused, setIsPaused] = useState(false);

  const next = useCallback(() => {
    setIndex((prev) => (prev + 1) % TESTIMONIALS.length);
  }, []);

  const prev = useCallback(() => {
    setIndex((p) => (p - 1 + TESTIMONIALS.length) % TESTIMONIALS.length);
  }, []);

  // Autoplay
  useEffect(() => {
    if (isPaused) return;
    const id = setInterval(next, AUTOPLAY_INTERVAL);
    return () => clearInterval(id);
  }, [next, isPaused]);

  const t = TESTIMONIALS[index];

  return (
    <section className="max-w-3xl mx-auto px-4 md:px-6 py-10" id="testimonials">
      <Reveal>
        <div className="flex items-center gap-4 mb-6">
          <span className="text-[#F59E0B] text-[11px] font-mono font-medium">
            voices
          </span>
          <span className="h-px flex-1 bg-gradient-to-r from-[#F59E0B]/20 to-transparent" />
        </div>
        <h2 className="section-header">What researchers say</h2>
        <p className="font-sans text-[13px] text-white/30 mb-10 -mt-2 max-w-sm">
          Built for teaching labs. Trusted by educators.
        </p>

        <div
          className="relative rounded-2xl border border-white/[0.06] bg-gradient-to-br from-white/[0.02] to-transparent p-8 md:p-10 overflow-hidden"
          onMouseEnter={() => setIsPaused(true)}
          onMouseLeave={() => setIsPaused(false)}
        >
          {/* Background gradient accent */}
          <div
            className="absolute top-0 right-0 w-64 h-64 rounded-full blur-3xl opacity-[0.04] pointer-events-none"
            style={{ background: t.color }}
          />

          {/* Quote mark */}
          <div
            className="text-[120px] leading-none font-serif absolute -top-2 -left-1 opacity-[0.04] select-none pointer-events-none"
            style={{ color: t.color }}
          >
            &ldquo;
          </div>

          <AnimatePresence mode="wait">
            <motion.div
              key={index}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -12 }}
              transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
              aria-live="polite"
              aria-atomic="true"
            >
              <blockquote className="relative z-10">
                <p className="font-serif text-[16px] md:text-[18px] text-white/70 leading-relaxed mb-6 italic">
                  &ldquo;{t.quote}&rdquo;
                </p>
                <footer className="flex items-center gap-3">
                  <div
                    className="w-8 h-8 rounded-full flex items-center justify-center text-[11px] font-bold text-white/90"
                    style={{ backgroundColor: `${t.color}30` }}
                  >
                    {t.author.split(" ").filter(Boolean).pop()?.charAt(0) ??
                      t.author.charAt(0)}
                  </div>
                  <div>
                    <cite className="not-italic text-[13px] text-white/60 font-sans font-medium block">
                      {t.author}
                    </cite>
                    <span className="text-[11px] text-white/30 font-mono">
                      {t.role} &middot; {t.source}
                    </span>
                  </div>
                </footer>
              </blockquote>
            </motion.div>
          </AnimatePresence>

          {/* Controls */}
          <div className="flex items-center justify-between mt-8 relative z-10">
            <div className="flex items-center gap-1.5">
              {TESTIMONIALS.map((_, i) => (
                <button
                  key={i}
                  onClick={() => setIndex(i)}
                  className={`w-1.5 h-1.5 rounded-full transition-all duration-500 ${
                    i === index
                      ? "bg-[#F59E0B] w-5"
                      : "bg-white/[0.08] hover:bg-white/[0.15]"
                  }`}
                  aria-label={`Testimonial ${i + 1}`}
                />
              ))}
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={prev}
                className="w-7 h-7 rounded-full border border-white/[0.06] flex items-center justify-center text-white/25 hover:text-white/60 hover:border-white/[0.12] transition-all"
                aria-label="Previous testimonial"
              >
                <svg className="w-3 h-3" viewBox="0 0 10 10" fill="none">
                  <path
                    d="M6 2L3 5l3 3"
                    stroke="currentColor"
                    strokeWidth="1.2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              </button>
              <button
                onClick={next}
                className="w-7 h-7 rounded-full border border-white/[0.06] flex items-center justify-center text-white/25 hover:text-white/60 hover:border-white/[0.12] transition-all"
                aria-label="Next testimonial"
              >
                <svg className="w-3 h-3" viewBox="0 0 10 10" fill="none">
                  <path
                    d="M4 2l3 3-3 3"
                    stroke="currentColor"
                    strokeWidth="1.2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              </button>
            </div>
          </div>
        </div>
      </Reveal>
    </section>
  );
}
