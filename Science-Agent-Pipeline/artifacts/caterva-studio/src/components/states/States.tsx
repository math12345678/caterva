/**
 * The states every screen uses, designed as one family: empty, error,
 * refused, negative, and the outcome of a finished run that chooses between
 * them.
 *
 * Three outcomes stay apart because the CLI keeps them apart in its exit
 * code (docs/studio/CONTRACT.md 6):
 *
 * - a refusal (exit 3) is Caterva declining a question and saying why. It is
 *   drawn as a finding, in ink, with the reason in the command's own words,
 *   never as a red error;
 * - a negative finding (exit 4: "the computed value disagrees with the
 *   measured band") is a result, drawn with its verdict, in the caution
 *   colour that means "read twice";
 * - an error is something that went wrong (a crash, a server that stopped,
 *   a malformed question) and says what to do next.
 *
 * Neither is ever a bare "Something went wrong": the server's message is
 * shown whole.
 */
import type { ReactNode } from "react";

import type { ApiError, NetworkFailure, Outcome, RunError } from "@/api/types";
import { cn } from "@/lib/cn";
import { CompoundChoices } from "@/components/run/CompoundChoices";
import { hostLabel, networkFailureOf, networkSentence, plain, plural, readCompoundList, withoutUrls } from "@/lib/copy";
import { describeApiError, describeError, type ReadableError } from "@/lib/errors";

type Tone = "refusal" | "negative" | "error" | "empty" | "network";

function Kicker({ tone, children }: { tone: Tone; children: ReactNode }) {
  const mark =
    tone === "error" ? (
      <rect x="1.5" y="1.5" width="7" height="7" fill="var(--danger)" />
    ) : tone === "negative" ? (
      <circle cx="5" cy="5" r="3.35" fill="none" stroke="var(--caution)" strokeWidth="1.6" />
    ) : tone === "refusal" ? (
      <circle cx="5" cy="5" r="3.4" fill="none" stroke="currentColor" strokeWidth="1.35" strokeDasharray="1.7 1.35" />
    ) : tone === "network" ? (
      <path d="M1.5 5h2M6.5 5h2" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" fill="none" />
    ) : (
      <circle cx="5" cy="5" r="3.4" fill="none" stroke="var(--rule-strong)" strokeWidth="1.35" />
    );
  return (
    <span className="state-kicker">
      <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden="true" focusable="false">
        {mark}
      </svg>
      {children}
    </span>
  );
}

/**
 * One layout for everything that did not come out: a kicker, a heading, the
 * reason in plain words, what to change, the engine's own text in a
 * disclosure when it was reworded, and the actions. The refusal, the
 * negative finding, the failure and the outage are this component with a
 * different tone, so they read the same on every screen.
 */
function Problem({
  tone,
  kicker,
  title,
  reason,
  raw,
  change,
  actions,
  children,
  inset,
  role,
  labelled = true,
}: {
  tone: Tone;
  kicker: string;
  title: string;
  reason?: string;
  /** The engine's text before the page reworded it; shown in a disclosure when it differs from `reason`. */
  raw?: string;
  /** What to change, in a sentence. */
  change?: ReactNode;
  actions?: ReactNode;
  children?: ReactNode;
  inset: boolean;
  role?: "alert";
  labelled?: boolean;
}) {
  return (
    <section
      className={cn("state", `state-${tone === "network" ? "refusal state-network" : tone}`, inset && "state-inset")}
      aria-label={labelled ? title : undefined}
      role={role}
    >
      <Kicker tone={tone}>{kicker}</Kicker>
      <h2 className="state-title">{title}</h2>
      {reason ? <p className="state-reason">{reason}</p> : null}
      {change ? <p className="state-change">{change}</p> : null}
      {children ? <div className="state-body">{children}</div> : null}
      {raw && raw.trim() !== (reason ?? "").trim() ? (
        <details className="state-raw">
          <summary>What the engine said</summary>
          <pre>{raw}</pre>
        </details>
      ) : null}
      {actions ? <div className="state-actions">{actions}</div> : null}
    </section>
  );
}

export function EmptyState({
  title,
  children,
  actions,
  inset = false,
}: {
  title: string;
  children?: ReactNode;
  actions?: ReactNode;
  inset?: boolean;
}) {
  return (
    <section className={cn("state state-empty", inset && "state-inset")} aria-label={title}>
      <h2 className="state-title">{title}</h2>
      {children ? <div className="state-body">{children}</div> : null}
      {actions ? <div className="state-actions">{actions}</div> : null}
    </section>
  );
}

/** Caterva declined the question, and says why (exit 3). */
export function RefusalState({
  title = "Refused, and why",
  reason,
  rawText,
  change,
  children,
  inset = true,
}: {
  title?: string;
  /** The command's own words. Request URLs, flags and dashes are reworded; the engine's text stays in a disclosure. */
  reason: string;
  /** The engine's whole text, when `reason` is only part of it. */
  rawText?: string;
  change?: ReactNode;
  children?: ReactNode;
  inset?: boolean;
}) {
  return (
    <Problem
      tone="refusal"
      kicker="Refused"
      title={plain(withoutUrls(title))}
      reason={plain(withoutUrls(reason))}
      raw={rawText ?? reason}
      change={change}
      inset={inset}
    >
      {children}
    </Problem>
  );
}

/**
 * A database that did not answer. Not Caterva declining: a sentence naming
 * the host, what to do, a Retry, and the engine's exception text behind a
 * disclosure.
 */
export function NetworkState({
  failure,
  raw,
  again = "try again",
  onRetry,
  retryLabel = "Retry",
  inset = true,
  children,
}: {
  failure: NetworkFailure | null;
  raw?: string;
  /** Finishes "Check the network, then ...": "search again", "try again". */
  again?: string;
  onRetry?: () => void;
  retryLabel?: string;
  inset?: boolean;
  children?: ReactNode;
}) {
  const who = failure?.host ? hostLabel(failure.host) : "A database";
  const cap = who.charAt(0).toUpperCase() + who.slice(1);
  const refusedRequest = failure?.status !== null && failure?.status !== undefined && failure.status < 500 && failure.status !== 429;
  return (
    <Problem
      tone="network"
      kicker="Did not answer"
      title={`${cap} ${refusedRequest ? "refused the request" : "did not answer"}`}
      reason={networkSentence(failure, again)}
      raw={raw}
      inset={inset}
      actions={
        onRetry ? (
          <button type="button" className="btn btn-sm" onClick={onRetry}>
            {retryLabel}
          </button>
        ) : undefined
      }
    >
      {children}
    </Problem>
  );
}

/** A result that is a negative finding (exit 4), with its verdict. */
export function NegativeState({
  title = "A negative finding",
  reason,
  children,
  inset = true,
}: {
  title?: string;
  /** contract.NEGATIVE_MEANING[kind]: the command's words for exit 4. */
  reason: string;
  children?: ReactNode;
  inset?: boolean;
}) {
  return (
    <Problem tone="negative" kicker="Negative finding" title={plain(title)} reason={plain(reason)} raw={reason} inset={inset}>
      {children}
    </Problem>
  );
}

function readable(error: unknown): ReadableError {
  if (error && typeof error === "object" && "code" in error && "message" in error && !(error instanceof Error)) {
    return describeApiError(error as ApiError);
  }
  return describeError(error);
}

/**
 * Something failed. Takes anything a request can throw (or an ApiError the
 * server sent) and says what happened and what to do, in that order. A
 * failure that is a database not answering takes the network layout.
 */
export function ErrorState({
  error,
  title,
  action,
  onRetry,
  again,
  inset = false,
}: {
  error: unknown;
  title?: string;
  action?: ReactNode;
  /** Draws the outage's Retry button when the failure is a database not answering. */
  onRetry?: () => void;
  again?: string;
  inset?: boolean;
}) {
  const r = readable(error);
  const outage = r.code === "unavailable" || r.code === "crash" || r.code === "page" ? networkFailureOf(r.raw) : null;
  if (outage) {
    return <NetworkState failure={outage} raw={r.raw} onRetry={onRetry} again={again} inset={inset} />;
  }
  return (
    <Problem
      tone="error"
      kicker={r.code === "malformed" ? "Not well formed" : "Failed"}
      title={title ?? r.title}
      reason={r.message}
      raw={r.raw}
      change={r.hint ?? undefined}
      inset={inset}
      role="alert"
      labelled={false}
      actions={action}
    >
      {r.field ? (
        <p className="state-field">
          field <span className="font-mono">{r.field}</span>
        </p>
      ) : null}
    </Problem>
  );
}

/** A run that crashed (exit 1): its exception type and message; the traceback stays in the bundle. */
export function RunFailedState({ error, action, onRetry }: { error: RunError; action?: ReactNode; onRetry?: () => void }) {
  const outage = networkFailureOf(error.message);
  if (outage) {
    return <NetworkState failure={outage} raw={`${error.type}: ${error.message}`} onRetry={onRetry} again="run it again" />;
  }
  return (
    <Problem
      tone="error"
      kicker="Failed"
      title="The run stopped with an error"
      reason={`${error.type}: ${plain(withoutUrls(error.message))}`}
      raw={`${error.type}: ${error.message}`}
      change="The full traceback is kept with the run; export its bundle from History to report it."
      inset
      role="alert"
      labelled={false}
      actions={action}
    />
  );
}

/**
 * The verdict of a finished run, chosen from its outcome: nothing for a
 * produced result (the screen draws the result), a refusal, an upstream
 * outage or a negative finding. The screen draws the result itself below a
 * negative finding.
 */
export function OutcomeNotice({
  outcome,
  onRetry,
  again,
  onChooseCompound,
  children,
}: {
  outcome: Outcome | null;
  onRetry?: () => void;
  again?: string;
  /** Fills the form's Inhibitor field with a compound a refusal says has a measurement. */
  onChooseCompound?: (name: string) => void;
  children?: ReactNode;
}) {
  if (!outcome || outcome.meaning === "produced") return null;
  if (outcome.meaning === "network") {
    return (
      <NetworkState
        failure={outcome.network ?? networkFailureOf(outcome.reason)}
        raw={outcome.reason ?? outcome.summary}
        onRetry={onRetry}
        again={again}
      >
        {children}
      </NetworkState>
    );
  }
  const refused = outcome.meaning === "refused";
  const compounds = refused && outcome.reason ? readCompoundList(outcome.reason) : null;
  if (compounds) {
    const n = compounds.compounds.length;
    const lead = noticeText(compounds.lead.split("\n")[0], compounds.lead, "Refused, and why");
    return (
      <RefusalState
        title={lead.title}
        reason={`${lead.reason}\n${plural(n, "compound")} ${n === 1 ? "does" : "do"} have one.`}
        rawText={outcome.reason ?? undefined}
      >
        <CompoundChoices compounds={compounds.compounds} onChoose={onChooseCompound} />
        {children}
      </RefusalState>
    );
  }
  const { title, reason } = noticeText(outcome.summary, outcome.reason ?? "", refused ? "Refused, and why" : "A negative finding");
  if (refused) {
    return (
      <RefusalState title={title} reason={reason}>
        {children}
      </RefusalState>
    );
  }
  return (
    <NegativeState title={title} reason={reason}>
      {children}
    </NegativeState>
  );
}

/** Past this length a summary is a paragraph, not a heading. */
const TITLE_LIMIT = 160;

/**
 * An outcome's summary is the first line of the command's message, and its
 * reason is often that whole message: shown as heading and body, the first
 * sentence was printed twice (bind's "No Ki for ..."), and compose's
 * 2,000-character list of shapes became a heading. A summary too long to
 * be a heading gives way to the generic one, and a reason line that only
 * repeats the heading is left out. Nothing is reworded or cut: every line
 * the command wrote is still on the page once.
 */
export function noticeText(summary: string, reason: string, fallback: string): { title: string; reason: string } {
  const said = summary.trim();
  const title = said && said.length <= TITLE_LIMIT ? said : fallback;
  if (title === fallback) {
    return { title, reason: reason.includes(said) ? reason : [said, reason].filter(Boolean).join("\n\n") };
  }
  const lines = reason.split("\n");
  const kept = lines.filter((line) => line.trim() !== title);
  return { title, reason: kept.join("\n").replace(/^\n+/, "") };
}
