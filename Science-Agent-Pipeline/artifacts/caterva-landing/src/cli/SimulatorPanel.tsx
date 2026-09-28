import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import ExportButtons from "@/components/ui/export-buttons";
import TerminalWindow from "./TerminalWindow";
import LineChart from "./LineChart";
import { simulateMichaelisMenten } from "@/lib/simulate";

// Enzyme kinetics only since 2026-09-27, when the SIR domain was archived.
// The prop stays so the page that embeds this panel keeps its shape.
export type Domain = "mm";

interface SimulatorPanelProps {
  domain: Domain;
  onDomainChange: (d: Domain) => void;
}

function Field({
  label,
  value,
  onChange,
  step = 0.1,
  min = 0,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  step?: number;
  min?: number;
}) {
  return (
    <label className="flex flex-col gap-0.5 min-w-0">
      <span className="text-[9px] text-white/25 uppercase tracking-wide">
        {label}
      </span>
      <input
        type="number"
        value={value}
        step={step}
        min={min}
        onChange={(e) => {
          const v = Number(e.target.value);
          // min is a physical floor (e.g. Km > 0) -- the HTML min attribute
          // doesn't stop typed/pasted/cleared values from reaching the integrator.
          onChange(Number.isFinite(v) ? Math.max(min, v) : min);
        }}
        className="w-full rounded-lg border border-white/[0.06] bg-white/[0.02] px-2.5 py-1.5 text-white/80 text-[12px] outline-none transition-all duration-200 focus:border-[#1D8A72]/30 focus:shadow-[0_0_12px_rgba(29,138,114,0.06)]"
      />
    </label>
  );
}

export default function SimulatorPanel(_props: SimulatorPanelProps) {
  const [km, setKm] = useState(2);
  const [vmax, setVmax] = useState(5);
  const [s0, setS0] = useState(10);
  const [mmEnd, setMmEnd] = useState(3);

  const [pulse, setPulse] = useState(0);
  useEffect(() => setPulse((p) => p + 1), [km, vmax, s0, mmEnd]);

  const mm = useMemo(
    () => simulateMichaelisMenten({ km, vmax, s0, end: mmEnd, points: 60 }),
    [km, vmax, s0, mmEnd],
  );

  const command = `caterva simulate mm --km ${km} --vmax ${vmax} --s0 ${s0} --end ${mmEnd}`;

  return (
    <TerminalWindow path="~/caterva — live simulator" glow>
      <motion.div
        key={command}
        initial={{ opacity: 0.4 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.25 }}
        className="mb-5 text-white/80 text-[12px]"
      >
        <span className="text-[#1D8A72]">$</span> {command}
      </motion.div>

        <>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-5">
            <Field label="km" value={km} onChange={setKm} min={0.01} />
            <Field label="vmax" value={vmax} onChange={setVmax} min={0.01} />
            <Field label="s0" value={s0} onChange={setS0} min={0.01} />
            <Field
              label="end"
              value={mmEnd}
              onChange={setMmEnd}
              min={0.1}
              step={0.5}
            />
          </div>
          <motion.div
            key={pulse}
            initial={{ opacity: 0.5 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.3 }}
          >
            <div className="rounded-lg border border-white/[0.04] bg-white/[0.01] p-2">
              <LineChart
                data={mm.trajectory}
                series={[{ key: "S", color: "#1D8A72" }]}
              />
            </div>
          </motion.div>
          <div className="mt-4 text-[11px] text-white/30 space-y-1.5">
            <div className="flex items-center gap-2">
              <span className="text-white/20">rate law:</span>
              <span className="text-white/50">
                dS/dt = -Vmax&middot;S / (Km + S)
              </span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-white/20">final [S] at t={mmEnd}:</span>
              <span className="text-white/50">
                {mm.trajectory[mm.trajectory.length - 1].S.toFixed(3)}
              </span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-white/20">residual:</span>
              <span
                className={
                  mm.finalResidual < 1e-2 ? "text-[#1D8A72]" : "text-yellow-500"
                }
              >
                {mm.finalResidual.toExponential(2)}
              </span>
            </div>
            <div className="mt-3">
              <ExportButtons trajectory={mm.trajectory} filenamePrefix="mm" />
            </div>
          </div>
        </>

      <div className="mt-5 pt-4 border-t border-white/[0.04] text-[11px] text-white/20 leading-relaxed">
        Runs RK4 integration in your browser using the same rate laws verified
        in caterva/caterva_engine.py. The production engine integrates via
        roadrunner against exact closed-form solutions to 1e-10; this demo
        checks itself against the same equations at a coarser tolerance so it
        stays instant on every keystroke.
      </div>
    </TerminalWindow>
  );
}
