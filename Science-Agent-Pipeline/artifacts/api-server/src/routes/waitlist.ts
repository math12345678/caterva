import { Router, type IRouter, type Request, type Response } from "express";
import { logger } from "../lib/logger";
import { readFileSync, writeFileSync, existsSync, mkdirSync } from "node:fs";
import { join } from "node:path";
import { validate } from "../lib/validate";
import { WaitlistBody } from "../lib/schemas";

const router: IRouter = Router();

interface WaitlistEntry {
  email: string;
  createdAt: string;
}

const DATA_DIR = join(import.meta.dirname, "..", "data");
const DB_PATH = process.env.WAITLIST_FILE || join(DATA_DIR, "waitlist.json");

function loadWaitlist(): WaitlistEntry[] {
  try {
    if (existsSync(DB_PATH)) {
      return JSON.parse(readFileSync(DB_PATH, "utf-8"));
    }
  } catch (err) {
    logger.warn({ err }, "Failed to load waitlist from disk");
  }
  return [];
}

function saveWaitlist(entries: WaitlistEntry[]): void {
  try {
    if (!existsSync(DATA_DIR)) {
      mkdirSync(DATA_DIR, { recursive: true });
    }
    writeFileSync(DB_PATH, JSON.stringify(entries, null, 2));
  } catch (err) {
    logger.warn({ err }, "Failed to save waitlist to disk");
  }
}

let WAITLIST = loadWaitlist();

router.post("/waitlist", validate(WaitlistBody), async (req: Request, res: Response) => {
  try {
    const { email } = req.body as { email: string };

    if (WAITLIST.some((entry) => entry.email === email)) {
      res.status(409).json({
        error: "ALREADY_SIGNED_UP",
        message: "This email is already on the waitlist.",
      });
      return;
    }

    const entry: WaitlistEntry = { email, createdAt: new Date().toISOString() };
    WAITLIST.push(entry);
    saveWaitlist(WAITLIST);

    if (WAITLIST.length > 10000) {
      WAITLIST = WAITLIST.slice(-10000);
    }

    logger.info({ email }, "Waitlist signup");

    res.status(201).json({
      position: WAITLIST.length,
      message: "You're on the list! We'll reach out when a pilot spot opens up.",
    });
  } catch (err) {
    logger.error({ err }, "Waitlist signup failed");
    res.status(500).json({
      error: "INTERNAL_SERVER_ERROR",
      message: "Failed to add to waitlist.",
    });
  }
});

router.get("/waitlist/count", async (_req: Request, res: Response) => {
  res.json({ count: WAITLIST.length });
});

/**
 * Reset the in-memory waitlist. Used by tests only.
 */
export function resetWaitlist(): void {
  WAITLIST = [];
  try {
    if (existsSync(DB_PATH)) {
      writeFileSync(DB_PATH, "[]");
    }
  } catch { /* ignore */ }
}

export default router;
