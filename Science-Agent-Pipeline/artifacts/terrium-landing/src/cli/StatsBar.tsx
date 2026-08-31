import { useEffect, useState } from "react";
import AnimatedCounter from "@/components/ui/animated-counter";
import { totals } from "@/lib/testResults";

const staticStats = [
  {
    key: "tests",
    target: totals().passed,
    suffix: "",
    label: "tests passing",
  },
  { key: "domains", target: 15, suffix: "", label: "simulation domains" },
];

const API_BASE = import.meta.env.VITE_API_URL || "";

export default function StatsBar() {
  // null means "not loaded / request failed" -- distinct from a real 0,
  // and never backfilled with a plausible-looking made-up number. A
  // fallback like `waitlistCount || 47` used to run on both request
  // failure AND a genuine zero count, so either an outage or an honest
  // "nobody yet" got silently replaced with an invented "47".
  const [waitlistCount, setWaitlistCount] = useState<number | null>(null);
  const [uptimeHours, setUptimeHours] = useState<number | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    fetch(`${API_BASE}/api/waitlist/count`, { signal: controller.signal })
      .then((r) => r.json())
      .then((d) => setWaitlistCount(d.count))
      .catch(() => {});
    fetch(`${API_BASE}/api/metrics`, { signal: controller.signal })
      .then((r) => r.json())
      .then((d) => setUptimeHours(Math.round(d.uptime / 3600)))
      .catch(() => {});
    return () => controller.abort();
  }, []);

  type StatItem = {
    key: string;
    target: number;
    suffix: string;
    label: string;
  };
  const liveStats: StatItem[] = [];
  if (waitlistCount !== null) {
    liveStats.push({
      key: "waiting",
      target: waitlistCount,
      suffix: "+",
      label: "researchers waiting",
    });
  }
  if (uptimeHours !== null) {
    liveStats.push({
      key: "uptime",
      target: uptimeHours,
      suffix: "h",
      label: "pipeline uptime",
    });
  }

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
