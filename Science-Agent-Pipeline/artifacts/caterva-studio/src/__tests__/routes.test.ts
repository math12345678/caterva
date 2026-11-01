import { describe, expect, it } from "vitest";

import { KIND_SHAPES, type RunKind } from "@/api/types";
import { ROUTES, routeForKind } from "@/routes";

/** The routes docs/studio/CONTRACT.md reserves, in its order. */
const RESERVED = [
  "/",
  "/compose",
  "/constants",
  "/rates",
  "/structure",
  "/prepare",
  "/md",
  "/analyze",
  "/bind",
  "/sim",
  "/history",
  "/settings",
  "/about",
];

describe("the route table", () => {
  it("reserves every route the contract names, each once", () => {
    const paths = ROUTES.map((r) => r.path);
    expect([...paths].sort()).toEqual([...RESERVED].sort());
  });

  it("gates /rates on the rates capability and nothing else", () => {
    expect(ROUTES.filter((r) => r.gate).map((r) => r.path)).toEqual(["/rates"]);
  });

  it("has a screen for every run kind, so History can open any run", () => {
    for (const kind of Object.keys(KIND_SHAPES) as RunKind[]) {
      expect(routeForKind(kind), kind).toBeDefined();
    }
  });
});
