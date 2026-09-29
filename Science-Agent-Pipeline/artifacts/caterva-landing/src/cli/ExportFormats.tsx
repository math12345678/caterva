import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import TerminalWindow from "./TerminalWindow";
import Reveal from "./Reveal";
import { toast } from "@/hooks/use-toast";

import {
  EXPORT_COMMAND,
  EXPORT_RUN_DATE,
  EXPORT_SAMPLES,
  type ExportSample,
} from "@/lib/exportSamples";

type ExportFormat = ExportSample["format"];

// The four formats `caterva compose --export` writes, and nothing else.
//
// This panel once showed Km 2.0 and Vmax 5.0 "from BRENDA" with PMID
// 12345678: the unverified teaching defaults the hard rule (ADR 0008) blocks,
// and a placeholder PMID. It then showed an API response and a CSV
// trajectory; the CLI's CSV export is the parameter audit trail, not a
// trajectory, so that sample described a file Caterva does not write.
//
// Every sample now comes from `scripts/refresh_export_samples.py`, which
// runs the README's headline command once per format and writes
// src/lib/exportSamples.ts. Nothing below is typed by hand.
const FORMATS: {
  id: ExportFormat;
  label: string;
  ext: string;
  opensIn: string;
}[] = [
  { id: "sbml", label: "SBML", ext: ".xml", opensIn: "SBML Level 3: COPASI, libSBML, Tellurium. Provenance travels in each parameter's notes." },
  { id: "antimony", label: "Antimony", ext: ".ant", opensIn: "Human-readable model source for Tellurium. Every assignment carries its origin as a comment." },
  { id: "csv", label: "CSV", ext: ".csv", opensIn: "The audit trail: one row per number, with citation, assay conditions, the source row, and the spread." },
  { id: "methods", label: "Methods", ext: ".md", opensIn: "A methods section to paste into a manuscript, with every placeholder named." },
];

const SAMPLE: Record<ExportFormat, ExportSample> = Object.fromEntries(
  EXPORT_SAMPLES.map((s) => [s.format, s]),
) as Record<ExportFormat, ExportSample>;

export default function ExportFormats() {
  const [format, setFormat] = useState<ExportFormat>("sbml");

  const handleCopy = async (text: string, label: string) => {
    try {
      await navigator.clipboard.writeText(text);
      toast({ title: `Copied ${label} to clipboard` });
    } catch {
      toast({ title: `Failed to copy ${label}` });
    }
  };

  const active = FORMATS.find((f) => f.id === format)!;

  return (
    <section className="max-w-3xl mx-auto px-4 md:px-6 py-10" id="exports">
      <Reveal>
        <div className="flex items-center gap-4 mb-6">
          <span className="text-muted text-[11px] font-mono font-medium">
            export
          </span>
          <span className="h-px flex-1 bg-gradient-to-r from-muted/20 to-transparent" />
        </div>
        <h2 className="section-header">Four files, one audit trail</h2>
        <p className="font-sans text-[13px] text-fg/76 mb-8 -mt-2 max-w-md">
          A model leaves Caterva with its provenance attached. What the source
          row measured, and how far the other rows disagree, go with it.
        </p>

        <TerminalWindow path={`~ — compose --export ${format}`} glow>
          <div className="mb-4 text-fg/92">
            <span className="text-signal">$</span>{" "}
            <span className="font-mono text-[12px] whitespace-pre-wrap break-words">
              {EXPORT_COMMAND} {format}
            </span>
          </div>

          {/* Format tabs */}
          <div className="flex items-center gap-0.5 mb-4 p-0.5 rounded-lg border border-fg/[0.10] bg-fg/[0.015] w-fit">
            {FORMATS.map((f) => (
              <button
                key={f.id}
                onClick={() => setFormat(f.id)}
                className={`relative px-3 py-1.5 rounded-md text-[11px] font-mono transition-all duration-300 ${
                  format === f.id
                    ? "text-fg/92"
                    : "text-fg/66 hover:text-fg/76"
                }`}
              >
                {format === f.id && (
                  <motion.div
                    layoutId="export-tab-active"
                    className="absolute inset-0 rounded-md border border-fg/[0.16] bg-fg/[0.04]"
                    transition={{ type: "spring", stiffness: 400, damping: 30 }}
                  />
                )}
                <span className="relative z-10 flex items-center gap-1.5">
                  {f.label}
                  <span className="text-fg/66 text-[9px]">{f.ext}</span>
                </span>
              </button>
            ))}
          </div>

          {/* Preview */}
          <AnimatePresence mode="wait">
            <motion.div
              key={format}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -6 }}
              transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
              className="relative"
            >
              <pre
                className={`cite-code-block text-[11px] leading-relaxed max-h-[400px] overflow-auto ${
                  // The methods section is prose and wraps; the rest are
                  // files whose line breaks mean something.
                  format === "methods" ? "whitespace-pre-wrap" : "whitespace-pre"
                }`}
              >
                <code>{SAMPLE[format].text}</code>
              </pre>
              <button
                onClick={() => handleCopy(SAMPLE[format].text, active.label)}
                className="cite-copy-btn top-2 right-2 z-10"
              >
                copy
              </button>
            </motion.div>
          </AnimatePresence>

          {/* What the file is, and what this excerpt is of it */}
          <div className="mt-4 pt-3 border-t border-fg/[0.08] flex flex-col gap-1.5 text-[10px] font-mono">
            <span className="text-fg/76">{active.opensIn}</span>
            <span className="text-fg/66">
              Excerpt: {SAMPLE[format].excerpt}, of a{" "}
              {SAMPLE[format].bytes.toLocaleString("en-US")}-byte file. Run{" "}
              {EXPORT_RUN_DATE}; values are what BRENDA returned that day.
            </span>
          </div>
        </TerminalWindow>
      </Reveal>
    </section>
  );
}
