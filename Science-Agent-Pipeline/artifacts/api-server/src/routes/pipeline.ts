import { Router, type IRouter, type Request, type Response, type NextFunction } from "express";
import { access } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { spawn } from "node:child_process";
import { isDbAvailable } from "@workspace/db";
import * as queue from "../lib/queue";

const router: IRouter = Router();

const _dirname = path.dirname(fileURLToPath(import.meta.url));

async function fileExists(filePath: string): Promise<boolean> {
  try {
    await access(filePath);
    return true;
  } catch {
    return false;
  }
}

async function checkPython3(): Promise<{ available: boolean; version: string | null }> {
  return new Promise((resolve) => {
    const proc = spawn("python3", ["--version"]);
    const timer = setTimeout(() => {
      proc.kill();
      resolve({ available: false, version: null });
    }, 4000);
    let out = "";
    proc.stdout.on("data", (chunk: Buffer) => { out += chunk.toString(); });
    proc.on("error", () => { clearTimeout(timer); resolve({ available: false, version: null }); });
    proc.on("close", (code) => {
      clearTimeout(timer);
      if (code === 0) {
        resolve({ available: true, version: out.trim() });
      } else {
        resolve({ available: false, version: null });
      }
    });
  });
}

interface SubsystemStatus {
  ok: boolean;
  label: string;
  detail: string;
}

router.get("/pipeline/status", async (_req: Request, res: Response, next: NextFunction) => {
  try {
    const scriptsDir = path.resolve(_dirname, "..", "src", "lib");
    const [telluriumExists, scienceAgentExists, python, dbAvailable] = await Promise.all([
      fileExists(path.join(scriptsDir, "tellurium_runner.py")),
      fileExists(path.join(scriptsDir, "science_agent_runner.py")),
      checkPython3(),
      Promise.resolve(isDbAvailable()),
    ]);

    const subsystems: SubsystemStatus[] = [
      {
        ok: telluriumExists,
        label: "tellurium_runner.py",
        detail: telluriumExists
          ? "Script found"
          : "Missing — pipeline will fail at 'running' stage",
      },
      {
        ok: scienceAgentExists,
        label: "science_agent_runner.py",
        detail: scienceAgentExists
          ? "Script found"
          : "Missing — enzyme lookups will fail",
      },
      {
        ok: python.available,
        label: "python3",
        detail: python.available
          ? `Found: ${python.version}`
          : "Not found — pipeline cannot run Tellurium or science agent",
      },
      {
        ok: dbAvailable,
        label: "postgres (via drizzle)",
        detail: dbAvailable
          ? "DATABASE_URL configured and connected"
          : "Not configured — results are in-memory only (no persistence)",
      },
      {
        ok: !!process.env["OPENAI_API_KEY"] || !!process.env["LLM_API_KEY"],
        label: "openai / llm api key",
        detail: process.env["OPENAI_API_KEY"] || process.env["LLM_API_KEY"]
          ? "Configured — queries will use LLM resolution"
          : "Not set — falling back to keyword matching (no enzyme lookups via LLM)",
      },
    ];

    const allOk = subsystems.every((s) => s.ok);
    const queueJobs = queue.listJobs();
    const statusCounts: Record<string, number> = {};
    for (const job of queueJobs) {
      statusCounts[job.status] = (statusCounts[job.status] ?? 0) + 1;
    }

    res.json({
      status: allOk ? "healthy" : "degraded",
      uptime: process.uptime(),
      subsystems,
      queue: {
        total: queueJobs.length,
        byStatus: statusCounts,
      },
    });
  } catch (err) {
    next(err);
  }
});

router.get("/metrics", async (_req: Request, res: Response, next: NextFunction) => {
  try {
    const jobs = queue.listJobs();
    const completed = jobs.filter((j) => j.status === "completed").length;
    const enqueued = jobs.filter((j) => j.status === "pending" || j.status === "resolving" || j.status === "running").length;
    const failed = jobs.filter((j) => j.status === "failed").length;

    let waitlistCount = 0;
    try {
      const { existsSync, readFileSync } = await import("node:fs");
      const { join } = await import("node:path");
      const dbPath = process.env.WAITLIST_FILE || join(import.meta.dirname, "..", "data", "waitlist.json");
      if (existsSync(dbPath)) {
        const raw = JSON.parse(readFileSync(dbPath, "utf-8"));
        waitlistCount = Array.isArray(raw) ? raw.length : 0;
      }
    } catch { /* best effort */ }

    res.json({
      totalSimulations: jobs.length,
      completedSimulations: completed,
      enqueuedSimulations: enqueued,
      failedSimulations: failed,
      waitlistSignups: waitlistCount,
      uptime: process.uptime(),
    });
  } catch (err) {
    next(err);
  }
});

export default router;
