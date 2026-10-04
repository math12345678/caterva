/**
 * The persistent indicator: whenever data can leave this computer through the assistant, the status line says
 * where it goes. Off, nothing is shown here (Settings says it is off); a model on this computer says nothing
 * leaves it.
 */
import { Link } from "wouter";

import { useAssistantStatus, useHasQueryClient } from "./useAssistant";

function StatusItem() {
  const status = useAssistantStatus();
  const s = status.data;
  if (!s || s.state === "off" || s.state === "idle") return null;
  const sends = s.state === "ready" && s.leaves_machine;
  return (
    <Link
      href="/settings"
      className="status-item"
      aria-label={s.indicator}
      data-assistant={s.state}
      data-leaves={sends ? "true" : "false"}
    >
      <span className="status-dot" data-state={s.state === "ready" ? (sends ? "off" : "ok") : "unknown"} aria-hidden="true" />
      {s.indicator}
    </Link>
  );
}

export function AssistantStatusItem() {
  return useHasQueryClient() ? <StatusItem /> : null;
}
