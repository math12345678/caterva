/**
 * The status line along the bottom: what this installation can reach right
 * now. The server and its version, the literature layer, the network (not
 * probed until the reader asks, because probing contacts five third-party
 * hosts), GROMACS, and the workspace. Each item's dot uses the same
 * vocabulary (signal: available; caution ring: off, with the reason;
 * dashed: not checked; danger: failing) and each says its reason on
 * hover or focus, in the server's words.
 */
import * as Tooltip from "@radix-ui/react-tooltip";
import type { ReactNode } from "react";
import { Link } from "wouter";

import type { Capabilities, Health } from "@/api/types";
import { describeError } from "@/lib/errors";
import { formatCount } from "@/lib/format";

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
        <Item
          state={c ? (!c.network.checked ? "unknown" : c.network.reachable ? "ok" : "off") : "unknown"}
          label={c?.network.checked ? "network" : "network not checked"}
          reason={
            c
              ? c.network.checked
                ? c.network.reachable
                  ? `Every database host answered (checked ${c.network.checked_at ?? ""}).`
                  : `Not reachable: ${Object.entries(c.network.hosts)
                      .filter(([, ok]) => ok === false)
                      .map(([h]) => h)
                      .join(", ") || (c.network.reason ?? "unknown")}`
                : `${c.network.reason ?? "Not checked."} Check it from About.`
              : capsReason
          }
          href="/about"
        />
        <Item
          state={c ? (c.gromacs.found ? "ok" : "off") : "unknown"}
          label={c?.gromacs.found ? `GROMACS ${c.gromacs.version ?? ""}`.trim() : "GROMACS"}
          reason={c ? (c.gromacs.found ? `gmx at ${c.gromacs.path ?? "an unknown path"}` : (c.gromacs.reason ?? "gmx was not found")) : capsReason}
        />
        <span className="status-spacer" />
        <Item
          state={c ? (c.data_dir.writable ? "ok" : "bad") : "unknown"}
          label={c ? `${formatCount(c.data_dir.runs)} run${c.data_dir.runs === 1 ? "" : "s"}` : "workspace"}
          reason={c ? (c.data_dir.writable ? `Workspace: ${c.data_dir.path}` : (c.data_dir.reason ?? `${c.data_dir.path} is not writable`)) : capsReason}
          href="/history"
        />
        {c?.dev_origin ? (
          <Item state="unknown" label="development" reason={`The server also accepts ${c.dev_origin} (--dev-origin). Development only.`} />
        ) : null}
      </footer>
    </Tooltip.Provider>
  );
}
