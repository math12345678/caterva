import express, {
  type Express,
  type Request,
  type Response,
  type NextFunction,
} from "express";
import cors from "cors";
import pinoHttp from "pino-http";
import router from "./routes";
import { logger } from "./lib/logger";

/**
 * Global rate limiting: 1000 requests per 15 minutes.
 * Applies to all endpoints that don't have specific limiters.
 */
const GLOBAL_RATE_LIMIT = 1000;
const GLOBAL_RATE_WINDOW_MS = 15 * 60 * 1000; // 15 minutes

interface RateLimitBucket {
  count: number;
  resetAt: number;
}

/**
 * Simple global rate limiter using in-memory buckets.
 * For production, use Redis or external service.
 */
class GlobalRateLimiter {
  private buckets = new Map<string, RateLimitBucket>();
  private readonly limit: number;
  private readonly windowMs: number;

  constructor(limit: number, windowMs: number) {
    this.limit = limit;
    this.windowMs = windowMs;
  }

  middleware() {
    return (_req: Request, res: Response, next: NextFunction) => {
      const now = Date.now();
      const key = "global";
      let bucket = this.buckets.get(key);

      if (!bucket || now > bucket.resetAt) {
        bucket = { count: 0, resetAt: now + this.windowMs };
        this.buckets.set(key, bucket);
      }

      bucket.count++;

      res.setHeader("X-RateLimit-Limit", String(this.limit));
      res.setHeader("X-RateLimit-Remaining", String(Math.max(0, this.limit - bucket.count)));
      res.setHeader("X-RateLimit-Reset", String(Math.ceil(bucket.resetAt / 1000)));

      next();
    };
  }
}

const app: Express = express();
const globalLimiter = new GlobalRateLimiter(GLOBAL_RATE_LIMIT, GLOBAL_RATE_WINDOW_MS);

app.use(
  pinoHttp({
    logger,
    serializers: {
      req(req) {
        return {
          id: req.id,
          method: req.method,
          url: req.url?.split("?")[0],
        };
      },
      res(res) {
        return {
          statusCode: res.statusCode,
        };
      },
    },
  }),
);
app.use(cors());
app.use(express.json());
app.use(express.urlencoded({ extended: true }));
app.use(globalLimiter.middleware());

app.use("/api", router);

app.get("/", (_req: Request, res: Response) => {
  res.type("html").send(`<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Terrium API</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      font-family: 'DM Mono', 'Cascadia Code', monospace;
      background: #0A0E0C;
      color: rgba(255,255,255,0.9);
      display: flex;
      align-items: center;
      justify-content: center;
      min-height: 100vh;
    }
    .card {
      text-align: center;
      padding: 3rem;
    }
    .logo {
      display: inline-flex;
      align-items: center;
      gap: 0.75rem;
      margin-bottom: 1.5rem;
    }
    .dot {
      width: 10px; height: 10px;
      border-radius: 50%;
      background: #1D8A72;
      animation: pulse 2s ease-in-out infinite;
    }
    @keyframes pulse {
      0%, 100% { opacity: 0.4; }
      50% { opacity: 1; }
    }
    h1 {
      font-family: 'Space Grotesk', system-ui, sans-serif;
      font-size: 1.75rem;
      font-weight: 600;
      margin-bottom: 0.75rem;
      background: linear-gradient(135deg, #ffffff 0%, #c8e6de 50%, #1D8A72 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
    }
    p { color: rgba(255,255,255,0.4); margin-bottom: 2rem; font-size: 0.875rem; }
    .endpoints {
      text-align: left;
      display: inline-block;
    }
    .endpoint {
      display: flex;
      gap: 1rem;
      padding: 0.5rem 0;
      font-size: 0.75rem;
      color: rgba(255,255,255,0.5);
    }
    .method { color: #1D8A72; width: 4rem; }
    .path { color: rgba(255,255,255,0.7); }
    .ok { color: rgba(255,255,255,0.25); }
    a { color: #1D8A72; text-decoration: none; }
    a:hover { text-decoration: underline; }
  </style>
</head>
<body>
  <div class="card">
    <div class="logo">
      <span class="dot"></span>
      <span style="font-size:1.25rem;color:rgba(255,255,255,0.7)">terrium</span>
    </div>
    <h1>API Server</h1>
    <p>Science-Agent-Pipeline backend &mdash; all systems nominal</p>
    <div class="endpoints">
      <div class="endpoint"><span class="method">GET</span><span class="path">/api/healthz</span><span class="ok">health check</span></div>
      <div class="endpoint"><span class="method">GET</span><span class="path">/api/pipeline/status</span><span class="ok">pipeline subsystem status</span></div>
      <div class="endpoint"><span class="method">GET</span><span class="path">/api/metrics</span><span class="ok">aggregate platform metrics</span></div>
      <div class="endpoint"><span class="method">GET</span><span class="path">/api/enzymes</span><span class="ok">list known enzymes</span></div>
      <div class="endpoint"><span class="method">POST</span><span class="path">/api/resolve</span><span class="ok">preview domain resolution</span></div>
      <div class="endpoint"><span class="method">GET</span><span class="path">/api/simulate</span><span class="ok">list recent jobs</span></div>
      <div class="endpoint"><span class="method">POST</span><span class="path">/api/simulate</span><span class="ok">enqueue simulation</span></div>
      <div class="endpoint"><span class="method">POST</span><span class="path">/api/waitlist</span><span class="ok">join the pre-launch waitlist</span></div>
      <div class="endpoint"><span class="method">GET</span><span class="path">/api/waitlist/count</span><span class="ok">waitlist signup count</span></div>
    </div>
    <p style="margin-top:2rem;font-size:0.625rem">
      see the <a href="https://github.com/anomalyco/Terrium">landing page</a> for the full app
    </p>
  </div>
</body>
</html>`);
});

// Global error handler. Keeps the response shape consistent with the
// OpenAPI ErrorResponse schema and ensures pino always has a log line.
// eslint-disable-next-line @typescript-eslint/no-unused-vars
app.use((err: Error, _req: Request, res: Response, _next: NextFunction) => {
  logger.error({ err }, "Unhandled error in request handler");

  const message = err instanceof Error ? err.message : "Internal server error";
  res.status(500).json({
    error: "INTERNAL_SERVER_ERROR",
    message,
  });
});

export default app;
