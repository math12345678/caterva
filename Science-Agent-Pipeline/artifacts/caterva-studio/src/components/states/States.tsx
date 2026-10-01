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

import type { ApiError, Outcome, RunError } from "@/api/types";
import { cn } from "@/lib/cn";
import { describeApiError, describeError, type ReadableError } from "@/lib/errors";

function Kicker({ tone, children }: { tone: "refusal" | "negative" | "error" | "empty"; children: ReactNode }) {
  const mark =
    tone === "error" ? (
      <rect x="1.5" y="1.5" width="7" height="7" fill="var(--danger)" />
    ) : tone === "negative" ? (
      <circle cx="5" cy="5" r="3.35" fill="none" stroke="var(--caution)" strokeWidth="1.6" />
    ) : tone === "refusal" ? (
      <circle cx="5" cy="5" r="3.4" fill="none" stroke="currentColor" strokeWidth="1.35" strokeDasharray="1.7 1.35" />
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
  children,
  inset = true,
}: {
  title?: string;
  /** The command's own words, verbatim. */
  reason: string;
  children?: ReactNode;
  inset?: boolean;
}) {
  return (
    <section className={cn("state state-refusal", inset && "state-inset")} aria-label={title}>
      <Kicker tone="refusal">Refused</Kicker>
      <h2 className="state-title">{title}</h2>
      <p className="state-reason">{reason}</p>
      {children ? <div className="state-body">{children}</div> : null}
    </section>
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
    <section className={cn("state state-negative", inset && "state-inset")} aria-label={title}>
      <Kicker tone="negative">Negative finding</Kicker>
      <h2 className="state-title">{title}</h2>
      <p className="state-reason">{reason}</p>
      {children ? <div className="state-body">{children}</div> : null}
    </section>
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
 * server sent) and says what happened and what to do, in that order.
 */
export function ErrorState({
  error,
  title,
  action,
  inset = false,
}: {
  error: unknown;
  title?: string;
  action?: ReactNode;
  inset?: boolean;
}) {
  const r = readable(error);
  return (
    <section className={cn("state state-error", inset && "state-inset")} role="alert">
      <Kicker tone="error">{r.code === "malformed" ? "Not well formed" : "Failed"}</Kicker>
      <h2 className="state-title">{title ?? r.title}</h2>
      <p className="state-reason">{r.message}</p>
      {r.field ? (
        <p className="state-field">
          field <span className="font-mono">{r.field}</span>
        </p>
      ) : null}
      {r.hint ? <p className="state-body">{r.hint}</p> : null}
      {action ? <div className="state-actions">{action}</div> : null}
    </section>
  );
}

/** A run that crashed (exit 1): its exception type and message; the traceback stays in the bundle. */
export function RunFailedState({ error, action }: { error: RunError; action?: ReactNode }) {
  return (
    <section className="state state-error state-inset" role="alert">
      <Kicker tone="error">Failed</Kicker>
      <h2 className="state-title">The run stopped with an error</h2>
      <p className="state-reason">
        <span className="font-mono">{error.type}</span>: {error.message}
      </p>
      <p className="state-body">
        The full traceback is kept with the run; export its bundle from History to report it.
      </p>
      {action ? <div className="state-actions">{action}</div> : null}
    </section>
  );
}

/**
 * The verdict of a finished run, chosen from its outcome: nothing for a
 * produced result (the screen draws the result), a refusal, or a negative
 * finding. The screen draws the result itself below a negative finding.
 */
export function OutcomeNotice({ outcome, children }: { outcome: Outcome | null; children?: ReactNode }) {
  if (!outcome || outcome.meaning === "produced") return null;
  if (outcome.meaning === "refused") {
    return (
      <RefusalState title={outcome.summary || "Refused, and why"} reason={outcome.reason ?? ""}>
        {children}
      </RefusalState>
    );
  }
  return (
    <NegativeState title={outcome.summary || "A negative finding"} reason={outcome.reason ?? ""}>
      {children}
    </NegativeState>
  );
}
