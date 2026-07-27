import { useEffect, useMemo, useState } from 'react';
import { motion } from 'framer-motion';
import ExportButtons from '@/components/ui/export-buttons';
import TerminalWindow from './TerminalWindow';
import LineChart from './LineChart';
import { simulateMichaelisMenten, simulateSIR } from '@/lib/simulate';

export type Domain = 'mm' | 'sir';

interface SimulatorPanelProps {
  domain: Domain;
  onDomainChange: (d: Domain) => void;
}

function Field({ label, value, onChange, step = 0.1, min = 0 }: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  step?: number;
  min?: number;
}) {
  return (
    <label className="flex flex-col gap-0.5 min-w-0">
      <span className="text-[9px] text-white/25 uppercase tracking-wide">{label}</span>
      <input
        type="number"
        value={value}
        step={step}
        min={min}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full rounded-lg border border-white/[0.06] bg-white/[0.02] px-2.5 py-1.5 text-white/80 text-[12px] outline-none transition-all duration-200 focus:border-[#1D8A72]/30 focus:shadow-[0_0_12px_rgba(29,138,114,0.06)]"
      />
    </label>
  );
}

export default function SimulatorPanel({ domain, onDomainChange }: SimulatorPanelProps) {
  const [km, setKm] = useState(2);
  const [vmax, setVmax] = useState(5);
  const [s0, setS0] = useState(10);
  const [mmEnd, setMmEnd] = useState(3);

  const [beta, setBeta] = useState(0.3);
  const [gamma, setGamma] = useState(0.1);
  const [susceptible0, setSusceptible0] = useState(990);
  const [infected0, setInfected0] = useState(10);
  const [sirEnd, setSirEnd] = useState(60);

  const [pulse, setPulse] = useState(0);
  useEffect(() => setPulse((p) => p + 1), [km, vmax, s0, mmEnd, beta, gamma, susceptible0, infected0, sirEnd]);

  const mm = useMemo(
    () => simulateMichaelisMenten({ km, vmax, s0, end: mmEnd, points: 60 }),
    [km, vmax, s0, mmEnd],
  );
  const sir = useMemo(
    () => simulateSIR({ beta, gamma, s0: susceptible0, i0: infected0, end: sirEnd, points: 60 }),
    [beta, gamma, susceptible0, infected0, sirEnd],
  );

  const command =
    domain === 'mm'
      ? `terrium simulate mm --km ${km} --vmax ${vmax} --s0 ${s0} --end ${mmEnd}`
      : `terrium simulate sir --beta ${beta} --gamma ${gamma} --s0 ${susceptible0} --i0 ${infected0} --end ${sirEnd}`;

  const peakInfected = useMemo(() => {
    if (domain !== 'sir') return null;
    return Math.max(...sir.trajectory.map((p) => p.I));
  }, [domain, sir]);

  return (
    <TerminalWindow path="~/terrium — live simulator" glow>
      <div className="flex gap-2 mb-5">
        {(['mm', 'sir'] as const).map((d) => (
          <button
            key={d}
            onClick={() => onDomainChange(d)}
            className={`px-3 py-1.5 rounded-lg text-[11px] border transition-all duration-300 ${
              domain === d
                ? 'border-[#1D8A72]/25 text-[#1D8A72] bg-[#1D8A72]/[0.06] shadow-[0_0_20px_rgba(29,138,114,0.08)]'
                : 'border-white/[0.06] text-white/40 hover:text-white/70 hover:border-white/[0.12] bg-white/[0.02]'
            }`}
          >
            {d === 'mm' ? 'enzyme-kinetics' : 'sir-epidemiology'}
          </button>
        ))}
      </div>

      <motion.div
        key={command}
        initial={{ opacity: 0.4 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.25 }}
        className="mb-5 text-white/80 text-[12px]"
      >
        <span className="text-[#1D8A72]">$</span> {command}
      </motion.div>

      {domain === 'mm' ? (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-5">
            <Field label="km" value={km} onChange={setKm} min={0.01} />
            <Field label="vmax" value={vmax} onChange={setVmax} min={0.01} />
            <Field label="s0" value={s0} onChange={setS0} min={0.01} />
            <Field label="end" value={mmEnd} onChange={setMmEnd} min={0.1} step={0.5} />
          </div>
          <motion.div key={pulse} initial={{ opacity: 0.5 }} animate={{ opacity: 1 }} transition={{ duration: 0.3 }}>
            <div className="rounded-lg border border-white/[0.04] bg-white/[0.01] p-2">
              <LineChart data={mm.trajectory} series={[{ key: 'S', color: '#1D8A72' }]} />
            </div>
          </motion.div>
          <div className="mt-4 text-[11px] text-white/30 space-y-1.5">
            <div className="flex items-center gap-2">
              <span className="text-white/20">rate law:</span>
              <span className="text-white/50">dS/dt = -Vmax&middot;S / (Km + S)</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-white/20">final [S] at t={mmEnd}:</span>
              <span className="text-white/50">{mm.trajectory[mm.trajectory.length - 1].S.toFixed(3)}</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-white/20">residual:</span>
              <span className={mm.finalResidual < 1e-2 ? 'text-[#1D8A72]' : 'text-yellow-500'}>
                {mm.finalResidual.toExponential(2)}
              </span>
            </div>
            <div className="mt-3">
              <ExportButtons
                trajectory={mm.trajectory}
                filenamePrefix="mm"
              />
            </div>
          </div>
        </>
      ) : (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 mb-5">
            <Field label="beta" value={beta} onChange={setBeta} min={0.01} step={0.05} />
            <Field label="gamma" value={gamma} onChange={setGamma} min={0.01} step={0.05} />
            <Field label="s0" value={susceptible0} onChange={setSusceptible0} min={1} step={10} />
            <Field label="i0" value={infected0} onChange={setInfected0} min={1} step={1} />
            <Field label="end" value={sirEnd} onChange={setSirEnd} min={1} step={5} />
          </div>
          <motion.div key={pulse} initial={{ opacity: 0.5 }} animate={{ opacity: 1 }} transition={{ duration: 0.3 }}>
            <div className="rounded-lg border border-white/[0.04] bg-white/[0.01] p-2">
              <LineChart
                data={sir.trajectory}
                series={[
                  { key: 'S', color: '#3B82F6' },
                  { key: 'I', color: '#EF4444' },
                  { key: 'R', color: '#1D8A72' },
                ]}
              />
            </div>
          </motion.div>
          <div className="mt-4">
            <div className="flex gap-4 text-[11px] mb-3">
              <span className="flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-sm bg-[#3B82F6]" />
                <span className="text-white/40">susceptible</span>
              </span>
              <span className="flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-sm bg-[#EF4444]" />
                <span className="text-white/40">infected</span>
              </span>
              <span className="flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-sm bg-[#1D8A72]" />
                <span className="text-white/40">recovered</span>
              </span>
            </div>
            <div className="text-[11px] text-white/30 space-y-1.5">
              <div className="flex items-center gap-2">
                <span className="text-white/20">peak infected:</span>
                <span className="text-white/50">{peakInfected?.toFixed(1)}</span>
                <span className="text-white/20">of N = {susceptible0 + infected0}</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-white/20">conservation error:</span>
                <span className={sir.conservationError < 1e-2 ? 'text-[#1D8A72]' : 'text-yellow-500'}>
                  {sir.conservationError.toExponential(2)}
                </span>
              </div>
              <div className="mt-3">
                <ExportButtons
                  trajectory={sir.trajectory}
                  filenamePrefix="sir"
                />
              </div>
            </div>
          </div>
        </>
      )}

      <div className="mt-5 pt-4 border-t border-white/[0.04] text-[11px] text-white/20 leading-relaxed">
        Runs RK4 integration in your browser using the same rate laws verified in
        Tellurium/tellurium_engine.py. The production engine integrates via roadrunner
        against exact closed-form solutions to 1e-10; this demo checks itself against
        the same equations at a coarser tolerance so it stays instant on every keystroke.
      </div>
    </TerminalWindow>
  );
}
