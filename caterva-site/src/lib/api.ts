/**
 * Real HTTP client to the literature-backed resolution pipeline.
 *
 * CONSTITUTION.md requirement, non-negotiable: every number this site shows
 * as a simulation result must trace to a real source (BRENDA/KEGG/PubMed, or
 * an explicit "could not resolve, using default" flag) -- never a value
 * invented in the browser. `simulate.ts` in this directory is real RK4 math,
 * but its parameters were hand-picked constants with no citation; that is
 * fine for *verifying the integrator against a closed form* (see `verify`
 * commands) but is not an acceptable basis for a `run` command that claims
 * to simulate something. This file is what actually calls the science-agent
 * pipeline (Science-Agent-Pipeline/artifacts/api-server) that does real
 * literature resolution, so `run kinetics <enzyme>` and
 * `run epidemiology <query>` report only what that pipeline actually found,
 * with its citations and its flags, not a fabricated demo.
 */

export interface ParameterProvenanceEntry {
  origin: "resolved" | "user" | "llm" | "default";
  source?: string;
  note?: string;
}

export interface SimulationJob {
  jobId: string;
  status:
    | "queued"
    | "resolving"
    | "validating"
    | "running"
    | "completed"
    | "failed"
    | "cancelled";
  result?: {
    runId: string;
    domain: string;
    parameters: Record<string, unknown>;
    trajectory: Record<string, unknown>[];
    provenance: {
      reasoning: string;
      modelCitations: string[];
      flags: string[];
    };
    parameterProvenance: Record<string, ParameterProvenanceEntry>;
    completedAt: string;
  };
  error?: { error: string; message: string };
}

/**
 * Base URL of the science-agent API. Empty by default -- this is a real
 * network dependency the browser cannot fabricate an answer for, so with no
 * configured server the caller must surface "no literature source
 * reachable," never a hardcoded number standing in for one.
 *
 * Configure via `.env.local`: VITE_CATERVA_API_URL=http://localhost:3000
 */
export const API_BASE_URL: string =
  (import.meta.env.VITE_CATERVA_API_URL as string | undefined) || "";

export class ApiUnavailableError extends Error {}

async function postSimulate(query: string): Promise<SimulationJob> {
  if (!API_BASE_URL) {
    throw new ApiUnavailableError(
      "No science-agent API configured (VITE_CATERVA_API_URL is unset). " +
        "Cannot resolve literature-backed parameters without it.",
    );
  }
  const res = await fetch(`${API_BASE_URL}/api/simulate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query }),
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new ApiUnavailableError(
      `POST /api/simulate failed: ${res.status} ${body}`.trim(),
    );
  }
  return (await res.json()) as SimulationJob;
}

async function getJob(jobId: string): Promise<SimulationJob> {
  const res = await fetch(`${API_BASE_URL}/api/simulate/${jobId}`);
  if (!res.ok) {
    throw new ApiUnavailableError(`GET /api/simulate/${jobId} failed: ${res.status}`);
  }
  return (await res.json()) as SimulationJob;
}

const TERMINAL_STATUSES = new Set(["completed", "failed", "cancelled"]);

/**
 * Submit a natural-language query to the real resolution pipeline and poll
 * until it reaches a terminal state. Every parameter in the result traces to
 * `job.result.provenance.modelCitations` and `job.result.parameterProvenance`
 * -- render those, don't hide them, since the citation is the actual product
 * claim being made.
 */
export async function resolveAndSimulate(
  query: string,
  { timeoutMs = 20000, pollMs = 400 }: { timeoutMs?: number; pollMs?: number } = {},
): Promise<SimulationJob> {
  const created = await postSimulate(query);
  const start = Date.now();
  let job = created;
  while (!TERMINAL_STATUSES.has(job.status)) {
    if (Date.now() - start > timeoutMs) {
      throw new ApiUnavailableError(
        `Timed out waiting for job ${job.jobId} after ${timeoutMs}ms`,
      );
    }
    await new Promise((r) => setTimeout(r, pollMs));
    job = await getJob(job.jobId);
  }
  return job;
}
