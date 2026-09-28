import { useEffect, useRef, useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { simulateMichaelisMenten } from "@/lib/simulate";
import LineChart from "./LineChart";

// Human LDH-A reducing pyruvate, with and without the competitive
// inhibitor oxamate. Km and Ki are recorded BRENDA values (both Homo
// sapiens); [I], Vmax and [S]0 are chosen for the picture and labelled so.
// A competitive inhibitor keeps the Michaelis-Menten form with the
// apparent Km = Km(1 + [I]/Ki), so one integrator draws both curves.
const citations = [
  { label: "Km 0.03 mM", id: "BRENDA 286469" },
  { label: "Ki 0.00059 mM", id: "BRENDA 739793" },
  { label: "Michaelis & Menten", id: "1913" },
];

const KM = 0.03;
const KI = 0.00059;
const VMAX = 0.05;
const S0 = 0.2;
const END = 6;
const INHIBITOR_LEVELS = [0, 0.0005, 0.001, 0.002];

export default function DashboardPreview() {
  const [level, setLevel] = useState(0);
  const [selectedTab, setSelectedTab] = useState<
    "simulation" | "citations" | "parameters"
  >("simulation");

  // Step through inhibitor concentrations; the constants never move.
  useEffect(() => {
    const id = window.setInterval(
      () => setLevel((v) => (v + 1) % INHIBITOR_LEVELS.length),
      2500,
    );
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

  const inhibitor = INHIBITOR_LEVELS[level]!;
  const kmApp = KM * (1 + inhibitor / KI);
  const free = simulateMichaelisMenten({ km: KM, vmax: VMAX, s0: S0, end: END, points: 61 });
  const inhibited = simulateMichaelisMenten({ km: kmApp, vmax: VMAX, s0: S0, end: END, points: 61 });
  const data = free.trajectory.map((p, i) => ({
    t: p.t,
    S: p.S,
    S_inhibited: inhibited.trajectory[i]!.S,
  }));

  const series = [
    { key: "S", color: "var(--signal)" },
    { key: "S_inhibited", color: "var(--caution)" },
  ];

  const finalFree = free.trajectory[free.trajectory.length - 1]!.S;
  const finalInh = inhibited.trajectory[inhibited.trajectory.length - 1]!.S;
  // The closed-form MM solution, checked at the last point for both runs.
  const exact = Math.max(free.finalResidual, inhibited.finalResidual) < 1e-6;

  return (
    <div
      className="ink-surface rounded-lg"
      style={{ overflow: 'clip' }}
    >
      {/* mock window controls */}
      <div className="flex items-center gap-1.5 px-3 py-2 border-b border-fg/[0.08]">
        <span className="w-2 h-2 rounded-full bg-fg/10" />
        <span className="w-2 h-2 rounded-full bg-fg/10" />
        <span className="w-2 h-2 rounded-full bg-fg/10" />
        <span className="text-[10px] text-fg/66 ml-2 font-mono">
          simulation — LDH-A + oxamate
        </span>
      </div>

      {/* tabs */}
      <div className="flex border-b border-fg/[0.08] text-[11px]">
        {(["simulation", "parameters", "citations"] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => {
              setSelectedTab(tab);
              startAutoCycle();
            }}
            className={`px-3 py-2 border-b-2 transition-colors ${
              selectedTab === tab
                ? "border-signal text-fg/85"
                : "border-transparent text-fg/66 hover:text-fg/76"
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
                  <span className="w-1.5 h-1.5 rounded-full bg-signal animate-pulse" />
                  <span className="text-[10px] text-fg/70 font-mono">
                    ode-int:rk4 · t=6
                  </span>
                </div>
                <div className="flex items-center gap-1.5">
                  <span
                    className={`inline-block w-1.5 h-1.5 rounded-full ${
                      exact ? "bg-signal" : "bg-danger"
                    }`}
                  />
                  <span className="text-[9px] text-fg/66 font-mono">
                    {exact ? "matches closed form ✓" : "closed-form check FAILED"}
                  </span>
                </div>
              </div>

              <div className="h-[130px]">
                <LineChart
                  data={data}
                  series={series}
                  height={130}
                />
              </div>

              <div className="grid grid-cols-4 gap-2 mt-2">
                {[
                  { label: "[oxamate]", value: `${(inhibitor * 1000).toFixed(1)} µM`, color: "text-fg/78" },
                  { label: "apparent Km", value: `${kmApp.toFixed(3)} mM`, color: "text-caution" },
                  { label: "[S] left", value: `${finalInh.toFixed(3)} mM`, color: "text-caution" },
                  { label: "uninhibited", value: `${finalFree.toFixed(3)} mM`, color: "text-signal" },
                ].map((stat) => (
                  <div key={stat.label} className="text-center">
                    <div
                      className={`text-[11px] font-mono font-medium ${stat.color}`}
                    >
                      {stat.value}
                    </div>
                    <div className="text-[8px] text-fg/66 uppercase tracking-wider mt-0.5">
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
                { key: "Km (pyruvate)", val: "0.03 mM", range: "BRENDA 286469", color: "[#5D7F8D]" },
                { key: "Ki (oxamate)", val: "0.00059 mM", range: "BRENDA 739793", color: "[#946522]" },
                { key: "Vmax", val: `${VMAX} mM/min`, range: "chosen", color: "[#6A6E78]" },
                { key: "[S]0, [I]", val: `${S0} mM, ${(inhibitor * 1000).toFixed(1)} µM`, range: "chosen", color: "[#6A6E78]" },
              ].map((p) => (
                <div
                  key={p.key}
                  className="flex items-center justify-between text-[11px]"
                >
                  <span className="text-fg/70">{p.key}</span>
                  <div className="flex items-center gap-3">
                    <span className="text-fg/66 text-[9px]">{p.range}</span>
                    <span
                      className={`text-fg/85 font-mono bg-${p.color}/10 px-2 py-0.5 rounded text-[10px]`}
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
                    className="inline-flex items-center gap-1 rounded-full border border-fg/[0.12] bg-fg/[0.03] px-2 py-0.5 text-[9px] text-fg/70"
                  >
                    <span className="text-signal font-medium">
                      {c.label}
                    </span>
                    {c.id}
                  </span>
                ))}
              </div>
              <div className="text-[10px] text-fg/66 leading-relaxed border-t border-fg/[0.08] pt-2 mt-2">
                Km and Ki are recorded measurements for human LDH-A, each
                with its BRENDA reference. Vmax and the concentrations are
                chosen for this preview and labelled so; Caterva never
                presents a chosen number as a measured one.
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* status bar */}
      <div className="flex items-center justify-between px-3 py-1.5 border-t border-fg/[0.08] text-[9px] text-fg/66 font-mono">
        <span className="flex items-center gap-1.5">
          <span className="w-1 h-1 rounded-full bg-signal" />
          ode simulation · rk4
        </span>
        <span>competitive · Vmax unchanged</span>
      </div>
    </div>
  );
}
