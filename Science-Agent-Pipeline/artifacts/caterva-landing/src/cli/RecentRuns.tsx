import { useEffect, useMemo, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { toast } from "sonner";
import { listSimulationJobs } from "@workspace/api-client-react";
import type {
  SimulationJob,
  SimulationResponse,
} from "@workspace/api-client-react";
import { Skeleton } from "@/components/ui/skeleton";
import ExportButtons from "@/components/ui/export-buttons";
import TerminalWindow from "./TerminalWindow";
import LineChart from "./LineChart";
import ComparePanel from "./ComparePanel";

const STATUS_COLORS: Record<string, string> = {
  pending: "text-blue-400/80",
  resolving: "text-yellow-400/80",
  validating: "text-orange-400/80",
  running: "text-signal",
  completed: "text-signal",
  failed: "text-red-400/80",
  cancelled: "text-fg/70",
};

const STATUS_BG: Record<string, string> = {
  pending: "bg-blue-400/[0.06]",
  resolving: "bg-yellow-400/[0.06]",
  validating: "bg-orange-400/[0.06]",
  running: "bg-signal/[0.06]",
  completed: "bg-signal/[0.06]",
  failed: "bg-red-400/[0.06]",
  cancelled: "bg-fg/[0.03]",
};

function StatusBadge({ status }: { status: string }) {
  return (
    <span
      className={`shrink-0 inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 text-[10px] uppercase tracking-wide transition-all ${STATUS_COLORS[status] ?? "text-fg/76"} ${STATUS_BG[status] ?? "bg-fg/[0.03]"}`}
    >
      {status === "running" && (
        <span className="inline-block w-1.5 h-1.5 rounded-full bg-signal animate-pulse" />
      )}
      {status}
    </span>
  );
}

function formatTime(iso: string) {
  try {
    return new Date(iso).toLocaleTimeString();
  } catch {
    return iso;
  }
}

function seriesForResponse(response: SimulationResponse) {
  const colorMap: Record<string, string> = {
    S: "#5D7F8D",
    P: "#946522",
    I: "#A63D35",
    R: "#6A6E78",
    E: "#6A6E78",
  };
  if (!response.trajectory || response.trajectory.length === 0) return [];
  const keys = Object.keys(response.trajectory[0]!).filter((k) => k !== "t");
  return keys.map((key) => ({ key, color: colorMap[key] ?? "#FDF8EE" }));
}

interface RecentRunsProps {
  pollInterval?: number;
  onReRun?: (query: string) => void;
  pageSize?: number;
}

const TERMINAL = new Set(["completed", "failed", "cancelled"]);
const PAGE_SIZE_DEFAULT = 8;
const CACHE_KEY = "caterva:recent-runs";

function loadCachedRuns(): SimulationJob[] {
  try {
    const raw = localStorage.getItem(CACHE_KEY);
    if (!raw) return [];
    return JSON.parse(raw) as SimulationJob[];
  } catch {
    return [];
  }
}

function saveCachedRuns(runs: SimulationJob[]): void {
  try {
    localStorage.setItem(CACHE_KEY, JSON.stringify(runs));
  } catch {}
}

const BOOKMARK_KEY = "caterva:bookmarked-runs";

function loadBookmarks(): Set<string> {
  try {
    const raw = localStorage.getItem(BOOKMARK_KEY);
    if (!raw) return new Set();
    return new Set(JSON.parse(raw) as string[]);
  } catch {
    return new Set();
  }
}

function saveBookmarks(ids: Set<string>): void {
  try {
    localStorage.setItem(BOOKMARK_KEY, JSON.stringify([...ids]));
  } catch {}
}

function SkeletonRow() {
  return (
    <div className="rounded-lg border border-fg/[0.08] p-3">
      <div className="flex items-center justify-between gap-3 mb-2">
        <Skeleton className="h-3 w-44 bg-fg/[0.04]" />
        <Skeleton className="h-4 w-16 rounded-md bg-fg/[0.04]" />
      </div>
      <div className="flex items-center gap-3">
        <Skeleton className="h-2.5 w-20 bg-fg/[0.03]" />
        <Skeleton className="h-2.5 w-16 bg-fg/[0.03]" />
      </div>
    </div>
  );
}

export default function RecentRuns({
  pollInterval = 5000,
  onReRun,
  pageSize = PAGE_SIZE_DEFAULT,
}: RecentRunsProps) {
  const [runs, setRuns] = useState<SimulationJob[]>(loadCachedRuns);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [cancelling, setCancelling] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [displayCount, setDisplayCount] = useState(pageSize);
  const [search, setSearch] = useState("");
  const [copiedParams, setCopiedParams] = useState<Set<string>>(new Set());
  const [compare, setCompare] = useState<Set<string>>(new Set());
  const [highlighted, setHighlighted] = useState<Set<string>>(new Set());
  const [newlyCompleted, setNewlyCompleted] = useState<Set<string>>(
    new Set(),
  );
  const [bookmarked, setBookmarked] = useState<Set<string>>(loadBookmarks);

  const toggleBookmark = (jobId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setBookmarked((prev) => {
      const next = new Set(prev);
      if (next.has(jobId)) next.delete(jobId);
      else next.add(jobId);
      saveBookmarks(next);
      return next;
    });
  };
  const pollRef = useRef<number | undefined>(undefined);
  const prevStatusRef = useRef<Map<string, string>>(new Map());
  const knownIdsRef = useRef<Set<string>>(new Set());

  const toggleCompare = (jobId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setCompare((prev) => {
      const next = new Set(prev);
      if (next.has(jobId)) next.delete(jobId);
      else if (next.size < 2) next.add(jobId);
      return next;
    });
  };

  const filteredRuns = useMemo(
    () =>
      search
        ? runs.filter((r) =>
            r.query.toLowerCase().includes(search.toLowerCase()),
          )
        : runs,
    [runs, search],
  );

  useEffect(() => {
    let cancelled = false;

    const fetchRuns = async () => {
      try {
        const data = await listSimulationJobs();
        if (!cancelled) {
          const newHighlighted = new Set<string>();
          const newlyCompletedIds = new Set<string>();
          for (const job of data) {
            const prev = prevStatusRef.current.get(job.jobId);
            const isNew = !knownIdsRef.current.has(job.jobId);
            if (prev && prev !== job.status) {
              if (job.status === "completed") {
                toast.success("Simulation completed", {
                  description: job.query,
                  duration: 4000,
                });
                newHighlighted.add(job.jobId);
                setTimeout(
                  () =>
                    setHighlighted((h) => {
                      const n = new Set(h);
                      n.delete(job.jobId);
                      return n;
                    }),
                  4000,
                );
              } else if (job.status === "failed") {
                toast.error("Simulation failed", {
                  description: job.query,
                  duration: 4000,
                });
              }
            }
            if (isNew && job.status === "completed") {
              newlyCompletedIds.add(job.jobId);
              setTimeout(
                () =>
                  setNewlyCompleted((n) => {
                    const next = new Set(n);
                    next.delete(job.jobId);
                    return next;
                  }),
                4000,
              );
            }
            prevStatusRef.current.set(job.jobId, job.status);
            knownIdsRef.current.add(job.jobId);
          }
          if (newHighlighted.size > 0) {
            setHighlighted((h) => new Set([...h, ...newHighlighted]));
          }
          if (newlyCompletedIds.size > 0) {
            setNewlyCompleted((n) => new Set([...n, ...newlyCompletedIds]));
          }
          setRuns(data);
          saveCachedRuns(data);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to fetch runs");
          setRuns((prev) => (prev.length > 0 ? prev : loadCachedRuns()));
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    fetchRuns();
    pollRef.current = window.setInterval(fetchRuns, pollInterval);

    return () => {
      cancelled = true;
      window.clearInterval(pollRef.current);
    };
  }, []);

  const sortedRuns = useMemo(
    () =>
      [...filteredRuns].sort((a, b) => {
        const aBm = bookmarked.has(a.jobId) ? 0 : 1;
        const bBm = bookmarked.has(b.jobId) ? 0 : 1;
        return aBm - bBm;
      }),
    [filteredRuns, bookmarked],
  );
  const displayedRuns = sortedRuns.slice(0, displayCount);
  const hasMore = displayCount < sortedRuns.length;

  const toggleExpanded = (jobId: string) => {
    setExpanded((current) => (current === jobId ? null : jobId));
  };

  const handleCancel = async (jobId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setCancelling((prev) => new Set(prev).add(jobId));
    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), 10000);
    try {
      const response = await fetch(`/api/simulate/${jobId}/cancel`, {
        method: "POST",
        signal: controller.signal,
      });
      if (response.ok) {
        const updated = await response.json();
        setRuns((prev) => prev.map((r) => (r.jobId === jobId ? updated : r)));
      } else {
        toast.error("Failed to cancel run", {
          description: `Server responded with ${response.status}`,
        });
      }
    } catch (err) {
      toast.error("Failed to cancel run", {
        description:
          err instanceof Error ? err.message : "Request could not complete",
      });
    } finally {
      window.clearTimeout(timeoutId);
      setCancelling((prev) => {
        const next = new Set(prev);
        next.delete(jobId);
        return next;
      });
    }
  };

  const handleRerun = (query: string, e: React.MouseEvent) => {
    e.stopPropagation();
    onReRun?.(query);
  };

  const handleExport = (jobId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    const anchor = document.createElement("a");
    anchor.href = `/api/simulate/${jobId}/export`;
    anchor.download = `simulation-${jobId.slice(0, 8)}.csv`;
    anchor.click();
  };

  return (
    <TerminalWindow path="~/caterva — recent runs" glow>
      <div className="mb-4 text-[11px] font-mono text-fg/60">
        # runs from this browser
      </div>
      <p className="text-fg/70 text-[12px] mb-5 leading-relaxed">
        Latest pipeline runs. Click a row to inspect, select two to compare.
        Refreshes every 5 seconds.
      </p>

      {error && (
        <div className="text-red-400/70 text-[12px] mb-4 border border-red-500/10 rounded-lg bg-red-500/[0.03] p-3">
          {error}
        </div>
      )}

      <div className="flex gap-2 mb-3">
        <input
          type="text"
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setDisplayCount(pageSize);
          }}
          placeholder="filter runs..."
          className="flex-1 rounded-lg border border-fg/[0.12] bg-fg/[0.02] px-3 py-2 text-fg/80 text-[11px] outline-none transition-all duration-300 focus:border-signal/30 focus:bg-signal/[0.02] placeholder:text-fg/66"
        />
        {compare.size > 0 && (
          <button
            onClick={() => setCompare(new Set())}
            className="px-2.5 py-1.5 rounded-lg border border-fg/[0.12] text-[10px] text-fg/70 hover:text-fg/80 transition-colors"
          >
            clear ({compare.size})
          </button>
        )}
      </div>

      {compare.size === 2 && (
        <ComparePanel
          runs={runs.filter((r) => compare.has(r.jobId))}
          onClear={() => setCompare(new Set())}
        />
      )}

      <div className="space-y-2 max-h-96 overflow-y-auto pr-1">
        <AnimatePresence initial={false}>
          {loading && runs.length === 0 && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="space-y-2"
            >
              <SkeletonRow />
              <SkeletonRow />
              <SkeletonRow />
            </motion.div>
          )}

          {!loading && filteredRuns.length === 0 && !error && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="text-fg/66 text-[12px] italic"
            >
              {search
                ? `No runs matching "${search}".`
                : "No runs yet. Submit a query above to get started."}
            </motion.div>
          )}

          {displayedRuns.map((run) => (
            <motion.div
              key={run.jobId}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              className={`rounded-lg border overflow-hidden transition-all duration-500 ${
                highlighted.has(run.jobId)
                  ? "border-signal/40"
                  : "border-fg/[0.08] hover:border-fg/[0.16]"
              }`}
            >
              <div className="flex items-center justify-between">
                <button
                  onClick={() => toggleExpanded(run.jobId)}
                  className="flex-1 text-left hover:bg-fg/[0.015] transition-colors duration-150 p-3"
                >
                  <div className="flex items-center justify-between gap-3 mb-1">
                    <span className="flex items-center gap-2 min-w-0">
                      <span
                        className="text-fg/80 truncate text-[12px]"
                        title={run.query}
                      >
                        {run.query}
                      </span>
                      {newlyCompleted.has(run.jobId) &&
                        run.status === "completed" && (
                          <span className="shrink-0 inline-flex items-center rounded bg-signal/15 px-1.5 py-0.5 text-[8px] text-signal uppercase tracking-wide animate-pulse-soft">
                            new
                          </span>
                        )}
                    </span>
                    <StatusBadge status={run.status} />
                  </div>
                  <div className="flex items-center gap-3 text-[10px] text-fg/66">
                    <span>progress: {run.progress}%</span>
                    <span>&middot;</span>
                    <span>{formatTime(run.updatedAt)}</span>
                  </div>
                </button>
                <div className="flex gap-1 pr-3">
                  {run.status === "completed" && (
                    <>
                      <button
                        onClick={(e) => toggleBookmark(run.jobId, e)}
                        className={`px-2 py-1 rounded-md border text-[9px] transition-all duration-200 ${
                          bookmarked.has(run.jobId)
                            ? "border-caution/30 text-caution bg-caution/[0.06]"
                            : "border-fg/[0.12] text-fg/66 hover:text-fg/76 hover:bg-fg/[0.03]"
                        }`}
                        title={
                          bookmarked.has(run.jobId)
                            ? "Remove bookmark"
                            : "Bookmark this run"
                        }
                      >
                        {bookmarked.has(run.jobId) ? "\u2605" : "\u2606"}
                      </button>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          toggleCompare(run.jobId, e);
                        }}
                        className={`px-2 py-1 rounded-md border text-[9px] transition-all duration-200 ${
                          compare.has(run.jobId)
                            ? "border-caution/30 text-caution/60 bg-caution/[0.06]"
                            : "border-fg/[0.12] text-fg/66 hover:text-fg/76 hover:bg-fg/[0.03]"
                        }`}
                        title="Select for comparison"
                      >
                        {compare.has(run.jobId) ? "selected" : "compare"}
                      </button>
                      <button
                        onClick={(e) => handleRerun(run.query, e)}
                        className="px-2 py-1 rounded-md border border-signal/15 text-signal/50 text-[9px] hover:bg-signal/[0.06] hover:text-signal transition-all duration-200"
                        title="Re-run this query"
                      >
                        re-run
                      </button>
                      <button
                        onClick={(e) => handleExport(run.jobId, e)}
                        className="px-2 py-1 rounded-md border border-fg/[0.12] text-fg/70 text-[9px] hover:bg-fg/[0.03] hover:text-fg/76 transition-all duration-200"
                        title="Download CSV"
                      >
                        csv
                      </button>
                    </>
                  )}
                  {!TERMINAL.has(run.status) && (
                    <button
                      onClick={(e) => handleCancel(run.jobId, e)}
                      disabled={cancelling.has(run.jobId)}
                      className="px-2 py-1 rounded-md border border-red-500/15 text-red-400/40 text-[9px] hover:bg-red-500/[0.06] hover:text-red-400/70 transition-all duration-200 disabled:opacity-30"
                    >
                      {cancelling.has(run.jobId) ? "..." : "cancel"}
                    </button>
                  )}
                </div>
              </div>

              <AnimatePresence>
                {expanded === run.jobId && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: "auto", opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    className="border-t border-fg/[0.06] bg-fg/[0.01]"
                  >
                    <div className="p-3 space-y-4">
                      {run.error && (
                        <div className="text-red-400/70 text-[12px] border border-red-500/10 rounded-lg bg-red-500/[0.03] p-3">
                          {run.error.message}
                        </div>
                      )}

                      {run.result && (
                        <>
                          <div className="flex items-center gap-3 text-[11px] text-fg/70">
                            <span className="inline-flex items-center gap-1 rounded bg-signal/10 px-2 py-0.5 text-[10px] text-signal uppercase tracking-wide">
                              {run.result.domain}
                            </span>
                            <span>runId: {run.result.runId}</span>
                            <span className="ml-auto">
                              <ExportButtons
                                trajectory={
                                  (run.result.trajectory ?? []) as Record<
                                    string,
                                    number
                                  >[]
                                }
                                result={
                                  run.result as unknown as Record<
                                    string,
                                    unknown
                                  >
                                }
                                filenamePrefix={run.result.domain}
                                runId={run.result.runId}
                              />
                            </span>
                          </div>

                          {run.result.trajectory &&
                            run.result.trajectory.length > 0 && (
                              <div className="rounded-lg border border-fg/[0.08] bg-fg/[0.01] p-2">
                                <LineChart
                                  data={
                                    (run.result.trajectory ??
                                      []) as unknown as import("@/lib/simulate").Point[]
                                  }
                                  series={seriesForResponse(run.result)}
                                />
                              </div>
                            )}

                          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                            <div className="rounded-lg border border-fg/[0.08] p-3">
                              <div className="flex items-center justify-between mb-2">
                                <span className="text-fg/66 text-[10px] uppercase tracking-wide">
                                  parameters
                                </span>
                                <button
                                  onClick={() => {
                                    const p = run.result!.parameters;
                                    navigator.clipboard
                                      .writeText(JSON.stringify(p, null, 2))
                                      .then(() => {
                                        setCopiedParams((prev) =>
                                          new Set(prev).add(run.jobId),
                                        );
                                        setTimeout(
                                          () =>
                                            setCopiedParams((prev) => {
                                              const next = new Set(prev);
                                              next.delete(run.jobId);
                                              return next;
                                            }),
                                          2000,
                                        );
                                      })
                                      .catch(() => {});
                                  }}
                                  className="flex items-center gap-1 rounded border border-fg/[0.12] px-1.5 py-0.5 text-[9px] text-fg/66 hover:text-fg/76 hover:border-fg/[0.24] transition-all duration-200"
                                >
                                  {copiedParams.has(run.jobId)
                                    ? "copied"
                                    : "copy"}
                                </button>
                              </div>
                              <pre className="text-fg/80 overflow-x-auto text-[11px]">
                                {JSON.stringify(run.result.parameters, null, 2)}
                              </pre>
                            </div>
                            <div className="rounded-lg border border-fg/[0.08] p-3">
                              <div className="text-fg/66 text-[10px] uppercase tracking-wide mb-2">
                                provenance
                              </div>
                              <p className="text-fg/80 mb-2 text-[11px] leading-relaxed">
                                {run.result.provenance.reasoning}
                              </p>
                              {run.result.provenance.flags &&
                                run.result.provenance.flags.length > 0 && (
                                  <div className="flex flex-wrap gap-1 mb-2">
                                    {run.result.provenance.flags.map(
                                      (flag, i) => (
                                        <span
                                          key={i}
                                          className="text-[9px] text-yellow-500/50 bg-yellow-500/[0.04] rounded px-1.5 py-0.5"
                                        >
                                          {flag}
                                        </span>
                                      ),
                                    )}
                                  </div>
                                )}
                              {run.result.provenance.modelCitations &&
                                run.result.provenance.modelCitations.length >
                                  0 && (
                                  <div className="border-t border-fg/[0.08] pt-2 mt-2 space-y-0.5">
                                    {run.result.provenance.modelCitations.map(
                                      (citation, i) => (
                                        <div
                                          key={i}
                                          className="text-[10px] text-fg/66 truncate"
                                        >
                                          {citation}
                                        </div>
                                      ),
                                    )}
                                  </div>
                                )}
                            </div>
                          </div>
                        </>
                      )}

                      {!run.result && !run.error && (
                        <div className="text-fg/66 text-[12px] italic">
                          Job is still running. Expand again once it completes.
                        </div>
                      )}
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </motion.div>
          ))}

          {!loading && filteredRuns.length > 0 && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="flex items-center justify-center gap-2 pt-1"
            >
              {hasMore ? (
                <button
                  onClick={() => setDisplayCount((p) => p + pageSize)}
                  className="px-3 py-1.5 rounded-md border border-fg/[0.12] text-[10px] text-fg/70 hover:text-signal hover:border-signal/20 transition-all duration-200 bg-fg/[0.02] hover:bg-signal/[0.03]"
                >
                  show more ({filteredRuns.length - displayCount} remaining)
                </button>
              ) : displayCount > pageSize ? (
                <button
                  onClick={() => setDisplayCount(pageSize)}
                  className="px-3 py-1.5 rounded-md border border-fg/[0.12] text-[10px] text-fg/70 hover:text-fg/76 transition-all duration-200 bg-fg/[0.02] hover:bg-fg/[0.03]"
                >
                  show less
                </button>
              ) : null}
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </TerminalWindow>
  );
}
