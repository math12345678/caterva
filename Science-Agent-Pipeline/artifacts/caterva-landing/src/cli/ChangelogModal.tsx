import { useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";

interface Release {
  date: string;
  tag: "feature" | "fix" | "improvement";
  title: string;
  desc: string;
}

// Pulled from this repo's own CHANGELOG.md. Entries before 2026-08-29 carry
// real dates from git history and no version number, because there was no
// release to version then; CHANGELOG.md follows Semantic Versioning from
// 0.1.0 (2026-08-29) onward and the three tagged versions are listed as
// such. This used to be a fabricated version-numbered history (v0.4.0
// "Private Alpha Launch" with a "pilot cohort" and 3 nonexistent database
// backends) -- removed entirely rather than corrected, since none of it
// happened. Every line below names something CHANGELOG.md records.
const RELEASES: Release[] = [
  {
    date: "September 27, 2026",
    tag: "feature",
    title: "v0.4.0: Terrium is now Caterva",
    desc: "A new logo, the same code, and a name that can no longer be confused with Tellurium. The command is caterva (terrium still works), the repository is public at github.com/math12345678/caterva, and private business records were removed from its history first.",
  },
  {
    date: "September 24, 2026",
    tag: "fix",
    title: "v0.3.4: every shape builds from its own words, and the verdict reads the search",
    desc: "All 36 shapes build from the one-line description --shapes prints (21 did not). A fully sourced model is graded GROUNDED. --organism human works, a misspelt substrate lists what BRENDA holds, and an unknown EC number says so.",
  },
  {
    date: "September 24, 2026",
    tag: "feature",
    title: "v0.3.3: a model whose constants are sourced",
    desc: "compose searches BRENDA and every constant names its reference. The report also says what the evidence did not settle (two papers 13-fold apart on one Km), the pH and temperature each value was measured under, and why a missing constant is missing: most often it exists in another organism.",
  },
  {
    date: "September 22, 2026",
    tag: "improvement",
    title: "v0.3.1: a guide, and a first run that teaches",
    desc: "docs/USING_CATERVA.md, written from commands run before they were written down, and pinned to the code by a test. Running caterva with no arguments prints the quick start.",
  },
  {
    date: "September 21, 2026",
    tag: "feature",
    title: "v0.3.0: on the Releases page, downloadable as an app",
    desc: "A CI workflow publishes each tag after rebuilding, reinstalling and running what it attaches. One folder per platform (macOS arm64, Linux, Windows) runs without Python; libSBML stays a separate replaceable file and every licence rides inside. Wheel and sdist byte-reproducible from the tag.",
  },
  {
    date: "September 19, 2026",
    tag: "feature",
    title: "v0.2.0: the first installable wheel",
    desc: "Packaging that built an empty install now builds Caterva; two commands, caterva and caterva-compose; a NOTICE that says what the artifacts convey. Verified from an empty directory.",
  },
  {
    date: "August 29, 2026",
    tag: "improvement",
    title: "v0.1.0: the first tag",
    desc: "A source archive only, deliberately: nothing that contains libSBML was distributed. Its packaging could not produce an installable package; 0.2.0 fixed that.",
  },
  {
    date: "July 25, 2026",
    tag: "feature",
    title: "PCR amplification",
    desc: "Third live simulation domain: exact closed-form exponential growth with an optional discrete-logistic plateau mode. 32 new tests, mutation-verified.",
  },
  {
    date: "July 23, 2026",
    tag: "feature",
    title: "Caterva simulation engine",
    desc: "Michaelis-Menten enzyme kinetics and SIR/SEIR epidemiology, built on antimony/roadrunner. 258-test suite verified against exact closed-form solutions, an independent scipy solver, and property-based tests.",
  },
  {
    date: "July 21-22, 2026",
    tag: "feature",
    title: "Literature-scraping layer",
    desc: "Initial BRENDA/KEGG/PubMed parsing layer -- 124 tests -- so simulation parameters can be resolved to a real citation instead of a hardcoded default.",
  },
];

const TAG_STYLES: Record<
  Release["tag"],
  { bg: string; text: string; icon: string; dotColor: string }
> = {
  feature: {
    bg: "bg-signal/15",
    text: "text-signal",
    icon: "✦",
    dotColor: "#5D7F8D",
  },
  fix: {
    bg: "bg-caution/15",
    text: "text-caution",
    icon: "◆",
    dotColor: "#946522",
  },
  improvement: {
    bg: "bg-muted/15",
    text: "text-muted",
    icon: "▲",
    dotColor: "#6A6E78",
  },
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
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
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
            className="fixed inset-0 z-50 bg-surface/70 backdrop-blur-sm"
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
              className="relative w-full max-w-lg max-h-[80vh] overflow-y-auto rounded-xl border border-fg/[0.16] bg-surface shadow-2xl"
              style={{
                boxShadow:
                  "0 0 80px rgba(93,127,141,0.1), 0 30px 60px rgba(42,45,53,0.6)",
              }}
            >
              {/* Terminal title bar */}
              <div className="sticky top-0 z-10 flex items-center gap-2 px-4 py-3 border-b border-fg/[0.10] bg-surface/95 backdrop-blur-xl">
                <div className="flex gap-1.5">
                  <span className="w-2.5 h-2.5 rounded-full bg-red-500/60" />
                  <span className="w-2.5 h-2.5 rounded-full bg-yellow-500/60" />
                  <span className="w-2.5 h-2.5 rounded-full bg-green-500/60" />
                </div>
                <span className="flex-1 text-center text-[10px] font-mono text-fg/66 uppercase tracking-widest">
                  changelog — caterva changelog
                </span>
                <button
                  onClick={onClose}
                  className="text-fg/66 hover:text-fg/80 transition-colors p-2.5 -m-2.5"
                  aria-label="Close changelog"
                >
                  <svg className="w-3.5 h-3.5" viewBox="0 0 14 14" fill="none">
                    <path
                      d="M3 3l8 8M11 3l-8 8"
                      stroke="currentColor"
                      strokeWidth="1.5"
                      strokeLinecap="round"
                    />
                  </svg>
                </button>
              </div>

              {/* Content */}
              <div className="p-5">
                <div className="mb-5">
                  <h2 className="text-[15px] font-sans font-medium text-fg/85 mb-1">
                    Release notes
                  </h2>
                  <p className="text-[11px] text-fg/70 font-mono">
                    <span className="text-signal">$</span> caterva changelog
                    --recent
                  </p>
                </div>

                {/* Timeline */}
                <div className="relative">
                  <div className="absolute left-[15px] top-2 bottom-2 w-px bg-gradient-to-b from-signal/30 via-signal/10 to-transparent" />

                  <div className="space-y-5">
                    {RELEASES.map((rel, i) => {
                      const style = TAG_STYLES[rel.tag];
                      return (
                        <motion.div
                          key={rel.date + rel.title}
                          initial={{ opacity: 0, x: -8 }}
                          animate={{ opacity: 1, x: 0 }}
                          transition={{ duration: 0.3, delay: i * 0.05 }}
                          className="relative flex gap-4"
                        >
                          {/* Dot */}
                          <div className="relative z-10 shrink-0 mt-1.5">
                            <div
                              className={`w-[8px] h-[8px] rounded-full border transition-colors ${style.bg} ${style.text}`}
                              style={{
                                backgroundColor: style.dotColor,
                                borderColor: style.dotColor,
                              }}
                            />
                          </div>

                          {/* Card */}
                          <div className="flex-1 min-w-0 pb-4 border-b border-fg/[0.06] last:border-b-0">
                            <div className="flex flex-wrap items-center gap-2 mb-1.5">
                              <span
                                className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[9px] uppercase tracking-wide ${style.bg} ${style.text}`}
                              >
                                <span>{style.icon}</span>
                                {rel.tag}
                              </span>
                              <span className="text-[10px] text-fg/66 font-mono">
                                {rel.date}
                              </span>
                            </div>
                            <h3 className="text-[13px] font-sans font-medium text-fg/78 mb-1">
                              {rel.title}
                            </h3>
                            <p className="text-[11px] text-fg/76 leading-relaxed">
                              {rel.desc}
                            </p>
                          </div>
                        </motion.div>
                      );
                    })}
                  </div>
                </div>

                {/* Footer */}
                <div className="mt-6 pt-3 border-t border-fg/[0.08] flex items-center justify-between text-[10px] text-fg/66">
                  <span>{RELEASES.length} releases shown</span>
                  {/* Full history lives in CHANGELOG.md -- not linked here
                      because the repository isn't public yet, and a link
                      to a private repo is a dead link for every visitor
                      who isn't already a collaborator. */}
                  <span>Full history in CHANGELOG.md</span>
                </div>
              </div>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
