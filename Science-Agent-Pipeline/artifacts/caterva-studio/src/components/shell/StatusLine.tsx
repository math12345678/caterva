/**
 * The status line along the bottom: what this installation can reach right
 * now. The server and its version, the literature layer, the network (what
 * a real lookup last found, or what an explicit check found; "not checked"
 * only before either has happened, and the popover checks again on request,
 * because probing contacts third-party hosts), GROMACS, and the
 * workspace. Each item's dot uses the same
 * vocabulary (signal: available; caution ring: off, with the reason;
 * dashed: not checked; danger: failing) and each says its reason on
 * hover or focus, in the server's words.
 */
import * as Popover from "@radix-ui/react-popover";
import * as Tooltip from "@radix-ui/react-tooltip";
import { useEffect, type ReactNode } from "react";
import { Link } from "wouter";

import type { Capabilities, Health } from "@/api/types";
import { describeError } from "@/lib/errors";
import { formatCount } from "@/lib/format";
import { readNetwork, useNetworkCheck } from "@/lib/network";

import { AssistantStatusItem } from "@/components/assistant/AssistantStatusItem";

import { NetworkPanel } from "./NetworkPanel";

type DotState = "ok" | "off" | "unknown" | "bad";

function Item({
  state,
  label,
  reason,
  href,
}: {
  state: DotState;
  label: ReactNode;
  reason: string;
  href?: string;
}) {
  const inner = (
    <>
      <span className="status-dot" data-state={state} aria-hidden="true" />
      {label}
    </>
  );
  const trigger = href ? (
    <Link href={href} className="status-item" aria-label={`${typeof label === "string" ? label : ""} ${reason}`.trim()}>
      {inner}
    </Link>
  ) : (
    <button type="button" className="status-item" aria-label={`${typeof label === "string" ? label : ""}: ${reason}`}>
      {inner}
    </button>
  );
  return (
    <Tooltip.Root>
      <Tooltip.Trigger asChild>{trigger}</Tooltip.Trigger>
      <Tooltip.Portal>
        <Tooltip.Content className="tooltip" side="top" sideOffset={6} collisionPadding={8}>
          {reason}
        </Tooltip.Content>
      </Tooltip.Portal>
    </Tooltip.Root>
  );
}

/**
 * The network, with a popover that says what is known and from where, and
 * checks again when asked. A button, not a link: the explanation and the
 * check are right here.
 */
function NetworkItem({ net }: { net: Capabilities["network"] }) {
  const reading = readNetwork(net);
  return (
    <Popover.Root>
      <Popover.Trigger className="status-item" aria-label={`${reading.label}. ${reading.sentence}`}>
        <span className="status-dot" data-state={reading.state} aria-hidden="true" />
        {reading.label}
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content className="overlay popover net-popover" side="top" align="start" sideOffset={6} collisionPadding={12} aria-label="The network">
          <NetworkPanel net={net} />
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}

/** The first check of this page load has been started. */
let checkedOnLaunch = false;

/** Lets a test start a "page load" again. */
export function resetLaunchCheck(): void {
  checkedOnLaunch = false;
}

export function StatusLine({
  health,
  healthError,
  capabilities,
  capabilitiesError,
}: {
  health: Health | undefined;
  healthError: unknown;
  capabilities: Capabilities | undefined;
  capabilitiesError: unknown;
}) {
  const c = capabilities;
  const capsReason = capabilitiesError ? describeError(capabilitiesError).message : "asking the server";
  const check = useNetworkCheck();
  const unchecked = c ? !c.network.checked : false;
  useEffect(() => {
    // Once per page load: a status that says "not checked" on a working network reads as a broken one.
    // The server skips the contact itself while offline mode is on.
    if (unchecked && !checkedOnLaunch) {
      checkedOnLaunch = true;
      check.mutate();
    }
  }, [unchecked, check]);
  return (
    <Tooltip.Provider delayDuration={250} skipDelayDuration={150}>
      <footer className="status-line" aria-label="What this installation can reach">
        <Item
          state={healthError ? "bad" : health ? "ok" : "unknown"}
          label={health ? `server ${health.version}` : "server"}
          reason={
            healthError
              ? describeError(healthError).message
              : health
                ? `caterva studio ${health.version} (API ${health.api_version}), running since ${health.started_at}`
                : "connecting"
          }
        />
        <Item
          state={c ? (c.literature.available ? "ok" : "off") : "unknown"}
          label="literature"
          reason={c ? (c.literature.available ? "The literature layer is installed: BRENDA, UniProt, NCBI and PubMed lookups can run." : (c.literature.reason ?? "not available")) : capsReason}
        />
        {c ? (
          <NetworkItem net={c.network} />
        ) : (
          <Item state="unknown" label="network not checked" reason={capsReason} />
        )}
        <Item
          state={c ? (c.gromacs.found ? "ok" : "off") : "unknown"}
          label={c?.gromacs.found ? `GROMACS ${c.gromacs.version ?? ""}`.trim() : "GROMACS"}
          reason={c ? (c.gromacs.found ? `gmx at ${c.gromacs.path ?? "an unknown path"}` : (c.gromacs.reason ?? "gmx was not found")) : capsReason}
        />
        <AssistantStatusItem />
        <span className="status-spacer" />
        <Item
          state={c ? (c.data_dir.writable ? "ok" : "bad") : "unknown"}
          label={c ? `${formatCount(c.data_dir.runs)} run${c.data_dir.runs === 1 ? "" : "s"}` : "workspace"}
          reason={c ? (c.data_dir.writable ? `Workspace: ${c.data_dir.path}` : (c.data_dir.reason ?? `${c.data_dir.path} is not writable`)) : capsReason}
          href="/history"
        />
        {c?.dev_origin ? (
          <Item state="unknown" label="development" reason={`The server also accepts requests from ${c.dev_origin}. Development only.`} />
        ) : null}
      </footer>
    </Tooltip.Provider>
  );
}
