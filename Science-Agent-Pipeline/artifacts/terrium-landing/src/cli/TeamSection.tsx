import { motion } from 'framer-motion';
import Reveal from './Reveal';
import TerminalWindow from './TerminalWindow';

interface Contributor {
  initials: string;
  name: string;
  role: string;
  gradient: string;
  links?: { label: string; href: string }[];
}

const CONTRIBUTORS: Contributor[] = [
  {
    initials: 'SR',
    name: 'Smyan Reddy',
    role: 'Creator & Lead Developer',
    gradient: 'from-[#1D8A72] to-[#0D6B5A]',
    links: [
      { label: 'github', href: 'https://github.com/smyan' },
      { label: 'email', href: 'mailto:smyan@terrium.app' },
    ],
  },
  {
    initials: '??',
    name: 'You?',
    role: 'Contributor — join us',
    gradient: 'from-[#8B5CF6] to-[#6D28D9]',
    links: [
      { label: 'contribute', href: 'https://github.com/smyan/terrium' },
    ],
  },
];

const ECOSYSTEM = [
  {
    name: 'BRENDA',
    desc: 'Enzyme functional data — the gold standard for kinetic parameters.',
    url: 'https://www.brenda-enzymes.org',
    color: '#1D8A72',
    emoji: '\u{1F9EC}',
  },
  {
    name: 'KEGG',
    desc: 'Kyoto Encyclopedia of Genes and Genomes — pathway & genomic reference.',
    url: 'https://www.genome.jp/kegg/',
    color: '#3B82F6',
    emoji: '\u{1F517}',
  },
  {
    name: 'PubMed',
    desc: '30M+ biomedical citations — every parameter linked to its source paper.',
    url: 'https://pubmed.ncbi.nlm.nih.gov',
    color: '#F59E0B',
    emoji: '\u{1F4DA}',
  },
  {
    name: 'Tellurium',
    desc: 'Python-based systems biology modeling environment powering our ODE engine.',
    url: 'https://tellurium.analogmachine.org',
    color: '#8B5CF6',
    emoji: '\u2699',
  },
  {
    name: 'roadrunner',
    desc: 'High-performance SBML JIT compiler and ODE solver from the Sys-Bio community.',
    url: 'https://github.com/sys-bio/roadrunner',
    color: '#EC4899',
    emoji: '\u26A1',
  },
];

export default function TeamSection() {
  return (
    <section className="max-w-3xl mx-auto px-4 md:px-6 py-10 section-bg-purple scroll-mt-16" id="team">
      <Reveal>
        <div className="flex items-center gap-4 mb-6">
          <span className="text-[#8B5CF6] text-[11px] font-mono font-medium">TEAM</span>
          <span className="h-px flex-1 bg-gradient-to-r from-[#8B5CF6]/20 to-transparent" />
        </div>
        <h2 className="section-header">Built by humans, for humans</h2>
        <p className="font-sans text-[13px] text-white/30 mb-8 -mt-2 max-w-sm">
          A small team building big things. Open source, open science.
        </p>

        <TerminalWindow path="~ — terrium team --list" glow>
          <div className="mb-4 text-white/90">
            <span className="text-[#1D8A72]">$</span> terrium team --list
          </div>

          {/* Contributors grid */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-8">
            {CONTRIBUTORS.map((c, i) => (
              <motion.div
                key={c.name}
                initial={{ opacity: 0, y: 16 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ duration: 0.4, delay: i * 0.1, ease: [0.16, 1, 0.3, 1] }}
                className="flex items-start gap-4 rounded-xl border border-white/[0.06] bg-white/[0.01] p-5 hover:border-[#8B5CF6]/20 hover:bg-white/[0.02] transition-all duration-500 group"
              >
                {/* Avatar */}
                <div
                  className={`shrink-0 w-12 h-12 rounded-xl bg-gradient-to-br ${c.gradient} flex items-center justify-center text-white/90 font-sans text-[15px] font-semibold shadow-lg group-hover:scale-105 transition-transform duration-300`}
                  aria-hidden="true"
                >
                  {c.initials}
                </div>

                {/* Info */}
                <div className="min-w-0">
                  <h3 className="text-[14px] font-sans font-medium text-white/80 group-hover:text-white transition-colors">
                    {c.name}
                  </h3>
                  <p className="text-[11px] text-white/35 mt-0.5 mb-2">{c.role}</p>
                  {c.links && (
                    <div className="flex gap-3">
                      {c.links.map((link) => (
                        <a
                          key={link.label}
                          href={link.href}
                          target={link.href.startsWith('http') ? '_blank' : undefined}
                          rel={link.href.startsWith('http') ? 'noopener noreferrer' : undefined}
                          className="text-[10px] text-white/25 hover:text-[#8B5CF6] transition-colors uppercase tracking-wide"
                        >
                          {link.label}
                        </a>
                      ))}
                    </div>
                  )}
                </div>
              </motion.div>
            ))}
          </div>

          {/* Ecosystem section */}
          <div className="border-t border-white/[0.04] pt-6">
            <div className="flex items-center gap-2 mb-4">
              <span className="text-[#8B5CF6]/60 text-[10px] uppercase tracking-widest font-medium">
                standing on the shoulders of giants
              </span>
              <span className="flex-1 h-px bg-gradient-to-r from-[#8B5CF6]/10 to-transparent" />
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {ECOSYSTEM.map((eco, i) => (
                <motion.a
                  key={eco.name}
                  href={eco.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  initial={{ opacity: 0, y: 8 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true }}
                  transition={{ duration: 0.3, delay: 0.3 + i * 0.06 }}
                  className="flex items-start gap-3 rounded-lg border border-white/[0.04] bg-white/[0.01] p-3 hover:border-white/[0.10] hover:bg-white/[0.02] transition-all duration-300 group/eco"
                >
                  <span
                    className="shrink-0 w-8 h-8 rounded-lg flex items-center justify-center text-[14px]"
                    style={{
                      backgroundColor: `${eco.color}15`,
                      border: `1px solid ${eco.color}20`,
                    }}
                  >
                    {eco.emoji}
                  </span>
                  <div className="min-w-0">
                    <div className="flex items-center gap-1.5">
                      <span className="text-[12px] font-medium text-white/60 group-hover/eco:text-white/80 transition-colors">
                        {eco.name}
                      </span>
                      <svg className="w-3 h-3 text-white/15 group-hover/eco:text-white/30 transition-colors shrink-0" viewBox="0 0 12 12" fill="none">
                        <path d="M4 2h6v6M10 2L2 10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                      </svg>
                    </div>
                    <p className="text-[10px] text-white/25 leading-relaxed mt-0.5 group-hover/eco:text-white/35 transition-colors">
                      {eco.desc}
                    </p>
                  </div>
                </motion.a>
              ))}
            </div>
          </div>

          {/* Open source CTA */}
          <div className="mt-6 pt-4 border-t border-white/[0.04] flex items-center gap-3 text-[11px]">
            <span className="text-[#8B5CF6]">
              <svg className="w-4 h-4" viewBox="0 0 16 16" fill="currentColor">
                <path fillRule="evenodd" d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z" />
              </svg>
            </span>
            <span className="text-white/30">
              Terrium is open source.{' '}
              <a
                href="https://github.com/smyan/terrium"
                target="_blank"
                rel="noopener noreferrer"
                className="text-[#8B5CF6]/60 hover:text-[#8B5CF6] transition-colors"
              >
                Star us on GitHub
              </a>
              {' '}&mdash; contributions welcome.
            </span>
          </div>
        </TerminalWindow>
      </Reveal>
    </section>
  );
}
