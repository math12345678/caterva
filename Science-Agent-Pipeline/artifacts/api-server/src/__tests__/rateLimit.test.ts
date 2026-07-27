import { describe, it, expect, afterAll } from "vitest";
import request from "supertest";
import express from "express";
import rateLimit from "express-rate-limit";
import type { Server } from "node:http";

describe("Rate limiter", () => {
  it("allows requests under the limit then blocks over it", async () => {
    const limiter = rateLimit({
      windowMs: 60_000,
      max: 5,
      standardHeaders: true,
      legacyHeaders: false,
      message: { error: "TOO_MANY_REQUESTS", message: "Rate limit exceeded." },
    });

    const app = express();
    app.use(express.json());
    app.post("/test", limiter, (_req, res) => {
      res.status(200).json({ ok: true });
    });

    const server = app.listen(0);
    const doReq = () => request(server).post("/test").send({});

    for (let i = 0; i < 5; i++) {
      const res = await doReq();
      expect(res.status).toBe(200);
    }

    for (let i = 0; i < 3; i++) {
      const res = await doReq();
      expect(res.status).toBe(429);
    }

    server.close();
  });
});
