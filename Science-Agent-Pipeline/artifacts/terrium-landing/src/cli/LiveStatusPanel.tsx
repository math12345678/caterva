import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import TerminalWindow from './TerminalWindow';
import Reveal from './Reveal';

interface ServiceStatus {
  name: string;
  endpoint: string;
  ok: boolean;
  latency: number; // ms
  description: string;
}

const SERVICES: ServiceStatus[] = [
  { name: 'BRENDA', endpoint: 'brenda-enzymes.org', ok: true, latency: 142, description: 'Enzyme kinetic parameters (Km, Vmax, kcat)' },
  { name: 'KEGG', endpoint: 'kegg.jp', ok: true, latency: 287, description: 'Pathway & reaction data' },
  { name: 'PubMed', endpoint: 'eutils.ncbi.nlm.nih.gov', ok: true, latency: 95, description: 'Literature citations & abstracts' },
  { name: 'Tellurium', endpoint: 'tellurium.analogmachine.org', ok: true, latency: 12, description: 'ODE engine (RK4 integration)' },
  { name: 'API Server', endpoint: 'api.terrium.app', ok: true, latency: 34, description: 'Agent pipeline & SSE streaming' },
];

function LatencyBar({ ms, maxMs }: { ms: number; maxMs: number }) {
  const pct = Math.min((ms / maxMs) * 100, 100);
  const color = ms < 50 ? '#1D8A72' : ms < 200 ? '#F59E0B' : '#EF4444';

  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1 bg-white/[0.04] rounded-full overflow-hidden">
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.8, ease: 'easeOut' }}
          className="h-full rounded-full"
          style={{ backgroundColor: color }}
        />
      </div>
      <span className="text-[10px] text-white/30 font-mono tabular-nums w-10 text-right">{ms}ms</span>
    </div>
  );
}

const API_BASE = import.meta.env.VITE_API_URL || '';

export default function LiveStatusPanel() {
  const [uptime, setUptime] = useState<number | null>(null);
  const [waitlist, setWaitlist] = useState<number | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([
      fetch(`${API_BASE}/api/metrics`, { signal: controller.signal })
        .then((r) => r.json().then((d) => Math.round(d.uptime / 3600)))
        .catch(() => null),
      fetch(`${API_BASE}/api/waitlist/count`, { signal: controller.signal })
        .then((r) => r.json().then((d) => d.count))
        .catch(() => null),
    ]).then(([u, w]) => {
      setUptime(u);
      setWaitlist(w);
    });
    return () => controller.abort();
  }, []);

  const maxLatency = Math.max(...SERVICES.map((s) => s.latency), 100);
  const allOk = SERVICES.every((s) => s.ok);

  return (
    <section className="max-w-3xl mx-auto px-4 md:px-6 py-10 section-bg-blue" id="status">
      <Reveal>
        <div className="flex items-center gap-4 mb-6">
          <span className="text-[#3B82F6] text-[11px] font-mono font-medium">status</span>
          <span className="h-px flex-1 bg-gradient-to-r from-[#3B82F6]/20 to-transparent" />
        </div>
        <h2 className="section-header">System status</h2>
        <p className="font-sans text-[13px] text-white/30 mb-8 -mt-2 max-w-md">
          Real-time health of data sources and compute infrastructure.
        </p>

        <TerminalWindow path="~ — terrium status --live" glow>
          <div className="mb-4 text-white/90">
            <span className="text-[#1D8A72]">$</span>{' '}
            <span className="font-mono text-[12px]">terrium status --all --live</span>
          </div>

          {/* Overall health */}
          <div className="flex items-center gap-3 mb-5 p-3 rounded-lg border border-white/[0.04] bg-white/[0.01]">
            <motion.div
              animate={{ scale: [1, 1.15, 1] }}
              transition={{ duration: 2, repeat: Infinity, ease: 'easeInOut' }}
              className={`w-2.5 h-2.5 rounded-full ${allOk ? 'bg-[#1D8A72]' : 'bg-[#F59E0B]'}`}
            />
            <span className="text-[12px] text-white/70 font-sans">
              {allOk ? 'All systems operational' : 'Some services degraded'}
            </span>
            {uptime !== null && (
              <>
                <span className="w-px h-3 bg-white/[0.06]" />
                <span className="text-[11px] text-white/25 font-mono">
                  {uptime}h uptime
                </span>
              </>
            )}
            {waitlist !== null && (
              <>
                <span className="w-px h-3 bg-white/[0.06]" />
                <span className="text-[11px] text-white/25 font-mono">
                  {waitlist} waiting
                </span>
              </>
            )}
          </div>

          {/* Service list */}
          <div className="space-y-3">
            {SERVICES.map((svc, i) => (
              <motion.div
                key={svc.name}
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.4, delay: i * 0.06 }}
                className="flex items-start gap-3 p-2.5 rounded-lg border border-white/[0.03] hover:border-white/[0.06] transition-all group"
              >
                <motion.span
                  animate={{ opacity: svc.ok ? [1, 0.6, 1] : 1 }}
                  transition={{ duration: 2, repeat: Infinity }}
                  className={`shrink-0 mt-0.5 w-1.5 h-1.5 rounded-full ${svc.ok ? 'bg-[#1D8A72]' : 'bg-[#EF4444]'}`}
                />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-0.5">
                    <span className="text-[12px] text-white/70 font-sans font-medium">{svc.name}</span>
                    <span className="text-[10px] text-white/15 font-mono">{svc.endpoint}</span>
                  </div>
                  <p className="text-[10px] text-white/30 mb-1.5">{svc.description}</p>
                  <LatencyBar ms={svc.latency} maxMs={maxLatency} />
                </div>
              </motion.div>
            ))}
          </div>

          <div className="mt-4 pt-3 border-t border-white/[0.04] text-[9px] text-white/15 font-mono flex items-center justify-between">
            <span>refreshed just now</span>
            <span>{SERVICES.length} services monitored</span>
          </div>
        </TerminalWindow>
      </Reveal>
    </section>
  );
}
