/**
 * One assistant call, drawn from first click to answer: the consent preview, the wait, and the reply.
 *
 * Calm and subordinate on purpose. The assistant's words sit in a quiet well under a caption that says what
 * they are ("Assistant text, not a measurement"), with the `ai` mark, and never in a verdict's style. A reply
 * the engine rejected is not shown as the assistant's wording at all: the engine's own text takes its place
 * and says why, with the rejected text one disclosure away.
 *
 * The preview is an inline disclosure, not a dialog: the exact payload (after redaction), where it goes, what
 * it holds, and, for the first use of a feature, the agreement the server insists on.
 */
import { useId, useState, type ReactNode } from "react";

import type { AssistantAnswer, AssistantPreview } from "@/api/assistant";
import { Disclosure } from "@/components/forms/Disclosure";
import { Checkbox } from "@/components/forms/Field";
import { ProvenanceMark } from "@/components/provenance/ProvenanceMark";
import { Loading } from "@/components/states/Loading";
import { plain } from "@/lib/copy";

import type { AssistantCall } from "./useAssistant";
import "./assistant.css";

/** The caption over every piece of assistant text. */
export function AiCaption({ model, local, checked }: { model?: string; local?: boolean; checked?: boolean }) {
  return (
    <p className="asst-caption">
      <ProvenanceMark provenance={{ kind: "ai" }} decorative />
      <span className="asst-caption-main">Assistant text, not a measurement</span>
      {model ? (
        <span className="asst-caption-detail">
          {model}
          {local ? ", on this computer" : ""}
        </span>
      ) : null}
      {checked ? (
        <span className="asst-caption-detail">every figure and name in it was found in your results</span>
      ) : null}
    </p>
  );
}

/** The engine's own words, shown when the assistant's were not used. */
export function EngineText({ text, title = "The engine's own words" }: { text: string; title?: string }) {
  return (
    <div className="asst-engine">
      <p className="asst-caption asst-caption-engine">
        <span className="asst-caption-main">{title}</span>
      </p>
      <pre className="report-text asst-engine-text">{plain(text)}</pre>
    </div>
  );
}

function Payload({ preview, open }: { preview: AssistantPreview; open?: boolean }) {
  return (
    <Disclosure
      title="Show exactly what will be sent"
      aside={<span className="font-mono">{preview.bytes.toLocaleString("en-US")} bytes</span>}
      defaultOpen={open}
    >
      <p className="field-hint">
        This is the whole request, after paths, your user name, e-mail addresses and anything shaped like a key
        were removed. Nothing else is added when it is sent.
      </p>
      <pre className="asst-payload" tabIndex={0} aria-label="The request, as it will be sent">
        {preview.payload}
      </pre>
    </Disclosure>
  );
}

function Destination({ preview }: { preview: AssistantPreview }) {
  return preview.destination.local ? (
    <>This runs on a model on this computer. Nothing leaves it.</>
  ) : (
    <>
      This is sent to <strong>{preview.destination.host}</strong> ({preview.destination.label}). What it does with it
      is governed by its own terms.
    </>
  );
}

function ConsentPreview({
  call,
  preview,
  includeDataOption,
}: {
  call: AssistantCall;
  preview: AssistantPreview;
  includeDataOption: boolean;
}) {
  const [agreed, setAgreed] = useState(false);
  const id = useId();
  const needsAgreement = preview.consent_required;
  return (
    <div className="asst-preview" aria-labelledby={`${id}-h`}>
      <p className="asst-preview-head" id={`${id}-h`}>
        {needsAgreement ? "Before the first send" : "What would be sent"}
      </p>
      <p>
        <Destination preview={preview} /> {preview.sends}
      </p>
      {includeDataOption ? (
        <Checkbox
          checked={preview.include_data}
          onChange={(v) => void call.reprepare({ include_data: v })}
          label="Include my data"
          hint="What you typed or chose to start this run (its title, compound names). Left out unless you tick this."
        />
      ) : null}
      <Payload preview={preview} open={needsAgreement} />
      {needsAgreement ? (
        <Checkbox
          checked={agreed}
          onChange={setAgreed}
          label={preview.destination.local ? "I have read what will be sent" : `I agree to send this to ${preview.destination.host}`}
          hint="Asked once for each feature. You can withdraw it in Settings."
        />
      ) : null}
      <div className="asst-actions">
        <button type="button" className="btn btn-sm btn-primary" disabled={needsAgreement && !agreed} onClick={() => void call.send(agreed)}>
          Send
        </button>
        <button type="button" className="btn btn-sm btn-quiet" onClick={call.cancel}>
          Not now
        </button>
      </div>
    </div>
  );
}

function Rejected({ answer }: { answer: AssistantAnswer }) {
  const r = answer.rejection;
  if (!r) return null;
  return (
    <div className="asst-rejected">
      <p className="asst-note" role="status">
        {r.message}
      </p>
      {answer.fallback.text ? <EngineText text={answer.fallback.text} /> : null}
      <Disclosure title="Show the rejected wording and what failed">
        {r.failures?.length ? (
          <ul className="asst-failures">
            {r.failures.map((f, i) => (
              <li key={`${f.kind}-${f.token}-${i}`}>
                <span className="font-mono">{f.token}</span> <span className="asst-fail-kind">{f.kind}</span> {f.reason}
              </li>
            ))}
          </ul>
        ) : r.reasons?.length ? (
          <ul className="asst-failures">
            {r.reasons.map((x) => (
              <li key={x}>{x}</li>
            ))}
          </ul>
        ) : (
          <p>{r.detail}</p>
        )}
        <p className="asst-caption asst-caption-engine">
          <span className="asst-caption-main">The rejected text, not used</span>
        </p>
        <pre className="report-text asst-engine-text">{r.rejected_text}</pre>
      </Disclosure>
    </div>
  );
}

export function CallView({
  call,
  includeDataOption = false,
  children,
  waitLabel = "Waiting for the assistant",
}: {
  call: AssistantCall;
  includeDataOption?: boolean;
  /** The accepted reply, drawn by the feature. */
  children: (answer: AssistantAnswer, preview: AssistantPreview) => ReactNode;
  waitLabel?: string;
}) {
  const { phase } = call;
  switch (phase.name) {
    case "idle":
      return null;
    case "preparing":
      return <Loading label="Preparing the request" size={26} />;
    case "preview":
      return <ConsentPreview call={call} preview={phase.preview} includeDataOption={includeDataOption} />;
    case "sending":
      return (
        <div className="asst-wait">
          <Loading
            label={waitLabel}
            size={26}
            detail={phase.preview.destination.local ? "on this computer" : `sent to ${phase.preview.destination.host}`}
          />
          <button type="button" className="btn btn-sm" onClick={call.cancel}>
            Cancel
          </button>
        </div>
      );
    case "failed":
      return (
        <p className="asst-note" role="status">
          {phase.message}
        </p>
      );
    case "done": {
      const { answer, preview } = phase;
      let body: ReactNode;
      if (answer.outcome === "accepted" || answer.outcome === "declined") body = children(answer, preview);
      else if (answer.outcome === "rejected") body = <Rejected answer={answer} />;
      else if (answer.outcome === "cancelled")
        body = <p className="asst-note">Cancelled. Nothing from the assistant was used.</p>;
      else
        body = (
          <div className="asst-rejected">
            <p className="asst-note" role="status">
              {answer.error?.message ?? "The assistant did not answer."} The engine's own text is below.
            </p>
            {answer.fallback.text ? <EngineText text={answer.fallback.text} /> : null}
          </div>
        );
      return (
        <div className="asst-done">
          {body}
          <Disclosure title="What was sent" aside={<span className="font-mono">{answer.model}</span>}>
            <p className="field-hint">
              Recorded with this run, with the reply and the result of the check. {answer.local ? "It stayed on this computer." : ""}
            </p>
            <pre className="asst-payload" tabIndex={0} aria-label="The request that was sent">
              {preview.payload}
            </pre>
          </Disclosure>
        </div>
      );
    }
  }
}
