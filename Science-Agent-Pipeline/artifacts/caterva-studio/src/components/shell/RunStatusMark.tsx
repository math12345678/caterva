/**
 * A run's state as a mark, in the provenance family's shapes: the signal
 * dot for a produced result, a dashed ring for a refusal, a broken line for a
 * database that did not answer, a caution ring
 * for a negative finding, a danger square for a crash, a short bar for a
 * cancelled or interrupted run, and the loading mark's dots, small, for a
 * run still working. Each has an accessible name.
 */
import type { OutcomeMeaning, RunStatus } from "@/api/types";
import { MarkLoader } from "@/components/brand/MarkLoader";

export function runStatusLabel(status: RunStatus, meaning: OutcomeMeaning | null): string {
  switch (status) {
    case "queued":
      return "queued";
    case "running":
      return "running";
    case "cancelling":
      return "cancelling";
    case "done":
      return meaning === "refused"
        ? "refused"
        : meaning === "negative"
          ? "negative finding"
          : meaning === "network"
            ? "a database did not answer"
            : "finished";
    case "failed":
      return "failed";
    case "cancelled":
      return "cancelled";
    case "abandoned":
      return "abandoned";
    case "interrupted":
      return "interrupted";
  }
}

export function RunStatusMark({ status, meaning }: { status: RunStatus; meaning: OutcomeMeaning | null }) {
  const label = runStatusLabel(status, meaning);
  if (status === "queued" || status === "running" || status === "cancelling") {
    return (
      <span className="run-status-mark" role="img" aria-label={label}>
        <MarkLoader size={13} still={status === "queued"} />
      </span>
    );
  }
  let shape;
  if (status === "done" && meaning === "refused") {
    shape = <circle cx="5" cy="5" r="3.4" fill="none" stroke="var(--fg-soft)" strokeWidth="1.35" strokeDasharray="1.7 1.35" />;
  } else if (status === "done" && meaning === "network") {
    shape = <path d="M1 5h2.6M6.4 5H9" stroke="var(--fg-soft)" strokeWidth="1.8" strokeLinecap="round" fill="none" />;
  } else if (status === "done" && meaning === "negative") {
    shape = <circle cx="5" cy="5" r="3.35" fill="none" stroke="var(--caution)" strokeWidth="1.6" />;
  } else if (status === "done") {
    shape = <circle cx="5" cy="5" r="4" fill="var(--signal)" />;
  } else if (status === "failed") {
    shape = <rect x="1.5" y="1.5" width="7" height="7" fill="var(--danger)" />;
  } else {
    shape = <rect x="1.25" y="4.1" width="7.5" height="1.8" rx="0.4" fill="var(--muted)" />;
  }
  return (
    <svg className="run-status-mark" width="10" height="10" viewBox="0 0 10 10" role="img" aria-label={label} focusable="false">
      {shape}
    </svg>
  );
}
