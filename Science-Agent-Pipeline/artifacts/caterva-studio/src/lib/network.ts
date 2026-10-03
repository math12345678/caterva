/**
 * What the network is known to be, in words, and the one way to ask again.
 *
 * The server learns it two ways (docs/studio/CONTRACT.md 10): from real
 * use, when a BRENDA, UniProt, NCBI or RCSB request was answered or could
 * not be made, and from an explicit check that contacts each database host
 * with a short timeout. "Not checked" is only what the server says before
 * either has happened. This reads that answer; it never decides one.
 */
import { useMutation, useQueryClient } from "@tanstack/react-query";

import type { NetworkCapability } from "@/api/types";

import { hostLabel, plain, withoutUrls } from "./copy";
import { formatDateTime } from "./format";
import { CAPABILITIES_KEY, probeNetwork } from "./queries";

export type NetworkState = "unknown" | "ok" | "off";

export interface NetworkReading {
  state: NetworkState;
  /** The status line's label. */
  label: string;
  /** One honest sentence about what is known and from where. */
  sentence: string;
  /** The server's own text for a failure, for a disclosure; null when there is none. */
  detail: string | null;
}

export function hostName(host: string): string {
  return hostLabel(host);
}

/**
 * What a recorded reason says, in words: a host that "could not be reached"
 * with an exception after it is a host that did not answer; the exception
 * text itself stays in `NetworkReading.detail` for a disclosure and is never
 * part of a sentence or an accessible name.
 */
export function describeReason(reason: string | null, fallback: string): string {
  if (!reason) return fallback;
  const one = /^(\S+) could not be reached: /.exec(reason);
  if (one) return `${hostLabel(one[1])} did not answer`;
  const many = /^not reachable from this computer: (.+)$/s.exec(reason);
  if (many) {
    const hosts = many[1].split("; ").map((entry) => /^(\S+?): /.exec(entry)?.[1]).filter((h): h is string => Boolean(h));
    if (hosts.length) return `${hosts.map(hostLabel).join(", ")} did not answer`;
  }
  return plain(withoutUrls(reason));
}

/** The hosts whose latest outcome was `answered`, named. */
function named(hosts: Record<string, boolean | null>, answered: boolean): string[] {
  return Object.entries(hosts)
    .filter(([, ok]) => ok === answered)
    .map(([h]) => hostName(h));
}

export function readNetwork(net: NetworkCapability): NetworkReading {
  if (!net.checked) {
    return {
      state: "unknown",
      label: "network not checked",
      sentence: "Nothing has contacted a database since this studio started, so there is nothing to report yet. Check it to find out.",
      detail: null,
    };
  }
  const when = net.checked_at ? formatDateTime(net.checked_at) : "";
  if (net.source === "use") {
    if (net.reachable) {
      const who = named(net.hosts, true).join(", ");
      return {
        state: "ok",
        label: "network reachable",
        sentence: `${who || "A database"} answered the last real request (${when}). That was a lookup you ran, not a check of every host; check to test them all.`,
        detail: null,
      };
    }
    return {
      state: "off",
      label: "network unreachable",
      sentence: `${describeReason(net.reason, "A database could not be reached")} (${when}). That was a lookup you ran; check to test every host again.`,
      detail: net.reason,
    };
  }
  if (net.reachable) {
    return { state: "ok", label: "network reachable", sentence: `Every database host answered a check (${when}).`, detail: null };
  }
  const failing = named(net.hosts, false);
  return {
    state: "off",
    label: "network unreachable",
    sentence: `${failing.length ? `${failing.join(", ")} did not answer a check` : describeReason(net.reason, "A check failed")} (${when}).`,
    detail: net.reason,
  };
}

/** The explicit re-check: contacts each host once, with a short timeout, and updates what every screen reads. */
export function useNetworkCheck() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: probeNetwork,
    onSuccess: (fresh) => client.setQueryData(CAPABILITIES_KEY, fresh),
  });
}
