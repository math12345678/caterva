/**
 * The empty, error and refusal states every screen uses.
 *
 * A refusal is not an error: it is Caterva declining a question and saying
 * why (exit 3), and it is drawn as a finding, in ink, with the reason in
 * full. An error is something that went wrong (a crash, a server that
 * stopped) and says what to do next. Neither is ever a bare "Something went
 * wrong".
 */
import type { ReactNode } from "react";

import type { ApiError } from "@/api/types";

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <section className="state state-empty" aria-label={title}>
      <h2 className="state-title">{title}</h2>
      {children ? <div className="state-body">{children}</div> : null}
    </section>
  );
}

export function RefusalState({ title = "Refused, and why", reason }: { title?: string; reason: string }) {
  return (
    <section className="state state-refusal" aria-label={title}>
      <h2 className="state-title">{title}</h2>
      <p className="state-body whitespace-pre-wrap">{reason}</p>
    </section>
  );
}

export function ErrorState({ error, action }: { error: ApiError; action?: ReactNode }) {
  return (
    <section className="state state-error" role="alert">
      <h2 className="state-title">{error.code === "malformed" ? "That question is not well formed" : "Something failed"}</h2>
      <p className="state-body whitespace-pre-wrap">{error.message}</p>
      {error.field ? <p className="state-field font-mono">{error.field}</p> : null}
      {action}
    </section>
  );
}
