/**
 * The core reads every screen shares: the server's health, what this
 * installation can do, and the run list. One query key each, so the top
 * bar, the status line and a screen asking the same question share one
 * answer and one request.
 */
import { keepPreviousData, QueryClient, useQuery } from "@tanstack/react-query";

import { ApiRequestError, apiJson } from "@/api/client";
import { type ListRunsQuery, listRuns } from "@/api/runs";
import type { Capabilities, Health } from "@/api/types";

import { CapabilitiesSchema, HealthSchema } from "./schemas";

export function makeQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        // A refusal will not change on a retry; only a dropped connection might.
        retry: (count, error) => error instanceof ApiRequestError && error.kind === "network" && count < 2,
        refetchOnWindowFocus: false,
      },
    },
  });
}

export const HEALTH_KEY = ["health"] as const;
export const CAPABILITIES_KEY = ["capabilities"] as const;

export function useHealth() {
  return useQuery({
    queryKey: HEALTH_KEY,
    queryFn: () => apiJson<Health>("/api/health", {}, HealthSchema),
    // A server that stops is noticed within half a minute, and the shell says so.
    refetchInterval: 30_000,
    refetchIntervalInBackground: false,
  });
}

export function useCapabilities(enabled = true) {
  return useQuery({
    queryKey: CAPABILITIES_KEY,
    queryFn: () => apiJson<Capabilities>("/api/capabilities", {}, CapabilitiesSchema),
    enabled,
    staleTime: 60_000,
  });
}

/** Contacts the five hosts of CONTRACT.md 10.2; only when the reader asks. */
export function probeNetwork(): Promise<Capabilities> {
  return apiJson<Capabilities>("/api/capabilities?probe=network", {}, CapabilitiesSchema);
}

/** Runs the chosen gmx now (CONTRACT.md 7): the only request that does. Answers the capabilities. */
export function refreshGromacs(): Promise<Capabilities> {
  return apiJson<Capabilities>("/api/capabilities/refresh", { method: "POST", body: "{}" }, CapabilitiesSchema);
}

export function useRunList(query: ListRunsQuery = {}, enabled = true) {
  return useQuery({
    queryKey: ["runs", "list", query],
    queryFn: () => listRuns(query),
    enabled,
    placeholderData: keepPreviousData,
  });
}
