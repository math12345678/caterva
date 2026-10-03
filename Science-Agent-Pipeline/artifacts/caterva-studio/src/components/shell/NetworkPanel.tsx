/**
 * What is known about the network, and the button that asks again. Shown in
 * the status bar's popover and on the Settings screen, so the answer and
 * the way to refresh it are the same in both.
 *
 * The check contacts each database host once with a short timeout (5 s) and
 * only when this button is pressed; nothing here runs it on its own.
 */
import type { NetworkCapability } from "@/api/types";
import { hostName, readNetwork, useNetworkCheck } from "@/lib/network";
import { describeError } from "@/lib/errors";

export function NetworkPanel({ net }: { net: NetworkCapability }) {
  const check = useNetworkCheck();
  const reading = readNetwork(net);
  return (
    <div className="net-panel">
      <p className="net-sentence" data-state={reading.state}>
        <span className="status-dot" data-state={reading.state === "off" ? "off" : reading.state} aria-hidden="true" />
        {reading.sentence}
      </p>
      <ul className="host-list" aria-label="Database hosts">
        {Object.entries(net.hosts).map(([host, ok]) => (
          <li key={host}>
            <span className="status-dot" data-state={ok === null ? "unknown" : ok ? "ok" : "off"} aria-hidden="true" />
            <span className="font-mono">{host}</span>
            <span className="muted">
              {hostName(host)}: {ok === null ? "not checked" : ok ? "answered" : "did not answer"}
            </span>
          </li>
        ))}
      </ul>
      <div className="net-actions">
        <button type="button" className="btn btn-sm" onClick={() => check.mutate()} disabled={check.isPending}>
          {check.isPending ? "Checking" : "Check the network"}
        </button>
        <span className="field-hint">Contacts each host once, 5 seconds at most.</span>
      </div>
      {check.isError ? (
        <p className="field-error" role="alert">
          The check could not be made: {describeError(check.error).message}
        </p>
      ) : null}
    </div>
  );
}
