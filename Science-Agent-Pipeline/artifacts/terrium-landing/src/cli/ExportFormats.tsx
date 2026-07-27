import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import TerminalWindow from './TerminalWindow';
import Reveal from './Reveal';
import { toast } from '@/hooks/use-toast';

type ExportFormat = 'sbml' | 'csv' | 'json';

const FORMATS: { id: ExportFormat; label: string; ext: string; icon: string; color: string }[] = [
  { id: 'sbml', label: 'SBML', ext: '.xml', icon: '\u2699', color: '#1D8A72' },
  { id: 'csv', label: 'CSV', ext: '.csv', icon: '\u25A6', color: '#3B82F6' },
  { id: 'json', label: 'JSON', ext: '.json', icon: '\u27E8\u27E9', color: '#F59E0B' },
];

const SBML_PREVIEW = `<?xml version="1.0" encoding="UTF-8"?>
<sbml xmlns="http://www.sbml.org/sbml/level3/version2/core" level="3" version="2">
  <model id="mm_kinetics" name="Michaelis-Menten Kinetics">
    <listOfCompartments>
      <compartment id="cytosol" constant="true"/>
    </listOfCompartments>
    <listOfSpecies>
      <species id="S" compartment="cytosol"
               initialConcentration="10.0" constant="false"/>
      <species id="P" compartment="cytosol"
               initialConcentration="0.0" constant="false"/>
    </listOfSpecies>
    <listOfParameters>
      <parameter id="Km" value="2.0" units="mM"/>
      <parameter id="Vmax" value="5.0" units="mM/s"/>
    </listOfParameters>
    <listOfReactions>
      <reaction id="MM_reaction" reversible="false">
        <listOfReactants><speciesReference species="S"/></listOfReactants>
        <listOfProducts><speciesReference species="P"/></listOfProducts>
        <kineticLaw>
          <math xmlns="http://www.w3.org/1998/Math/MathML">
            <apply><divide/>
              <apply><times/><ci>Vmax</ci><ci>S</ci></apply>
              <apply><plus/><ci>Km</ci><ci>S</ci></apply>
            </apply>
          </math>
        </kineticLaw>
      </reaction>
    </listOfReactions>
  </model>
</sbml>`;

const CSV_PREVIEW = `t,S,P
0.000000,10.000000,0.000000
0.083333,9.678234,0.321766
0.166667,9.357201,0.642799
0.250000,9.036892,0.963108
0.333333,8.717299,1.282701
0.416667,8.398413,1.601587
0.500000,8.080226,1.919774
0.583333,7.762728,2.237272
0.666667,7.445911,2.554089
0.750000,7.129765,2.870235
...
3.000000,3.521403,6.478597`;

const JSON_PREVIEW = `{
  "model": "mm_kinetics",
  "domain": "enzyme-kinetics",
  "parameters": {
    "Km": { "value": 2.0, "unit": "mM", "source": "BRENDA" },
    "Vmax": { "value": 5.0, "unit": "mM/s", "source": "BRENDA" }
  },
  "trajectory": [
    { "t": 0.0, "S": 10.0, "P": 0.0 },
    { "t": 0.5, "S": 8.08, "P": 1.92 },
    { "t": 1.0, "S": 6.42, "P": 3.58 }
  ],
  "validation": {
    "residual": 1.23e-14,
    "conserved": true,
    "citations": ["PMID:12345678"]
  }
}`;

const PREVIEWS: Record<ExportFormat, string> = {
  sbml: SBML_PREVIEW,
  csv: CSV_PREVIEW,
  json: JSON_PREVIEW,
};

export default function ExportFormats() {
  const [format, setFormat] = useState<ExportFormat>('sbml');

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
          <span className="text-[#8B5CF6] text-[11px] font-mono font-medium">export</span>
          <span className="h-px flex-1 bg-gradient-to-r from-[#8B5CF6]/20 to-transparent" />
        </div>
        <h2 className="section-header">Export anywhere</h2>
        <p className="font-sans text-[13px] text-white/30 mb-8 -mt-2 max-w-md">
          SBML for modeling tools, CSV for spreadsheets, JSON for custom pipelines.
          Every export includes full provenance.
        </p>

        <TerminalWindow path={`~ — terrium export --format ${format}`} glow>
          <div className="mb-4 text-white/90">
            <span className="text-[#1D8A72]">$</span>{' '}
            <span className="font-mono text-[12px]">terrium export --format {format} --include-citations</span>
          </div>

          {/* Format tabs */}
          <div className="flex items-center gap-0.5 mb-4 p-0.5 rounded-lg border border-white/[0.05] bg-white/[0.015] w-fit">
            {FORMATS.map((f) => (
              <button
                key={f.id}
                onClick={() => setFormat(f.id)}
                className={`relative px-3 py-1.5 rounded-md text-[11px] font-mono transition-all duration-300 ${
                  format === f.id ? 'text-white/90' : 'text-white/25 hover:text-white/50'
                }`}
              >
                {format === f.id && (
                  <motion.div
                    layoutId="export-tab-active"
                    className="absolute inset-0 rounded-md border border-white/[0.08] bg-white/[0.04]"
                    transition={{ type: 'spring', stiffness: 400, damping: 30 }}
                  />
                )}
                <span className="relative z-10 flex items-center gap-1.5">
                  <span className="text-[10px]">{f.icon}</span>
                  {f.label}
                  <span className="text-white/15 text-[9px]">{f.ext}</span>
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
              <pre className="cite-code-block text-[11px] leading-relaxed max-h-[400px] overflow-auto whitespace-pre">
                <code>{PREVIEWS[format]}</code>
              </pre>
              <button
                onClick={() => handleCopy(PREVIEWS[format], active.label)}
                className="cite-copy-btn top-2 right-2 z-10"
              >
                copy
              </button>
            </motion.div>
          </AnimatePresence>

          {/* Format description */}
          <div className="mt-4 pt-3 border-t border-white/[0.04] flex flex-wrap items-center gap-4 text-[10px]">
            <span className="text-white/25 font-mono">
              {format === 'sbml' && 'Systems Biology Markup Language — opens in COPASI, Tellurium, libSBML'}
              {format === 'csv' && 'Comma-Separated Values — opens in Excel, Python/Pandas, R, MATLAB'}
              {format === 'json' && 'JavaScript Object Notation — machine-readable with full metadata tree'}
            </span>
            <span className="ml-auto text-white/15 font-mono">
              citations included &middot; provenance preserved
            </span>
          </div>
        </TerminalWindow>
      </Reveal>
    </section>
  );
}
