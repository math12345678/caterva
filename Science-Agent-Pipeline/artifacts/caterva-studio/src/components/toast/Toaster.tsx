/**
 * Where notifications appear: the lower right, above the status line, in a
 * polite live region so a screen reader hears a run finish without losing
 * its place. Each one keeps its tone's mark (the provenance family's
 * shapes: a signal dot for a result, a dashed ring for a refusal, a caution
 * ring for a negative finding, a danger square for a failure) so it reads in
 * greyscale. Hovering or focusing one holds it; Escape inside it dismisses.
 */
import { X } from "lucide-react";

import { dismissToast, holdToast, type ToastTone, useToasts } from "@/lib/toast";

function ToneMark({ tone }: { tone: ToastTone }) {
  const common = { width: 10, height: 10, viewBox: "0 0 10 10", "aria-hidden": true as const, focusable: "false" as const };
  switch (tone) {
    case "done":
      return (
        <svg {...common}>
          <circle cx="5" cy="5" r="4" fill="var(--signal)" />
        </svg>
      );
    case "refused":
      return (
        <svg {...common}>
          <circle cx="5" cy="5" r="3.4" fill="none" stroke="var(--fg-soft)" strokeWidth="1.35" strokeDasharray="1.7 1.35" />
        </svg>
      );
    case "negative":
      return (
        <svg {...common}>
          <circle cx="5" cy="5" r="3.35" fill="none" stroke="var(--caution)" strokeWidth="1.6" />
        </svg>
      );
    case "failed":
      return (
        <svg {...common}>
          <rect x="1.5" y="1.5" width="7" height="7" fill="var(--danger)" />
        </svg>
      );
    case "info":
      return (
        <svg {...common}>
          <rect x="1.25" y="4.1" width="7.5" height="1.8" rx="0.4" fill="var(--muted)" />
        </svg>
      );
  }
}

export function Toaster() {
  const toasts = useToasts();
  return (
    <section className="toaster" aria-label="Notifications" aria-live="polite" aria-relevant="additions">
      {toasts.map((t) => (
        <div
          key={t.id}
          className="toast"
          data-tone={t.tone}
          role={t.tone === "failed" ? "alert" : "status"}
          tabIndex={-1}
          onMouseEnter={() => holdToast(t.id, true)}
          onMouseLeave={() => holdToast(t.id, false)}
          onFocus={() => holdToast(t.id, true)}
          onBlur={() => holdToast(t.id, false)}
          onKeyDown={(e) => {
            if (e.key === "Escape") dismissToast(t.id);
          }}
        >
          <span className="toast-mark">
            <ToneMark tone={t.tone} />
          </span>
          <div className="toast-text">
            <p className="toast-title">{t.title}</p>
            {t.description ? <p className="toast-description">{t.description}</p> : null}
          </div>
          <div className="toast-actions">
            {t.action ? (
              <button
                type="button"
                className="btn btn-sm"
                onClick={() => {
                  t.action?.onClick();
                  dismissToast(t.id);
                }}
              >
                {t.action.label}
              </button>
            ) : null}
            <button type="button" className="btn btn-sm btn-quiet btn-icon" aria-label="Dismiss" onClick={() => dismissToast(t.id)}>
              <X size={13} aria-hidden="true" />
            </button>
          </div>
        </div>
      ))}
    </section>
  );
}
