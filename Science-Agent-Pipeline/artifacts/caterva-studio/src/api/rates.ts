/**
 * The Rates screen's one endpoint of its own: how a table is read.
 *
 * `POST /api/rates/preview` hands the text of a dropped or pasted table (and
 * the mapping the person has confirmed so far) to the server, which says what
 * the table is: its delimiter, header, decimal mark, columns, units, every
 * decision and every problem by line and column. The page never parses a
 * number itself, so what it shows is what the run will fit. A bad table is a
 * 200 with `ok: false` and the reason; only a body that is not a question is
 * a 400.
 */
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { apiPost } from "./client";
import type { RatesMapping, RatesPreview, RatesPreviewRequest } from "./types";

export function previewTable(body: RatesPreviewRequest): Promise<RatesPreview> {
  return apiPost<RatesPreview>("/api/rates/preview", body);
}

/** A short hash of a table's text, so a query key is not half a megabyte. */
export function fnv1a(text: string): string {
  let h = 0x811c9dc5;
  for (let i = 0; i < text.length; i++) {
    h ^= text.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return (h >>> 0).toString(16).padStart(8, "0") + text.length.toString(16);
}

/** How long a typed change to the mapping waits before it is asked about, in ms. */
export const PREVIEW_DELAY = 120;

/**
 * The server's reading of `text` under `mapping`, asked for once the mapping
 * has stopped changing. The previous answer stays on screen while the next
 * is on its way, so the table does not blink.
 */
export function useTablePreview(text: string | null, filename: string | null, mapping: RatesMapping) {
  const key = JSON.stringify(mapping);
  const [settled, setSettled] = useState(key);
  useEffect(() => {
    const timer = window.setTimeout(() => setSettled(key), PREVIEW_DELAY);
    return () => window.clearTimeout(timer);
  }, [key]);
  const asked = text === null ? null : fnv1a(text);
  return useQuery({
    queryKey: ["rates-preview", asked, filename, settled],
    queryFn: () => previewTable({ text: text as string, filename, mapping: JSON.parse(settled) as RatesMapping }),
    enabled: text !== null,
    staleTime: Infinity,
    gcTime: 60_000,
    retry: false,
    placeholderData: keepPreviousData,
  });
}
