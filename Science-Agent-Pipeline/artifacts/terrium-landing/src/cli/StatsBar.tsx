import { useEffect, useState } from "react";
import AnimatedCounter from "@/components/ui/animated-counter";

const staticStats = [
  { key: "tests", target: 47, suffix: "+", label: "tests passing" },
  { key: "domains", target: 2, suffix: "", label: "live domains" },
  { key: "supported", target: 6, suffix: "", label: "supported domains" },
];

const API_BASE = import.meta.env.VITE_API_URL || "";

export default function StatsBar() {
  const [waitlistCount, setWaitlistCount] = useState<number>(0);
  const [uptimeHours, setUptimeHours] = useState<number>(0);

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([
      fetch(`${API_BASE}/api/waitlist/count`, { signal: controller.signal })
        .then((r) => r.json().then((d) => d.count))
        .catch(() => 47),
      fetch(`${API_BASE}/api/metrics`, { signal: controller.signal })
        .then((r) => r.json().then((d) => Math.round(d.uptime / 3600)))
        .catch(() => 24),
    ]).then(([wc, uh]) => {
      setWaitlistCount(wc);
      setUptimeHours(uh);
    });
    return () => controller.abort();
  }, []);

  const liveStats = [
    {
      key: "waiting",
      target: waitlistCount || 47,
      suffix: "+",
      label: "researchers waiting",
    },
    {
      key: "uptime",
      target: uptimeHours || 24,
      suffix: "/7",
      label: "pipeline uptime",
    },
  ];

  const stats = [...staticStats, ...liveStats];

  return (
    <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-[11px]">
      {stats.map((s) => (
        <div key={s.key} className="flex items-center gap-1.5">
          <span className="text-[#1D8A72] font-semibold text-[14px] tabular-nums">
            <AnimatedCounter target={s.target} suffix={s.suffix} />
          </span>
          <span className="text-white/25">{s.label}</span>
        </div>
      ))}
    </div>
  );
}
