import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  runSimulation,
  type SimulationJob,
  type SimulationResponse,
} from "@workspace/api-client-react";
import { Spinner } from "@/components/ui/spinner";
import ExportButtons from "@/components/ui/export-buttons";
import ShareSimulation from "./ShareSimulation";
import TerminalWindow from "./TerminalWindow";
import LineChart from "./LineChart";

type PipelineStage =
  | "idle"
  | "pending"
  | "resolving"
  | "validating"
  | "running"
  | "completed"
  | "failed";

const STAGE_LABEL: Record<PipelineStage, string> = {
  idle: "Ready",
  pending: "Queued",
  resolving: "Resolving query",
  validating: "Validating parameters",
  running: "Running Terium engine",
  completed: "Done",
  failed: "Failed",
};

const STAGE_COLORS: Record<PipelineStage, string> = {
  idle: "text-white/40",
  pending: "text-blue-400",
  resolving: "text-yellow-400",
  validating: "text-orange-400",
  running: "text-[#1D8A72]",
  completed: "text-[#1D8A72]",
  failed: "text-red-400",
};

const DOMAIN_PARAMS: Record<
  string,
  { key: string; label: string; default: number }[]
> = {
  mm: [
    { key: "km", label: "Km (mM)", default: 2 },
    { key: "vmax", label: "Vmax", default: 5 },
    { key: "s0", label: "S\u2080 (mM)", default: 10 },
    { key: "end", label: "Time (units)", default: 10 },
    { key: "points", label: "Points", default: 51 },
  ],
  sir: [
    { key: "beta", label: "\u03b2 (transmission)", default: 0.3 },
    { key: "gamma", label: "\u03b3 (recovery)", default: 0.1 },
    { key: "s0", label: "S\u2080", default: 990 },
    { key: "i0", label: "I\u2080", default: 10 },
    { key: "end", label: "Days", default: 100 },
    { key: "points", label: "Points", default: 101 },
  ],
  seir: [
    { key: "beta", label: "\u03b2 (transmission)", default: 0.3 },
    { key: "sigma", label: "\u03c3 (incubation)", default: 0.2 },
    { key: "gamma", label: "\u03b3 (recovery)", default: 0.1 },
    { key: "s0", label: "S\u2080", default: 990 },
    { key: "e0", label: "E\u2080", default: 10 },
    { key: "i0", label: "I\u2080", default: 0 },
    { key: "end", label: "Days", default: 100 },
    { key: "points", label: "Points", default: 101 },
  ],
};

const EXAMPLE_QUERIES = [
  "simulate lactate dehydrogenase with pyruvate",
  "model an outbreak with beta 0.4 and gamma 0.1",
  "enzyme kinetics km 5 vmax 10",
];

const DOMAIN_CONSTRAINTS: Record<
  string,
  Record<string, { min?: number; max?: number; integer?: boolean }>
> = {
  mm: {
    km: { min: 0.001, max: 1e4 },
    vmax: { min: 0.001, max: 1e6 },
    s0: { min: 0.001, max: 1e6 },
    end: { min: 0.1, max: 1e5 },
    points: { min: 3, max: 10000, integer: true },
  },
  sir: {
    beta: { min: 0, max: 1 },
    gamma: { min: 0, max: 1 },
    s0: { min: 0, max: 1e9 },
    i0: { min: 0, max: 1e9 },
    end: { min: 0.1, max: 1e5 },
    points: { min: 3, max: 10000, integer: true },
  },
  seir: {
    beta: { min: 0, max: 1 },
    sigma: { min: 0, max: 1 },
    gamma: { min: 0, max: 1 },
    s0: { min: 0, max: 1e9 },
    e0: { min: 0, max: 1e9 },
    i0: { min: 0, max: 1e9 },
    end: { min: 0.1, max: 1e5 },
    points: { min: 3, max: 10000, integer: true },
  },
};

function seriesForResponse(response: SimulationResponse) {
  const colorMap: Record<string, string> = {
    S: "#1D8A72",
    P: "#F59E0B",
    I: "#EF4444",
    R: "#3B82F6",
    E: "#8B5CF6",
  };
  if (response.trajectory.length === 0) return [];
  const keys = Object.keys(response.trajectory[0]!).filter((k) => k !== "t");
  return keys.map((key) => ({ key, color: colorMap[key] ?? "#ffffff" }));
}

interface EnzymeInfo {
  ecNumber: string;
  name: string;
  substrates: string[];
  description: string;
  organism: string;
}

interface AgentSimulatorProps {
  rerunQuery?: string;
  onRerunConsumed?: () => void;
}

export default function AgentSimulator({
  rerunQuery,
  onRerunConsumed,
}: AgentSimulatorProps) {
  const [query, setQuery] = useState("");
  const [stage, setStage] = useState<PipelineStage>("idle");
  const [progress, setProgress] = useState(0);
  const [result, setResult] = useState<SimulationResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  const [resolvedDomain, setResolvedDomain] = useState<string | null>(null);
  const [resolvedParams, setResolvedParams] = useState<Record<string, number>>(
    {},
  );
  const [editableParams, setEditableParams] = useState<Record<string, string>>(
    {},
  );
  const [reasoning, setReasoning] = useState("");
  const [modelCitations, setModelCitations] = useState<string[]>([]);
  const [flags, setFlags] = useState<string[]>([]);
  const [enzymes, setEnzymes] = useState<EnzymeInfo[]>([]);
  const [enzymesLoading, setEnzymesLoading] = useState(true);
  const [enzymesError, setEnzymesError] = useState(false);
  const [showEnzymes, setShowEnzymes] = useState(false);
  const [paramErrors, setParamErrors] = useState<Record<string, string>>({});
  const [paramsCopied, setParamsCopied] = useState(false);

  const resolveBtnRef = useRef<HTMLButtonElement>(null);

  const validateParams = (
    domain: string,
    params: Record<string, string>,
  ): Record<string, string> => {
    const errors: Record<string, string> = {};
    const constraints = DOMAIN_CONSTRAINTS[domain];
    if (!constraints) return errors;
    for (const [key, value] of Object.entries(params)) {
      const c = constraints[key];
      if (!c) continue;
      const num = Number(value);
      if (value.trim() === "" || Number.isNaN(num)) {
        errors[key] = "Required";
      } else if (c.min !== undefined && num < c.min) {
        errors[key] = `Min ${c.min}`;
      } else if (c.max !== undefined && num > c.max) {
        errors[key] = `Max ${c.max}`;
      } else if (c.integer && !Number.isInteger(num)) {
        errors[key] = "Must be integer";
      }
    }
    return errors;
  };

  useEffect(() => {
    setEnzymesLoading(true);
    fetch("/api/enzymes")
      .then((r) => {
        if (!r.ok) throw new Error("Failed to load enzymes");
        return r.json();
      })
      .then((data) => {
        setEnzymes(data);
        setEnzymesError(false);
      })
      .catch(() => {
        setEnzymesError(true);
      })
      .finally(() => setEnzymesLoading(false));
  }, []);

  useEffect(() => {
    if (!rerunQuery) return;
    setQuery(rerunQuery);
    onRerunConsumed?.();
    const timer = setTimeout(() => resolveBtnRef.current?.click(), 100);
    return () => clearTimeout(timer);
  }, [rerunQuery]);

  useEffect(() => {
    return () => {
      abortControllerRef.current?.abort();
    };
  }, []);

  const loadJob = async (jobId: string, signal?: AbortSignal) => {
    const response = await fetch(`/api/simulate/${jobId}`, { signal });
    if (!response.ok) {
      throw new Error(`Failed to fetch job status: ${response.status}`);
    }
    return (await response.json()) as SimulationJob;
  };

  const handleResolve = async () => {
    if (!query.trim()) return;
    setError(null);
    setResult(null);
    setResolvedDomain(null);
    setResolvedParams({});
    setStage("resolving");

    try {
      const response = await fetch("/api/resolve", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: query.trim() }),
      });
      if (!response.ok) {
        const err = await response
          .json()
          .catch(() => ({ message: "Resolve failed" }));

        // A missing experimental condition (s0, end, points -- values
        // nobody can look up, because they describe the experiment, not
        // the enzyme) is not a failure to explain in prose and stop. The
        // server already sends back exactly what a labeled input form
        // needs: which domain, which keys are missing, and everything
        // else it already resolved. This used to be thrown as a plain
        // Error, landing on the SAME "Failed" screen as a genuine
        // pipeline error, telling the user to type CLI flags
        // (`vmax=<value> s0=<value>...`) into the same free-text box --
        // in a product whose own pitch is "no syntax to learn". The
        // labeled-field form a few lines below already existed for the
        // success path; it was simply unreachable from here.
        if (
          err.error === "RequiredParametersMissingError" &&
          typeof err.domain === "string" &&
          Array.isArray(err.missingKeys)
        ) {
          const domain = err.domain as string;
          const resolved: Record<string, number | number[]> =
            err.resolvedParameters ?? {};
          const fields = DOMAIN_PARAMS[domain] ?? [];

          // Blank for anything truly missing -- nothing invented, not
          // even the field's own documentation-example default. Filled
          // in for anything the resolver already established (a
          // literature Km, or a value the user already typed), so
          // re-submitting does not mean re-typing what already worked.
          const seeded = Object.fromEntries(
            fields.map((f) => [
              f.key,
              f.key in resolved ? String(resolved[f.key]) : "",
            ]),
          );
          // A resolved value outside the known field list is still
          // real and must not be dropped just because this UI has no
          // labeled slot for it -- computed and not delivered is the
          // one failure mode this project treats as worse than any
          // error message.
          for (const [key, value] of Object.entries(resolved)) {
            if (!(key in seeded)) seeded[key] = String(value);
          }

          setResolvedDomain(domain);
          setEditableParams(seeded);
          setParamErrors(validateParams(domain, seeded));
          setReasoning("");
          setModelCitations([]);
          setFlags([]);
          setError(
            `${err.missingKeys.join(", ")} ${
              err.missingKeys.length > 1 ? "are" : "is"
            } yours to choose, not something the literature reports — fill ${
              err.missingKeys.length > 1 ? "them" : "it"
            } in below.`,
          );
          setStage("idle");
          return;
        }

        throw new Error(err.message || "Resolve failed");
      }
      const data = await response.json();
      setResolvedDomain(data.domain);
      setResolvedParams(data.parameters);
      setReasoning(data.provenance.reasoning);
      setModelCitations(data.provenance.modelCitations || []);
      setFlags(data.provenance.flags || []);
      setEditableParams(
        Object.fromEntries(
          Object.entries(data.parameters).map(([k, v]) => [k, String(v)]),
        ),
      );
      setParamErrors(
        validateParams(
          data.domain,
          Object.fromEntries(
            Object.entries(data.parameters).map(([k, v]) => [k, String(v)]),
          ),
        ),
      );
      setStage("idle");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to resolve query");
      setStage("failed");
    }
  };

  const handleParamChange = (key: string, value: string) => {
    const next = { ...editableParams, [key]: value };
    setEditableParams(next);
    if (resolvedDomain) {
      setParamErrors(validateParams(resolvedDomain, next));
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;

    abortControllerRef.current?.abort();
    const abortController = new AbortController();
    abortControllerRef.current = abortController;

    setStage("pending");
    setProgress(0);
    setResult(null);
    setError(null);

    let pollInterval: number | undefined;

    const finish = () => {
      window.clearInterval(pollInterval);
      abortController.abort();
    };

    const applyJobUpdate = (data: SimulationJob) => {
      setStage(data.status as PipelineStage);
      setProgress(data.progress);
      if (data.status === "completed" && data.result) {
        setResult(data.result);
        finish();
      } else if (data.status === "failed") {
        setError(data.error?.message ?? "Simulation failed.");
        finish();
      }
    };

    let pollRetries = 0;
    const MAX_POLL_RETRIES = 15;

    const startPollingFallback = (jobId: string) => {
      const tick = () => {
        loadJob(jobId)
          .then((data) => {
            pollRetries = 0;
            applyJobUpdate(data);
          })
          .catch(() => {
            pollRetries++;
            if (pollRetries > MAX_POLL_RETRIES) {
              window.clearInterval(pollInterval);
              setError(
                "Pipeline status updates lost. The job may still be running — check Recent Runs for results.",
              );
              setStage("failed");
            }
          });
      };

      // Fire once immediately, THEN every 1000ms. A job can complete
      // before a 1000ms setInterval would ever check for the first time --
      // measured directly: an immediate call to `tick()` reached a job
      // that was still "pending" at that exact instant, moments after
      // creation.
      tick();
      pollInterval = window.setInterval(tick, 1000);

      // A backgrounded tab throttles or fully suspends `setInterval` --
      // standard browser power-saving behaviour, not something a page
      // should fight. Measured directly: with the tab hidden, the interval
      // above did not tick even once in 52 seconds, while a job that
      // completes in under a second sat finished and unseen the whole
      // time. Re-checking the instant the tab becomes visible again closes
      // exactly that gap -- the user submits, switches tabs while it
      // resolves, comes back, and sees the answer immediately rather than
      // waiting for a throttled timer to notice.
      const onVisible = () => {
        if (document.visibilityState === "visible") tick();
      };
      document.addEventListener("visibilitychange", onVisible);
      abortController.signal.addEventListener("abort", () =>
        document.removeEventListener("visibilitychange", onVisible),
      );
    };

    try {
      const paramsForSubmit = Object.fromEntries(
        Object.entries(editableParams).map(([k, v]) => [
          k,
          Number.parseFloat(v),
        ]),
      );
      const overrides =
        Object.keys(paramsForSubmit).length > 0
          ? ` ${Object.entries(paramsForSubmit)
              .map(([k, v]) => `${k}=${v}`)
              .join(" ")}`
          : "";
      const job = await runSimulation({ query: query.trim() + overrides });
      const jobId = job.jobId;

      if (job.status === "completed" && job.result) {
        applyJobUpdate(job);
        return;
      }

      const es = new EventSource(`/api/simulate/${jobId}/stream`);
      abortController.signal.addEventListener("abort", () => es.close());

      es.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data) as SimulationJob;
          applyJobUpdate(data);
        } catch {
          setError("Failed to parse stream update.");
          es.close();
        }
      };

      es.onerror = () => {
        es.close();
      };

      // Polling runs ALONGSIDE the stream from the start, not only after
      // `es.onerror` fires. It used to be onerror-only, and that leaves a
      // real completed simulation permanently invisible: `EventSource`
      // does not fire `onerror` when a connection is closed deliberately
      // (our own `abortController` cleanup, a StrictMode remount, a dev
      // proxy recycling an idle connection) -- only on an actual transport
      // failure. Measured: submitting a real query, the stream opened,
      // was aborted within the same tick (`net::ERR_ABORTED` in the
      // network log, no `onerror`), and the job -- which had genuinely
      // completed server-side inside a second, real BRENDA citation and
      // trajectory included -- stayed on "Queued 0%" for the rest of the
      // page's life. No error, no retry, nothing: the answer existed and
      // never reached the screen.
      //
      // `applyJobUpdate` is idempotent (setting the same status/progress
      // twice does nothing), and `finish()` already tears down whichever
      // channel is still open the moment either one reports a terminal
      // state, so running both is a pure safety net, not a race to
      // resolve.
      startPollingFallback(jobId);
    } catch (err) {
      if (abortController.signal.aborted) return;
      if (err && typeof err === "object" && "message" in err) {
        setError(String((err as { message: string }).message));
      } else {
        setError("Simulation failed. Please try again.");
      }
      setStage("failed");
      finish();
    }
  };

  const parameterFields = resolvedDomain
    ? (DOMAIN_PARAMS[resolvedDomain] ?? [])
    : [];
  const hasParamErrors = Object.keys(paramErrors).length > 0;

  const isRunning =
    stage !== "idle" && stage !== "completed" && stage !== "failed";

  return (
    <TerminalWindow path="~/terrium — agent simulator" glow>
      <div className="mb-5 text-white/90">
        <span className="text-[#1D8A72]">$</span> terrium agent --simulate
      </div>

      {stage === "idle" && !resolvedDomain && !result && (
        <p className="text-white/30 text-[12px] mb-5 leading-relaxed">
          Ask a scientific question in plain language. The agent resolves
          parameters from literature via LLM + keyword matching, then runs the
          Terium ODE engine.
        </p>
      )}

      <form
        onSubmit={handleSubmit}
        className="flex flex-col sm:flex-row gap-2 mb-5"
      >
        <div className="flex-1 relative">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="e.g. simulate lactate dehydrogenase with pyruvate"
            className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2.5 text-white/90 text-[12px] outline-none transition-all duration-300 focus:border-[#1D8A72]/40 focus:bg-[#1D8A72]/[0.02] focus:shadow-[0_0_20px_rgba(29,138,114,0.06)] placeholder:text-white/20"
          />
        </div>
        <button
          type="button"
          ref={resolveBtnRef}
          onClick={handleResolve}
          disabled={!query.trim() || stage === "resolving"}
          className="px-4 py-2.5 rounded-lg border border-white/[0.08] text-white/50 text-[12px] transition-all duration-300 hover:border-[#1D8A72]/30 hover:text-[#1D8A72] hover:bg-[#1D8A72]/[0.04] disabled:opacity-30 disabled:hover:border-white/[0.08] disabled:hover:text-white/50 disabled:hover:bg-transparent"
        >
          {stage === "resolving" ? (
            <span className="flex items-center gap-1.5">
              <Spinner className="size-3 text-yellow-400" />
              resolving
            </span>
          ) : (
            "resolve"
          )}
        </button>
        <button
          type="submit"
          disabled={stage !== "idle" || !resolvedDomain || hasParamErrors}
          className="px-5 py-2.5 rounded-lg border border-[#1D8A72]/25 text-[#1D8A72] text-[12px] transition-all duration-300 hover:bg-[#1D8A72]/[0.06] hover:shadow-[0_0_20px_rgba(29,138,114,0.08)] disabled:opacity-30 disabled:hover:shadow-none disabled:hover:bg-transparent"
        >
          {hasParamErrors ? "fix parameter errors" : "run pipeline"}
        </button>
      </form>

      <div className="flex flex-wrap gap-1.5 mb-5">
        {EXAMPLE_QUERIES.map((q) => (
          <button
            key={q}
            onClick={() => setQuery(q)}
            className="text-[10px] text-white/30 hover:text-[#1D8A72] border border-white/[0.06] hover:border-[#1D8A72]/20 rounded-md px-2 py-1 transition-all duration-200 bg-white/[0.02] hover:bg-[#1D8A72]/[0.03]"
          >
            {q}
          </button>
        ))}
        <button
          onClick={() => setShowEnzymes(!showEnzymes)}
          disabled={enzymesLoading}
          className="text-[10px] text-white/30 hover:text-[#1D8A72] border border-white/[0.06] hover:border-[#1D8A72]/20 rounded-md px-2 py-1 transition-all duration-200 bg-white/[0.02] hover:bg-[#1D8A72]/[0.03] ml-auto disabled:opacity-40"
        >
          {enzymesLoading ? (
            <span className="flex items-center gap-1">
              <Spinner className="size-2.5" />
              loading
            </span>
          ) : enzymesError ? (
            "enzymes unavailable"
          ) : showEnzymes ? (
            "hide enzymes"
          ) : (
            `${enzymes.length} enzymes`
          )}
        </button>
      </div>

      <AnimatePresence>
        {showEnzymes && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            className="mb-5 overflow-hidden"
          >
            <div className="rounded-lg border border-white/[0.06] max-h-48 overflow-y-auto text-[10px]">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-white/[0.04] text-white/20">
                    <th className="text-left p-2 font-normal">EC</th>
                    <th className="text-left p-2 font-normal">Enzyme</th>
                    <th className="text-left p-2 font-normal">Substrates</th>
                    <th className="text-left p-2 font-normal hidden sm:table-cell">
                      Organism
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {enzymes.map((e) => (
                    <tr
                      key={e.ecNumber}
                      className="border-b border-white/[0.03] hover:bg-white/[0.02] transition-colors"
                    >
                      <td className="p-2 text-[#1D8A72]">{e.ecNumber}</td>
                      <td className="p-2 text-white/60">{e.name}</td>
                      <td className="p-2 text-white/40">
                        {e.substrates.join(", ")}
                      </td>
                      <td className="p-2 text-white/25 hidden sm:table-cell">
                        {e.organism}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence mode="wait">
        {resolvedDomain && stage === "idle" && !result && (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="mb-5 rounded-lg border border-[#1D8A72]/15 bg-[#1D8A72]/[0.02] p-4"
          >
            <div className="flex items-center gap-2 text-[11px] text-white/30 mb-4">
              <span className="inline-flex items-center gap-1 rounded bg-[#1D8A72]/10 px-2 py-0.5 text-[10px] text-[#1D8A72] uppercase tracking-wide">
                {resolvedDomain}
              </span>
              <span className="text-white/20">
                domain resolved — edit parameters below
              </span>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2 mb-4">
              {parameterFields.map((field) => {
                const err = paramErrors[field.key];
                return (
                  <label key={field.key} className="flex flex-col gap-1">
                    <span className="text-[10px] text-white/25">
                      {field.label}
                    </span>
                    <input
                      type="number"
                      step="any"
                      value={editableParams[field.key] ?? ""}
                      onChange={(e) =>
                        handleParamChange(field.key, e.target.value)
                      }
                      className={`rounded-lg border bg-white/[0.02] px-2.5 py-1.5 text-white/80 text-[11px] outline-none transition-all duration-200 ${
                        err
                          ? "border-red-500/30 focus:border-red-400/50 focus:shadow-[0_0_12px_rgba(239,68,68,0.08)]"
                          : "border-white/[0.06] focus:border-[#1D8A72]/30 focus:shadow-[0_0_12px_rgba(29,138,114,0.06)]"
                      }`}
                    />
                    {err && (
                      <span className="text-[8px] text-red-400/60">{err}</span>
                    )}
                  </label>
                );
              })}
            </div>

            {reasoning && (
              <p className="text-[11px] text-white/30 italic mb-2 leading-relaxed">
                {reasoning}
              </p>
            )}

            {flags.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mb-2">
                {flags.map((f, i) => (
                  <span
                    key={i}
                    className="text-[9px] text-yellow-500/60 bg-yellow-500/[0.06] rounded px-1.5 py-0.5"
                  >
                    {f}
                  </span>
                ))}
              </div>
            )}

            {modelCitations.length > 0 && (
              <div className="text-[10px] text-white/20 space-y-0.5 border-t border-white/[0.04] pt-2 mt-2">
                {modelCitations.map((c, i) => (
                  <div key={i} className="truncate">
                    {c}
                  </div>
                ))}
              </div>
            )}
          </motion.div>
        )}

        {isRunning && (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="mb-5 rounded-lg border border-[#1D8A72]/10 bg-[#1D8A72]/[0.02] p-4"
          >
            <div className="flex items-center justify-between text-[11px] mb-3">
              <span
                className={`flex items-center gap-2 ${STAGE_COLORS[stage]}`}
              >
                {stage === "running" && (
                  <span className="inline-block w-2 h-2 rounded-full bg-[#1D8A72] animate-pulse" />
                )}
                {STAGE_LABEL[stage]}
              </span>
              <span className="text-white/30">{progress}%</span>
            </div>
            <div className="h-1.5 w-full bg-white/[0.04] rounded-full overflow-hidden">
              <motion.div
                className="h-full rounded-full bg-gradient-to-r from-[#1D8A72]/60 to-[#1D8A72]"
                initial={{ width: 0 }}
                animate={{ width: `${progress}%` }}
                transition={{ duration: 0.4, ease: "easeOut" }}
              />
            </div>
          </motion.div>
        )}

        {error && (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="mb-4 border border-red-500/10 rounded-lg bg-red-500/[0.03] p-3"
          >
            <div className="flex items-start justify-between gap-3">
              <p className="text-red-400/70 text-[12px] leading-relaxed">
                {error}
              </p>
              <button
                onClick={() => {
                  setError(null);
                  setStage("idle");
                  setResult(null);
                }}
                className="shrink-0 text-[10px] text-red-400/50 hover:text-red-400/80 border border-red-500/15 hover:border-red-400/30 rounded-md px-2 py-1 transition-all duration-200"
              >
                retry
              </button>
            </div>
          </motion.div>
        )}

        {result && (
          <motion.div
            key={result.runId}
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.4 }}
          >
            <div className="flex items-center gap-3 text-[11px] text-white/30 mb-4">
              <span className="inline-flex items-center gap-1 rounded bg-[#1D8A72]/10 px-2 py-0.5 text-[10px] text-[#1D8A72] uppercase tracking-wide">
                {result.domain}
              </span>
              <span className="text-white/20">runId: {result.runId}</span>
              <span className="ml-auto flex items-center gap-2">
                <ShareSimulation
                  query={query}
                  domain={result.domain}
                  runId={result.runId}
                  parameters={result.parameters as Record<string, unknown>}
                  citationCount={result.provenance.modelCitations?.length ?? 0}
                  hasFlags={(result.provenance.flags?.length ?? 0) > 0}
                />
                <ExportButtons
                  trajectory={
                    (result.trajectory ?? []) as Record<string, number>[]
                  }
                  result={result as unknown as Record<string, unknown>}
                  filenamePrefix={result.domain}
                  runId={result.runId}
                />
              </span>
            </div>

            <div className="rounded-lg border border-white/[0.06] bg-white/[0.015] p-3 mb-4">
              <LineChart
                data={
                  (result.trajectory ??
                    []) as unknown as import("@/lib/simulate").Point[]
                }
                series={seriesForResponse(result)}
              />
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-[11px]">
              <div className="rounded-lg border border-white/[0.06] p-3 bg-white/[0.015]">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-white/20 text-[10px] uppercase tracking-wide">
                    parameters
                  </span>
                  <button
                    onClick={() => {
                      navigator.clipboard
                        .writeText(JSON.stringify(result.parameters, null, 2))
                        .then(() => {
                          setParamsCopied(true);
                          setTimeout(() => setParamsCopied(false), 2000);
                        })
                        .catch(() => {});
                    }}
                    className="flex items-center gap-1 rounded border border-white/[0.06] px-1.5 py-0.5 text-[9px] text-white/25 hover:text-white/50 hover:border-white/[0.12] transition-all duration-200"
                  >
                    {paramsCopied ? "copied" : "copy"}
                  </button>
                </div>
                <pre className="text-white/60 overflow-x-auto text-[11px]">
                  {JSON.stringify(result.parameters, null, 2)}
                </pre>
              </div>
              <div className="rounded-lg border border-white/[0.06] p-3 bg-white/[0.015]">
                <div className="text-white/20 text-[10px] uppercase tracking-wide mb-2">
                  provenance
                </div>
                <p className="text-white/60 mb-2 leading-relaxed">
                  {result.provenance.reasoning}
                </p>
                {result.provenance.flags &&
                  result.provenance.flags.length > 0 && (
                    <div className="flex flex-wrap gap-1 mb-2">
                      {result.provenance.flags.map((flag, i) => (
                        <span
                          key={i}
                          className="text-[9px] text-yellow-500/50 bg-yellow-500/[0.05] rounded px-1.5 py-0.5"
                        >
                          {flag}
                        </span>
                      ))}
                    </div>
                  )}
                {result.provenance.modelCitations &&
                  result.provenance.modelCitations.length > 0 && (
                    <div className="border-t border-white/[0.04] pt-2 mt-2 space-y-0.5">
                      {result.provenance.modelCitations.map((citation, i) => (
                        <div
                          key={i}
                          className="text-[10px] text-white/25 truncate"
                        >
                          {citation}
                        </div>
                      ))}
                    </div>
                  )}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </TerminalWindow>
  );
}
