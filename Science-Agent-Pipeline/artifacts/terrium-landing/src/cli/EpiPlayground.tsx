import { useState, useMemo, useCallback } from "react";
import { motion } from "framer-motion";
import TerminalWindow from "./TerminalWindow";
import LineChart from "./LineChart";
import { simulateSIR } from "@/lib/simulate";

import ParamSlider from "@/components/ui/param-slider";

const PRESETS = [
  { label: "Flu (moderate)", beta: 0.3, gamma: 0.1, s0: 990, i0: 10 },
  { label: "COVID (mild)", beta: 0.2, gamma: 0.07, s0: 990, i0: 10 },
  { label: "Measles (high)", beta: 0.9, gamma: 0.08, s0: 990, i0: 10 },
  { label: "Ebola (slow)", beta: 0.15, gamma: 0.05, s0: 950, i0: 50 },
];

export default function EpiPlayground() {
  const [beta, setBeta] = useState(0.3);
  const [gamma, setGamma] = useState(0.1);
  const [s0, setS0] = useState(990);
  const [i0, setI0] = useState(10);
  const end = 100;
  const points = 100;

  const result = useMemo(
    () => simulateSIR({ beta, gamma, s0, i0, end, points }),
    [beta, gamma, s0, i0],
  );

  const r0 = useMemo(() => (beta / gamma).toFixed(2), [beta, gamma]);
  const peakInfected = useMemo(
    () => Math.max(...result.trajectory.map((p) => p.I)).toFixed(0),
    [result.trajectory],
  );
  const totalPop = s0 + i0;
  const finalSusceptible =
    result.trajectory[result.trajectory.length - 1]?.S ?? 0;

  const applyPreset = useCallback((p: (typeof PRESETS)[number]) => {
    setBeta(p.beta);
    setGamma(p.gamma);
    setS0(p.s0);
    setI0(p.i0);
  }, []);

  return (
    <TerminalWindow path="~ — terrium playground --domain sir" glow>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
        {/* Controls column */}
        <div className="space-y-6">
          {/* Presets */}
          <div>
            <span className="text-[10px] text-white/25 uppercase tracking-widest mb-2 block">
              outbreak presets
            </span>
            <div className="flex flex-wrap gap-1.5">
              {PRESETS.map((p) => (
                <motion.button
                  key={p.label}
                  onClick={() => applyPreset(p)}
                  className="px-2.5 py-1 rounded-md text-[10px] border border-white/[0.06] text-white/40
                    hover:border-[#3B82F6]/30 hover:text-[#3B82F6] hover:bg-[#3B82F6]/[0.04]
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
              label="β (transmission)"
              value={beta}
              min={0.01}
              max={2.0}
              step={0.01}
              unit="1/day"
              onChange={setBeta}
              color="#3B82F6"
              hint="infection rate per contact"
            />
            <ParamSlider
              label="γ (recovery)"
              value={gamma}
              min={0.01}
              max={1.0}
              step={0.01}
              unit="1/day"
              onChange={setGamma}
              color="#1D8A72"
              hint="1/γ = avg. infectious days"
            />
            <ParamSlider
              label="S₀ (susceptible)"
              value={s0}
              min={100}
              max={1000}
              step={10}
              unit="people"
              onChange={setS0}
              color="#8B5CF6"
            />
            <ParamSlider
              label="I₀ (initial infected)"
              value={i0}
              min={1}
              max={200}
              step={1}
              unit="people"
              onChange={setI0}
              color="#EF4444"
            />
          </div>

          {/* Computed values */}
          <div className="rounded-lg border border-white/[0.06] bg-white/[0.015] p-3 space-y-2">
            <div className="flex justify-between text-[11px]">
              <span className="text-white/35">R₀ (basic repro.)</span>
              <span className="text-[#3B82F6] font-mono">{r0}</span>
            </div>
            <div className="flex justify-between text-[11px]">
              <span className="text-white/35">peak infected</span>
              <span className="text-[#EF4444] font-mono">{peakInfected}</span>
            </div>
            <div className="flex justify-between text-[11px]">
              <span className="text-white/35">final susceptible</span>
              <span className="text-[#8B5CF6] font-mono">
                {finalSusceptible.toFixed(0)}
              </span>
            </div>
            <div className="flex justify-between text-[11px]">
              <span className="text-white/35">cons. error</span>
              <span className="text-[#F59E0B] font-mono">
                {result.conservationError.toExponential(2)}
              </span>
            </div>
            <div className="flex justify-between text-[11px]">
              <span className="text-white/35">total population</span>
              <span className="text-white/45 font-mono">
                {totalPop.toLocaleString()}
              </span>
            </div>
          </div>
        </div>

        {/* Chart column */}
        <div className="md:col-span-2">
          <div className="rounded-lg border border-white/[0.04] bg-white/[0.01] p-3">
            <div className="flex items-center justify-between mb-2 text-[10px]">
              <span className="text-white/30 font-mono">
                {r0 >= "1" ? "epidemic (R₀ ≥ 1)" : "outbreak fades (R₀ < 1)"}{" "}
                over {end} days
              </span>
              <span className="text-white/15 font-mono">{points} points</span>
            </div>
            <motion.div
              key={`${beta}-${gamma}-${s0}-${i0}`}
              initial={{ opacity: 0.6 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.3 }}
            >
              <LineChart
                data={result.trajectory}
                series={[
                  { key: "S", color: "#3B82F6" },
                  { key: "I", color: "#EF4444" },
                  { key: "R", color: "#1D8A72" },
                ]}
                height={260}
              />
            </motion.div>
            <div className="mt-2 flex flex-wrap items-center gap-4 text-[9px] text-white/25 font-mono">
              <span className="flex items-center gap-1">
                <span className="w-2 h-0.5 rounded bg-[#3B82F6]" /> S
              </span>
              <span className="flex items-center gap-1">
                <span className="w-2 h-0.5 rounded bg-[#EF4444]" /> I
              </span>
              <span className="flex items-center gap-1">
                <span className="w-2 h-0.5 rounded bg-[#1D8A72]" /> R
              </span>
              <span className="ml-auto">
                herd immunity ≈ {((1 - 1 / (beta / gamma)) * 100).toFixed(0)}%
              </span>
            </div>
          </div>
        </div>
      </div>
    </TerminalWindow>
  );
}
