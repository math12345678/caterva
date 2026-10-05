/**
 * The assistant on a finished run: explain it, draft its methods, ask about it, and (when the engine ranked
 * measurements) put those in plain words.
 *
 * Each tool is behind its own switch in Settings and appears only when that switch is on. With the assistant
 * off this is one quiet line. Every tool works only from THIS run's own result, which the server reads itself;
 * the page sends the run's id, never the result. Nothing is sent until a person has clicked, and the first use
 * of each tool stops at a preview of the exact payload.
 */
import { useId, useState } from "react";
import { Link } from "wouter";

import { type AssistantAnswer, confirmAssistant, type ExplainReply } from "@/api/assistant";
import type { RunKind, RunRecord } from "@/api/types";
import { TextInput } from "@/components/forms/Field";
import { ProvenanceMark } from "@/components/provenance/ProvenanceMark";

import { AiCaption, CallView, EngineText } from "./CallView";
import { type AssistantCall, useAssistantCall, useAssistantStatus, useHasQueryClient } from "./useAssistant";
import "./assistant.css";

/** Kinds whose results the assistant reads. */
export const ASSISTANT_KINDS: readonly RunKind[] = ["compose", "constants", "bind", "analyze", "rates"];

function hasRankedMeasurements(result: unknown): boolean {
  const sections = (result as { sections?: { key?: string; status?: string }[] } | null)?.sections;
  return Array.isArray(sections) && sections.some((s) => s?.key === "design" && s.status !== "refused");
}

function ExplainBody({ answer }: { answer: AssistantAnswer }) {
  const content = answer.content as { reply: ExplainReply } | null;
  if (!content) return null;
  const r = content.reply;
  return (
    <div className="asst-reply">
      <AiCaption model={answer.model} local={answer.local} checked={Boolean(answer.grounding?.ok)} />
      <p>{r.summary}</p>
      <dl className="asst-dl">
        <dt>The worst thing wrong with it</dt>
        <dd>{r.worst_thing}</dd>
        <dt>What to do next</dt>
        <dd>{r.next_step}</dd>
      </dl>
      {r.terms.length ? (
        <dl className="asst-dl asst-terms">
          {r.terms.map((t) => (
            <div key={t.term}>
              <dt>{t.term}</dt>
              <dd>{t.meaning}</dd>
            </div>
          ))}
        </dl>
      ) : null}
    </div>
  );
}

function MethodsBody({ answer, runId }: { answer: AssistantAnswer; runId: string }) {
  const content = answer.content as { reply: { text: string } } | null;
  const original = content?.reply.text ?? "";
  const [text, setText] = useState(original);
  const [copied, setCopied] = useState(false);
  const id = useId();
  const edited = text !== original;
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
    } catch {
      setCopied(false);
    }
    void confirmAssistant({ call_id: answer.call_id, event: edited ? "edit" : "use" }).catch(() => undefined);
  };
  return (
    <div className="asst-reply" data-run={runId}>
      <AiCaption model={answer.model} local={answer.local} checked={Boolean(answer.grounding?.ok)} />
      <label className="asst-label" htmlFor={id}>
        Draft, yours to edit
      </label>
      <textarea
        id={id}
        className="textarea asst-draft"
        value={text}
        rows={7}
        onChange={(e) => {
          setText(e.target.value);
          setCopied(false);
        }}
      />
      <div className="asst-actions">
        <button type="button" className="btn btn-sm" onClick={() => void copy()}>
          {copied ? "Copied" : "Copy"}
        </button>
        {edited ? (
          <button type="button" className="btn btn-sm btn-quiet" onClick={() => setText(original)}>
            Back to the draft
          </button>
        ) : null}
      </div>
      <p className="field-hint">
        Edits are yours: Caterva checked the draft above, not what you change. The engine's own methods text, below,
        remains the default.
      </p>
      {answer.fallback.text ? <EngineText text={answer.fallback.text} title="Caterva's own methods text" /> : null}
    </div>
  );
}

function PlainBody({ answer, text }: { answer: AssistantAnswer; text: string }) {
  return (
    <div className="asst-reply">
      <AiCaption model={answer.model} local={answer.local} checked={Boolean(answer.grounding?.ok)} />
      <p>{text}</p>
    </div>
  );
}

function NextBody({ answer }: { answer: AssistantAnswer }) {
  const content = answer.content as { reply: { narration: string; order: string[] } } | null;
  if (!content) return null;
  return (
    <div className="asst-reply">
      <AiCaption model={answer.model} local={answer.local} checked={Boolean(answer.grounding?.ok)} />
      <p>{content.reply.narration}</p>
      {content.reply.order.length ? (
        <p className="asst-order">
          In the engine's order: <span className="font-mono">{content.reply.order.join(", ")}</span>
        </p>
      ) : null}
      {answer.fallback.text ? <EngineText text={answer.fallback.text} /> : null}
    </div>
  );
}

function Tool({
  label,
  call,
  onClick,
  onShow,
  busy,
}: {
  label: string;
  call: AssistantCall;
  onClick: () => void;
  onShow: () => void;
  busy: boolean;
}) {
  void call;
  return (
    <span className="asst-tool">
      <button type="button" className="btn btn-sm" onClick={onClick} disabled={busy}>
        {label}
      </button>
      <button type="button" className="btn btn-sm btn-quiet" onClick={onShow} disabled={busy} aria-label={`Show what ${label} would send`}>
        Show what is sent
      </button>
    </span>
  );
}

function RunAssistantInner({ run, result }: { run: RunRecord; result: unknown }) {
  const status = useAssistantStatus();
  const explain = useAssistantCall();
  const methods = useAssistantCall();
  const ask = useAssistantCall();
  const next = useAssistantCall();
  const [question, setQuestion] = useState("");
  const askId = useId();
  if (!ASSISTANT_KINDS.includes(run.kind)) return null;
  if (status.isError || !status.data) return null;
  const s = status.data;
  if (s.state === "off") {
    return (
      <p className="asst-off">
        Assistant off. <Link href="/settings">Settings</Link> can switch it on.
      </p>
    );
  }
  const busy = (c: AssistantCall) => c.phase.name === "preparing" || c.phase.name === "sending";
  const on = (f: "explain" | "methods" | "ask" | "next") => s.features[f]?.on;
  const canNext = on("next") && hasRankedMeasurements(result);
  const anyTool = on("explain") || on("methods") || on("ask") || canNext;
  const header = (
    <header className="asst-head">
      <ProvenanceMark provenance={{ kind: "ai" }} decorative />
      <h3 className="asst-title">Assistant</h3>
      <span className="asst-where">{s.indicator}</span>
    </header>
  );
  if (s.state !== "ready" || !anyTool) {
    return (
      <section className="asst" aria-label="Assistant">
        {header}
        <p className="asst-off">
          {s.state === "ready" || s.state === "idle"
            ? "No assistant tool is switched on."
            : s.state === "needs_key"
              ? "It needs a key."
              : s.state === "needs_model"
                ? "It needs a model name."
                : "It is paused."}{" "}
          <Link href="/settings">Settings</Link>
        </p>
      </section>
    );
  }
  const base = { run_id: run.id } as const;
  return (
    <section className="asst" aria-label="Assistant">
      {header}
      <div className="asst-tools">
        {on("explain") ? (
          <Tool
            label="Explain this result"
            call={explain}
            busy={busy(explain)}
            onClick={() => void explain.run({ feature: "explain", ...base })}
            onShow={() => void explain.show({ feature: "explain", ...base })}
          />
        ) : null}
        {on("methods") ? (
          <Tool
            label="Draft my methods"
            call={methods}
            busy={busy(methods)}
            onClick={() => void methods.run({ feature: "methods", ...base })}
            onShow={() => void methods.show({ feature: "methods", ...base })}
          />
        ) : null}
        {canNext ? (
          <Tool
            label="What should I measure next"
            call={next}
            busy={busy(next)}
            onClick={() => void next.run({ feature: "next", ...base })}
            onShow={() => void next.show({ feature: "next", ...base })}
          />
        ) : null}
      </div>
      {on("explain") ? (
        <CallView call={explain} includeDataOption>
          {(a) => <ExplainBody answer={a} />}
        </CallView>
      ) : null}
      {on("methods") ? (
        <CallView call={methods} includeDataOption>
          {(a) => <MethodsBody answer={a} runId={run.id} />}
        </CallView>
      ) : null}
      {canNext ? (
        <CallView call={next}>{(a) => <NextBody answer={a} />}</CallView>
      ) : null}
      {on("ask") ? (
        <form
          className="asst-ask"
          onSubmit={(e) => {
            e.preventDefault();
            if (question.trim()) void ask.run({ feature: "ask", question: question.trim(), ...base });
          }}
        >
          <label className="asst-label" htmlFor={askId}>
            Ask this run
          </label>
          <div className="asst-ask-row">
            <TextInput
              id={askId}
              value={question}
              maxLength={400}
              placeholder="Why is kcat a placeholder?"
              onChange={(e) => setQuestion(e.target.value)}
            />
            <button type="submit" className="btn btn-sm" disabled={!question.trim() || busy(ask)}>
              Ask
            </button>
          </div>
          <p className="field-hint">About this result only. Each question stands alone; nothing is kept beyond this run.</p>
          <CallView call={ask} includeDataOption>
            {(a) => {
              const c = a.content as { declined?: boolean; text?: string; reply?: { answer: string } } | null;
              if (c?.declined) return <p className="asst-note">{c.text}</p>;
              return <PlainBody answer={a} text={c?.reply?.answer ?? ""} />;
            }}
          </CallView>
        </form>
      ) : null}
    </section>
  );
}

export function RunAssistant(props: { run: RunRecord; result: unknown }) {
  return useHasQueryClient() ? <RunAssistantInner {...props} /> : null;
}
