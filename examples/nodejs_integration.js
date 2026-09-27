#!/usr/bin/env node
/**
 * Caterva Node.js Integration Examples
 *
 * Working examples of Caterva's REST API from Node.
 *
 * WHICH SERVER THIS TALKS TO
 * --------------------------
 * Caterva serves TWO HTTP APIs, and they are not interchangeable:
 *
 *   * `Science-Agent-Pipeline/artifacts/api-server/` — the Express service,
 *     reference at `docs/API.md`. THIS FILE TARGETS THAT ONE. Routes are
 *     /api/healthz and /api/simulate/<jobId>/..., and parameters go INSIDE
 *     the query string.
 *
 *   * `src/web/server.ts` — the root tree's own server, started with
 *     `npm run web`, which `examples/python_integration.py` targets.
 *     Different routes (/api/health, /api/jobs/<id>, /api/sweep,
 *     /api/batch) and a different request shape:
 *     `{query, parameters, enzyme, substrate}`.
 *
 * Pointing a client at the wrong one produces 404s that look like the
 * product is broken. `scripts/check_example_endpoints.py` checks every
 * endpoint here against the routes both servers actually register.
 *
 * WHY THE QUERY STRING CARRIES THE PARAMETERS (on this server)
 * -----------------------------------------------------------
 *     { query: "simulate michaelis menten km=2 vmax=5 s0=10 end=10 points=51" }
 *
 * There is no separate `parameters` field here. The resolver reads
 * `km=2 vmax=5 s0=10` out of the text, and refuses to invent anything it
 * cannot find: experimental conditions like s0, end and points are chosen
 * by whoever runs the experiment and are never defaulted or resolved from
 * literature (ADR 0012/0013). Omit them and the job fails with
 * MISSING_REQUIRED_INPUT naming exactly what to add.
 *
 * No dependencies — uses the built-in fetch (Node 18+).
 */

const CATERVA_URL = process.env.CATERVA_URL || 'http://localhost:3000';

class CatervaClient {
  constructor(baseUrl = CATERVA_URL) {
    this.baseUrl = baseUrl.replace(/\/$/, '');
  }

  async #get(path) {
    const response = await fetch(`${this.baseUrl}${path}`);
    if (!response.ok) {
      throw new Error(`GET ${path} -> HTTP ${response.status}`);
    }
    return response.json();
  }

  // -- health ---------------------------------------------------------

  /** Liveness. Returns { status: "ok" }. */
  healthCheck() {
    return this.#get('/api/healthz');
  }

  /** Per-subsystem status and queue depth. */
  pipelineStatus() {
    return this.#get('/api/pipeline/status');
  }

  // -- running a simulation -------------------------------------------

  /**
   * Enqueue a simulation, return its job id.
   *
   * `query` carries the parameters. There is no separate `parameters`
   * field: the resolver reads `km=2 vmax=5 s0=10` out of the text, and
   * anything it cannot find there and cannot resolve from literature is
   * reported as missing rather than guessed.
   */
  async simulate(query) {
    const response = await fetch(`${this.baseUrl}/api/simulate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query }),
    });
    const body = await response.json();
    if (response.status === 400) {
      throw new Error(`Rejected: ${body.message}`);
    }
    if (!response.ok) {
      throw new Error(`POST /api/simulate -> HTTP ${response.status}`);
    }
    return body.jobId;
  }

  /** Current state of a job: pending, running, completed or failed. */
  getJob(jobId) {
    return this.#get(`/api/simulate/${jobId}`);
  }

  /**
   * Poll to completion. Throws on failure rather than returning null.
   *
   * A failed job is a result, not an absence of one — its error names what
   * was missing, which is usually the thing the caller needs to read.
   */
  async waitFor(jobId, { attempts = 60, intervalMs = 500 } = {}) {
    for (let i = 0; i < attempts; i++) {
      const job = await this.getJob(jobId);
      if (job.status === 'completed') return job.result;
      if (job.status === 'failed') {
        throw new Error(`Job ${jobId} failed: ${JSON.stringify(job.error)}`);
      }
      await new Promise((resolve) => setTimeout(resolve, intervalMs));
    }
    throw new Error(
      `Job ${jobId} did not finish in ${(attempts * intervalMs) / 1000}s`
    );
  }

  /** Cancel a pending or running job. */
  async cancel(jobId) {
    const response = await fetch(
      `${this.baseUrl}/api/simulate/${jobId}/cancel`,
      { method: 'POST' }
    );
    return response.json();
  }

  // -- what backs the numbers ------------------------------------------

  /** Per-parameter confidence, derived from provenance. */
  confidence(jobId) {
    return this.#get(`/api/simulate/${jobId}/confidence`);
  }

  /**
   * Publication audit: which parameters can be cited, and which cannot.
   *
   * Measured quantities (km, ki, kcat, vmax) need a citation. Experimental
   * conditions (s0, i0, temperature, pH) are chosen by the experimenter and
   * are reported, not cited — so they never block publication readiness.
   */
  audit(jobId) {
    return this.#get(`/api/simulate/${jobId}/audit`);
  }

  /** The trajectory as CSV text. */
  async exportCsv(jobId) {
    const response = await fetch(
      `${this.baseUrl}/api/simulate/${jobId}/export`
    );
    if (!response.ok) {
      throw new Error(`export -> HTTP ${response.status}`);
    }
    return response.text();
  }

  // -- catalogue and metrics -------------------------------------------

  /** Enzymes the resolver recognises by name. */
  enzymes() {
    return this.#get('/api/enzymes');
  }

  /** Stage-level metrics with Wilson confidence intervals. */
  pipelineMetrics() {
    return this.#get('/api/simulate/metrics/pipeline');
  }

  /** System state: queue, literature backing, STRENDA compliance. */
  dashboardOverview() {
    return this.#get('/api/dashboard/overview');
  }
}

// ---------------------------------------------------------------------------
// Examples
// ---------------------------------------------------------------------------

async function exampleMichaelisMenten(client) {
  const jobId = await client.simulate(
    'simulate michaelis menten km=2 vmax=5 s0=10 end=10 points=51'
  );
  const result = await client.waitFor(jobId);
  console.log(`  domain     : ${result.domain}`);
  console.log(`  points     : ${result.trajectory.length}`);
  console.log(`  parameters : ${JSON.stringify(result.parameters)}`);
}

async function exampleMissingCondition(client) {
  // The behaviour most worth understanding: Caterva does not fill in
  // s0/i0/end/points with plausible-looking numbers. It names them.
  const jobId = await client.simulate('simulate sir beta=0.3 gamma=0.1');
  try {
    await client.waitFor(jobId, { attempts: 30 });
  } catch (err) {
    console.log(`  refused, as designed: ${err.message}`);
  }
}

async function exampleProvenance(client) {
  const jobId = await client.simulate(
    'simulate lactate dehydrogenase vmax=5 s0=10 end=10 points=51'
  );
  const result = await client.waitFor(jobId);

  for (const [key, prov] of Object.entries(result.parameterProvenance ?? {})) {
    console.log(
      `  ${key.padEnd(8)} ${String(prov.origin).padEnd(10)} ${prov.citation ?? '-'}`
    );
  }

  const audit = await client.audit(jobId);
  console.log(`  publication ready: ${audit.readyToPublish}`);
}

async function main() {
  const client = new CatervaClient();

  try {
    await client.healthCheck();
  } catch {
    console.log(`No Caterva server at ${CATERVA_URL}. Start it with \`npm start\`.`);
    process.exitCode = 1;
    return;
  }

  const examples = [
    ['Michaelis-Menten', exampleMichaelisMenten],
    ['A missing experimental condition', exampleMissingCondition],
    ['Provenance and publication audit', exampleProvenance],
  ];

  for (const [name, example] of examples) {
    console.log(`\n${name}`);
    console.log('-'.repeat(name.length));
    try {
      await example(client);
    } catch (err) {
      // An example should show the error rather than swallow it.
      console.log(`  ${err.constructor.name}: ${err.message}`);
    }
  }
}

if (require.main === module) {
  main();
}

module.exports = { CatervaClient };
