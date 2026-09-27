import {
  Router,
  type IRouter,
  type Request,
  type Response,
  type NextFunction,
} from "express";
import {
  RunSimulationBody,
  type SimulationRequest as RunSimulationRequest,
  GetSimulationJobParams,
  StreamSimulationJobParams,
} from "@workspace/api-zod";
import { getDb, isDbAvailable } from "@workspace/db";
import { logger } from "../lib/logger";
import type { ModelGroundingReport } from "../lib/modelGrounding";
import { citationObligations } from "../lib/dataSources";
import type { SourceObligation } from "../lib/dataSources";
import { buildTrajectoryCsv } from "../lib/trajectoryCsv";
import { asSimulationDomain, runCaterva, type SimulationDomain, type CatervaResult } from "../lib/catervaRunner";
import { SimulationParameterSchemas, CustomModelBody } from "../lib/schemas";
import {
  NetworkRequestSchema,
  unsourcedQuantityIds,
  ParameterizeRequestSchema,
  unknownRequestIds,
  type NetworkRequest,
  type ParameterizeRequest,
} from "../lib/reactionNetwork";
import {
  toCompositionReport,
  toLiteratureSearchReport,
  type CompositionRefusal,
  type CompositionReport,
  type ParameterizePayload,
} from "../lib/literatureSearch";
import * as queue from "../lib/queue";
import { findCachedEntryByQuery, persistJob } from "../lib/cache";
import { simulateLimiter } from "../lib/rateLimit";
import {
  PARAMETER_ORIGINS,
  RequiredParametersMissingError,
  UnrecognizedQueryError,
  STRENDA_GOVERNED_FIELDS,
  validateParameterProvenance,
  type ParameterProvenance,
} from "../lib/provenance";
import {
  verifyParameterAgainstLiterature,
  type LiteratureReference,
  type VerificationResult,
} from "../lib/literature-verifier";
import { validateSTREANDA } from "../lib/strenda-validator";
import { getDomainCitation } from "../lib/domain-literature";
import { verifiableMetricsCollector } from "../lib/verifiable-metrics";

/**
 * Extract the value from the first locator matching a kind.
 */
function findLocatorValue(
  locators: Array<{ kind: string; value: string }>,
  kind: string,
): string | undefined {
  return locators.find((l) => l.kind === kind)?.value;
}

/**
 * Extract a URL from locators, preferring deep links over generic URLs.
 */
function findLocatorUrl(
  locators: Array<{ kind: string; value: string; deepLink?: string }>,
): string | undefined {
  return (
    locators.find((l) => l.deepLink !== undefined)?.deepLink ??
    findLocatorValue(locators, "url")
  );
}

/**
 * Derive a structured LiteratureReference from a ParameterProvenance entry
 * for the audit report. `prov.citation` is a formatted DISPLAY string (ADR
 * 0008 — "citations" -> "modelCitations" rename made this explicit), not a
 * structured object with its own .doi/.pmid/.source fields; the structured
 * data already exists separately as `citationLocators` (citeVerify.ts) and
 * is reassembled here rather than parsed back out of the display string a
 * second time.
 */
function literatureReferenceFromProvenance(
  prov: ParameterProvenance,
): LiteratureReference | undefined {
  if (prov.origin !== "resolved") return undefined;
  const locators = prov.citationLocators ?? [];
  const doi = findLocatorValue(locators, "doi");
  const pmid = findLocatorValue(locators, "pubmed");
  const url = findLocatorUrl(locators);
  if (!doi && !pmid && !url && !prov.source) return undefined;
  return {
    doi,
    pmid,
    url,
    source: prov.source,
  };
}

/**
 * Type guard to check if a value is a valid finite number.
 */
function isValidFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

/**
 * Type guard to check if a value is an array of valid finite numbers.
 */
function isValidNumberArray(value: unknown): value is number[] {
  return Array.isArray(value) && value.every(isValidFiniteNumber);
}

/**
 * Narrow a job's stored parameters to the numeric ones the audit and
 * confidence reports can actually say something about.
 *
 * `SimulationResponse.parameters` is `Record<string, unknown>` because it
 * round-trips through the job store as opaque JSON. Rather than casting it
 * (which would let a string or null reach code that assumes a number and
 * produce a nonsense confidence score for it), this drops anything that is
 * not a number or an array of numbers. A parameter that isn't numeric has
 * no literature-comparable value to audit, so omitting it is the honest
 * reading -- not a silent data loss.
 */
function numericParameters(
  parameters: Record<string, unknown>,
): Record<string, number | number[]> {
  const out: Record<string, number | number[]> = {};
  for (const [key, value] of Object.entries(parameters)) {
    if (isValidFiniteNumber(value)) {
      out[key] = value;
    } else if (isValidNumberArray(value)) {
      out[key] = value;
    }
  }
  return out;
}

const router: IRouter = Router();

/** Terminal states that cannot transition further. */
const TERMINAL = new Set<queue.JobStatus>(["completed", "failed", "cancelled"]);

/**
 * GET /api/simulate
 *
 * Returns the most recent simulation jobs from the in-memory queue, ordered
 * by updatedAt descending. This is a lightweight "runs dashboard" endpoint
 * that lets clients show a history of pipeline runs.
 */
router.get(
  "/simulate",
  async (_req: Request, res: Response, next: NextFunction) => {
    try {
      const jobs = queue.listJobs();
      res.json(jobs);
    } catch (err) {
      next(err);
    }
  },
);

/**
 * GET /api/simulate/metrics/pipeline
 *
 * Returns comprehensive pipeline metrics with literature backing:
 * - Little's Law queue theory (Little 1961)
 * - Wilson confidence intervals (Wilson 1927)
 * - Harter percentiles (Harter 1974)
 * - Domain-specific usage
 * - LLM classification rates
 */
router.get(
  "/simulate/metrics/pipeline",
  async (_req: Request, res: Response, next: NextFunction) => {
    try {
      const snapshot = verifiableMetricsCollector.getSnapshot();

      // Add success rate with confidence interval
      const successRate = verifiableMetricsCollector.getSuccessRateWithConfidence();

      // Add latency percentiles
      const latencyPercentiles = verifiableMetricsCollector.getLatencyPercentiles();

      res.json({
        timestamp: new Date().toISOString(),
        literature: {
          // Each entry says what the work actually contributes. Until
          // 2026-09-05 this block named four works of which one was used:
          // Wilson's interval IS computed here; Little's Law was cited for
          // a Set's size, Harter for an ordinary sorted-array percentile,
          // and Nielsen for nothing in this payload at all. Naming a real
          // paper beside a number it did not produce is the defect this
          // product exists to refuse.
          queueTheory:
            "Little (1961) L = \u03BBW -- the steady-state relation these " +
            "three metrics can be CHECKED against (activeJobs should " +
            "approximate completionRate x avgLatency). activeJobs is a " +
            "direct count, not derived from it.",
          confidenceIntervals:
            "Wilson (1927) -- computed here: the binomial proportion " +
            "interval around successRate, which is why a 1-of-1 sample " +
            "does not report 100% with no uncertainty.",
          percentiles:
            "Empirical order statistics from the sorted latency sample. " +
            "No estimator or interpolation is applied, so no method " +
            "citation is claimed.",
        },
        metrics: {
          ...snapshot,
          successRate,
          latencyPercentiles,
        },
      });
    } catch (err) {
      next(err);
    }
  },
);

/**
 * POST /api/simulate
 *
 * Enqueues a new science-agent simulation job and immediately returns a
 * 202 Accepted job object. The actual pipeline runs asynchronously; clients
 * can poll `GET /simulate/:jobId` or subscribe to `GET /simulate/:jobId/stream`
 * for real-time progress updates.
 */
/**
 * POST /api/simulate/model -- simulate a model the caller supplies.
 *
 * The engine has always been able to do this: `simulate_sbml` runs any SBML
 * document through libRoadRunner, and `run_sbml` has been in the dispatch
 * table (and contract-tested) the whole time. Nothing could reach it. The
 * API exposed no way to send a model, and `resolveQuery` never yields the
 * "sbml" domain, so the most general capability in the system was
 * unreachable from the product -- a lab could pick from fifteen presets or
 * nothing.
 *
 * That exclusion was also load-bearing security, whatever its stated
 * rationale: `sbml_string` reaches RoadRunner's loader, which accepts a
 * path or URL as readily as a document. The guards in
 * caterva_runner.run_sbml (path/URL refusal, Antimony `import` refusal, and
 * the MAX_API_SBML_* ceilings) are what make opening it safe, and they are
 * enforced engine-side so they hold no matter which caller arrives.
 */
router.post(
  "/simulate/model",
  simulateLimiter,
  async (req: Request, res: Response, next: NextFunction) => {
    try {
      const parse = CustomModelBody.safeParse(req.body);
      if (!parse.success) {
        res.status(400).json({
          error: "BAD_REQUEST",
          message: parse.error.errors.map((e) => e.message).join("; "),
        });
        return;
      }

      const { antimony, sbml, start, end, points } = parse.data;

      // The job's `query` is a label for a request that has no query. It is
      // what Recent Runs and the job record display, so it says what the
      // run WAS rather than repeating the whole model source into a field
      // sized for a sentence.
      const label = antimony
        ? "custom model (antimony)"
        : "custom model (sbml)";
      const job = queue.createJob(label);

      runCustomModelPipeline(job.jobId, {
        antimony,
        sbml,
        start,
        end,
        points,
      }).catch((err) => {
        logger.error(
          { err, jobId: job.jobId },
          "Custom-model pipeline threw unexpectedly",
        );
        queue.setJobError(job.jobId, {
          error: "INTERNAL_SERVER_ERROR",
          message:
            err instanceof Error ? err.message : "Unexpected pipeline failure",
        });
      });

      res.status(202).json(job);
    } catch (err) {
      next(err);
    }
  },
);

/**
 * POST /api/simulate/network -- run a model the caller CONSTRUCTED.
 *
 * The open path. Every other simulate route asks Caterva to recognise a
 * system from its catalogue of sixteen; this one accepts the system itself,
 * as species, parameters, reactions and rate rules, and runs it.
 *
 * WHAT KEEPS IT HONEST
 *
 * Opening the model surface without opening the provenance surface would
 * be the whole product given away. Three checks run engine-side, in
 * `caterva/core/network.py` and `network_provenance.py`, so they hold no
 * matter which caller arrives:
 *
 *   - every symbol in a rate law must resolve to a species or parameter of
 *     the same network, with no statement syntax and only a fixed list of
 *     mathematical functions;
 *   - every quantity -- species initials included, not just rate constants
 *     -- must carry a source, and a quantity with NO source is refused
 *     rather than defaulted;
 *   - `resolved` without a citation is refused.
 *
 * The Zod schema here checks shape only, and deliberately does not
 * re-implement any of that: two enforcers of one rule in two languages
 * drift into two rules, which is what the four duplicate domain lists in
 * this codebase already demonstrate.
 *
 * The response carries the model's conservation laws, DERIVED from its own
 * stoichiometry -- `["S + I + R"]` for an SIR-shaped network, nobody having
 * told it that epidemics conserve people.
 */
router.post(
  "/simulate/network",
  simulateLimiter,
  async (req: Request, res: Response, next: NextFunction) => {
    try {
      const parse = NetworkRequestSchema.safeParse(req.body);
      if (!parse.success) {
        res.status(400).json({
          error: "BAD_REQUEST",
          message: parse.error.errors
            .map((e) => `${e.path.join(".") || "body"}: ${e.message}`)
            .join("; "),
        });
        return;
      }

      const request = parse.data;

      // Answered here rather than after paying for a subprocess. The
      // ENGINE's refusal is the authoritative one and covers more (blocked
      // origins, resolved-without-citation); this is the same question
      // asked early, for the commonest mistake.
      const missing = unsourcedQuantityIds(request.network, request.sources);
      if (missing.length > 0) {
        res.status(400).json({
          error: "UNSOURCED_QUANTITIES",
          message:
            `This model has ${missing.length} quantit` +
            `${missing.length === 1 ? "y" : "ies"} with no recorded source: ` +
            `${missing.join(", ")}. Every species initial and every ` +
            `parameter needs one -- resolve it from literature, or supply ` +
            `it yourself and it will be recorded as yours.`,
          unsourced: missing,
        });
        return;
      }

      const job = queue.createJob(`network model: ${request.network.name}`);

      runNetworkPipeline(job.jobId, request).catch((err) => {
        logger.error(
          { err, jobId: job.jobId },
          "Network pipeline threw unexpectedly",
        );
        queue.setJobError(job.jobId, {
          error: "INTERNAL_SERVER_ERROR",
          message:
            err instanceof Error ? err.message : "Unexpected pipeline failure",
        });
      });

      res.status(202).json(job);
    } catch (err) {
      next(err);
    }
  },
);

async function runNetworkPipeline(
  jobId: string,
  request: NetworkRequest,
): Promise<void> {
  try {
    queue.updateJob(jobId, { status: "running" });

    const engineResult = await runCaterva("network", {
      network: request.network as unknown as Record<string, unknown>,
      sources: request.sources as unknown as Record<string, unknown>,
      start: request.start,
      end: request.end,
      points: request.points,
    });

    // Provenance is reported from the ENGINE's report, not from the request
    // body. The request says what the caller claims; the engine's report is
    // what actually passed the rule, and echoing the claim back would make
    // the response agree with the caller by construction.
    const parameterProvenance: Record<string, ParameterProvenance> = {};
    for (const [quantity, source] of Object.entries(
      engineResult.quantitySources ?? {},
    )) {
      // Not cast. `ParameterProvenance` has `origin` required and the rest
      // optional, so the compiler checks this shape -- and the origin is
      // narrowed by a guard rather than asserted, because the engine's
      // report is JSON and a cast here would launder an unexpected string
      // into a typed field.
      const origin = source.origin ?? "user";
      if (!PARAMETER_ORIGINS.includes(origin as ParameterProvenance["origin"])) {
        throw new Error(
          `engine reported origin "${origin}" for ${quantity}, which is not ` +
            `a ParameterOrigin. The two enforcers have drifted.`,
        );
      }
      parameterProvenance[quantity] = {
        origin: origin as ParameterProvenance["origin"],
        ...(source.citation ? { citation: source.citation } : {}),
        ...(source.note ? { note: source.note } : {}),
      };
    }

    const laws = engineResult.conservationLaws ?? [];
    const result: queue.SimulationResponse = {
      runId: jobId,
      domain: engineResult.domain,
      parameters: engineResult.parameters,
      trajectory: engineResult.trajectory,
      provenance: {
        reasoning:
          `Caller-constructed reaction network "${request.network.name}": ` +
          `${request.network.species.length} species, ` +
          `${request.network.reactions.length} reaction(s), ` +
          `${request.network.rateRules.length} rate rule(s). Caterva did ` +
          `not choose this model; it validated it, required a source for ` +
          `every quantity, compiled it and ran it.`,
        modelCitations: [],
        flags: [
          ...(laws.length > 0
            ? [
                `conservation_laws_derived: ${laws.join("; ")} -- computed ` +
                  `from this model's stoichiometry, not asserted.`,
              ]
            : [
                "no_conservation_law_derived: this model's rate rules may " +
                  "change their species by any amount, so no stoichiometric " +
                  "conservation can be claimed.",
              ]),
          ...(engineResult.flagged && engineResult.flagReason
            ? [engineResult.flagReason]
            : []),
        ],
      },
      parameterProvenance,
      completedAt: new Date().toISOString(),
    };

    queue.setJobResult(jobId, result);
  } catch (err) {
    const message =
      err instanceof Error ? err.message : "Network simulation failed";
    queue.setJobError(jobId, { error: "PIPELINE_ERROR", message });
  }
}

router.post(
  "/simulate/parameterize",
  simulateLimiter,
  async (req: Request, res: Response, next: NextFunction) => {
    try {
      const parse = ParameterizeRequestSchema.safeParse(req.body);
      if (!parse.success) {
        res.status(400).json({
          error: "BAD_REQUEST",
          message: parse.error.errors
            .map((e) => `${e.path.join(".") || "body"}: ${e.message}`)
            .join("; "),
        });
        return;
      }

      const request = parse.data;

      // Same question the engine asks (a `ValueError` on declared minus
      // available) asked early, so a typo'd quantity never pays for a
      // subprocess or a literature search. This is a sanity check, not the
      // authoritative refusal: unlike the network route, sourcing is the
      // POINT of this route, so blockers like "unsourced" are not checked
      // here at all.
      const unknown = unknownRequestIds(request.network, request.requests);
      if (unknown.length > 0) {
        res.status(400).json({
          error: "UNKNOWN_REQUEST_QUANTITIES",
          message:
            `These requested quantities do not exist in the network: ` +
            `${unknown.join(", ")}. Every request must name a constant ` +
            `the model declares.`,
          unknown,
        });
        return;
      }

      const job = queue.createJob(
        `parameterize network: ${request.network.name}`,
      );

      runParameterizePipeline(job.jobId, request).catch((err) => {
        logger.error(
          { err, jobId: job.jobId },
          "Parameterize pipeline threw unexpectedly",
        );
        queue.setJobError(job.jobId, {
          error: "INTERNAL_SERVER_ERROR",
          message:
            err instanceof Error ? err.message : "Unexpected pipeline failure",
        });
      });

      res.status(202).json(job);
    } catch (err) {
      next(err);
    }
  },
);

async function runParameterizePipeline(
  jobId: string,
  request: ParameterizeRequest,
): Promise<void> {
  try {
    queue.updateJob(jobId, { status: "running" });

    // `requests` is an array of records, which the transport's parameter
    // union does not declare (it has `NetworkPayload` for single objects and
    // `number[]` for vectors). The payload is JSON across the bridge either
    // way; this widens at the transport boundary, same as `network` above.
    const engineResult = (await runCaterva(
      "parameterize",
      {
        network: request.network as unknown as Record<string, unknown>,
        requests: request.requests,
        sources: request.sources as unknown as Record<string, unknown>,
        ...(request.organism ? { organism: request.organism } : {}),
        start: request.start,
        end: request.end,
        points: request.points,
      } as unknown as Parameters<typeof runCaterva>[1],
    )) as unknown as ParameterizePayload;

    const search = toLiteratureSearchReport(engineResult);
    const simulation = search.simulation;

    // When the search ran, the engine reports where each resolved value
    // came from (origin/citation/note). That IS the per-parameter
    // provenance: mirroring the network route's mapping, so the values in
    // `parameters` are never left un-tagged for
    // guardSerializationProvenance. When the search did NOT run there is
    // nothing resolved and nothing to tag.
    const parameterProvenance: Record<string, ParameterProvenance> = {};
    for (const [quantity, source] of Object.entries(
      simulation.quantitySources ?? {},
    )) {
      const origin = source.origin ?? "user";
      if (!PARAMETER_ORIGINS.includes(origin as ParameterProvenance["origin"])) {
        throw new Error(
          `engine reported origin "${origin}" for ${quantity}, which is not ` +
            `a ParameterOrigin. The two enforcers have drifted.`,
        );
      }
      parameterProvenance[quantity] = {
        origin: origin as ParameterProvenance["origin"],
        ...(source.citation ? { citation: source.citation } : {}),
        ...(source.note ? { note: source.note } : {}),
      };
    }

    const result: queue.SimulationResponse = {
      runId: jobId,
      domain: engineResult.domain,
      parameters: simulation.values ?? {},
      trajectory: simulation.trajectory ?? [],
      provenance: {
        reasoning:
          `Network "${request.network.name}" with ` +
          `${request.requests.length} constant(s) to resolve` +
          `${request.organism ? ` under organism "${request.organism}"` : ""}. ` +
          `${search.summary} ` +
          (simulation.ran
            ? "The resolved set was simulated."
            : "The resolved set was not simulated."),
        modelCitations: [],
        flags: [
          ...(search.chosenOrganism
            ? [`chosen_organism: ${search.chosenOrganism}`]
            : ["no_organism_chosen: the search did not settle on one."]),
          ...(search.undecidedOrganisms.length > 0
            ? [
                `undecided_organisms: ${search.undecidedOrganisms.join(", ")} ` +
                  `-- the request did not separate these from the winner.`,
              ]
            : []),
          ...(simulation.ran ? [] : [`not_simulated: ${simulation.because}`]),
        ],
      },
      parameterProvenance,
      literatureSearch: search,
      completedAt: new Date().toISOString(),
    };

    queue.setJobResult(jobId, result);
  } catch (err) {
    const message =
      err instanceof Error ? err.message : "Parameterize simulation failed";
    queue.setJobError(jobId, { error: "PIPELINE_ERROR", message });
  }
}


router.post(
  "/simulate",
  simulateLimiter,
  async (req: Request, res: Response, next: NextFunction) => {
    try {
      const parse = RunSimulationBody.safeParse(req.body);
      if (!parse.success) {
        res.status(400).json({
          error: "BAD_REQUEST",
          message: parse.error.errors.map((e) => e.message).join("; "),
        });
        return;
      }

      const { query } = parse.data;
      const allowCrossSpecies = parse.data.allowCrossSpecies === true;
      // Absent means false, for the same reason allowCrossSpecies reads that
      // way: the permissive reading of a missing flag is how an opt-in
      // quietly stops being one.
      const allowVariants = parse.data.allowVariants === true;
      const physiologicalReference = parse.data.physiologicalReference;
      const normalizedQuery = normalizeQuery(
        query,
        allowCrossSpecies,
        allowVariants,
        physiologicalReference,
      );
      logger.info(
        { query, normalizedQuery, allowCrossSpecies, allowVariants },
        "Enqueuing simulation job",
      );

      const cached = (await isDbAvailable())
        ? await findCachedSimulation(normalizedQuery)
        : findCachedEntryByQuery(normalizedQuery);
      if (cached) {
        logger.info(
          { query, cachedAt: cached.cachedAt },
          "Returning cached simulation result",
        );
        const job = queue.createJob(query);
        // A replay must say it is one, and say when the answer was
        // computed. Until 2026-09-05 a cache hit was returned with the
        // same 202 and the same body shape as a live run: two people
        // running the same query a month apart got byte-identical output,
        // with nothing distinguishing a reproduction from a replay of a
        // resolution made against literature data that may since have
        // been recurated.
        //
        // Added to the RESPONSE, not to the stored entry, so replaying
        // does not mutate the cache and the flag cannot accumulate.
        queue.setJobResult(job.jobId, withReplayProvenance(cached));
        guardSerializationProvenance(cached.result);
        res.status(202).json(job);
        return;
      }

      const job = queue.createJob(query);

      // Run the pipeline asynchronously. Errors are captured in the job state.
      runPipeline(
        job.jobId,
        query,
        allowCrossSpecies,
        allowVariants,
        physiologicalReference,
      ).catch((err) => {
        logger.error(
          { err, jobId: job.jobId },
          "Pipeline runner threw unexpectedly",
        );
        queue.setJobError(job.jobId, {
          error: "INTERNAL_SERVER_ERROR",
          message:
            err instanceof Error ? err.message : "Unexpected pipeline failure",
        });
      });

      res.status(202).json(job);
    } catch (err) {
      next(err);
    }
  },
);

/**
 * Normalize a query so that tiny whitespace/casing differences hit the cache.
 */
/**
 * The cache key for a query.
 *
 * `allowCrossSpecies` is part of the key, not an afterthought. The same
 * query run with and without the opt-in produces genuinely different
 * answers -- one refuses, the other may return a related organism's value
 * -- so a key that ignored it would serve one user's result to the other.
 *
 * The dangerous direction is specific: a cross-species value cached by
 * someone who opted in, then served to a student who did not. They would
 * receive a rabbit's Km presented as their answer, having explicitly never
 * agreed to that, and every guard downstream would be satisfied because
 * the value really was resolved and really was cited. Jeske's checkbox
 * would be defeated by a cache.
 *
 * The suffix is only appended when the flag is on, so existing cache
 * entries written before ADR 0024 still hit for the default path rather
 * than being silently invalidated.
 */
// Exported for testing. The cache key is the single place where an opt-in
// can be defeated without any guard noticing -- ADR 0016's failure class --
// and until now nothing tested it at all, for any of the three flags.
export function normalizeQuery(
  query: string,
  allowCrossSpecies = false,
  allowVariants = false,
  physiologicalReference?: RunSimulationRequest["physiologicalReference"],
): string {
  const base = query.trim().toLowerCase().replace(/\s+/g, " ");
  const withSpecies = allowCrossSpecies
    ? `${base} [allow-cross-species]`
    : base;

  // `allowVariants` is part of the key for exactly the reason
  // `allowCrossSpecies` is, and the dangerous direction is the same: a point
  // mutant's constant, cached by someone who opted in, then served to a
  // student who did not. They would receive a Y337A mutant's kcat presented
  // as the enzyme's, having explicitly never agreed to it, and every guard
  // downstream would pass because the value really was resolved and really
  // was cited. ADR 0029's opt-in defeated by a cache.
  //
  // Appended only when on, so entries written before this still hit for the
  // default path rather than being silently invalidated.
  const withVariants = allowVariants
    ? `${withSpecies} [allow-variants]`
    : withSpecies;

  // The reference is part of the key for the same reason allowCrossSpecies
  // is, and the argument is ADR 0016's: two callers who state different
  // modelled conditions are asking different questions, and the answers
  // differ in the `conditionProximity` grade of every resolved parameter.
  //
  // Without this, a result graded `near` against a thermophile's 70 C would
  // be served to a caller who stated 37 C, carrying a reliability grade
  // computed against conditions they never described -- and every guard
  // downstream would pass, because the value really was resolved and really
  // was cited. Exactly the shape of the cross-species cache leak this
  // function already guards against, one field over.
  //
  // Only appended when a reference was supplied, so entries written before
  // this existed still hit for the no-reference path rather than being
  // silently invalidated.
  if (!physiologicalReference) return withVariants;
  const r = physiologicalReference;
  return (
    `${withVariants} [ref ${r.ph}/${r.temperatureC}` +
    `±${r.phTolerance}/${r.temperatureToleranceC} ${r.basis.trim().toLowerCase()}]`
  );
}

/**
 * GET /api/simulate/:jobId
 *
 * Returns the current state of a simulation job, including its result if it
 * has completed.
 */
router.get(
  "/simulate/:jobId",
  async (req: Request, res: Response, next: NextFunction) => {
    try {
      const params = GetSimulationJobParams.safeParse(req.params);
      if (!params.success) {
        res.status(400).json({
          error: "BAD_REQUEST",
          message: params.error.errors.map((e) => e.message).join("; "),
        });
        return;
      }

      const job = queue.getJob(params.data.jobId);
      if (!job) {
        res
          .status(404)
          .json({ error: "NOT_FOUND", message: "Simulation job not found" });
        return;
      }

      if (job.result) guardSerializationProvenance(job.result);

      res.json(job);
    } catch (err) {
      next(err);
    }
  },
);

/**
 * GET /api/simulate/:jobId/stream
 *
 * Server-Sent Events endpoint that pushes the job state every time it changes.
 * The stream closes automatically once the job reaches a terminal state
 * (completed or failed).
 */
router.get(
  "/simulate/:jobId/stream",
  async (req: Request, res: Response, next: NextFunction) => {
    try {
      const params = StreamSimulationJobParams.safeParse(req.params);
      if (!params.success) {
        res.status(400).json({
          error: "BAD_REQUEST",
          message: params.error.errors.map((e) => e.message).join("; "),
        });
        return;
      }

      const { jobId } = params.data;
      const job = queue.getJob(jobId);
      if (!job) {
        res
          .status(404)
          .json({ error: "NOT_FOUND", message: "Simulation job not found" });
        return;
      }

      res.setHeader("Content-Type", "text/event-stream");
      res.setHeader("Cache-Control", "no-cache");
      res.setHeader("Connection", "keep-alive");
      res.flushHeaders();

      const send = (data: queue.Job) => {
        if (data.result) guardSerializationProvenance(data.result);
        res.write(`data: ${JSON.stringify(data)}\n\n`);
      };

      send(job);

      const unsubscribe = queue.subscribe(jobId, (updated) => {
        send(updated);
        if (
          updated.status === "completed" ||
          updated.status === "failed" ||
          updated.status === "cancelled"
        ) {
          unsubscribe();
          queue.cleanupJob(jobId);
          res.end();
        }
      });

      req.on("close", () => {
        unsubscribe();
      });
    } catch (err) {
      next(err);
    }
  },
);

/**
 * POST /api/simulate/:jobId/cancel
 *
 * Cancels a running simulation job. Jobs in terminal states are no-ops.
 * The pipeline runner checks for cancellation between stages and the
 * Python process receives SIGTERM.
 */
router.post(
  "/simulate/:jobId/cancel",
  async (req: Request, res: Response, next: NextFunction) => {
    try {
      const jobId = req.params.jobId as string;
      const job = queue.getJob(jobId);
      if (!job) {
        res
          .status(404)
          .json({ error: "NOT_FOUND", message: "Simulation job not found" });
        return;
      }
      if (TERMINAL.has(job.status)) {
        res.status(409).json({
          error: "ALREADY_TERMINAL",
          message: `Job is already ${job.status}`,
        });
        return;
      }
      const updated = queue.cancelJob(jobId);
      logger.info({ jobId, status: updated?.status }, "Job cancelled");
      res.json(updated);
    } catch (err) {
      next(err);
    }
  },
);

/**
 * GET /api/simulate/:jobId/export
 *
 * Export the simulation trajectory as a CSV file. Great for researchers
 * who want to import results into R, Python, or Excel.
 */
router.get(
  "/simulate/:jobId/export",
  async (req: Request, res: Response, next: NextFunction) => {
    try {
      const jobId = req.params.jobId as string;
      const job = queue.getJob(jobId);
      if (!job) {
        res
          .status(404)
          .json({ error: "NOT_FOUND", message: "Simulation job not found" });
        return;
      }
      if (
        !job.result ||
        !job.result.trajectory ||
        job.result.trajectory.length === 0
      ) {
        res.status(409).json({
          error: "NO_DATA",
          message: "Job has no trajectory data to export",
        });
        return;
      }

      // The provenance rides WITH the data, in the same file.
      //
      // This route returned bare numbers, described in its own docstring as
      // being for import into R, Python or Excel. That file is the artifact
      // that outlives the session and ends up in a lab report, and it
      // carried no citation at all -- in a project whose whole claim is
      // that every number traces to a source. See ADR 0050.
      const csv = buildTrajectoryCsv({
        runId: job.result.runId,
        domain: job.result.domain,
        completedAt: job.result.completedAt,
        parameters: job.result.parameters,
        trajectory: job.result.trajectory,
        provenance: job.result.provenance,
        parameterProvenance: job.result.parameterProvenance,
      });

      res.setHeader("Content-Type", "text/csv");
      res.setHeader(
        "Content-Disposition",
        `attachment; filename="simulation-${jobId.slice(0, 8)}.csv"`,
      );
      res.send(csv);
    } catch (err) {
      next(err);
    }
  },
);

/**
 * GET /api/simulate/:jobId/confidence
 *
 * Per-parameter confidence scores and explanations.
 * Shows why each parameter has its value and how confident we are in it.
 */
router.get(
  "/simulate/:jobId/confidence",
  async (req: Request, res: Response, next: NextFunction) => {
    try {
      const jobId = req.params.jobId as string;
      const job = queue.getJob(jobId);
      if (!job) {
        res
          .status(404)
          .json({ error: "NOT_FOUND", message: "Simulation job not found" });
        return;
      }

      if (!job.result || !job.result.parameterProvenance) {
        res.status(409).json({
          error: "NO_PROVENANCE",
          message: "Job has no parameter provenance",
        });
        return;
      }

      const confidenceBreakdown = buildConfidenceBreakdown(
        numericParameters(job.result.parameters),
        job.result.parameterProvenance,
      );

      res.json(confidenceBreakdown);
    } catch (err) {
      next(err);
    }
  },
);

/**
 * GET /api/simulate/:jobId/audit
 *
 * Publication-ready audit of parameter provenance. Shows:
 * - Verification level (verified/flagged/pending/unverifiable)
 * - DOI/source for each parameter
 * - STRENDA compliance
 * - Confidence score
 * - Whether publication is blocked
 */
router.get(
  "/simulate/:jobId/audit",
  async (req: Request, res: Response, next: NextFunction) => {
    try {
      const jobId = req.params.jobId as string;
      const job = queue.getJob(jobId);
      if (!job) {
        res
          .status(404)
          .json({ error: "NOT_FOUND", message: "Simulation job not found" });
        return;
      }

      if (!job.result || !job.result.parameterProvenance) {
        res.status(409).json({
          error: "NO_PROVENANCE",
          message: "Job has no parameter provenance to audit",
        });
        return;
      }

      const auditReport = buildAuditReport(
        jobId,
        job.result.domain,
        numericParameters(job.result.parameters),
        job.result.parameterProvenance,
      );

      res.json(auditReport);
    } catch (err) {
      next(err);
    }
  },
);

/**
 * Build comprehensive audit report for publication
 */
interface ParameterAudit {
  name: string;
  value: number;
  origin: string;
  verificationLevel: string;
  confidence: number;
  doi?: string;
  pmid?: string;
  source?: string;
  strendaCompliant?: boolean;
  /** STRENDA requirement numbers not met. Requirement 7 (confidence
   * intervals) is expected here for every resolved value: no upstream
   * source Caterva reads supplies per-value intervals. */
  strendaUnmetRequirements?: number[];
  requiresReview: boolean;
  message: string;
}

interface AuditReport {
  jobId: string;
  domain: string;
  publicationReady: boolean;
  /**
   * What the data sources behind this run ask of someone who publishes it.
   *
   * `publicationReady` is a green light for putting these numbers in a
   * paper, and this report said nothing about the obligations that come
   * with doing so -- while NOTICE states that citing Caterva is not a
   * substitute for citing BRENDA. Empty when no described source
   * contributed. See dataSources.ts and ADR 0081.
   */
  dataSourceObligations: SourceObligation[];
  blockedParameters: string[];
  overallConfidence: number;
  parameterAudits: ParameterAudit[];
  /** Absent for a domain with no literature entry (sbml: the caller
   * supplies the model, so there is nothing for Caterva to cite). */
  domainCitation?: string;
  timestamp: string;
}

/**
 * Confidence breakdown per-parameter
 */
interface ConfidenceScore {
  name: string;
  value: number;
  origin: string;
  confidence: number;
  explanation: string;
  source?: string;
  doi?: string;
}

interface ConfidenceBreakdown {
  timestamp: string;
  overallConfidence: number;
  parameters: ConfidenceScore[];
}

function buildConfidenceBreakdown(
  parameters: Record<string, number | number[]>,
  provenance: Record<string, ParameterProvenance>,
): ConfidenceBreakdown {
  const scores: ConfidenceScore[] = [];
  let confidenceSum = 0;
  let confidenceCount = 0;

  for (const [name, value] of Object.entries(parameters)) {
    const prov = provenance[name];
    if (!prov || Array.isArray(value)) continue;

    const reference = literatureReferenceFromProvenance(prov);
    const verification = verifyParameterAgainstLiterature(
      name,
      value,
      prov.origin as "resolved" | "keyword" | "llm" | "user" | "default",
      reference,
    );

    scores.push({
      name,
      value,
      origin: prov.origin,
      confidence: verification.confidence,
      explanation: verification.message,
      source: reference?.source,
      doi: reference?.doi,
    });

    confidenceSum += verification.confidence;
    confidenceCount++;
  }

  const overallConfidence =
    confidenceCount > 0 ? confidenceSum / confidenceCount : 0;

  return {
    timestamp: new Date().toISOString(),
    overallConfidence,
    parameters: scores,
  };
}

function buildAuditReport(
  jobId: string,
  domain: string,
  parameters: Record<string, number | number[]>,
  provenance: Record<string, ParameterProvenance>,
): AuditReport {
  const parameterAudits: ParameterAudit[] = [];
  const blockedParameters: string[] = [];
  let confidenceSum = 0;
  let confidenceCount = 0;

  for (const [name, value] of Object.entries(parameters)) {
    const prov = provenance[name];
    if (!prov) continue;
    // Array-valued parameters (e.g. starting_frequencies for two-locus
    // Wright-Fisher) have no single scalar to run through the
    // literature/STRENDA numeric checks below, which are built around one
    // kinetic-style value. Audited by presence/origin only.
    if (typeof value !== "number") {
      parameterAudits.push({
        name,
        value: NaN,
        origin: prov.origin,
        verificationLevel: "unverifiable",
        confidence: prov.origin === "user" ? 1.0 : 0,
        requiresReview: false,
        message: Array.isArray(value)
          ? "Array-valued parameter; not individually verified against literature."
          : "Non-numeric parameter; not individually verified against literature.",
      });
      continue;
    }

    const reference = literatureReferenceFromProvenance(prov);
    const verification = verifyParameterAgainstLiterature(
      name,
      value,
      prov.origin as "resolved" | "keyword" | "llm" | "user" | "default",
      reference,
    );

    const audit: ParameterAudit = {
      name,
      value,
      origin: prov.origin,
      verificationLevel: verification.level,
      confidence: verification.confidence,
      doi: reference?.doi,
      pmid: reference?.pmid,
      source: reference?.source,
      requiresReview: verification.requiresManualReview,
      message: verification.message,
    };

    // Check STRENDA compliance if applicable
    // STRENDA governs ENZYME KINETIC CONSTANTS -- km, ki, kcat, vmax -- and
    // nothing else. This previously gated on the DOMAIN name, so every
    // numeric parameter of an mm run got a STRENDA verdict, including `end`
    // and `points`. Reporting that an integration window is
    // "STRENDA non-compliant" is the ADR 0021 error resurfacing at a route
    // that bypassed the guard ADR 0021 installed.
    //
    // The bounds are also passed through now. Omitting them forced a
    // Requirement-7 violation on every call, capping `score` at 3 when
    // `compliant` needs >= 4 -- so `strendaCompliant` could never be true
    // for any parameter, in any domain, ever. It was a field that only ever
    // said "no".
    if (STRENDA_GOVERNED_FIELDS.has(name.toLowerCase())) {
      // Confidence bounds are genuinely absent: ParameterProvenance does
      // not carry them, because neither BRENDA rows nor the ADR 0017
      // registry report per-value intervals. So STRENDA Requirement 7 is
      // legitimately unmet and `compliant` is legitimately false -- the
      // defect was never the value, it was reporting a bare `false` with
      // no way to tell "we failed the standard" from "we never checked".
      //
      // The unmet requirement numbers are surfaced so a reader can see
      // which parts of the standard are outstanding and which are met.
      const strendaResult = validateSTREANDA(
        value,
        prov.assayConditions,
        undefined,
        undefined,
      );
      audit.strendaCompliant = strendaResult.compliant;
      audit.strendaUnmetRequirements = strendaResult.violations.map(
        (violation) => violation.requirement,
      );
    }

    parameterAudits.push(audit);
    confidenceSum += verification.confidence;
    confidenceCount++;

    if (verification.level === "pending") {
      blockedParameters.push(name);
    }
  }

  const overallConfidence =
    confidenceCount > 0 ? confidenceSum / confidenceCount : 0;
  const publicationReady = blockedParameters.length === 0;

  return {
    // Threaded from the caller. This was `""` with the comment "will be
    // set by caller if needed" -- the caller never did, so every audit
    // response identified itself as job "". The route test asserted the
    // presence of five other fields and never looked at this one.
    jobId,
    domain,
    publicationReady,
    // Derived from the provenance actually present: a source that supplied
    // nothing is not listed, because an obligation to cite data the run did
    // not use is a false one.
    dataSourceObligations: citationObligations(provenance),
    blockedParameters,
    overallConfidence,
    parameterAudits,
    ...(getDomainCitation(domain) !== undefined
      ? { domainCitation: getDomainCitation(domain) as string }
      : {}),
    timestamp: new Date().toISOString(),
  };
}

/**
 * Look up a previously-completed simulation with the same query. This is a
 * naive but effective cache: identical natural-language queries produce the
 * same resolved parameters, so we can short-circuit the engine entirely.
 */
/**
 * A cached result, labelled as a replay and dated.
 *
 * Returns a COPY. Mutating the stored entry would persist the flag and
 * accumulate one per replay, so the n-th reader of a popular query would
 * see n identical notices.
 */
function withReplayProvenance(cached: {
  result: queue.SimulationResponse;
  cachedAt: string;
}): queue.SimulationResponse {
  const { result, cachedAt } = cached;
  return {
    ...result,
    provenance: {
      ...result.provenance,
      flags: [
        ...result.provenance.flags,
        `served_from_cache: this result was computed on ${cachedAt} and ` +
          `replayed unchanged. Nothing was re-resolved, so any literature ` +
          `curated since that date is not reflected here.`,
      ],
    },
  };
}

async function findCachedSimulation(
  query: string,
): Promise<
  { result: queue.SimulationResponse; cachedAt: string } | undefined
> {
  try {
    const db = await getDb();
    if (!db) return undefined;

    // The query builder, its SQL helpers, and the table schema are loaded
    // only when a database query is actually possible, so route modules
    // that never touch the database never evaluate Drizzle.
    const [{ desc, sql }, { simulationsTable }] = await Promise.all([
      import("drizzle-orm"),
      import("@workspace/db/schema"),
    ]);

    const rows = await db
      .select()
      .from(simulationsTable)
      .where(
        sql`lower(trim(regexp_replace(${simulationsTable.query}, '\\s+', ' ', 'g'))) = ${query}`,
      )
      .orderBy(desc(simulationsTable.createdAt))
      .limit(1);

    if (rows.length === 0) return undefined;

    const row = rows[0];
    if (!row) return undefined;

    return {
      // The row's own createdAt, which is also what the replay notice
      // dates itself by -- one source, so the body and the flag cannot
      // disagree about when this was computed.
      cachedAt: row.createdAt.toISOString(),
      result: {
        runId: String(row.id),
        domain: row.domain,
        parameters: (row.parameters as Record<string, unknown>) || {},
        trajectory: (row.trajectory as Record<string, unknown>[]) || [],
        provenance: (row.provenance as {
          reasoning: string;
          modelCitations: string[];
          flags: string[];
        }) || {
          reasoning: "",
          modelCitations: [],
          flags: [],
        },
        parameterProvenance:
          (row.parameterProvenance as Record<string, ParameterProvenance>) || {},
        completedAt: row.createdAt.toISOString(),
      },
    };
  } catch (err) {
    logger.warn({ err }, "Cache lookup failed; continuing without cache");
    return undefined;
  }
}

/**
 * The core science-agent pipeline. Each stage updates the job state so that
 * SSE and polling clients can observe progress.
 *
 * Stages:
 *   1. Resolve domain and parameters (keyword/regex or LLM fallback).
 *   2. Validate parameters.
 *   3. Run the Caterva engine (with concurrency limit).
 *   4. Persist to PostgreSQL for provenance.
 *   5. Mark job completed (or failed).
 *
 * Between each stage we check for cancellation. Jobs that are cancelled
 * mid-flight are marked as cancelled rather than failed.
 */
/**
 * Run a caller-supplied model. Deliberately NOT runPipeline().
 *
 * runPipeline's stages are resolve -> validate -> run -> persist, and the
 * first two have nothing to do here: there is no query to classify and no
 * parameter to look up, because the caller wrote the model. Reusing it
 * would mean threading "skip this stage" flags through every step, which is
 * how a pipeline stops being readable.
 *
 * PROVENANCE. A parameter the caller typed is origin "user" -- not a
 * weaker claim than the preset domains make for an inline `km=2`, exactly
 * the same claim. `modelCitations` stays empty because Caterva did not
 * choose the model's structure and must not imply a source for it.
 *
 * LITERATURE GROUNDING. Everything above used to be the whole story, and
 * it made this endpoint useless for the people it was built for: a lab
 * brought their own model and Caterva's entire reason to exist -- every
 * number traceable -- switched off, leaving plain Tellurium with extra
 * steps. Nothing was checked, nothing was cited.
 *
 * A caller can now DECLARE what a parameter is, in a comment:
 *
 *     // caterva: km enzyme="hexokinase" substrate="glucose" unit="mM"
 *     Km_hex = 0.15;
 *
 * and Caterva resolves it, reports what the literature says beside what
 * the model says, and attaches the citation. Adding `resolve` to the
 * declaration hands the number over entirely: it is filled from
 * literature, or THE RUN REFUSES -- there is no fallback value, because a
 * fallback is the fabrication this project exists to prevent.
 *
 * Declarations are never inferred. See modelAnnotations.ts for why
 * reading "hexokinase" out of a parameter named `Km_hex` is the one thing
 * this must not do.
 */
async function runCustomModelPipeline(
  jobId: string,
  model: {
    antimony?: string | undefined;
    sbml?: string | undefined;
    start?: number | null | undefined;
    end?: number | null | undefined;
    points?: number | null | undefined;
  },
): Promise<void> {
  const abort = new AbortController();
  queue.registerAbortController(jobId, abort);

  try {
    if (queue.isCancelled(jobId)) return;
    queue.updateJob(jobId, { status: "running" });

    // Ground the caller's declarations BEFORE simulating. A `resolve`
    // annotation changes the model source, so this has to happen first;
    // and a model whose declarations are wrong should not consume an
    // engine run at all.
    //
    // Both formats. SBML uses the same declaration in an XML comment or
    // a <notes> element, naming its parameter explicitly. SBML is the
    // interchange format labs actually use, so Antimony-only grounding
    // would have shut most of them out of this entirely.
    let grounding: ModelGroundingReport | undefined;
    let antimony = model.antimony;
    let sbml = model.sbml;
    const declared = antimony ?? sbml;
    const format = antimony !== undefined ? "antimony" : "sbml";
    if (declared !== undefined) {
      // modelGrounding pulls in queryResolver and the resolution graph;
      // load it only when a custom model actually needs grounding.
      const { groundAnnotatedModel } = await import("../lib/modelGrounding");
      grounding = await groundAnnotatedModel(declared, { format });

      if (grounding.problems.length > 0) {
        queue.setJobError(jobId, {
          error: "MODEL_ERROR",
          message:
            "This model's caterva annotations could not be read:\n" +
            grounding.problems
              .map((p) => `  line ${p.line}: ${p.message}`)
              .join("\n"),
        });
        persistJob(queue.getJob(jobId)!).catch(() => {});
        return;
      }

      if (grounding.blocking.length > 0) {
        // A `resolve` declaration is a request for a literature value.
        // Running anyway would mean simulating with whatever placeholder
        // was in the source, which is the fabricated number this refuses.
        queue.setJobError(jobId, {
          error: "MODEL_ERROR",
          message:
            "Caterva could not supply every value you asked it to " +
            "resolve, and will not substitute one it cannot cite:\n" +
            grounding.blocking.map((b) => `  ${b}`).join("\n"),
        });
        persistJob(queue.getJob(jobId)!).catch(() => {});
        return;
      }

      if (grounding.groundedSource !== undefined) {
        if (format === "antimony") antimony = grounding.groundedSource;
        else sbml = grounding.groundedSource;
      }
    }

    if (queue.isCancelled(jobId)) {
      queue.setJobCancelled(jobId);
      return;
    }

    const parameters: Record<string, string | number> = {};
    if (antimony !== undefined) parameters["antimony_string"] = antimony;
    if (sbml !== undefined) parameters["sbml_string"] = sbml;
    if (model.start !== undefined && model.start !== null) {
      parameters["start"] = model.start;
    }
    if (model.end !== undefined && model.end !== null) {
      parameters["end"] = model.end;
    }
    if (model.points !== undefined && model.points !== null) {
      parameters["points"] = model.points;
    }

    const engineResult = await runCaterva("sbml", parameters, abort.signal);

    if (queue.isCancelled(jobId)) {
      queue.setJobCancelled(jobId);
      return;
    }

    // Every value came from the caller. `unverifiedOriginKeys` looks for
    // origin "default" -- a value nobody chose -- and there are none here
    // by construction, so the hard rule is satisfied rather than bypassed.
    const parameterProvenance: Record<string, ParameterProvenance> = {};
    for (const key of Object.keys(engineResult.parameters)) {
      parameterProvenance[key] = { origin: "user" };
    }

    // A grounded parameter is origin "resolved" and carries its citation,
    // exactly as it would on the query path. A `check` parameter stays
    // origin "user" -- the caller's number still stands, it has simply
    // been compared -- but gains the note and the citation, so a reader
    // sees both numbers and can judge the difference themselves.
    const grounded = grounding?.entries ?? [];
    for (const entry of grounded) {
      if (entry.status !== "grounded") continue;
      const comparison =
        entry.comparison === undefined
          ? entry.comparisonSkipped
            ? ` Not compared: ${entry.comparisonSkipped}`
            : ""
          : ` Literature, in your unit: ` +
            `${entry.comparison.literatureInYourUnit} ${entry.yourUnit ?? ""}.` +
            (entry.comparison.foldDifference === undefined
              ? ""
              : ` Your model: ${entry.yourValue} ${entry.yourUnit ?? ""} ` +
                `(${entry.comparison.foldDifference.toFixed(2)}x apart).`);

      parameterProvenance[entry.parameter] = {
        origin: entry.mode === "resolve" ? "resolved" : "user",
        citation: entry.citation,
        citationStatus: entry.crossSpecies ? "flagged" : "verified",
        citationLocators: entry.citationLocators,
        note: entry.note + comparison,
      };
    }

    const groundedCitations = grounded
      .filter((e) => e.status === "grounded" && e.citation)
      .map((e) => e.citation as string);

    const result: queue.SimulationResponse = {
      runId: jobId,
      // This path only ever runs `sbml`; the narrowing is checked rather
      // than cast so a future composed domain reaching here fails loudly.
      domain: asSimulationDomain(engineResult.domain),
      parameters: engineResult.parameters,
      trajectory: engineResult.trajectory,
      provenance: {
        reasoning:
          "Caller-supplied model, simulated as given. Caterva did not " +
          "choose the structure" +
          (grounded.length > 0
            ? ", and every parameter value is the caller's except those " +
              "declared `resolve`, which were taken from the literature " +
              "cited below."
            : " or any parameter value, and claims no literature backing " +
              "for them."),
        // Citations here name sources for individual PARAMETERS the
        // caller declared, never for the model structure -- that is the
        // caller's and Caterva must not imply a source for it.
        modelCitations: groundedCitations,
        flags: [
          ...(engineResult.flagged && engineResult.flagReason
            ? [engineResult.flagReason]
            : []),
          ...grounded
            .filter((e) => e.status !== "grounded")
            .map((e) => `${e.parameter}: ${e.note}`),
        ],
      },
      parameterProvenance,
      modelGrounding: grounded.length > 0 ? grounded : undefined,
      completedAt: new Date().toISOString(),
    };

    queue.setJobResult(jobId, result);
    persistJob(queue.getJob(jobId)!).catch(() => {});
  } catch (err) {
    if (abort.signal.aborted || queue.isCancelled(jobId)) {
      queue.setJobCancelled(jobId);
    } else {
      // The engine's guards (path/URL refusal, antimony import refusal,
      // the MAX_API_SBML_* ceilings) all surface as its own message, which
      // names what to change. MODEL_ERROR rather than PIPELINE_ERROR: this
      // is fixable by editing the model, which a pipeline error is not.
      queue.setJobError(jobId, {
        error: "MODEL_ERROR",
        message:
          err instanceof Error ? err.message : "Unexpected model failure",
      });
    }
    persistJob(queue.getJob(jobId)!).catch(() => {});
  }
}

async function runPipeline(
  jobId: string,
  query: string,
  allowCrossSpecies = false,
  allowVariants = false,
  physiologicalReference?: RunSimulationRequest["physiologicalReference"],
): Promise<void> {
  const abort = new AbortController();
  queue.registerAbortController(jobId, abort);

  try {
    if (queue.isCancelled(jobId)) return;

    queue.updateJob(jobId, { status: "resolving" });
    // Deferred: the resolution graph is large and only needed once a job
    // actually starts resolving.
    const { resolveQuery } = await import("../lib/queryResolver");
    const resolved = await resolveQuery(query, {
      allowCrossSpecies,
      allowVariants,
      physiologicalReference,
    });

    if (queue.isCancelled(jobId)) return;
    queue.updateJob(jobId, { status: "validating" });
    validateParameters(resolved.domain, resolved.parameters);

    if (queue.isCancelled(jobId)) return;
    queue.updateJob(jobId, { status: "running" });

    await queue.acquireRunnerSlot();
    if (abort.signal.aborted || queue.isCancelled(jobId)) {
      queue.releaseRunnerSlot();
      return;
    }

    let engineResult;
    try {
      engineResult = await runCaterva(
        resolved.domain,
        resolved.parameters,
        abort.signal,
      );
    } finally {
      queue.releaseRunnerSlot();
    }

    if (queue.isCancelled(jobId)) return;

    // The engine can return parameters resolveQuery() never saw -- most
    // notably an auto-generated `seed` for stochastic domains (ADR 0005:
    // numpy.random.default_rng(seed)) when the query didn't supply one.
    // That seed is real and belongs in the response (it's what a student
    // needs to reproduce this exact run), but it isn't a "default" in the
    // fallback-constant sense and it isn't literature-backed -- it's an
    // engine-generated reproducibility nonce. Give it its own honest
    // provenance entry rather than leaving it un-tagged, which previously
    // reached guardSerializationProvenance() as a silent violation.
    const parameterProvenance = { ...resolved.parameterProvenance };
    for (const key of Object.keys(engineResult.parameters)) {
      if (!(key in parameterProvenance)) {
        parameterProvenance[key] = {
          origin: "default",
          note:
            key === "seed"
              ? "Auto-generated by the engine for reproducibility (ADR 0005); " +
                "not a scientific claim. Re-run with seed=<this value> to reproduce " +
                "this exact trajectory."
              : "Added by the engine after literature/user resolution; not " +
                "traceable to a literature lookup or explicit user input.",
        };
      }
    }

    // The reverse direction, which the loop above does not cover: a
    // parameter the RESOLVER established that the engine does not echo
    // back. `enzyme_conc` is the live case -- run_mm consumes it to build
    // Vmax and returns only the engine's own parameter set, so a query
    // saying "with 50 nM enzyme" produced a response carrying provenance
    // for enzyme_conc and no enzyme_conc.
    //
    // That orphan tripped guardSerializationProvenance on EVERY query
    // using the kcat bridge, which is the headline enzyme-kinetics path,
    // and the flag it emitted told the reader nothing.
    //
    // Fixed by keeping the value, not by dropping the provenance. [E]0 is
    // what makes the derived Vmax checkable: without it a reader is asked
    // to accept Vmax = kcat x [E]0 while being shown neither factor. The
    // engine's value wins wherever both have the key, since the engine
    // may normalise; this only restores keys the engine omitted entirely.
    const responseParameters: Record<string, unknown> = {
      ...Object.fromEntries(
        Object.entries(resolved.parameters).filter(
          ([key]) => key in resolved.parameterProvenance,
        ),
      ),
      ...engineResult.parameters,
    };

    const provenance = {
      reasoning: resolved.provenance.reasoning,
      modelCitations: resolved.provenance.modelCitations,
      flags: [
        ...resolved.provenance.flags,
        ...(engineResult.flagged && engineResult.flagReason
          ? [engineResult.flagReason]
          : []),
      ],
    };
    const db = await getDb();
    if (db) {
      const { simulationsTable } = await import("@workspace/db/schema");
      await db.insert(simulationsTable).values({
        query,
        domain: asSimulationDomain(engineResult.domain),
        parameters: responseParameters,
        trajectory: engineResult.trajectory,
        provenance,
        parameterProvenance,
      });
    } else {
      logger.debug(
        { jobId },
        "Database unavailable; skipping persistence for this run",
      );
    }

    const result: queue.SimulationResponse = {
      runId: resolved.runId,
      // The resolver path yields catalogue domains only. Checked, not cast.
      domain: asSimulationDomain(engineResult.domain),
      parameters: responseParameters,
      trajectory: engineResult.trajectory,
      provenance,
      parameterProvenance,
      completedAt: new Date().toISOString(),
    };

    queue.setJobResult(jobId, result);
    persistJob(queue.getJob(jobId)!).catch(() => {});
  } catch (err) {
    if (abort.signal.aborted || queue.isCancelled(jobId)) {
      queue.setJobCancelled(jobId);
    } else if (err instanceof RequiredParametersMissingError) {
      // Not a pipeline failure -- the query itself was underspecified.
      // Distinguishing this from PIPELINE_ERROR matters to callers: this
      // one is fixable by editing the query, a real PIPELINE_ERROR isn't.
      queue.setJobError(jobId, {
        error: "MISSING_REQUIRED_INPUT",
        message: err.message,
      });
    } else if (err instanceof UnrecognizedQueryError) {
      // The catalogue gave up, but the composer may not have. Try to
      // compose the mechanism described before answering "unrecognized":
      // a practitioner who types a mechanism and is told "try vocabulary
      // closer to the fifteen supported domains" has been served worse than
      // they deserve, and has no idea whether the sentence itself was at
      // fault -- any grammar can only answer for the shapes it knows.
      const handled = await fallThroughToComposition(jobId, query, abort.signal);
      if (!handled) {
        // Not fixable by composition, or composition itself failed: keep the
        // resolver's refusal verbatim -- it is the one that explains the
        // fifteen domains.
        queue.setJobError(jobId, {
          error: "UNRECOGNIZED_QUERY",
          message: err.message,
        });
      }
    } else {
      queue.setJobError(jobId, {
        error: "PIPELINE_ERROR",
        message:
          err instanceof Error ? err.message : "Unexpected pipeline failure",
      });
    }
    persistJob(queue.getJob(jobId)!).catch(() => {});
  }
}

/**
 * Answer an unrecognized query through the composer, when the catalogue
 * cannot.
 *
 * Returns whether the job reached a terminal state. True when compose
 * built a mechanism (the job completes with a `composition` report) or
 * refused to build one (the job fails with a precise refusal message).
 * False when the composer could not run at all, so the caller keeps the
 * resolver's original refusal.
 *
 * A composed result is necessarily structure-only from this door: the
 * composer does not infer a subject enzyme from prose, and with no enzyme
 * named nothing is searched for. The honest answer is the mechanism and
 * the constants it needs (`composition.toResolve`), with `parameters`
 * deliberately empty and `trajectory` empty -- scaffold values are not
 * literature-resolved numbers, and a confidently wrong number is worse
 * than a refusal.
 */
async function fallThroughToComposition(
  jobId: string,
  query: string,
  signal: AbortSignal,
): Promise<boolean> {
  if (queue.isCancelled(jobId)) return true;

  await queue.acquireRunnerSlot();
  let engineResult: CatervaResult;
  try {
    engineResult = await runCaterva("compose", { description: query }, signal);
  } catch (err) {
    if (signal.aborted || queue.isCancelled(jobId)) {
      // The request owner walked away while the composer was working. That
      // is not a refusal -- the mechanism may well be right -- so mark the
      // job cancelled instead of answering "unrecognized".
      queue.setJobCancelled(jobId);
      return true;
    }
    logger.warn(
      { err, jobId },
      "Composition fallthrough failed; keeping the resolver's refusal",
    );
    return false;
  } finally {
    queue.releaseRunnerSlot();
  }

  if (queue.isCancelled(jobId)) return true;

  // The compose payload's mechanism keys (rule/reading/structureOnly/
  // network/...) are not declared on `CatervaResult`; they exist on the
  // JSON it parsed. Widening here is not a cast-of-convenience -- the
  // shape is checked by `toCompositionReport`, which is this module's
  // guard that the engine's report reached us in the form it promised.
  const payload = engineResult as unknown as {
    ok: boolean;
    built?: boolean;
    kind?: string;
    reason?: string;
    shapes?: string[];
    rule?: string;
    reading?: string;
    structureOnly?: boolean;
    network?: CompositionReport["network"];
    conservationLaws?: string[];
    notes?: string[];
    toResolve?: CompositionReport["toResolve"];
    yourChoice?: string[];
    unitFindings?: CompositionReport["unitFindings"];
    summary?: string;
  };

  if (!payload.ok || payload.built === undefined) return false;

  if (payload.built !== true) {
    const refusal: CompositionRefusal = {
      kind:
        payload.kind === "named_pathway"
          ? "named_pathway"
          : "unrecognised_shape",
      reason:
        payload.reason ??
        "compose declined to build this mechanism from the description",
      shapes: payload.shapes ?? [],
    };
    queue.setJobError(jobId, {
      error: "UNRECOGNIZED_QUERY",
      message: describeCompositionRefusal(refusal),
    });
    return true;
  }

  const composition = toCompositionReport(payload);
  const laws = payload.conservationLaws ?? [];

  const result: queue.SimulationResponse = {
    runId: jobId,
    domain: "compose",
    // Empty on purpose: nothing was resolved or simulated. The constants
    // this mechanism needs are listed in composition.toResolve.
    parameters: {},
    trajectory: [],
    provenance: {
      reasoning:
        payload.summary ??
        `Caterva built a mechanism for "${query}".`,
      modelCitations: [],
      flags: [
        ...(payload.structureOnly
          ? [
              "structure_only: no enzyme was named, so nothing was " +
                "searched for; the constants this mechanism requires are " +
                "listed in composition.toResolve.",
            ]
          : []),
        ...(laws.length > 0
          ? [
              `conservation_laws_derived: ${laws.join("; ")} -- computed ` +
                `from the composed mechanism's stoichiometry, not asserted.`,
            ]
          : []),
      ],
    },
    parameterProvenance: {},
    composition,
    completedAt: new Date().toISOString(),
  };

  queue.setJobResult(jobId, result);
  return true;
}

/**
 * A compose refusal is a result, not an exception, and the two refusal
 * kinds are different failures: a named pathway needs a pathway database
 * (editing the sentence won't help), an unrecognised shape means the
 * description disagreed with every shape the grammar knows (it might).
 * Say which.
 */
function describeCompositionRefusal(refusal: CompositionRefusal): string {
  const heading =
    refusal.kind === "named_pathway"
      ? "This names a pathway the composer does not hold. A named pathway "
        + "needs a pathway database to expand; editing the sentence will "
        + "not change the answer."
      : "The description did not match a mechanism shape the composer "
        + "knows how to build.";
  return (
    `${heading} ${refusal.reason}` +
    (refusal.shapes.length > 0
      ? ` -- recognised shapes were: ${refusal.shapes.join(", ")}`
      : "")
  );
}

/**
 * Structural validation of resolved parameters before invoking the engine.
 *
 * Shape validation (presence, numeric types, integer counts, the four-entry
 * haplotype array) happens here against the Zod schemas in `lib/schemas.ts`.
 * Scientific plausibility bounds remain in the engine only, so the two
 * layers cannot drift on physical constraints (ADR 0003). A malformed
 * request is rejected here with a structured message instead of reaching
 * Python and surfacing as a ValueError string.
 */
function validateParameters(
  domain: string,
  parameters: Record<string, unknown>,
): void {
  const schema = SimulationParameterSchemas[domain as SimulationDomain];
  if (!schema) {
    throw new Error(`Unknown simulation domain: ${domain}`);
  }

  const parse = schema.safeParse(parameters);
  if (!parse.success) {
    const messages = parse.error.errors.map(
      (e) => `parameter ${e.path.join(".")}: ${e.message}`,
    );
    throw new Error(`Invalid simulation parameters: ${messages.join("; ")}`);
  }
}

/**
 * Serialization-boundary provenance guard (ADR 0016 step 4 — the
 * generalizable fix).
 *
 * `validateParameterProvenance` is already enforced at computation time
 * (`queryResolver` throws on violation: ADR 0008 decision #3), but nothing
 * enforced it at the point a `SimulationResponse` is serialized back to the
 * client. The DB cache path builds its response by hand and shipped empty
 * per-parameter provenance (ADR 0016). Steps 1–3 of that ADR (schema column,
 * write at insert, read on cache path) fix *that instance*; this call is what
 * prevents the whole class from recurring through any future producer of
 * `SimulationResponse` — the same failure shape as the STRENDA gap: an
 * enforcement existed, and one path routed around it.
 *
 * Failure handling is log-and-flag, deliberately NOT throw-500. Rule 2 of
 * docs/CONSTITUTION.md draws the line between the *impossible* and the
 * *implausible-but-real*: reject the first, flag the second. A response with
 * missing per-parameter provenance is not structurally impossible — it still
 * satisfies the response schema, still carries correct numbers, and still
 * carries model-level provenance (reasoning/citations/flags). It is
 * degraded-but-real (the implausible tier), so we serve it but surface a flag
 * and log the violations. ADR 0008's hard rejection is the right behavior
 * where provenance is *guaranteed by construction* (fresh computation); it is
 * the wrong behavior at this boundary, which legitimately sees pre-migration
 * rows and would otherwise turn a working-but-degraded cache hit into an
 * availability regression (a 500 on every cache read).
 */
export function guardSerializationProvenanceForTests(
  result: queue.SimulationResponse,
): void {
  guardSerializationProvenance(result);
}

function guardSerializationProvenance(result: queue.SimulationResponse): void {
  const violations = validateParameterProvenance(
    result.parameters,
    result.parameterProvenance,
  );
  if (violations.length === 0) return;

  logger.warn(
    { violations, runId: result.runId, domain: result.domain },
    "SimulationResponse serialized with unsound parameter provenance",
  );

  // Name the violations. "See server log for details" is useless to
  // anyone using a hosted API -- it tells a reader something is wrong and
  // then withholds what, which is worse than silence because it costs
  // trust without buying understanding.
  //
  // `violations` is already a list of specific, readable sentences
  // ("kcat has a parameter value but no provenance"). Nothing in them is
  // sensitive: they name parameter keys and provenance shape, both of
  // which the response already carries in parameterProvenance.
  const detail = violations.slice(0, 5).join("; ");
  const flag =
    `parameter provenance is incomplete: ${detail}` +
    (violations.length > 5
      ? ` (and ${violations.length - 5} more)`
      : "");
  if (!result.provenance.flags.includes(flag)) {
    result.provenance.flags.push(flag);
  }
}

export default router;
