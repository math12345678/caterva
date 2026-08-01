import { program } from "commander";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

interface PackageJson { version: string }
const pkg = JSON.parse(readFileSync(join(__dirname, "..", "package.json"), "utf8")) as PackageJson;

interface SimulateResponse {
  jobId: string;
  status: string;
  progress: number;
  query: string;
  createdAt: string;
  updatedAt: string;
  result?: {
    runId: string;
    domain: string;
    parameters: Record<string, number>;
    trajectory: Record<string, number>[];
    provenance: { reasoning: string; modelCitations: string[]; flags: string[] };
    completedAt: string;
  };
  error?: { error: string; message: string };
}

const DEFAULT_BASE = "http://localhost:3000/api";

program
  .name("sci-pipe")
  .description("Science Agent Pipeline CLI — submit and monitor simulations")
  .version(pkg.version);

program
  .command("simulate <query>")
  .description("Submit a natural-language simulation query")
  .option("-b, --base <url>", `API base URL (default: ${DEFAULT_BASE})`, DEFAULT_BASE)
  .option("--poll", "Wait for completion and show result")
  .option("--interval <ms>", "Polling interval in ms", "1000")
  .action(async (query, opts) => {
    const base = opts.base.replace(/\/$/, "");
    const url = `${base}/simulate`;

    console.log(`Submitting: "${query}"`);
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ message: "Request failed" }));
      console.error(`Error: ${(err as { message?: string }).message ?? "Unknown error"}`);
      process.exit(1);
    }

    const job = await res.json() as SimulateResponse;
    console.log(`Job created: ${job.jobId}`);
    console.log(`Status: ${job.status} (${job.progress}%)`);

    if (opts.poll) {
      console.log("Waiting for completion...");
      await pollUntilDone(base, job.jobId, Number(opts.interval));
    }
  });

program
  .command("status <jobId>")
  .description("Check status of a simulation job")
  .option("-b, --base <url>", `API base URL (default: ${DEFAULT_BASE})`, DEFAULT_BASE)
  .action(async (jobId, opts) => {
    const base = opts.base.replace(/\/$/, "");
    const res = await fetch(`${base}/simulate/${jobId}`);
    if (!res.ok) {
      console.error("Job not found");
      process.exit(1);
    }
    const job = await res.json() as SimulateResponse;
    printJob(job);
  });

program
  .command("stream <jobId>")
  .description("Stream real-time updates via SSE")
  .option("-b, --base <url>", `API base URL (default: ${DEFAULT_BASE})`, DEFAULT_BASE)
  .action(async (jobId, opts) => {
    const base = opts.base.replace(/\/$/, "");
    const res = await fetch(`${base}/simulate/${jobId}/stream`);
    if (!res.ok) {
      console.error("Stream not available");
      process.exit(1);
    }
    console.log(`Streaming updates for ${jobId}...`);
    for await (const chunk of res.body!) {
      const text = new TextDecoder().decode(chunk);
      for (const line of text.split("\n")) {
        if (line.startsWith("data: ")) {
          const job = JSON.parse(line.slice(6)) as SimulateResponse;
          printJob(job);
        }
      }
    }
  });

program
  .command("health")
  .description("Check API server health")
  .option("-b, --base <url>", `API base URL (default: ${DEFAULT_BASE})`, DEFAULT_BASE)
  .action(async (opts) => {
    const base = opts.base.replace(/\/$/, "");
    const res = await fetch(`${base}/healthz`);
    console.log(await res.json());
  });

async function pollUntilDone(base: string, jobId: string, interval: number): Promise<void> {
  while (true) {
    await new Promise((r) => setTimeout(r, interval));
    const res = await fetch(`${base}/simulate/${jobId}`);
    if (!res.ok) {
      console.error("Job lookup failed");
      process.exit(1);
    }
    const job = await res.json() as SimulateResponse;
    console.log(`  ${job.status} (${job.progress}%)`);
    if (job.status === "completed" && job.result) {
      console.log("\n✅ Completed!");
      printResult(job.result);
      break;
    }
    if (job.status === "failed") {
      console.error(`\n❌ Failed: ${job.error?.message}`);
      process.exit(1);
    }
  }
}

function printJob(job: SimulateResponse): void {
  console.log(`Job: ${job.jobId}`);
  console.log(`  Status: ${job.status} (${job.progress}%)`);
  console.log(`  Query: ${job.query}`);
  console.log(`  Created: ${job.createdAt}`);
  console.log(`  Updated: ${job.updatedAt}`);
  if (job.result) printResult(job.result);
  if (job.error) console.log(`  Error: ${job.error.message}`);
}

function printResult(r: SimulateResponse["result"]): void {
  if (!r) return;
  console.log(`  Domain: ${r.domain}`);
  console.log(`  Parameters: ${JSON.stringify(r.parameters, null, 2)}`);
  console.log(`  Trajectory points: ${r.trajectory.length}`);
  console.log(`  Flags: ${r.provenance.flags.join("; ") || "none"}`);
  console.log(`  Model citations: ${r.provenance.modelCitations.length}`);
  console.log(`  Completed: ${r.completedAt}`);
}

program.parse();