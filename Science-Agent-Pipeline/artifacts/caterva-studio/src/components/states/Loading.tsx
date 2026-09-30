/**
 * Loading: the mark's eight dots in motion, never a generic spinner.
 *
 * A swell travels round the C (each dot scales and brightens in turn),
 * animated on transform and opacity only, with an exponential ease-out.
 * Under prefers-reduced-motion the dots stand still and the label carries
 * the state alone (index.css, `.loading-dot`).
 */
import { MARK_DOTS, MARK_VIEWBOX } from "@/components/brand/Mark";

export function Loading({ label, size = 40 }: { label: string; size?: number }) {
  return (
    <div className="loading" role="status" aria-live="polite">
      <svg viewBox={MARK_VIEWBOX} height={size} width={(size * 514) / 634} aria-hidden="true">
        {MARK_DOTS.map(([cx, cy, r, signal], i) => (
          <circle
            key={`${cx}-${cy}`}
            className="loading-dot"
            style={{ animationDelay: `${i * 90}ms`, transformOrigin: `${cx}px ${cy}px` }}
            cx={cx}
            cy={cy}
            r={r}
            fill={signal ? "var(--signal)" : "currentColor"}
          />
        ))}
      </svg>
      <span className="loading-label">{label}</span>
    </div>
  );
}
