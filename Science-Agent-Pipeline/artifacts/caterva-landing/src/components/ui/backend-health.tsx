import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";

type Status = "ok" | "error" | "loading";

interface Subsystem {
  ok: boolean;
  label: string;
  detail: string;
}

interface PipelineStatus {
  status: string;
  uptime: number;
  subsystems: Subsystem[];
  queue: { total: number; byStatus: Record<string, number> };
}

function formatUptime(s: number): string {
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

export default function BackendHealth() {
  const [status, setStatus] = useState<Status>("loading");
  const [detail, setDetail] = useState<PipelineStatus | null>(null);
  const [detailError, setDetailError] = useState(false);
  const [showPanel, setShowPanel] = useState(false);
  const toggleRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    let cancelled = false;
    let timer: number;

    const check = async () => {
      try {
        const res = await fetch("/api/healthz");
        if (!cancelled) setStatus(res.ok ? "ok" : "error");
      } catch {
        if (!cancelled) setStatus("error");
      }
    };

    const fetchDetail = async () => {
      try {
        const res = await fetch("/api/pipeline/status");
        if (res.ok) {
          const data: PipelineStatus = await res.json();
          if (!cancelled) {
            setDetail(data);
            setDetailError(false);
          }
        } else if (!cancelled) {
          setDetailError(true);
        }
      } catch {
        if (!cancelled) setDetailError(true);
      }
    };

    check();
    fetchDetail();
    timer = window.setInterval(() => {
      check();
      fetchDetail();
    }, 15000);

    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    if (!showPanel) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setShowPanel(false);
        toggleRef.current?.focus();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [showPanel]);

  return (
    <>
      <button
        ref={toggleRef}
        onClick={() => setShowPanel((p) => !p)}
        className="flex items-center gap-1.5 text-[10px] text-fg/70 hover:text-fg/80 transition-colors"
        title={
          status === "ok"
            ? "Backend connected — click for details"
            : status === "error"
              ? "Backend unreachable"
              : "Checking connection"
        }
      >
        <span className="relative flex size-2">
          {status === "ok" && (
            <motion.span
              className="absolute inline-flex h-full w-full rounded-full bg-signal"
              animate={{ opacity: [0.6, 0.2, 0.6] }}
              transition={{ duration: 2, repeat: Infinity, ease: "easeInOut" }}
            />
          )}
          <span
            className={`relative inline-flex size-2 rounded-full ${
              status === "ok"
                ? "bg-signal"
                : status === "error"
                  ? "bg-red-400"
                  : "bg-fg/20"
            }`}
          />
        </span>
        <span className="hidden sm:inline">
          {status === "ok"
            ? "connected"
            : status === "error"
              ? "disconnected"
              : "connecting"}
        </span>
      </button>

      <AnimatePresence>
        {showPanel && (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="fixed inset-0 z-40"
              onClick={() => {
                setShowPanel(false);
                toggleRef.current?.focus();
              }}
            />
            <motion.div
              initial={{ opacity: 0, y: 4, scale: 0.96 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 4, scale: 0.96 }}
              transition={{ duration: 0.15, ease: "easeOut" }}
              role="dialog"
              aria-modal="true"
              aria-label="Pipeline Status"
              className="fixed top-14 left-4 z-50 w-72 rounded-xl border border-fg/[0.16] bg-surface shadow-2xl p-4"
            >
              <div className="flex items-center justify-between mb-3">
                <span className="text-fg/80 text-[11px] font-medium">
                  Pipeline Status
                </span>
                {detail && (
                  <span
                    className={`text-[9px] uppercase tracking-wide ${detail.status === "healthy" ? "text-signal" : "text-yellow-500"}`}
                  >
                    {detail.status}
                  </span>
                )}
              </div>

              {detail ? (
                <>
                  <div className="space-y-1.5 mb-3 text-[10px]">
                    {detail.subsystems.map((s) => (
                      <div key={s.label} className="flex items-center gap-2">
                        <span
                          className={`shrink-0 w-1.5 h-1.5 rounded-full ${s.ok ? "bg-signal" : "bg-red-400"}`}
                        />
                        <span className="text-fg/70 truncate">{s.label}</span>
                      </div>
                    ))}
                  </div>

                  <div className="border-t border-fg/[0.08] pt-2 text-[10px] space-y-1">
                    <div className="flex justify-between">
                      <span className="text-fg/66">jobs in queue</span>
                      <span className="text-fg/76">{detail.queue.total}</span>
                    </div>
                    {Object.entries(detail.queue.byStatus).map(([s, count]) => (
                      <div key={s} className="flex justify-between">
                        <span className="text-fg/66 pl-3">{s}</span>
                        <span className="text-fg/76">{count}</span>
                      </div>
                    ))}
                    <div className="flex justify-between pt-1 border-t border-fg/[0.06]">
                      <span className="text-fg/66">uptime</span>
                      <span className="text-fg/76">
                        {formatUptime(detail.uptime)}
                      </span>
                    </div>
                  </div>
                </>
              ) : (
                <div className="text-[10px] text-fg/70">
                  {detailError
                    ? "Pipeline details unavailable."
                    : "Loading pipeline details…"}
                </div>
              )}
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </>
  );
}
