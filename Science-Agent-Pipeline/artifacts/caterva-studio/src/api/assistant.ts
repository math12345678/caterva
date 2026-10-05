/**
 * The assistant's routes (CONTRACT.md "Assistant"). Plain typed calls: nothing here ever holds, sends or reads
 * a key, and nothing runs until a person's click calls `send`.
 */
import { apiJson, apiPost, apiPut } from "./client";

export type AssistantFeature = "describe" | "explain" | "methods" | "ask" | "next";
export type AssistantState = "off" | "blocked" | "needs_key" | "needs_model" | "idle" | "ready";

export interface AssistantFeatureStatus {
  label: string;
  on: boolean;
  sends: string;
  consented_at: string | null;
}

export interface AssistantStatus {
  state: AssistantState;
  /** The sentence the status bar shows. */
  indicator: string;
  leaves_machine: boolean;
  destination: { host: string; local: boolean; label: string };
  provider: string;
  model: string;
  providers: { name: string; label: string; local: boolean; needs_key: boolean }[];
  key: { present: boolean; needed: boolean; source: "keychain" | "environment" | null; provider: string; note: string | null };
  features: Record<AssistantFeature, AssistantFeatureStatus>;
  spend: { remaining: number; max_calls_per_hour: number; max_tokens: number };
  note: string | null;
}

export interface AssistantSettings {
  enabled: boolean;
  provider: string;
  models: Record<string, string>;
  model_lists: Record<string, string[]>;
  local_url: string;
  local_only: boolean;
  features: Record<AssistantFeature, boolean>;
  max_calls_per_hour: number;
  max_tokens: number;
  consent: Record<string, string>;
}

export interface AssistantPreview {
  call_id: string;
  feature: AssistantFeature | "test";
  provider: string;
  model: string;
  destination: { host: string; local: boolean; label: string };
  leaves_machine: boolean;
  url: string;
  payload: string;
  payload_sha256: string;
  bytes: number;
  consent_required: boolean;
  include_data: boolean;
  sends: string;
  spend: { remaining: number };
  fallback: { text?: string };
}

export interface GroundingFailure {
  kind: string;
  token: string;
  reason: string;
  start: number;
  end: number;
}

export interface ExplainReply {
  summary: string;
  worst_thing: string;
  next_step: string;
  terms: { term: string; meaning: string }[];
}

export interface Proposal {
  shape: string;
  description: string;
  request: Record<string, unknown>;
  reading: string | null;
  organism_note: string | null;
  stages: number | null;
  variant: string | null;
  suggested: [string, unknown][];
  enzyme_candidates: { ec: string; name: string }[];
  /** The shape's own variants (empty when the engine does not branch on a word). */
  variants: string[];
  needs_stages: boolean;
  max_stages: number;
}

export type AssistantOutcome = "accepted" | "rejected" | "declined" | "cancelled" | "error";

export interface AssistantAnswer {
  call_id: string;
  feature: AssistantFeature | "test";
  outcome: AssistantOutcome;
  provider: string;
  model: string;
  local: boolean;
  latency_ms: number | null;
  content:
    | null
    | { kind: "ai"; reply: ExplainReply | { text: string } | { answerable: boolean; answer: string } | { narration: string; order: string[] } }
    | { proposal: Proposal }
    | { declined: true; text: string }
    | { reply: string };
  rejection: null | {
    kind: "schema" | "intent" | "grounding" | "unranked";
    message: string;
    detail: string;
    failures?: GroundingFailure[];
    reasons?: string[];
    rejected_text: string;
  };
  error: null | { code: string; message: string; retry_after_s?: number | null };
  fallback: { text?: string };
  grounding: { ok: boolean; failures: GroundingFailure[]; checked: Record<string, number> } | null;
  run_id: string | null;
}

export interface AssistantConfirmed {
  call_id: string;
  request: Record<string, unknown>;
  reading: string | null;
  provenance: {
    kind: "chosen";
    by: "user";
    reason: string;
    suggested_by: { assistant: string; provider: string; call_id: string };
  };
}

export interface AssistantLog {
  records: Record<string, unknown>[];
  methods: string[];
}

export const getAssistantStatus = () => apiJson<AssistantStatus>("/api/assistant/status");
export const getAssistantSettings = () => apiJson<AssistantSettings>("/api/assistant/settings");
export const putAssistantSettings = (body: Partial<Omit<AssistantSettings, "consent">>) =>
  apiPut<AssistantSettings>("/api/assistant/settings", body);
export const prepareAssistant = (body: {
  feature: AssistantFeature | "test";
  run_id?: string;
  text?: string;
  question?: string;
  include_data?: boolean;
}) => apiPost<AssistantPreview>("/api/assistant/prepare", body);
export const sendAssistant = (body: { call_id: string; payload_sha256: string; consent?: boolean }) =>
  apiPost<AssistantAnswer>("/api/assistant/send", body);
export const cancelAssistant = (call_id: string) => apiPost<{ call_id: string }>("/api/assistant/cancel", { call_id });
export const confirmAssistant = (body: { call_id: string; event: "confirm" | "use" | "edit"; choices?: Record<string, unknown> }) =>
  apiPost<AssistantConfirmed | { call_id: string; recorded: string }>("/api/assistant/confirm", body);
export const getAssistantLog = (run_id?: string) =>
  apiJson<AssistantLog>(`/api/assistant/log${run_id ? `?run_id=${encodeURIComponent(run_id)}` : ""}`);
export const getAssistantRuns = () => apiJson<{ run_ids: string[] }>("/api/assistant/runs");
export const attachAssistantCalls = (run_id: string, call_ids: string[]) =>
  apiPost<{ attached: number }>("/api/assistant/attach", { run_id, call_ids });
export const forgetAssistantConsent = () => apiPost<{ consent: Record<string, never> }>("/api/assistant/forget-consent", {});
