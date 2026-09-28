import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import TerminalWindow from "./TerminalWindow";
import Reveal from "./Reveal";

interface ServiceStatus {
  name: string;
  endpoint: string;
  description: string;
}

const SERVICES: ServiceStatus[] = [
  {
    name: "BRENDA",
    endpoint: "brenda-enzymes.org",
    description: "Enzyme kinetic parameters (Km, Vmax, kcat)",
  },
  {
    name: "PubMed",
    endpoint: "eutils.ncbi.nlm.nih.gov",
    description: "Literature citations & abstracts",
  },
  {
    name: "Caterva engine",
    endpoint: "local · libRoadRunner",
    description: "ODE integration, run on the machine that asks",
  },
  {
    name: "API Server",
    endpoint: "this site's /api",
    description: "Agent pipeline & SSE streaming",
  },
];

const API_BASE = import.meta.env.VITE_API_URL || "";

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

  return (
    <section
      className="max-w-3xl mx-auto px-4 md:px-6 py-10 section-bg-blue"
      id="status"
    >
      <Reveal>
        <div className="flex items-center gap-4 mb-6">
          <span className="text-muted text-[11px] font-mono font-medium">
            status
          </span>
          <span className="h-px flex-1 bg-gradient-to-r from-muted/20 to-transparent" />
        </div>
        <h2 className="section-header">System architecture</h2>
        <p className="font-sans text-[13px] text-fg/76 mb-8 -mt-2 max-w-md">
          Data sources and compute infrastructure behind the pipeline.
        </p>

        <TerminalWindow path="~ — caterva status --all" glow>
          <div className="mb-4 text-fg/92">
            <span className="text-signal">$</span>{" "}
            <span className="font-mono text-[12px]">
              caterva status --all
            </span>
          </div>

          {/* static reference, not a live check */}
          <div className="flex items-center gap-3 mb-5 p-3 rounded-lg border border-fg/[0.08] bg-fg/[0.01]">
            <div className="w-2.5 h-2.5 rounded-full bg-signal" />
            <span className="text-[12px] text-fg/78 font-sans">
              Data sources & infrastructure
            </span>
            {uptime !== null && (
              <>
                <span className="w-px h-3 bg-fg/[0.06]" />
                <span className="text-[11px] text-fg/66 font-mono">
                  {uptime}h uptime
                </span>
              </>
            )}
            {waitlist !== null && (
              <>
                <span className="w-px h-3 bg-fg/[0.06]" />
                <span className="text-[11px] text-fg/66 font-mono">
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
                className="flex items-start gap-3 p-2.5 rounded-lg border border-fg/[0.06] hover:border-fg/[0.12] transition-all group"
              >
                <span className="shrink-0 mt-0.5 w-1.5 h-1.5 rounded-full bg-signal" />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-0.5">
                    <span className="text-[12px] text-fg/78 font-sans font-medium">
                      {svc.name}
                    </span>
                    <span className="text-[10px] text-fg/66 font-mono">
                      {svc.endpoint}
                    </span>
                  </div>
                  <p className="text-[10px] text-fg/70">
                    {svc.description}
                  </p>
                </div>
              </motion.div>
            ))}
          </div>

          <div className="mt-4 pt-3 border-t border-fg/[0.08] text-[9px] text-fg/66 font-mono flex items-center justify-between">
            <span>static reference</span>
            <span>{SERVICES.length} services listed</span>
          </div>
        </TerminalWindow>
      </Reveal>
    </section>
  );
}
