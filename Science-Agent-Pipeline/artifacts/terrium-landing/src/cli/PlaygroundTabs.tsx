import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import KineticsPlayground from './KineticsPlayground';
import EpiPlayground from './EpiPlayground';
import Reveal from './Reveal';

type PlaygroundDomain = 'mm' | 'sir';

const TABS: { id: PlaygroundDomain; label: string; desc: string; color: string }[] = [
  {
    id: 'mm',
    label: 'Enzyme Kinetics',
    desc: 'Michaelis-Menten with Km, Vmax, and [S]₀',
    color: '#1D8A72',
  },
  {
    id: 'sir',
    label: 'Epidemiology',
    desc: 'SIR model with β, γ, and population parameters',
    color: '#3B82F6',
  },
];

export default function PlaygroundTabs() {
  const [domain, setDomain] = useState<PlaygroundDomain>('mm');

  const active = TABS.find((t) => t.id === domain)!;

  return (
    <section className="max-w-3xl mx-auto px-4 md:px-6 py-10 section-bg-teal" id="playground">
      <Reveal>
        <div className="flex items-center gap-4 mb-6">
          <span className="text-[#1D8A72] text-[11px] font-mono font-medium">play</span>
          <span className="h-px flex-1 bg-gradient-to-r from-[#1D8A72]/20 to-transparent" />
        </div>
        <h2 className="section-header">Interactive playground</h2>
        <p className="font-sans text-[13px] text-white/30 mb-2 -mt-2 max-w-md">
          Tweak real parameters and watch the full ODE trajectory update in real time. No backend.
        </p>

        {/* Domain Tabs */}
        <div className="flex items-center gap-0.5 mb-6 p-0.5 rounded-lg border border-white/[0.05] bg-white/[0.015] w-fit">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setDomain(tab.id)}
              className={`relative px-3.5 py-1.5 rounded-md text-[11px] font-mono transition-all duration-300 ${
                domain === tab.id
                  ? 'text-white/90'
                  : 'text-white/25 hover:text-white/50'
              }`}
            >
              {domain === tab.id && (
                <motion.div
                  layoutId="playground-tab-active"
                  className="absolute inset-0 rounded-md border border-white/[0.08] bg-white/[0.04]"
                  transition={{ type: 'spring', stiffness: 400, damping: 30 }}
                />
              )}
              <span className="relative z-10 flex items-center gap-1.5">
                <span
                  className="w-1 h-1 rounded-full"
                  style={{ background: domain === tab.id ? tab.color : 'rgba(255,255,255,0.15)' }}
                />
                {tab.label}
              </span>
            </button>
          ))}
        </div>

        {/* Active description */}
        <p className="font-sans text-[11px] text-white/25 mb-6 font-mono">
          $ terrium playground --domain {domain} &mdash;{' '}
          <span style={{ color: active.color }}>{active.desc}</span>
        </p>

        {/* Content */}
        <AnimatePresence mode="wait">
          <motion.div
            key={domain}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
          >
            {domain === 'mm' ? (
              <KineticsPlayground />
            ) : (
              <EpiPlayground />
            )}
          </motion.div>
        </AnimatePresence>
      </Reveal>
    </section>
  );
}
