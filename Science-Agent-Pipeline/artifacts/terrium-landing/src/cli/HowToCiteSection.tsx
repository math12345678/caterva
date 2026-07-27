import { motion } from 'framer-motion';
import { useState } from 'react';
import Reveal from './Reveal';
import TerminalWindow from './TerminalWindow';

const BIBTEX_TEMPLATE = `@software{terrium,
  author       = {Smyan Reddy and Terrium Contributors},
  title        = {Terrium: Verified Scientific Simulations},
  year         = {2026},
  url          = {https://terrium.app},
  note         = {Simulation run: <span class="string">\${runId}</span>},
  version      = {<span class="string">pre-launch</span>},
  doi          = {<span class="string">10.5281/zenodo.XXXXXXX</span>},
}`;

const PLAINTEXT_TEMPLATE = `Reddy, S. & Terrium Contributors (2026).
Terrium: Verified Scientific Simulations [Software].
Retrieved from https://terrium.app
Simulation ID: <span class="string">\${runId}</span>`;

const MARKDOWN_TEMPLATE = `[**Terrium**](https://terrium.app) —  
*Verified Scientific Simulations*  
Smyan Reddy & Terrium Contributors (2026).  
Run ID: \`<span class="string">\${runId}</span>\``;

const apaTemplate = `Reddy, S. & Terrium Contributors. (2026). <i>Terrium: Verified scientific simulations</i> [Software]. https://terrium.app`;

export default function HowToCiteSection() {
  const [activeTab, setActiveTab] = useState<'bibtex' | 'apa' | 'markdown'>('bibtex');
  const [copied, setCopied] = useState(false);

  const getContent = () => {
    switch (activeTab) {
      case 'bibtex':
        return BIBTEX_TEMPLATE;
      case 'apa':
        return apaTemplate;
      case 'markdown':
        return MARKDOWN_TEMPLATE;
    }
  };

  const handleCopy = () => {
    const text = getContent().replace(/<[^>]*>/g, '');
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }).catch(() => {});
  };

  return (
    <section className="max-w-3xl mx-auto px-4 md:px-6 py-10 section-bg-purple scroll-mt-16" id="cite">
      <Reveal>
        <div className="flex items-center gap-4 mb-6">
          <span className="text-[#8B5CF6] text-[11px] font-mono font-medium">CITE</span>
          <span className="h-px flex-1 bg-gradient-to-r from-[#8B5CF6]/20 to-transparent" />
        </div>
        <h2 className="section-header">How to cite</h2>
        <p className="font-sans text-[13px] text-white/30 mb-8 -mt-2 max-w-sm">
          Every simulation is citable. Copy the BibTeX, APA, or Markdown below.
        </p>

        <TerminalWindow path="~ — terrium cite --format bibtex" glow>
          <div className="mb-4 text-white/90">
            <span className="text-[#1D8A72]">$</span> terrium cite --format {activeTab}
          </div>

          <div className="flex gap-1.5 mb-4">
            {(['bibtex', 'apa', 'markdown'] as const).map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`px-3 py-1.5 rounded-md text-[10px] uppercase tracking-wide border transition-all duration-300 ${
                  activeTab === tab
                    ? 'border-[#8B5CF6]/25 text-[#8B5CF6] bg-[#8B5CF6]/[0.06]'
                    : 'border-white/[0.06] text-white/30 hover:text-white/50 hover:border-white/[0.12] bg-white/[0.02]'
                }`}
              >
                {tab}
              </button>
            ))}
          </div>

          <motion.div
            key={activeTab}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3 }}
          >
            <div className="cite-code-block relative group">
              <button
                onClick={handleCopy}
                className="cite-copy-btn"
              >
                {copied ? 'copied!' : 'copy'}
              </button>
              <pre
                className="whitespace-pre-wrap"
                dangerouslySetInnerHTML={{ __html: getContent() }}
              />
            </div>
          </motion.div>

          <div className="mt-5 pt-4 border-t border-white/[0.04]">
            <div className="flex items-start gap-3">
              <span className="text-[#1D8A72] mt-0.5 text-[14px]">!</span>
              <div className="text-[11px] text-white/30 leading-relaxed">
                <p className="mb-2">
                  Terrium is pre-launch and has a reserved DOI. Replace{' '}
                  <code className="text-[#F59E0B]/70 bg-[#F59E0B]/[0.06] px-1 py-0.5 rounded text-[10px]">
                    XXXXXXX
                  </code>{' '}
                  with the actual DOI once published. Every simulation run ID is
                  included for full reproducibility.
                </p>
                <p className="text-white/20">
                  Questions about citation?{' '}
                  <a href="mailto:hello@terrium.app" className="text-[#8B5CF6]/60 hover:text-[#8B5CF6] transition-colors">
                    hello@terrium.app
                  </a>
                </p>
              </div>
            </div>
          </div>
        </TerminalWindow>
      </Reveal>
    </section>
  );
}
