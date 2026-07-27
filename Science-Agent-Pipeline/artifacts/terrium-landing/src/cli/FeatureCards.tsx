import { motion } from 'framer-motion';
import Reveal from './Reveal';

const FEATURES = [
  {
    icon: '\u2318',
    title: 'Natural Language',
    desc: 'Ask in plain English. The LLM resolves your query into structured simulation parameters with full provenance.',
    gradient: 'from-[#1D8A72]/20 via-[#1D8A72]/10 to-transparent',
    border: 'hover:border-[#1D8A72]/30',
  },
  {
    icon: '\u2302',
    title: 'ODE Engine',
    desc: 'Powered by Tellurium. RK4 integration with conserved-quantity checks and numerical error bounds on every run.',
    gradient: 'from-[#3B82F6]/20 via-[#3B82F6]/10 to-transparent',
    border: 'hover:border-[#3B82F6]/30',
  },
  {
    icon: '\u25C9',
    title: 'Literature-Grounded',
    desc: 'Every parameter traces to BRENDA, KEGG, or PubMed citations. No black-box numbers.',
    gradient: 'from-[#F59E0B]/20 via-[#F59E0B]/10 to-transparent',
    border: 'hover:border-[#F59E0B]/30',
  },
  {
    icon: '\u221E',
    title: 'Real-time Feedback',
    desc: 'Watch simulations stream live via SSE. Inspect trajectories, export CSV, re-run with tweaked params.',
    gradient: 'from-[#8B5CF6]/20 via-[#8B5CF6]/10 to-transparent',
    border: 'hover:border-[#8B5CF6]/30',
  },
];

export default function FeatureCards() {
  return (
    <section className="max-w-3xl mx-auto px-4 md:px-6 py-10">
      <Reveal>
        <div className="flex items-center gap-3 text-[10px] text-white/15 uppercase tracking-widest mb-6">
          <span className="w-5 h-px bg-white/[0.06]" />
          <span>features</span>
          <span className="flex-1 h-px bg-white/[0.06]" />
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {FEATURES.map((f, i) => (
            <motion.div
              key={f.title}
              initial={{ opacity: 0, y: 16 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.5, delay: i * 0.08, ease: [0.16, 1, 0.3, 1] }}
              className={`group relative rounded-xl border border-white/[0.06] bg-gradient-to-br ${f.gradient} p-5 transition-all duration-500 hover:shadow-[0_0_40px_-10px_rgba(29,138,114,0.15)] ${f.border} hover:-translate-y-0.5`}
            >
              <div className="flex items-center gap-3 mb-3">
                <span className="inline-flex items-center justify-center w-8 h-8 rounded-lg bg-white/[0.04] border border-white/[0.06] text-[14px] text-white/50 group-hover:text-white/80 transition-colors">
                  {f.icon}
                </span>
                <span className="text-[13px] text-white/80 font-sans font-medium">{f.title}</span>
              </div>
              <p className="text-[11px] text-white/35 leading-relaxed">{f.desc}</p>
            </motion.div>
          ))}
        </div>
      </Reveal>
    </section>
  );
}
