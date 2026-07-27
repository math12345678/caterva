import { defineConfig } from "vitest/config";
import path from "node:path";

export default defineConfig({
  resolve: {
    conditions: ["workspace"],
  },
  test: {
    globals: true,
    environment: "node",
    include: ["src/**/*.test.ts"],
    testTimeout: 15000,
    hookTimeout: 10000,
  },
});
