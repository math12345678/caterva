/**
 * Once a run submitted on a screen exists, the address becomes its
 * permalink (`<path>?run=<id>`, replacing the linked question rather than
 * adding a history entry), so a reload or a copied address reopens this run
 * instead of showing an empty form. Shared by the kinetics and structure
 * screens: before the merge only the kinetics screens did this, and a
 * reload of a finished Structures, Prepare or Analyze run lost it.
 */
import { useEffect } from "react";
import { useLocation } from "wouter";

import type { RunRecord } from "@/api/types";

export function useRunAddress(path: string, run: Pick<RunRecord, "id"> | null, reopened: string | null): void {
  const [, navigate] = useLocation();
  const id = run?.id ?? null;
  useEffect(() => {
    if (id && id !== reopened) navigate(`${path}?run=${encodeURIComponent(id)}`, { replace: true });
    // navigate is stable; the run id is what decides.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);
}
