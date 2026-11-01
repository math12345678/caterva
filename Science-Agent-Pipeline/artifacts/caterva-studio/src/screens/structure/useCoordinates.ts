/**
 * An entry's atoms for the viewer: GET /api/structure/{pdb_id}/coordinates,
 * fetched once per entry and kept for the session (the server fetches
 * through `caterva prepare`'s cache, and the same audit's catalytic
 * residues and findings ride along).
 */
import { useQuery } from "@tanstack/react-query";

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
