/**
 * Loading: the mark's eight dots in motion with a sentence beside them,
 * never a generic spinner (docs/studio/CONTRACT.md 17.1).
 *
 * The sentence is the most specific one known: a run's current stage label
 * from its event stream ("Searching BRENDA for EC 2.7.1.1") when there is
 * one, otherwise what the page is waiting for. A counted stage shows its
 * count in figures too, so the state never rests on the dots alone.
 */
import type { CSSProperties } from "react";

import { MarkLoader } from "@/components/brand/MarkLoader";
import { cn } from "@/lib/cn";

export function Loading({
  label,
  fraction = null,
  detail,
  size = 36,
  className,
}: {
  label: string;
  /** 0..1 when the work can be counted. */
  fraction?: number | null;
  /** A second line: elapsed time, which stage of how many. */
  detail?: string;
  size?: number;
  className?: string;
}) {
  const counted = fraction !== null && Number.isFinite(fraction);
  const percent = counted ? Math.round((fraction as number) * 100) : null;
  // Only the sentence is a live region, so a stage change is announced and the
  // counter beside it, which changes every second, is not.
  return (
    <div className={cn("loading", className)}>
      <span
        className="loading-mark"
        role={counted ? "progressbar" : undefined}
        aria-label={counted ? label : undefined}
        aria-valuemin={counted ? 0 : undefined}
        aria-valuemax={counted ? 100 : undefined}
        aria-valuenow={percent ?? undefined}
        aria-valuetext={counted ? `${label}, ${percent}%` : undefined}
      >
        <MarkLoader size={size} fraction={fraction} />
      </span>
      <span className="loading-text">
        <span className="loading-label" role="status" aria-label={label}>
          {label}
        </span>
        {counted || detail ? (
          <span className="loading-sub">
            {counted ? `${percent}%` : null}
            {counted && detail ? " · " : null}
            {detail}
          </span>
        ) : null}
      </span>
    </div>
  );
}

/** Rows standing in for a list that is loading, pulsing in the mark's rhythm. */
export function SkeletonRows({ rows = 6, label = "Loading" }: { rows?: number; label?: string }) {
  return (
    <div className="grid gap-3 py-2" role="status" aria-label={label}>
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="grid gap-1.5">
          <div className="skeleton-row" style={{ "--i": i, width: `${62 - ((i * 17) % 30)}%` } as CSSProperties} />
          <div className="skeleton-row" style={{ "--i": i, width: `${34 - ((i * 7) % 12)}%`, height: 8 } as CSSProperties} />
        </div>
      ))}
    </div>
  );
}
