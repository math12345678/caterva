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
//   LDH          shipped 0.5   -> BRENDA gave 10.73 mM  (ref 740253)
//   Hexokinase   shipped 0.1   -> BRENDA gives 6 mM     (ref 641068)
//   AChE         shipped 0.09  -> BRENDA gave 0.09 mM   (ref 649716)
//   Trypsin      shipped 15    -> no resolved value; the name was dropped
//
// Off by 21x and 60x, under the enzyme's real name, on the page that
// advertises never inventing a number.
//
// The repair then hard-coded the resolver's answers, and they went stale
// the same way. Re-run live against BRENDA on 2026-11-02 (resolveQuery,
// no organism named, so the enzyme table's Homo sapiens): LDH with
// pyruvate resolves 0.03 mM, not 10.73; AChE with acetylcholine 0.0714
// mM, not 0.09; hexokinase with glucose 6 mM, ref 641068, unchanged. A
// constant pasted into a page is a snapshot of a database that keeps
// being recurated, so only the one that still matches stays, and it says
// when it was checked. LDH and AChE are gone rather than updated: the next
// recuration would make them wrong again, silently, and the agent
// simulator above resolves them live for anyone who asks.
//
// Vmax and s0 are NOT literature values and cannot be: Vmax = kcat x
// [E]0 needs an enzyme concentration (ADR 0013), and s0 is the
// experiment's own choice. They are rendered as "illustrative", next to
// the preset, so nothing reads them as hexokinase's.
const PRESETS = [
  {
    label: "Hexokinase",
    km: 6,
    vmax: 2.0,
    s0: 5,
    kmSource:
      "BRENDA ref 641068, Homo sapiens, glucose — checked against the live resolver 2026-11-02",
  },
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
            <span className="text-[10px] text-fg/66 uppercase tracking-widest mb-2 block">
              enzyme presets
            </span>
            <div className="flex flex-wrap gap-1.5">
              {PRESETS.map((p) => (
                <motion.button
                  key={p.label}
                  onClick={() => applyPreset(p)}
                  className="px-2.5 py-1 rounded-md text-[10px] border border-fg/[0.12] text-fg/70
                        hover:border-signal/30 hover:text-signal hover:bg-signal/[0.04]
                        transition-all duration-200 font-mono"
                  whileHover={{ scale: 1.03 }}
                  whileTap={{ scale: 0.97 }}
                >
                  {p.label}
                </motion.button>
              ))}
            </div>
            {PRESETS.map((p) => (
              <p
                key={p.label}
                data-testid="preset-provenance"
                className="mt-2 text-[9px] text-fg/60 leading-snug"
              >
                {p.label}: Km {p.km} mM — {p.kmSource}. Vmax {p.vmax} mM/s
                and [S]₀ {p.s0} mM are illustrative experimental choices, not
                literature values.
              </p>
            ))}
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
              color="#5D7F8D"
            />
            <ParamSlider
              label="Vmax"
              value={vmax}
              min={0.1}
              max={20}
              step={0.1}
              unit="mM/s"
              onChange={setVmax}
              color="#6A6E78"
            />
            <ParamSlider
              label="[S]₀"
              value={s0}
              min={0.1}
              max={30}
              step={0.1}
              unit="mM"
              onChange={setS0}
              color="#946522"
            />
          </div>

          {/* Computed values */}
          <div className="rounded-lg border border-fg/[0.12] bg-fg/[0.015] p-3 space-y-2">
            <div className="flex justify-between text-[11px]">
              <span className="text-fg/70">Km (affinity)</span>
              <span className="text-signal font-mono">{kmDisplay} mM</span>
            </div>
            <div className="flex justify-between text-[11px]">
              <span className="text-fg/70">v₀ (initial rate)</span>
              <span className="text-muted font-mono">{v0} mM/s</span>
            </div>
            <div className="flex justify-between text-[11px]">
              <span className="text-fg/70">residual</span>
              <span className="text-caution font-mono">
                {result.finalResidual.toExponential(2)}
              </span>
            </div>
            <div className="flex justify-between text-[11px]">
              <span className="text-fg/70">integration</span>
              <span className="text-fg/70 font-mono">
                RK4 (200 steps/pt)
              </span>
            </div>
          </div>
        </div>

        {/* Chart column */}
        <div className="md:col-span-2">
          <div className="rounded-lg border border-fg/[0.08] bg-fg/[0.01] p-3">
            <div className="flex items-center justify-between mb-2 text-[10px]">
              <span className="text-fg/70 font-mono">
                substrate depletion over {end}s
              </span>
              <span className="text-fg/66 font-mono">{points} points</span>
            </div>
            <motion.div
              key={`${km}-${vmax}-${s0}`}
              initial={{ opacity: 0.6 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.3 }}
            >
              <LineChart
                data={result.trajectory}
                series={[{ key: "S", color: "#5D7F8D" }]}
                height={260}
              />
            </motion.div>
            <div className="mt-2 flex items-center gap-4 text-[9px] text-fg/66 font-mono">
              <span className="flex items-center gap-1">
                <span className="w-2 h-0.5 rounded bg-signal" /> [S]
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
