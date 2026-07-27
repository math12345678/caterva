import { useMemo } from 'react';
import { motion } from 'framer-motion';

const STEPS = [
  { label: 'Natural Language Query', icon: 'A' },
  { label: 'LLM + Literature Resolver', icon: '\u2318' },
  { label: 'Parameter Validation', icon: '\u2713' },
  { label: 'Tellurium ODE Engine', icon: '\u26A1' },
  { label: 'Trajectory + Provenance', icon: '\u2261' },
];

function Arrow({ index }: { index: number }) {
  const dotPos = useMemo(() => Math.random(), []);
  return (
    <motion.div
      className="w-5 h-5 shrink-0 relative flex items-center justify-center"
      animate={{ x: [0, 2, 0] }}
      transition={{ duration: 2, delay: index * 0.3, repeat: Infinity, ease: 'easeInOut' }}
    >
      <svg viewBox="0 0 20 20" fill="none" className="w-full h-full text-white/15 group-hover:text-[#1D8A72]/40 transition-colors">
        <path d="M4 10h12M12 4l6 6-6 6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      <motion.div
        className="absolute w-1.5 h-1.5 rounded-full bg-[#1D8A72]"
        style={{ left: `${dotPos * 60 + 20}%`, top: '50%' }}
        animate={{
          opacity: [0, 1, 0],
          scale: [0, 1, 0],
        }}
        transition={{
          duration: 2.5 + index * 0.2,
          delay: index * 0.5,
          repeat: Infinity,
          ease: 'easeInOut',
        }}
      />
    </motion.div>
  );
}

export default function PipelineFlow() {
  return (
    <div className="w-full overflow-x-auto py-4">
      <div className="flex items-center gap-1 min-w-max px-2">
        {STEPS.map((step, i) => (
          <motion.div
            key={step.label}
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.8 + i * 0.12 }}
            className="flex items-center gap-1"
          >
            <motion.div
              className="group relative"
              whileHover={{ scale: 1.03 }}
              transition={{ type: 'spring', stiffness: 300, damping: 20 }}
            >
              <motion.div className="flex items-center gap-2 rounded-lg border border-white/10 bg-black/40 px-3 py-2 text-[11px] backdrop-blur-sm transition-all duration-300 hover:border-[#1D8A72]/30 hover:bg-[#1D8A72]/[0.04] hover:shadow-[0_0_20px_rgba(29,138,114,0.08)]">
                <span className="text-[11px] text-white/30">{step.icon}</span>
                <span className="text-white/60 whitespace-nowrap">{step.label}</span>
              </motion.div>
              {i < STEPS.length - 1 && <Arrow index={i} />}
            </motion.div>
          </motion.div>
        ))}
      </div>
    </div>
  );
}
