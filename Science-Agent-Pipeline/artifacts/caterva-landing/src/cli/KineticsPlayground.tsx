import { useState, useMemo, useCallback } from "react";
import { motion } from "framer-motion";
import TerminalWindow from "./TerminalWindow";
import LineChart from "./LineChart";
import { simulateMichaelisMenten } from "@/lib/simulate";

import ParamSlider from "@/components/ui/param-slider";

// A real enzyme name on a preset is a claim about that enzyme.
//
// These Km values were unsourced, and three of the four contradicted the
// values THIS PRODUCT resolves for the same enzyme:
//
//   LDH          shipped 0.5   -> BRENDA gives 10.73 mM  (ref 740253)
//   Hexokinase   shipped 0.1   -> BRENDA gives 6 mM      (ref 641068)
//   AChE         shipped 0.09  -> 0.09 mM, correct       (ref 649716)
//   Trypsin      shipped 15    -> no resolved value; the name is dropped
//
// Off by 21x and 60x, under the enzyme's real name, on the page that
// advertises never inventing a number. A student who clicked "LDH" here
// and then ran "lactate dehydrogenase with pyruvate" through the actual
// product got two different Km values from the same page.
//
// Km now carries the value Caterva itself resolves, with its BRENDA
// reference. Vmax and s0 stay illustrative and are labelled as such:
// Vmax is NEVER literature-resolvable here (it needs [E]0, ADR 0013), so
// attributing it to anything would be the same defect again.
const PRESETS = [
  { label: "LDH", km: 10.73, vmax: 4.5, s0: 10, kmSource: "BRENDA ref 740253" },
  { label: "Hexokinase", km: 6, vmax: 2.0, s0: 5, kmSource: "BRENDA ref 641068" },
  { label: "AChE", km: 0.09, vmax: 6.0, s0: 3, kmSource: "BRENDA ref 649716" },
];

export default function KineticsPlayground() {
  const [km, setKm] = useState(2.0);
  const [vmax, setVmax] = useState(5.0);
  const [s0, setS0] = useState(10.0);
  const end = 5;
  const points = 80;

  const result = useMemo(
    () => simulateMichaelisMenten({ km, vmax, s0, end, points }),
    [km, vmax, s0, end, points],
  );

  const kmDisplay = useMemo(() => km.toFixed(2), [km]);
  const v0 = useMemo(
    () => ((vmax * s0) / (km + s0)).toFixed(3),
    [vmax, km, s0],
  );

  const applyPreset = useCallback((p: (typeof PRESETS)[number]) => {
    setKm(p.km);
    setVmax(p.vmax);
    setS0(p.s0);
  }, []);

  return (
    <TerminalWindow path="~ — caterva playground --domain mm" glow>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
        {/* Controls column */}
        <div className="space-y-6">
          {/* Presets */}
          <div>
            <span className="text-[10px] text-white/25 uppercase tracking-widest mb-2 block">
              enzyme presets
            </span>
            <div className="flex flex-wrap gap-1.5">
              {PRESETS.map((p) => (
                <motion.button
                  key={p.label}
                  onClick={() => applyPreset(p)}
                  className="px-2.5 py-1 rounded-md text-[10px] border border-white/[0.06] text-white/40
                        hover:border-[#1D8A72]/30 hover:text-[#1D8A72] hover:bg-[#1D8A72]/[0.04]
                        transition-all duration-200 font-mono"
                  whileHover={{ scale: 1.03 }}
                  whileTap={{ scale: 0.97 }}
                >
                  {p.label}
                </motion.button>
              ))}
            </div>
          </div>

          {/* Sliders */}
          <div className="space-y-5">
            <ParamSlider
              label="Km"
              value={km}
              min={0.01}
              max={20}
              step={0.01}
              unit="mM"
              onChange={setKm}
              color="#1D8A72"
            />
            <ParamSlider
              label="Vmax"
              value={vmax}
              min={0.1}
              max={20}
              step={0.1}
              unit="mM/s"
              onChange={setVmax}
              color="#3B82F6"
            />
            <ParamSlider
              label="[S]₀"
              value={s0}
              min={0.1}
              max={30}
              step={0.1}
              unit="mM"
              onChange={setS0}
              color="#F59E0B"
            />
          </div>

          {/* Computed values */}
          <div className="rounded-lg border border-white/[0.06] bg-white/[0.015] p-3 space-y-2">
            <div className="flex justify-between text-[11px]">
              <span className="text-white/35">Km (affinity)</span>
              <span className="text-[#1D8A72] font-mono">{kmDisplay} mM</span>
            </div>
            <div className="flex justify-between text-[11px]">
              <span className="text-white/35">v₀ (initial rate)</span>
              <span className="text-[#3B82F6] font-mono">{v0} mM/s</span>
            </div>
            <div className="flex justify-between text-[11px]">
              <span className="text-white/35">residual</span>
              <span className="text-[#F59E0B] font-mono">
                {result.finalResidual.toExponential(2)}
              </span>
            </div>
            <div className="flex justify-between text-[11px]">
              <span className="text-white/35">integration</span>
              <span className="text-white/45 font-mono">
                RK4 (200 steps/pt)
              </span>
            </div>
          </div>
        </div>

        {/* Chart column */}
        <div className="md:col-span-2">
          <div className="rounded-lg border border-white/[0.04] bg-white/[0.01] p-3">
            <div className="flex items-center justify-between mb-2 text-[10px]">
              <span className="text-white/30 font-mono">
                substrate depletion over {end}s
              </span>
              <span className="text-white/15 font-mono">{points} points</span>
            </div>
            <motion.div
              key={`${km}-${vmax}-${s0}`}
              initial={{ opacity: 0.6 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.3 }}
            >
              <LineChart
                data={result.trajectory}
                series={[{ key: "S", color: "#1D8A72" }]}
                height={260}
              />
            </motion.div>
            <div className="mt-2 flex items-center gap-4 text-[9px] text-white/25 font-mono">
              <span className="flex items-center gap-1">
                <span className="w-2 h-0.5 rounded bg-[#1D8A72]" /> [S]
              </span>
              <span>t₀ = {result.trajectory[0]?.S.toFixed(1)} mM</span>
              <span>
                t_end ={" "}
                {result.trajectory[result.trajectory.length - 1]?.S.toFixed(3)}{" "}
                mM
              </span>
            </div>
          </div>
        </div>
      </div>
    </TerminalWindow>
  );
}
