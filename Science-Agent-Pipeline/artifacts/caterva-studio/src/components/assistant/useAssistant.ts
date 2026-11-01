/**
 * The assistant's two reads and its one flow.
 *
 * `useAssistantStatus` is what every assistant affordance looks at first: when it says `off`, nothing else
 * on the page talks to the assistant at all. `useAssistantCall` is the life of one call as the page sees it:
 *
 *   idle -> preparing -> preview -> sending -> done
 *
 * `prepare` builds the payload on the server and answers it as the PREVIEW; nothing is sent. `send` sends those
 * exact bytes (the page echoes the payload's hash, so what the server sends is what was shown) and answers once
 * the reply has been checked. A first use of a feature stops at `preview` until the person agrees; after that a
 * click goes straight through, and the payload stays one disclosure away.
 */
import { QueryClientContext, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useContext, useEffect, useRef, useState } from "react";

import {
  type AssistantAnswer,
  type AssistantFeature,
  type AssistantPreview,
  cancelAssistant,
  getAssistantRuns,
  getAssistantStatus,
  prepareAssistant,
  sendAssistant,
} from "@/api/assistant";
import { describeError } from "@/lib/errors";

/**
 * Whether a QueryClient is in scope. The assistant's affordances draw nothing without one, so a screen rendered
 * on its own (a component test, a story) is exactly what it was before the assistant existed.
 */
export function useHasQueryClient(): boolean {
  return useContext(QueryClientContext) !== undefined;
}

export const ASSISTANT_STATUS_KEY = ["assistant", "status"] as const;

export function useAssistantStatus() {
  return useQuery({
    queryKey: ASSISTANT_STATUS_KEY,
    queryFn: getAssistantStatus,
    staleTime: 5_000,
    // An older server has no such route: that is "no assistant", not an error to show.
    retry: false,
  });
}

/** The ids of runs that used the assistant, for History's mark. */
export function useAssistantRuns(enabled = true) {
  return useQuery({ queryKey: ["assistant", "runs"], queryFn: getAssistantRuns, enabled, staleTime: 10_000, retry: false });
}

export interface CallParams {
  feature: AssistantFeature | "test";
  run_id?: string;
  text?: string;
  question?: string;
  include_data?: boolean;
}

export type CallPhase =
  | { name: "idle" }
  | { name: "preparing" }
  | { name: "preview"; preview: AssistantPreview }
  | { name: "sending"; preview: AssistantPreview }
  | { name: "done"; preview: AssistantPreview; answer: AssistantAnswer }
  | { name: "failed"; message: string; code: string | null };

export interface AssistantCall {
  phase: CallPhase;
  /** Prepare, then send at once unless this feature still needs the person's agreement. */
  run: (params: CallParams) => Promise<void>;
  /** Prepare only: show what would be sent. */
  show: (params: CallParams) => Promise<void>;
  /** Prepare again with a changed option (include my data). */
  reprepare: (patch: Partial<CallParams>) => Promise<void>;
  send: (consent: boolean) => Promise<void>;
  cancel: () => void;
  reset: () => void;
  params: CallParams | null;
}

export function useAssistantCall(): AssistantCall {
  const [phase, setPhase] = useState<CallPhase>({ name: "idle" });
  const params = useRef<CallParams | null>(null);
  const live = useRef(true);
  const client = useQueryClient();
  useEffect(() => {
    live.current = true;
    return () => {
      live.current = false;
    };
  }, []);
  const settle = useCallback((next: CallPhase) => {
    if (live.current) setPhase(next);
  }, []);

  const fail = useCallback(
    (e: unknown) => {
      const read = describeError(e);
      settle({ name: "failed", message: read.message, code: read.status === 409 ? "refused" : read.code });
    },
    [settle],
  );

  const doSend = useCallback(
    async (preview: AssistantPreview, consent: boolean) => {
      settle({ name: "sending", preview });
      try {
        const answer = await sendAssistant({
          call_id: preview.call_id,
          payload_sha256: preview.payload_sha256,
          ...(consent ? { consent: true } : {}),
        });
        settle({ name: "done", preview, answer });
      } catch (e) {
        fail(e);
      } finally {
        void client.invalidateQueries({ queryKey: ASSISTANT_STATUS_KEY });
        void client.invalidateQueries({ queryKey: ["assistant", "runs"] });
      }
    },
    [client, fail, settle],
  );

  const prepare = useCallback(
    async (p: CallParams): Promise<AssistantPreview | null> => {
      params.current = p;
      settle({ name: "preparing" });
      try {
        return await prepareAssistant(p);
      } catch (e) {
        fail(e);
        return null;
      }
    },
    [fail, settle],
  );

  const run = useCallback(
    async (p: CallParams) => {
      const preview = await prepare(p);
      if (!preview) return;
      if (preview.consent_required) settle({ name: "preview", preview });
      else await doSend(preview, false);
    },
    [doSend, prepare, settle],
  );

  const show = useCallback(
    async (p: CallParams) => {
      const preview = await prepare(p);
      if (preview) settle({ name: "preview", preview });
    },
    [prepare, settle],
  );

  const reprepare = useCallback(
    async (patch: Partial<CallParams>) => {
      if (!params.current) return;
      const preview = await prepare({ ...params.current, ...patch });
      if (preview) settle({ name: "preview", preview });
    },
    [prepare, settle],
  );

  const send = useCallback(
    async (consent: boolean) => {
      if (phase.name !== "preview") return;
      await doSend(phase.preview, consent);
    },
    [doSend, phase],
  );

  const cancel = useCallback(() => {
    if (phase.name === "sending") void cancelAssistant(phase.preview.call_id).catch(() => undefined);
    else settle({ name: "idle" });
  }, [phase, settle]);

  const reset = useCallback(() => settle({ name: "idle" }), [settle]);
  return { phase, run, show, reprepare, send, cancel, reset, params: params.current };
}
