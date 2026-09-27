/**
 * Caterva Web Server
 *
 * REST API for scientific simulations
 * Serves interactive dashboard
 * Uses Node.js built-in HTTP module (no external dependencies)
 */

import * as http from 'http';
import * as fs from 'fs';
import * as path from 'path';
import * as yaml from 'js-yaml';
import { URL } from 'url';
import { logger } from '../logger';
import { describeError } from '../errors';
import ScientificPipeline from '../integration/scientificPipeline';
import { searchPubMedForEnzymeKinetics } from '../integrations/crossref-pubmed-real';
import { resolveDOIFromCrossRef } from '../integrations/crossref-pubmed-real';
// The SAME resolver the CLI uses. Not a second implementation and not a
// reimplementation over the api-server's HTTP surface: ADR 0027 records what
// happens when one score has two producers, and this endpoint exists
// precisely so the web page stops being a second-class citizen with a
// different answer.
import { resolveKinetic, ResolverUnavailableError } from '../literature/literatureResolver';
import { runSweep, parseSweepParameter } from '../engine/parameter-sweep';
import { processBatch, createMultiParamBatchJobs } from '../engine/batch-processor';
import { compareModels, fitRankingFor } from '../engine/model-comparison';
import { getDefaultDatabase } from '../storage/job-database';
import { recordRequest, getPerfSnapshot } from './perfCollector';
import {
  cacheKey,
  getCacheStats,
  isCacheable,
  readCache,
  writeCache,
} from './responseCache';
import {
  exportJobHistoryToCSV,
  exportSweepToCSV,
  exportBatchToCSV,
  exportComparisonToCSV,
  exportStatisticsToCSV
} from '../storage/csv-exporter';
import {
  compareJobs,
  compareMultipleJobs,
  analyzeSensitivity
} from '../storage/result-comparator';
import {
  validateSimulationRequest,
  validateSweepRequest,
  validateBatchRequest,
  validateComparisonRequest,
  validateJobComparisonRequest,
  formatValidationErrors
} from '../validation/request-validator';
import {
  parseQueryString,
  filterJobs,
  FilterPresets
} from '../storage/job-query-builder';
import { getMetricsCollector } from '../storage/metrics-collector';
import { generatePrometheusMetrics } from './metrics-exporter';
import {
  getAllSweepMetrics,
  getSweepMetrics,
  getSweepMetricsByQuery,
  getAllBatchMetrics,
  getBatchMetrics,
  getBatchMetricsByQuery
} from '../storage/sweep-batch-metrics';

const PORT = parseInt(process.env.PORT || '3000', 10);
const db = getDefaultDatabase();
const metrics = getMetricsCollector();

// In-memory job storage
const jobs = new Map<string, any>();
const sweeps = new Map<string, any>();
const batches = new Map<string, any>();

// ============================================================================
// HTTP SERVER
// ============================================================================

const server = http.createServer(async (req, res) => {
  // Enable CORS
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') {
    res.writeHead(200);
    res.end();
    return;
  }

  const url = new URL(req.url || '', `http://${req.headers.host}`);
  const pathname = url.pathname;

  // Timing wraps EVERY response, including the ones that throw and the
  // 404, by hooking res.end rather than by remembering to call a recorder
  // in each of the forty branches below. A perf collector that only sees
  // the paths someone remembered to instrument reports the healthy subset
  // of the system and calls it the system.
  const startedAt = Date.now();
  const originalEnd = res.end.bind(res);
  let recorded = false;
  (res as any).end = function patchedEnd(this: unknown, ...args: unknown[]) {
    if (!recorded) {
      recorded = true;
      recordRequest(pathname, req.method || 'GET', Date.now() - startedAt, res.statusCode);
    }
    return (originalEnd as (...a: unknown[]) => unknown).apply(this, args);
  };

  // Short-TTL cache for read-only aggregates (allowlist in responseCache.ts).
  if (isCacheable(pathname, req.method || 'GET')) {
    const key = cacheKey(pathname, url.search);
    const cached = readCache(key);
    if (cached !== null) {
      res.writeHead(200, { 'Content-Type': 'application/json', 'X-Cache': 'HIT' });
      res.end(cached);
      return;
    }
    // Set HERE, not in the patched `end` below.
    //
    // It used to be `res.setHeader('X-Cache', 'MISS')` inside `cachingEnd`,
    // and that killed the whole server on every cache miss. Each handler
    // calls `res.writeHead(...)` before `res.end(...)`, so by the time the
    // patched `end` ran the headers were already sent and `setHeader` threw
    // `ERR_HTTP_HEADERS_SENT`. The throw reached the outer catch, which
    // called `res.writeHead(500, ...)` on the same sent response, threw
    // again from inside the catch, and took the process down.
    //
    //     $ curl localhost:3000/api/metrics    -> connection reset
    //     $ curl localhost:3000/api/health     -> connection refused
    //
    // Every allowlisted route — /api/stats and the /api/metrics family, the
    // ones the dashboard polls — was fatal on first request. The second
    // request would have been a cache HIT and fine; the server never lived
    // to serve it.
    //
    // We are inside `cached === null`, so this IS a miss and can be declared
    // immediately. Nothing has written to the response yet, and a header set
    // before `writeHead` survives the merge — verified, not assumed.
    res.setHeader('X-Cache', 'MISS');

    // Capture this response so the next identical request can be served
    // from memory. Only 200s are stored: caching an error would make a
    // transient failure look persistent for the whole TTL.
    const capturingEnd = res.end.bind(res);
    (res as any).end = function cachingEnd(this: unknown, chunk?: unknown, ...rest: unknown[]) {
      if (res.statusCode === 200 && typeof chunk === 'string') {
        writeCache(key, chunk);
      }
      return (capturingEnd as (...a: unknown[]) => unknown).apply(this, [chunk, ...rest]);
    };
  }

  try {
    // POST /api/simulate
    if (pathname === '/api/simulate' && req.method === 'POST') {
      let body = '';
      req.on('data', chunk => (body += chunk));
      req.on('end', async () => {
        try {
          const data = JSON.parse(body);

          // Validate request
          const validation = validateSimulationRequest(data);
          if (!validation.valid) {
            res.writeHead(400, { 'Content-Type': 'application/json' });
            res.end(formatValidationErrors(validation.errors));
            return;
          }

          const { query, parameters, enzyme, substrate } = data;

          const jobId = `job_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
          logger.info({ jobId, query }, 'API: Simulation requested');

          res.writeHead(200, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ jobId, status: 'queued' }));

          // Background job processing
          (async () => {
            try {
              jobs.set(jobId, { status: 'running', startTime: Date.now(), progress: 0 });

              let literature: any[] = [];
              if (enzyme && substrate) {
                try {
                  jobs.set(jobId, { ...jobs.get(jobId), progress: 10 });
                  const papers = await searchPubMedForEnzymeKinetics(enzyme, substrate, 5);

                  for (const paper of papers) {
                    if (!paper.doi) continue;
                    try {
                      const resolved = await resolveDOIFromCrossRef(paper.doi);
                      if (resolved) {
                        literature.push({
                          id: `lit_${paper.pmid}`,
                          doi: paper.doi,
                          pubmedId: paper.pmid.toString(),
                          title: paper.title,
                          authors: paper.authors || [],
                          year: paper.year,
                          journal: paper.journal || 'Unknown',
                          peerReviewed: false,
                          abstract: paper.abstract || '',
                          domain: 'mm',
                          extractedParameters: []
                        });
                      }
                    } catch (e) {
                      // Skip unresolvable papers
                    }
                  }
                  jobs.set(jobId, { ...jobs.get(jobId), progress: 30 });
                } catch (e) {
                  logger.warn({ jobId, error: e }, 'Literature fetch failed');
                }
              }

              jobs.set(jobId, { ...jobs.get(jobId), progress: 50 });

              const pipeline = new ScientificPipeline();
              pipeline.initializeLiterature(literature);

              const response = await pipeline.execute({
                query,
                parameters
              });

              const jobStartTime = jobs.get(jobId)?.startTime || Date.now();
              const jobEndTime = Date.now();
              const duration = jobEndTime - jobStartTime;
              jobs.set(jobId, {
                status: 'complete',
                progress: 100,
                result: response,
                endTime: jobEndTime,
                duration
              });

              // Persist to database
              db.saveJob({
                jobId,
                query,
                parameters,
                status: 'complete',
                result: response,
                startTime: jobStartTime,
                endTime: jobEndTime,
                duration
              });

              // Feed the real metrics collector -- previously nothing in
              // production ever called recordExecution(), so every
              // /api/metrics/* endpoint reported "no data" forever
              // regardless of how many simulations actually ran. This is
              // the only writer for the /api/simulate path; /api/sweep
              // and /api/batch do not yet call recordExecution() and are
              // not reflected in these metrics.
              metrics.recordExecution({
                jobId,
                query,
                startTime: jobStartTime,
                endTime: jobEndTime,
                executionTimeMs: duration,
                convergenceSteps: response.results?.trajectory?.length ?? 0,
                success: response.validated === true,
                errorMessage: response.validated ? undefined : response.validationErrors?.join('; ')
              });

              logger.info({ jobId, validated: response.validated }, 'Simulation complete');
            } catch (error) {
              const jobStartTime = jobs.get(jobId)?.startTime || Date.now();
              const jobEndTime = Date.now();
              jobs.set(jobId, {
                status: 'error',
                error: describeError(error),
                endTime: jobEndTime,
                duration: jobEndTime - jobStartTime
              });
              metrics.recordExecution({
                jobId,
                query,
                startTime: jobStartTime,
                endTime: jobEndTime,
                executionTimeMs: jobEndTime - jobStartTime,
                convergenceSteps: 0,
                success: false,
                errorMessage: describeError(error)
              });
              logger.error({ jobId, error }, 'Simulation error');
            }
          })();
        } catch (e) {
          res.writeHead(400, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ error: 'Invalid JSON' }));
        }
      });
      return;
    }

    // GET /api/jobs/history (list all jobs)
    // NOTE: must be registered before the /api/jobs/:jobId catch-all below,
    // otherwise the :jobId regex matches the literal string "history" and
    // shadows this route (same for /api/jobs/query).
    if (pathname === '/api/jobs/history' && req.method === 'GET') {
      const recentJobs = db.getRecentJobs(50);
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ jobs: recentJobs, count: recentJobs.length }));
      return;
    }

    // GET /api/jobs/query (advanced job query with filters)
    // NOTE: must also be registered before /api/jobs/:jobId — see above.
    if (pathname === '/api/jobs/query' && req.method === 'GET') {
      const url = new URL(req.url || '', `http://${req.headers.host}`);
      const queryStr = url.search.substring(1); // Remove leading '?'

      const filter = parseQueryString(queryStr);
      const allJobs = db.getRecentJobs(10000); // Get all for filtering
      const result = filterJobs(allJobs, filter);

      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify(result));
      return;
    }

    // GET /api/jobs/:jobId
    if (pathname.match(/^\/api\/jobs\/[a-z0-9_]+$/i) && req.method === 'GET') {
      const jobId = pathname.split('/').pop();
      const job = jobs.get(jobId || '') || db.getJob(jobId || '');

      if (!job) {
        res.writeHead(404, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: 'Job not found' }));
        return;
      }

      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify(job));
      return;
    }

    // GET /api/stats (statistics)
    // GET /api/resolve — a measured parameter, with everything known about it
    //
    // WHY THIS EXISTS
    // Until now this server had no way to resolve anything. The dashboard's
    // only honest option was to tell the student to go and use the CLI,
    // which is not a product, it is an apology.
    //
    // It returns the WHOLE resolved object, not just the number. The value
    // alone is what a student would have typed anyway; the citation, assay
    // conditions, protein variant, cofactors and reliability grades are the
    // part that makes it different from a guess — and dropping them here
    // would repeat ADR 0040 on a new surface.
    if (pathname === '/api/resolve' && req.method === 'GET') {
      const enzyme = url.searchParams.get('enzyme') ?? undefined;
      const substrate = url.searchParams.get('substrate') ?? '';
      const organism = url.searchParams.get('organism') ?? '';
      const rawQuantity = url.searchParams.get('quantity') ?? 'km';
      const quantity =
        rawQuantity === 'ki' || rawQuantity === 'kcat' ? rawQuantity : 'km';

      // Refuse rather than assume. An organism is not optional and must not
      // be defaulted to human: "the enzyme" is not a thing that has one Km,
      // which is the whole of Jeske's objection (ADR 0024).
      const missing: string[] = [];
      if (!enzyme) missing.push('enzyme');
      if (!substrate) missing.push('substrate');
      if (!organism) missing.push('organism');
      if (missing.length > 0) {
        res.writeHead(400, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({
          error: 'MISSING_REQUIRED_INPUT',
          missing,
          message:
            `Cannot resolve: ${missing.join(', ')} not supplied. An organism ` +
            'is required and is never assumed — kinetic parameters are ' +
            'species-specific, so "the enzyme" does not have one Km.',
        }));
        return;
      }

      try {
        const resolved = await resolveKinetic({
          enzymeName: enzyme,
          substrate,
          organism,
          quantity,
          allowCrossSpecies: url.searchParams.get('allowCrossSpecies') === 'true',
        });
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify(resolved));
      } catch (err) {
        // THREE OUTCOMES, NOT TWO. `found: false` above means the literature
        // genuinely holds nothing; this means the lookup could not run. A
        // client that cannot tell them apart teaches its user to read an
        // absence of evidence as evidence of absence, which is the reason
        // the CLI has three exit codes.
        const message =
          err instanceof ResolverUnavailableError
            ? err.message
            : 'The literature resolver could not be run.';
        res.writeHead(503, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: 'RESOLVER_UNAVAILABLE', message }));
      }
      return;
    }

    if (pathname === '/api/stats' && req.method === 'GET') {
      const stats = db.getStatistics();
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify(stats));
      return;
    }

    // POST /api/compare (Model comparison)
    if (pathname === '/api/compare' && req.method === 'POST') {
      let body = '';
      req.on('data', chunk => (body += chunk));
      req.on('end', async () => {
        try {
          const data = JSON.parse(body);

          // Validate request
          const validation = validateComparisonRequest(data);
          if (!validation.valid) {
            res.writeHead(400, { 'Content-Type': 'application/json' });
            res.end(formatValidationErrors(validation.errors));
            return;
          }

          const { parameters } = data;

          const compareId = `compare_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
          logger.info({ compareId }, 'API: Model comparison requested');

          res.writeHead(200, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ compareId, status: 'queued' }));

          // Background model comparison
          (async () => {
            try {
              batches.set(compareId, {
                status: 'running',
                startTime: Date.now(),
                progress: 0,
                type: 'comparison'
              });

              const result = await compareModels(parameters, (completed: number, total: number) => {
                const progress = Math.round((completed / total) * 100);
                batches.set(compareId, { ...batches.get(compareId), progress, completed });
              });

              // Rank the models against the caller's OWN measurement, when
              // they supplied one.
              //
              // `rankModelsByFit` had no production caller. It is the
              // function that answers "which mechanism does my bench data
              // support" -- the most consequential question this codebase
              // can be asked -- and nothing invoked it, so the answer was
              // computed by nobody and reached no one.
              //
              // That is ADR 0039's defect class at the scale of a whole
              // capability: not a field dropped at a boundary, but an entire
              // analysis written, tested, and never wired. It also meant the
              // defect ADR 0060 found in it (a model that never ran ranking
              // FIRST, because its fabricated 0 sat closest to a small
              // experimental value) could sit there unnoticed.
              //
              // Optional by design. `experimentalFinalValue` is a
              // measurement the experimenter made; Caterva cannot resolve it
              // from literature and must not invent one, so its absence
              // means "no fit ranking", never a default.
              const experimental = data.experimentalFinalValue;
              const fit = fitRankingFor(result.models, experimental);

              batches.set(compareId, {
                status: 'complete',
                progress: 100,
                result: fit ? { ...result, experimentalFinalValue: experimental, fit } : result,
                endTime: Date.now(),
                duration: Date.now() - (batches.get(compareId)?.startTime || 0),
                type: 'comparison'
              });

              logger.info(
                {
                  compareId,
                  bestModel: result.bestModel,
                  fitRanked: fit?.ranked.length ?? 0,
                  fitExcluded: fit?.excluded.length ?? 0,
                },
                'Model comparison complete',
              );
            } catch (error) {
              batches.set(compareId, {
                status: 'error',
                error: describeError(error),
                endTime: Date.now(),
                duration: Date.now() - (batches.get(compareId)?.startTime || 0),
                type: 'comparison'
              });
              logger.error({ compareId, error }, 'Model comparison error');
            }
          })();
        } catch (e) {
          res.writeHead(400, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ error: 'Invalid JSON' }));
        }
      });
      return;
    }

    // POST /api/batch
    if (pathname === '/api/batch' && req.method === 'POST') {
      let body = '';
      req.on('data', chunk => (body += chunk));
      req.on('end', async () => {
        try {
          const data = JSON.parse(body);

          // Validate request
          const validation = validateBatchRequest(data);
          if (!validation.valid) {
            res.writeHead(400, { 'Content-Type': 'application/json' });
            res.end(formatValidationErrors(validation.errors));
            return;
          }

          const { query, parameterSets, baseParameters, concurrency } = data;

          const batchId = `batch_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
          logger.info({ batchId, query, jobCount: parameterSets.length }, 'API: Batch job submitted');

          res.writeHead(200, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ batchId, status: 'queued' }));

          // Background batch processing
          (async () => {
            try {
              batches.set(batchId, {
                status: 'running',
                startTime: Date.now(),
                progress: 0,
                totalJobs: parameterSets.length
              });

              const batchJobs = createMultiParamBatchJobs(parameterSets, baseParameters);
              const result = await processBatch(
                query,
                batchJobs,
                concurrency || 3,
                (completed: number, total: number) => {
                  const progress = Math.round((completed / total) * 100);
                  batches.set(batchId, { ...batches.get(batchId), progress, completedJobs: completed });
                }
              );

              batches.set(batchId, {
                status: 'complete',
                progress: 100,
                result,
                endTime: Date.now(),
                duration: Date.now() - (batches.get(batchId)?.startTime || 0),
                totalJobs: result.totalJobs,
                completedJobs: result.completedJobs
              });

              logger.info(
                { batchId, successful: result.successfulJobs, failed: result.failedJobs },
                'Batch complete'
              );
            } catch (error) {
              batches.set(batchId, {
                status: 'error',
                error: describeError(error),
                endTime: Date.now(),
                duration: Date.now() - (batches.get(batchId)?.startTime || 0)
              });
              logger.error({ batchId, error }, 'Batch error');
            }
          })();
        } catch (e) {
          res.writeHead(400, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ error: 'Invalid JSON' }));
        }
      });
      return;
    }

    // GET /api/batches/:batchId
    if (pathname.match(/^\/api\/batches\//) && req.method === 'GET') {
      const batchId = pathname.split('/').pop();
      const batch = batches.get(batchId || '');

      if (!batch) {
        res.writeHead(404, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: 'Batch not found' }));
        return;
      }

      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify(batch));
      return;
    }

    // POST /api/sweep
    if (pathname === '/api/sweep' && req.method === 'POST') {
      let body = '';
      req.on('data', chunk => (body += chunk));
      req.on('end', async () => {
        try {
          const data = JSON.parse(body);

          // Validate request
          const validation = validateSweepRequest(data);
          if (!validation.valid) {
            res.writeHead(400, { 'Content-Type': 'application/json' });
            res.end(formatValidationErrors(validation.errors));
            return;
          }

          const { query, baseParameters, sweepParameters } = data;

          const sweepId = `sweep_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
          logger.info({ sweepId, query }, 'API: Parameter sweep requested');

          res.writeHead(200, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ sweepId, status: 'queued' }));

          // Background sweep processing
          (async () => {
            try {
              sweeps.set(sweepId, { status: 'running', startTime: Date.now(), progress: 0 });

              // Parse sweep parameters
              const parsed = sweepParameters.map((param: any) =>
                parseSweepParameter(param.name, param.spec)
              );

              const result = await runSweep(
                query,
                baseParameters,
                parsed,
                (completed: number, total: number) => {
                  const progress = Math.round((completed / total) * 100);
                  sweeps.set(sweepId, { ...sweeps.get(sweepId), progress });
                }
              );

              sweeps.set(sweepId, {
                status: 'complete',
                progress: 100,
                result,
                endTime: Date.now(),
                duration: Date.now() - (sweeps.get(sweepId)?.startTime || 0)
              });

              logger.info({ sweepId, results: result.results.length }, 'Sweep complete');
            } catch (error) {
              sweeps.set(sweepId, {
                status: 'error',
                error: describeError(error),
                endTime: Date.now(),
                duration: Date.now() - (sweeps.get(sweepId)?.startTime || 0)
              });
              logger.error({ sweepId, error }, 'Sweep error');
            }
          })();
        } catch (e) {
          res.writeHead(400, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ error: 'Invalid JSON' }));
        }
      });
      return;
    }

    // GET /api/sweeps/:sweepId
    if (pathname.match(/^\/api\/sweeps\//) && req.method === 'GET') {
      const sweepId = pathname.split('/').pop();
      const sweep = sweeps.get(sweepId || '');

      if (!sweep) {
        res.writeHead(404, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: 'Sweep not found' }));
        return;
      }

      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify(sweep));
      return;
    }

    // GET /api/health
    if (pathname === '/api/health' && req.method === 'GET') {
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({
        status: 'ok',
        timestamp: new Date().toISOString(),
        uptime: process.uptime(),
        jobs: {
          total: jobs.size,
          running: Array.from(jobs.values()).filter(j => j.status === 'running').length,
          completed: Array.from(jobs.values()).filter(j => j.status === 'complete').length,
          failed: Array.from(jobs.values()).filter(j => j.status === 'error').length
        },
        sweeps: {
          total: sweeps.size,
          running: Array.from(sweeps.values()).filter(s => s.status === 'running').length,
          completed: Array.from(sweeps.values()).filter(s => s.status === 'complete').length,
          failed: Array.from(sweeps.values()).filter(s => s.status === 'error').length
        },
        batches: {
          total: batches.size,
          running: Array.from(batches.values()).filter(b => b.status === 'running').length,
          completed: Array.from(batches.values()).filter(b => b.status === 'complete').length,
          failed: Array.from(batches.values()).filter(b => b.status === 'error').length
        }
      }));
      return;
    }

    // GET /api/openapi.json (OpenAPI 3.0 specification)
    if (pathname === '/api/openapi.json' && req.method === 'GET') {
      try {
        // This used to send the raw YAML bytes with a
        // 'Content-Type: application/json' header, with a comment
        // admitting the "conversion" was a no-op ("simple regex
        // replacement" that was never written). Swagger UI, ReDoc, and
        // the OpenAPI client generators this repo ships all fetch this
        // exact endpoint and JSON.parse() the body -- every one of them
        // would fail on YAML. Reproduced by actually calling this route
        // and attempting JSON.parse() on the response before writing
        // this fix.
        const openapiYaml = fs.readFileSync(path.join(__dirname, '../../openapi.yaml'), 'utf-8');
        const openapiJson = yaml.load(openapiYaml);
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify(openapiJson));
      } catch (error) {
        logger.error({ error }, 'Failed to load/parse openapi.yaml');
        res.writeHead(500, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: 'OpenAPI specification unavailable' }));
      }
      return;
    }

    // GET /api/docs (Swagger UI)
    if (pathname === '/api/docs' && req.method === 'GET') {
      const swaggerUI = `
<!DOCTYPE html>
<html>
<head>
  <title>Caterva API Documentation</title>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/swagger-ui/5.17.14/swagger-ui.min.css">
  <style>
    html { box-sizing: border-box; overflow: -moz-scrollbars-vertical; overflow-y: scroll; }
    *, *:before, *:after { box-sizing: inherit; }
    body { margin:0; padding:0; }
  </style>
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/swagger-ui/5.17.14/swagger-ui.min.js"></script>
  <script>
    SwaggerUIBundle({
      url: "/api/openapi.json",
      dom_id: "#swagger-ui",
      presets: [
        SwaggerUIBundle.presets.apis,
        SwaggerUIBundle.SwaggerUIStandalonePreset
      ],
      layout: "StandaloneLayout"
    })
  </script>
</body>
</html>
      `;
      res.writeHead(200, { 'Content-Type': 'text/html' });
      res.end(swaggerUI);
      return;
    }

    // GET /api/docs/redoc (ReDoc alternative)
    if (pathname === '/api/docs/redoc' && req.method === 'GET') {
      const redoc = `
<!DOCTYPE html>
<html>
<head>
  <title>Caterva API Documentation (ReDoc)</title>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <!-- No webfont. This pulled Montserrat and Roboto from fonts.googleapis.com,
       handing every reader's IP to Google before the page rendered (GDPR
       Art. 4; CJEU Breyer C-582/14; LG Muenchen I, 20 Jan 2022, Az. 3 O
       17493/20). Redoc's own defaults fall back to the system UI font. -->
  <style>
    body {
      margin: 0;
      padding: 0;
    }
  </style>
</head>
<body>
  <redoc spec-url="/api/openapi.json"></redoc>
  <!-- Pinned, deliberately. This read \`redoc@next\` until 2026-08-16. \`next\` is
       not a version: it is whatever was published most recently under that
       dist-tag, and jsDelivr's own API reports it currently resolving to
       3.0.0-rc.0 -- a release candidate. So this page was serving readers a
       pre-release build that changed without anyone here deciding it should,
       on a server with no authentication. \`latest\` is 2.5.3, which is what the
       \`<redoc spec-url=...>\` element above is written against. -->
  <script src="https://cdn.jsdelivr.net/npm/redoc@2.5.3/bundles/redoc.standalone.js"></script>
</body>
</html>
      `;
      res.writeHead(200, { 'Content-Type': 'text/html' });
      res.end(redoc);
      return;
    }

    // GET /api/export/jobs/csv (Export job history as CSV)
    if (pathname === '/api/export/jobs/csv' && req.method === 'GET') {
      const jobs = db.getRecentJobs(1000);
      const csv = exportJobHistoryToCSV(jobs, { includeParameters: true, includeLiterature: true });

      res.writeHead(200, {
        'Content-Type': 'text/csv',
        'Content-Disposition': `attachment; filename="caterva-jobs-${Date.now()}.csv"`
      });
      res.end(csv);
      return;
    }

    // GET /api/export/sweep(s)/:sweepId/csv (Export sweep results as CSV)
    // Accepts BOTH the singular and plural spelling of the resource.
    //
    // The reads are plural (/api/sweeps/:id, /api/batches/:id); the exports
    // were singular. A user who has just fetched /api/sweeps/abc naturally
    // reaches for /api/export/sweeps/abc/csv and gets a 404 with no hint
    // that one letter is the problem.
    //
    // That is not hypothetical: it caught the person writing
    // API_QUICK_REFERENCE.md, who documented the plural form throughout.
    // check_example_endpoints.py flagged the doc, but the doc was the
    // reasonable guess and the API was the inconsistent thing.
    //
    // Both spellings work rather than renaming the route, because renaming
    // would break any existing caller using the singular form.
    if (pathname.match(/^\/api\/export\/sweeps?\/.*\/csv$/) && req.method === 'GET') {
      const sweepId = pathname.split('/')[4];
      const sweep = sweeps.get(sweepId || '');

      if (!sweep || sweep.status !== 'complete') {
        res.writeHead(404, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: 'Sweep not found or not complete' }));
        return;
      }

      const csv = exportSweepToCSV(sweep.result, { includeParameters: true });
      res.writeHead(200, {
        'Content-Type': 'text/csv',
        'Content-Disposition': `attachment; filename="caterva-sweep-${sweepId}-${Date.now()}.csv"`
      });
      res.end(csv);
      return;
    }

    // GET /api/export/batch(es)/:batchId/csv (Export batch results as CSV)
    // Both spellings accepted -- see the sweep export above.
    if (pathname.match(/^\/api\/export\/batch(?:es)?\/.*\/csv$/) && req.method === 'GET') {
      const batchId = pathname.split('/')[4];
      const batch = batches.get(batchId || '');

      if (!batch || batch.status !== 'complete') {
        res.writeHead(404, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: 'Batch not found or not complete' }));
        return;
      }

      const csv = exportBatchToCSV(batch.result, { includeParameters: true });
      res.writeHead(200, {
        'Content-Type': 'text/csv',
        'Content-Disposition': `attachment; filename="caterva-batch-${batchId}-${Date.now()}.csv"`
      });
      res.end(csv);
      return;
    }

    // GET /api/export/comparison(s)/:compareId/csv (Export comparison as CSV)
    // Both spellings accepted -- see the sweep export above.
    if (pathname.match(/^\/api\/export\/comparisons?\/.*\/csv$/) && req.method === 'GET') {
      const compareId = pathname.split('/')[4];
      const comparison = batches.get(compareId || '');

      if (!comparison || comparison.status !== 'complete' || comparison.type !== 'comparison') {
        res.writeHead(404, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: 'Comparison not found or not complete' }));
        return;
      }

      const csv = exportComparisonToCSV(comparison.result, {});
      res.writeHead(200, {
        'Content-Type': 'text/csv',
        'Content-Disposition': `attachment; filename="caterva-comparison-${compareId}-${Date.now()}.csv"`
      });
      res.end(csv);
      return;
    }

    // GET /api/export/stats/csv (Export statistics as CSV)
    if (pathname === '/api/export/stats/csv' && req.method === 'GET') {
      const stats = db.getStatistics();
      const csv = exportStatisticsToCSV(stats);

      res.writeHead(200, {
        'Content-Type': 'text/csv',
        'Content-Disposition': `attachment; filename="caterva-stats-${Date.now()}.csv"`
      });
      res.end(csv);
      return;
    }

    // POST /api/compare/jobs (Compare two or more job results)
    if (pathname === '/api/compare/jobs' && req.method === 'POST') {
      let body = '';
      req.on('data', chunk => (body += chunk));
      req.on('end', () => {
        try {
          const data = JSON.parse(body);

          // Validate request
          const validation = validateJobComparisonRequest(data);
          if (!validation.valid) {
            res.writeHead(400, { 'Content-Type': 'application/json' });
            res.end(formatValidationErrors(validation.errors));
            return;
          }

          const { jobIds } = data;

          const foundJobs = [];
          for (const jobId of jobIds) {
            const job = jobs.get(jobId) || db.getJob(jobId);
            if (job) foundJobs.push(job);
          }

          if (foundJobs.length < 2) {
            res.writeHead(404, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ error: 'Could not find at least 2 requested jobs' }));
            return;
          }

          if (foundJobs.length === 2) {
            // Two-job comparison
            const comparison = compareJobs(foundJobs[0], foundJobs[1]);
            res.writeHead(200, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify(comparison));
          } else {
            // Multi-job comparison
            const comparison = compareMultipleJobs(foundJobs);
            res.writeHead(200, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify(comparison));
          }
        } catch (e) {
          res.writeHead(400, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ error: 'Invalid JSON' }));
        }
      });
      return;
    }

    // GET /api/analyze/sweep(s)/:sweepId (Analyze sweep sensitivity)
    // Both spellings accepted -- see the sweep export above.
    if (pathname.match(/^\/api\/analyze\/sweeps?\//) && req.method === 'GET') {
      const sweepId = pathname.split('/').pop();
      const sweep = sweeps.get(sweepId || '');

      if (!sweep || sweep.status !== 'complete') {
        res.writeHead(404, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: 'Sweep not found or not complete' }));
        return;
      }

      const analysis = analyzeSensitivity(sweep.result);
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify(analysis));
      return;
    }

    // GET /api/metrics (Overall performance metrics)
    // GET /api/perf (per-endpoint timing; documented in
    // API_PERFORMANCE_GUIDE.md long before it existed)
    if (pathname === '/api/perf' && req.method === 'GET') {
      const limitRaw = url.searchParams.get('limit');
      const parsedLimit = limitRaw === null ? 5 : Number.parseInt(limitRaw, 10);
      const limit =
        Number.isFinite(parsedLimit) && parsedLimit > 0 ? Math.min(parsedLimit, 100) : 5;
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify(getPerfSnapshot(limit)));
      return;
    }

    // GET /api/cache/stats
    if (pathname === '/api/cache/stats' && req.method === 'GET') {
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify(getCacheStats()));
      return;
    }

    if (pathname === '/api/metrics' && req.method === 'GET') {
      const aggregated = metrics.getAggregatedMetrics();
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify(aggregated));
      return;
    }

    // GET /api/metrics/by-model (Metrics grouped by kinetic model)
    if (pathname === '/api/metrics/by-model' && req.method === 'GET') {
      const byModel = metrics.getMetricsByModel();
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify(byModel));
      return;
    }

    // GET /api/metrics/reproducibility (Track reproducibility across runs)
    if (pathname === '/api/metrics/reproducibility' && req.method === 'GET') {
      const all = metrics.getAllReproducibilityMetrics();
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify(all));
      return;
    }

    // GET /api/metrics/slow-queries (Queries slower than threshold)
    if (pathname.match(/^\/api\/metrics\/slow-queries/) && req.method === 'GET') {
      const url = new URL(req.url || '', `http://${req.headers.host}`);
      const threshold = parseInt(url.searchParams.get('threshold') || '1000', 10);
      const slow = metrics.getSlowQueries(threshold);
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ threshold, queries: slow, count: slow.length }));
      return;
    }

    // GET /api/metrics/failed-queries (Failed queries for debugging)
    if (pathname === '/api/metrics/failed-queries' && req.method === 'GET') {
      const failed = metrics.getFailedQueries();
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ queries: failed, count: failed.length }));
      return;
    }

    // GET /api/metrics/percentile (Percentile execution time)
    if (pathname.match(/^\/api\/metrics\/percentile/) && req.method === 'GET') {
      const url = new URL(req.url || '', `http://${req.headers.host}`);
      const percentile = parseInt(url.searchParams.get('percentile') || '50', 10);
      const value = metrics.getPercentile(percentile);
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ percentile, executionTimeMs: value }));
      return;
    }

    // GET /api/metrics/sweeps (All sweep metrics)
    if (pathname === '/api/metrics/sweeps' && req.method === 'GET') {
      const sweepMetrics = getAllSweepMetrics();
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({
        sweeps: sweepMetrics,
        count: sweepMetrics.length
      }));
      return;
    }

    // GET /api/metrics/sweeps/:id (Specific sweep metrics)
    if (pathname.match(/^\/api\/metrics\/sweeps\/[^\/]+$/) && req.method === 'GET') {
      const sweepId = pathname.split('/').pop() || '';
      const sweepMetrics = getSweepMetrics(sweepId);
      if (!sweepMetrics) {
        res.writeHead(404, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: 'Sweep not found' }));
        return;
      }
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify(sweepMetrics));
      return;
    }

    // GET /api/metrics/sweeps-by-query (Sweep metrics grouped by query)
    if (pathname === '/api/metrics/sweeps-by-query' && req.method === 'GET') {
      const byQuery = getSweepMetricsByQuery();
      const result: Record<string, any> = {};
      for (const [query, metrics] of byQuery.entries()) {
        result[query] = metrics;
      }
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify(result));
      return;
    }

    // GET /api/metrics/batches (All batch metrics)
    if (pathname === '/api/metrics/batches' && req.method === 'GET') {
      const batchMetrics = getAllBatchMetrics();
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({
        batches: batchMetrics,
        count: batchMetrics.length
      }));
      return;
    }

    // GET /api/metrics/batches/:id (Specific batch metrics)
    if (pathname.match(/^\/api\/metrics\/batches\/[^\/]+$/) && req.method === 'GET') {
      const batchId = pathname.split('/').pop() || '';
      const batchMetrics = getBatchMetrics(batchId);
      if (!batchMetrics) {
        res.writeHead(404, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: 'Batch not found' }));
        return;
      }
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify(batchMetrics));
      return;
    }

    // GET /api/metrics/batches-by-query (Batch metrics grouped by query)
    if (pathname === '/api/metrics/batches-by-query' && req.method === 'GET') {
      const byQuery = getBatchMetricsByQuery();
      const result: Record<string, any> = {};
      for (const [query, metrics] of byQuery.entries()) {
        result[query] = metrics;
      }
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify(result));
      return;
    }

    // GET /metrics (Prometheus metrics format for Grafana/Prometheus scraping)
    if (pathname === '/metrics' && req.method === 'GET') {
      const prometheusMetrics = generatePrometheusMetrics();
      res.writeHead(200, { 'Content-Type': 'text/plain; version=0.0.4' });
      res.end(prometheusMetrics);
      return;
    }

    // GET / (dashboard)
    if (pathname === '/' && req.method === 'GET') {
      const dashboardPath = path.join(__dirname, 'dashboard.html');
      const content = fs.readFileSync(dashboardPath, 'utf-8');
      res.writeHead(200, { 'Content-Type': 'text/html' });
      res.end(content);
      return;
    }

    // 404
    res.writeHead(404, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ error: 'Not found' }));
  } catch (error) {
    // LOG FIRST. This used to log last, so when the recovery below threw the
    // error that caused it was never recorded — the operator got a dead
    // process and a silent log.
    logger.error({ error, pathname, method: req.method }, 'Server error');

    // A handler that throws AFTER it started responding cannot be sent a 500:
    // the status line is already on the wire. Calling `writeHead` here throws
    // `ERR_HTTP_HEADERS_SENT` from inside the catch, where nothing is left to
    // catch it, and Node terminates the process.
    //
    // That is how one malformed request became a denial of service for every
    // other user of this server. An error handler that can crash the process
    // is worse than no error handler, because it converts a single failed
    // request into a total outage.
    //
    // Nothing useful can be sent at this point, so the connection is
    // destroyed: the client sees a truncated response and retries, rather
    // than hanging until timeout on a request that will never complete.
    if (res.headersSent) {
      res.destroy();
      return;
    }

    res.writeHead(500, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ error: 'Server error' }));
  }
});

server.listen(PORT, () => {
  console.log(`\n🧪 Caterva Dashboard: http://localhost:${PORT}\n`);

  // Printed on every start, not tucked into a document nobody opens.
  //
  // This server has NO authentication, and `GET /api/jobs/history` returns
  // the last 50 jobs -- including the query text somebody typed -- to any
  // caller. There is no per-user separation because there are no users.
  //
  // That is defensible for a localhost tool. What was not defensible is
  // that nothing said so: a teacher could put this on a lab network, and a
  // student could open the history panel and be reading somebody else's
  // work without either of them having any reason to expect it.
  //
  // The banner is the honest place for it. Anyone deploying reads this
  // line; far fewer read SECURITY.md first.
  console.log(
    '⚠  No authentication. /api/jobs/history returns EVERY user\'s queries\n' +
    '   to anyone who can reach this port. Safe on localhost; do not expose\n' +
    '   it to a shared network or the internet as-is. See SECURITY.md.\n'
  );
  logger.info({ port: PORT }, `✓ Server running`);
});
