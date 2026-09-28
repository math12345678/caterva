import { motion } from "framer-motion";
import { useState } from "react";
import Reveal from "./Reveal";
import TerminalWindow from "./TerminalWindow";

const BIBTEX_TEMPLATE = `@software{caterva,
  author       = {Smyan Reddy and Caterva Contributors},
  title        = {Caterva: Verified Scientific Simulations},
  year         = {2026},
  url          = {https://github.com/math12345678/caterva},
  note         = {Simulation run: <span class="string">\${runId}</span>},
  version      = {<span class="string">pre-launch</span>},
  doi          = {<span class="string">10.5281/zenodo.XXXXXXX</span>},
}`;

const PLAINTEXT_TEMPLATE = `Reddy, S. & Caterva Contributors (2026).
Caterva: Verified Scientific Simulations [Software].
Retrieved from https://github.com/math12345678/caterva
Simulation ID: <span class="string">\${runId}</span>`;

const MARKDOWN_TEMPLATE = `[**Caterva**](https://github.com/math12345678/caterva) —  
*Verified Scientific Simulations*  
Smyan Reddy & Caterva Contributors (2026).  
Run ID: \`<span class="string">\${runId}</span>\``;

const apaTemplate = `Reddy, S. & Caterva Contributors. (2026). <i>Caterva: Verified scientific simulations</i> [Software]. https://github.com/math12345678/caterva`;

export default function HowToCiteSection() {
  const [activeTab, setActiveTab] = useState<"bibtex" | "apa" | "markdown">(
    "bibtex",
  );
  const [copied, setCopied] = useState(false);

  const getContent = () => {
    switch (activeTab) {
      case "bibtex":
        return BIBTEX_TEMPLATE;
      case "apa":
        return apaTemplate;
      case "markdown":
        return MARKDOWN_TEMPLATE;
    }
  };

  const handleCopy = () => {
    const text = getContent().replace(/<[^>]*>/g, "");
    navigator.clipboard
      .writeText(text)
      .then(() => {
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      })
      .catch(() => {});
  };

  return (
    <section
      className="max-w-3xl mx-auto px-4 md:px-6 py-10 section-bg-purple scroll-mt-16"
      id="cite"
    >
      <Reveal>
        <div className="flex items-center gap-4 mb-6">
          <span className="text-muted text-[11px] font-mono font-medium">
            CITE
          </span>
          <span className="h-px flex-1 bg-gradient-to-r from-muted/20 to-transparent" />
        </div>
        <h2 className="section-header">How to cite</h2>
        <p className="font-sans text-[13px] text-fg/76 mb-8 -mt-2 max-w-sm">
          Every simulation is citable. Copy the BibTeX, APA, or Markdown below.
        </p>

        <TerminalWindow path="~ — caterva cite --format bibtex" glow>
          <div className="mb-4 text-fg/92">
            <span className="text-signal">$</span> caterva cite --format{" "}
            {activeTab}
          </div>

          <div className="flex gap-1.5 mb-4">
            {(["bibtex", "apa", "markdown"] as const).map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`px-3 py-1.5 rounded-md text-[10px] uppercase tracking-wide border transition-all duration-300 ${
                  activeTab === tab
                    ? "border-muted/25 text-muted bg-muted/[0.06]"
                    : "border-fg/[0.12] text-fg/70 hover:text-fg/76 hover:border-fg/[0.24] bg-fg/[0.02]"
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
              <button onClick={handleCopy} className="cite-copy-btn">
                {copied ? "copied!" : "copy"}
              </button>
              <pre
                className="whitespace-pre-wrap"
                dangerouslySetInnerHTML={{ __html: getContent() }}
              />
            </div>
          </motion.div>

          <div className="mt-5 pt-4 border-t border-fg/[0.08]">
            <div className="flex items-start gap-3">
              <span className="text-signal mt-0.5 text-[14px]">!</span>
              <div className="text-[11px] text-fg/70 leading-relaxed">
                <p className="mb-2">
                  Caterva is pre-launch and has a reserved DOI. Replace{" "}
                  <code className="text-caution/70 bg-caution/[0.06] px-1 py-0.5 rounded text-[10px]">
                    XXXXXXX
                  </code>{" "}
                  with the actual DOI once published. Every simulation run ID is
                  included for full reproducibility.
                </p>
                <p className="mb-2">
                  <strong className="text-fg/70">
                    Caterva is not Tellurium.
                  </strong>{" "}
                  Tellurium is a separate, established systems-biology
                  environment from the Sauro lab at the University of
                  Washington. Caterva is unaffiliated with it and claims none
                  of its work. Caterva runs on that group&rsquo;s
                  libRoadRunner (Apache 2.0 licence) and generates their
                  Antimony (MIT licence) &mdash; if you cite Caterva for a
                  simulation result, cite those too.
                </p>
                <p className="text-fg/66">
                  Questions about citation?{" "}
                  <a
                    href="mailto:admin.terrium@gmail.com"
                    className="text-muted/60 hover:text-muted transition-colors"
                  >
                    admin.terrium@gmail.com
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
