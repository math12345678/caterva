/**
 * An entry's atoms for the viewer: GET /api/structure/{pdb_id}/coordinates,
 * fetched once per entry and kept (the server fetches through `caterva
 * prepare`'s cache; the page keeps what it was sent for the session).
 */
import { useQuery } from "@tanstack/react-query";
import { useSearch } from "wouter";

import { apiJson } from "@/api/client";
import type { CoordinatesResponse } from "@/api/types";

export function useCoordinates(pdbId: string | null) {
  return useQuery({
    queryKey: ["structure-coordinates", pdbId],
    queryFn: () => apiJson<CoordinatesResponse>(`/api/structure/${encodeURIComponent(pdbId ?? "")}/coordinates`),
    enabled: Boolean(pdbId),
    staleTime: Infinity,
    gcTime: 30 * 60 * 1000,
  });
}

/** One query parameter of the current location (`?pdb=1I10`), or null. */
export function useParam(name: string): string | null {
  const search = useSearch();
  return new URLSearchParams(search).get(name);
}
