import rateLimit from "express-rate-limit";

const WINDOW_MS = 60_000;
const MAX_SIMULATE_PER_WINDOW = 10;

export const simulateLimiter = rateLimit({
  windowMs: WINDOW_MS,
  max: MAX_SIMULATE_PER_WINDOW,
  standardHeaders: true,
  legacyHeaders: false,
  skip: () => process.env["NODE_ENV"] === "test",
  message: {
    error: "TOO_MANY_REQUESTS",
    message: `Simulation rate limit exceeded. Max ${MAX_SIMULATE_PER_WINDOW} requests per ${WINDOW_MS / 1000}s.`,
  },
});

export function resetSimulateLimiter(): void {
  // no-op: limiter is stateless in test mode due to skip()
}
