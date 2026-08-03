#!/usr/bin/env node
/**
 * Demo script showing the full Science Agent Pipeline in action.
 * Run with: npm run cli -- demo
 * Or: tsx src/demo.ts
 */

const BASE_URL = "http://localhost:3000/api";

async function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

interface SimJob {
  jobId: string;
  status: string;
  progress: number;
  result?: {
    domain: string;
    trajectory: unknown[];
    provenance: { flags: string[] };
  };
  error?: { message: string };
}

async function submit(query: string): Promise<SimJob> {
  const res = await fetch(`${BASE_URL}/simulate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query }),
  });
  if (!res.ok) throw new Error(`Submit failed: ${res.status}`);
  return res.json() as Promise<SimJob>;
}

async function poll(jobId: string): Promise<SimJob["result"]> {
  while (true) {
    await sleep(500);
    const res = await fetch(`${BASE_URL}/simulate/${jobId}`);
    if (!res.ok) throw new Error(`Poll failed: ${res.status}`);
    const job = (await res.json()) as SimJob;
    console.log(`  ${job.status} (${job.progress}%)`);
    if (job.status === "completed" && job.result) return job.result;
    if (job.status === "failed")
      throw new Error(job.error?.message ?? "Failed");
  }
}

async function main() {
  console.log("🧪 Science Agent Pipeline Demo\n");

  const queries = [
    "simulate lactate dehydrogenase with pyruvate",
    "simulate enzyme kinetics km=0.5 vmax=10 s0=20",
    "simulate SIR epidemic with beta=0.5 gamma=0.2",
    "simulate SEIR with exposed compartment",
  ];

  for (const query of queries) {
    console.log(`\n📝 Query: "${query}"`);
    try {
      const job = await submit(query);
      console.log(`  Job: ${job.jobId} (${job.status}, ${job.progress}%)`);
      const result = await poll(job.jobId);
      console.log(`  ✅ Domain: ${result?.domain}`);
      console.log(`  ✅ Points: ${result?.trajectory.length}`);
      console.log(
        `  ✅ Flags: ${result?.provenance.flags.join("; ") || "none"}`,
      );
    } catch (err) {
      console.error(`  ❌ ${err instanceof Error ? err.message : String(err)}`);
    }
  }

  console.log("\n🎉 Demo complete!");
}

main().catch(console.error);
