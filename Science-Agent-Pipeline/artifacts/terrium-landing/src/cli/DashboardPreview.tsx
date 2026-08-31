import { useEffect, useRef, useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { simulateSIR } from "@/lib/simulate";
import LineChart from "./LineChart";

// This widget shows an SIR outbreak model (compartmental epidemiology),
// so its citations must be the real SIR literature -- not an enzyme
// EC number and a KEGG reaction ID, which is what stood here before and
// belongs to an entirely different domain. See
// Science-Agent-Pipeline/artifacts/api-server/src/lib/domain-literature.ts
// (SIR_LITERATURE) for the source of truth.
const citations = [
  { label: "Kermack & McKendrick", id: "1927", href: "#" },
  { label: "DOI", id: "10.1098/rspa.1927.0118", href: "#" },
  { label: "Heesterbeek et al.", id: "2015", href: "#" },
];

const replicatingParams = { beta: 0.35, gamma: 0.12 };

export default function DashboardPreview() {
  const [phase, setPhase] = useState(0);
  const params = useRef({ ...replicatingParams });
  const [selectedTab, setSelectedTab] = useState<
    "simulation" | "citations" | "parameters"
  >("simulation");

  useEffect(() => {
    const id = window.setInterval(() => {
      const p = params.current;
      p.beta += (Math.random() - 0.5) * 0.02;
      p.gamma += (Math.random() - 0.5) * 0.01;
      p.beta = Math.max(0.1, Math.min(0.9, p.beta));
      p.gamma = Math.max(0.01, Math.min(0.5, p.gamma));
      setPhase((v) => v + 1);
    }, 2500);
    return () => window.clearInterval(id);
  }, []);

  // Auto-cycle tabs every 5 seconds, reset on manual click
  const autoCycleRef = useRef<number>(0);

  const startAutoCycle = useCallback(() => {
    window.clearInterval(autoCycleRef.current);
    const tabs = ["simulation", "parameters", "citations"] as const;
    autoCycleRef.current = window.setInterval(() => {
      setSelectedTab((prev) => {
        const idx = tabs.indexOf(prev);
        return tabs[(idx + 1) % tabs.length];
      });
    }, 5000);
  }, []);

  useEffect(() => {
    startAutoCycle();
    return () => window.clearInterval(autoCycleRef.current);
  }, [startAutoCycle]);

  const result = simulateSIR({
    beta: params.current.beta,
    gamma: params.current.gamma,
    s0: 990,
    i0: 10,
    end: 100,
    points: 60,
  });

  const series = [
    { key: "S", color: "#1D8A72" },
    { key: "I", color: "#EF4444" },
    { key: "R", color: "#3B82F6" },
  ];

  const t = result.trajectory;
  const peakI = t.length > 0 ? Math.max(...t.map((d) => d.I)) : 0;
  const peakIdx = Math.max(
    0,
    t.findIndex((d) => d.I === peakI),
  );
  const finalS = t.length > 0 ? t[t.length - 1].S : 0;
  const conserved =
    t.length > 0
      ? t.every(
          (d) => Math.abs(d.S + d.I + d.R - (t[0].S + t[0].I + t[0].R)) < 1,
        )
      : false;

  return (
    <div
      className="rounded-xl border border-white/[0.06] bg-black/50 backdrop-blur-sm"
      style={{ overflow: 'clip' }}
    >
      {/* mock window controls */}
      <div className="flex items-center gap-1.5 px-3 py-2 border-b border-white/[0.04]">
        <span className="w-2 h-2 rounded-full bg-white/10" />
        <span className="w-2 h-2 rounded-full bg-white/10" />
        <span className="w-2 h-2 rounded-full bg-white/10" />
        <span className="text-[10px] text-white/20 ml-2 font-mono">
          simulation — SIR outbreak model
        </span>
      </div>

      {/* tabs */}
      <div className="flex border-b border-white/[0.04] text-[11px]">
        {(["simulation", "parameters", "citations"] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => {
              setSelectedTab(tab);
              startAutoCycle();
            }}
            className={`px-3 py-2 border-b-2 transition-colors ${
              selectedTab === tab
                ? "border-[#1D8A72] text-white/80"
                : "border-transparent text-white/25 hover:text-white/50"
            }`}
          >
            {tab}
          </button>
        ))}
      </div>

      {/* content */}
      <div className="p-3">
        <AnimatePresence mode="wait">
          {selectedTab === "simulation" && (
            <motion.div
              key="sim"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
            >
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-[#1D8A72] animate-pulse" />
                  <span className="text-[10px] text-white/30 font-mono">
                    ode-int:rk4 · t=100
                  </span>
                </div>
                <div className="flex items-center gap-1.5">
                  <span
                    className={`inline-block w-1.5 h-1.5 rounded-full ${
                      conserved ? "bg-[#1D8A72]" : "bg-[#EF4444]"
                    }`}
                  />
                  <span className="text-[9px] text-white/25 font-mono">
                    {conserved ? "conserved ✓" : "NOT conserved"}
                  </span>
                </div>
              </div>

              <div className="h-[130px]">
                <LineChart
                  data={result.trajectory}
                  series={series}
                  height={130}
                />
              </div>

              <div className="grid grid-cols-4 gap-2 mt-2">
                {[
                  {
                    label: "R₀",
                    value: (params.current.beta / params.current.gamma).toFixed(
                      2,
                    ),
                    color: "text-white/70",
                  },
                  {
                    label: "peak I",
                    value: Math.round(peakI).toLocaleString(),
                    color: "text-[#EF4444]",
                  },
                  {
                    label: "final S",
                    value: Math.round(finalS).toLocaleString(),
                    color: "text-[#1D8A72]",
                  },
                  {
                    label: "β/γ",
                    value: `${params.current.beta.toFixed(2)}/${params.current.gamma.toFixed(2)}`,
                    color: "text-white/40",
                  },
                ].map((stat) => (
                  <div key={stat.label} className="text-center">
                    <div
                      className={`text-[11px] font-mono font-medium ${stat.color}`}
                    >
                      {stat.value}
                    </div>
                    <div className="text-[8px] text-white/20 uppercase tracking-wider mt-0.5">
                      {stat.label}
                    </div>
                  </div>
                ))}
              </div>
            </motion.div>
          )}

          {selectedTab === "parameters" && (
            <motion.div
              key="params"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
              className="space-y-2 py-1"
            >
              {[
                {
                  key: "β (transmission rate)",
                  val: params.current.beta.toFixed(3),
                  range: "0.10 – 0.90",
                  color: "[#1D8A72]",
                },
                {
                  key: "γ (recovery rate)",
                  val: params.current.gamma.toFixed(3),
                  range: "0.01 – 0.50",
                  color: "[#3B82F6]",
                },
                {
                  key: "population",
                  val: "1,000",
                  range: "fixed",
                  color: "[#8B5CF6]",
                },
                {
                  key: "initial infected",
                  val: "10",
                  range: "1 – 100",
                  color: "[#EF4444]",
                },
              ].map((p) => (
                <div
                  key={p.key}
                  className="flex items-center justify-between text-[11px]"
                >
                  <span className="text-white/40">{p.key}</span>
                  <div className="flex items-center gap-3">
                    <span className="text-white/20 text-[9px]">{p.range}</span>
                    <span
                      className={`text-white/80 font-mono bg-${p.color}/10 px-2 py-0.5 rounded text-[10px]`}
                    >
                      {p.val}
                    </span>
                  </div>
                </div>
              ))}
            </motion.div>
          )}

          {selectedTab === "citations" && (
            <motion.div
              key="citations"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
              className="space-y-2 py-1"
            >
              <div className="flex flex-wrap gap-1.5 mb-2">
                {citations.map((c) => (
                  <span
                    key={c.id}
                    className="inline-flex items-center gap-1 rounded-full border border-white/[0.06] bg-white/[0.03] px-2 py-0.5 text-[9px] text-white/40"
                  >
                    <span className="text-[#1D8A72] font-medium">
                      {c.label}
                    </span>
                    {c.id}
                  </span>
                ))}
              </div>
              <div className="text-[10px] text-white/25 leading-relaxed border-t border-white/[0.04] pt-2 mt-2">
                The SIR model itself is Kermack &amp; McKendrick (1927). The
                β/γ shown here drift randomly for this preview &mdash; ask
                about a named disease and Terrium resolves real rates with
                a citation instead.
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* status bar */}
      <div className="flex items-center justify-between px-3 py-1.5 border-t border-white/[0.04] text-[9px] text-white/20 font-mono">
        <span className="flex items-center gap-1.5">
          <span className="w-1 h-1 rounded-full bg-[#1D8A72]" />
          ode simulation · rk4
        </span>
        <span>peak at t={peakIdx * 2}</span>
      </div>
    </div>
  );
}
