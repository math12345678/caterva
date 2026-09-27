import { useEffect, useState } from "react";

const API_BASE = import.meta.env.VITE_API_URL || "";

export default function FooterMetrics() {
  const [wc, setWc] = useState<number | null>(null);

  useEffect(() => {
    const ctrl = new AbortController();
    fetch(`${API_BASE}/api/waitlist/count`, { signal: ctrl.signal })
      .then((r) => r.json().then((d) => setWc(d.count)))
      .catch(() => {});
    return () => ctrl.abort();
  }, []);

  if (wc === null) return null;

  return (
    <span className="text-white/15">
      {wc} researcher{wc !== 1 ? "s" : ""} on the waitlist
    </span>
  );
}
