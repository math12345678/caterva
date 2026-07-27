import { useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

interface Release {
  version: string;
  date: string;
  tag: 'feature' | 'fix' | 'improvement' | 'launch';
  title: string;
  desc: string;
}

const RELEASES: Release[] = [
  {
    version: 'v0.7.0',
    date: 'July 24, 2026',
    tag: 'feature',
    title: 'PCR Amplification Engine',
    desc: 'Added primer annealing & extension kinetics, gel-electrophoresis output preview, and Tm calculator. Full support for 2-step and 3-step PCR protocols.',
  },
  {
    version: 'v0.6.3',
    date: 'July 10, 2026',
    tag: 'improvement',
    title: 'BRENDA Parser v2',
    desc: 'Rewrote BRENDA HTML scraper with structured sub-row extraction. Km/Vmax now include organism, pH, temperature metadata. 3× more parameters per enzyme.',
  },
  {
    version: 'v0.6.0',
    date: 'June 28, 2026',
    tag: 'feature',
    title: 'Live ODE Simulator',
    desc: 'Browser-side RK4 integration with real-time parameter sliders. Export CSV, PNG charts, and SBML stub. Conserved-quantity checks on every step.',
  },
  {
    version: 'v0.5.2',
    date: 'June 15, 2026',
    tag: 'fix',
    title: 'Citation Provenance Chain',
    desc: 'Fixed PubMed abstract fetching pipeline. Now every simulation parameter links directly to its source paper via DOI — from BRENDA ID → PubMed ID → abstract text.',
  },
  {
    version: 'v0.5.0',
    date: 'June 1, 2026',
    tag: 'feature',
    title: 'SEIR Epidemiology Domain',
    desc: 'Added exposed-compartment modeling with latent period. Configurable R₀, incubation, and recovery rates with population conservation validation.',
  },
  {
    version: 'v0.4.0',
    date: 'May 15, 2026',
    tag: 'launch',
    title: 'Private Alpha Launch',
    desc: 'First pilot cohort onboarded. Michaelis-Menten kinetics + SIR epidemiology fully operational. 48 tests passing, 3 database backends integrated.',
  },
];

const TAG_STYLES: Record<Release['tag'], { bg: string; text: string; icon: string; dotColor: string }> = {
  feature: { bg: 'bg-[#1D8A72]/15', text: 'text-[#1D8A72]', icon: '✦', dotColor: '#1D8A72' },
  fix: { bg: 'bg-[#F59E0B]/15', text: 'text-[#F59E0B]', icon: '◆', dotColor: '#F59E0B' },
  improvement: { bg: 'bg-[#3B82F6]/15', text: 'text-[#3B82F6]', icon: '▲', dotColor: '#3B82F6' },
  launch: { bg: 'bg-[#8B5CF6]/15', text: 'text-[#8B5CF6]', icon: '★', dotColor: '#8B5CF6' },
};

interface Props {
  open: boolean;
  onClose: () => void;
}

export default function ChangelogModal({ open, onClose }: Props) {
  // Close on Escape key
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  return (
    <AnimatePresence>
      {open && (
        <>
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm"
            onClick={onClose}
          />

          {/* Modal */}
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 20 }}
            transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
            className="fixed inset-0 z-50 flex items-center justify-center p-4"
            onClick={(e) => e.stopPropagation()}
          >
            <div
              role="dialog"
              aria-modal="true"
              aria-label="Changelog"
              className="relative w-full max-w-lg max-h-[80vh] overflow-y-auto rounded-xl border border-white/[0.08] bg-[#0A0E0C] shadow-2xl"
              style={{
                boxShadow: '0 0 80px rgba(29,138,114,0.1), 0 30px 60px rgba(0,0,0,0.6)',
              }}
            >
              {/* Terminal title bar */}
              <div className="sticky top-0 z-10 flex items-center gap-2 px-4 py-3 border-b border-white/[0.05] bg-[#0A0E0C]/95 backdrop-blur-xl">
                <div className="flex gap-1.5">
                  <span className="w-2.5 h-2.5 rounded-full bg-red-500/60" />
                  <span className="w-2.5 h-2.5 rounded-full bg-yellow-500/60" />
                  <span className="w-2.5 h-2.5 rounded-full bg-green-500/60" />
                </div>
                <span className="flex-1 text-center text-[10px] font-mono text-white/25 uppercase tracking-widest">
                  changelog — terrium changelog
                </span>
                <button
                  onClick={onClose}
                  className="text-white/25 hover:text-white/60 transition-colors p-0.5"
                  aria-label="Close changelog"
                >
                  <svg className="w-3.5 h-3.5" viewBox="0 0 14 14" fill="none">
                    <path d="M3 3l8 8M11 3l-8 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                  </svg>
                </button>
              </div>

              {/* Content */}
              <div className="p-5">
                <div className="mb-5">
                  <h2 className="text-[15px] font-sans font-medium text-white/80 mb-1">
                    Release notes
                  </h2>
                  <p className="text-[11px] text-white/30 font-mono">
                    <span className="text-[#1D8A72]">$</span> terrium changelog --recent
                  </p>
                </div>

                {/* Timeline */}
                <div className="relative">
                  <div className="absolute left-[15px] top-2 bottom-2 w-px bg-gradient-to-b from-[#1D8A72]/30 via-[#1D8A72]/10 to-transparent" />

                  <div className="space-y-5">
                    {RELEASES.map((rel, i) => {
                      const style = TAG_STYLES[rel.tag];
                      return (
                        <motion.div
                          key={rel.version}
                          initial={{ opacity: 0, x: -8 }}
                          animate={{ opacity: 1, x: 0 }}
                          transition={{ duration: 0.3, delay: i * 0.05 }}
                          className="relative flex gap-4"
                        >
                          {/* Dot */}
                          <div className="relative z-10 shrink-0 mt-1.5">
                            <div
                              className={`w-[8px] h-[8px] rounded-full border transition-colors ${style.bg} ${style.text}`}
                              style={{ backgroundColor: style.dotColor, borderColor: style.dotColor }}
                            />
                          </div>

                          {/* Card */}
                          <div className="flex-1 min-w-0 pb-4 border-b border-white/[0.03] last:border-b-0">
                            <div className="flex flex-wrap items-center gap-2 mb-1.5">
                              <span className="text-[10px] font-mono text-white/25">{rel.version}</span>
                              <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[9px] uppercase tracking-wide ${style.bg} ${style.text}`}>
                                <span>{style.icon}</span>
                                {rel.tag}
                              </span>
                              <span className="text-[10px] text-white/20 font-mono">{rel.date}</span>
                            </div>
                            <h3 className="text-[13px] font-sans font-medium text-white/70 mb-1">{rel.title}</h3>
                            <p className="text-[11px] text-white/35 leading-relaxed">{rel.desc}</p>
                          </div>
                        </motion.div>
                      );
                    })}
                  </div>
                </div>

                {/* Footer */}
                <div className="mt-6 pt-3 border-t border-white/[0.04] flex items-center justify-between text-[10px] text-white/20">
                  <span>6 releases shown</span>
                  <a
                    href="https://github.com/smyan/terrium/blob/main/CHANGELOG.md"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-[#1D8A72]/50 hover:text-[#1D8A72] transition-colors"
                  >
                    Full changelog →
                  </a>
                </div>
              </div>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
