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

import { formatDateTime } from "./format";
import { CAPABILITIES_KEY, probeNetwork } from "./queries";

export type NetworkState = "unknown" | "ok" | "off";

export interface NetworkReading {
  state: NetworkState;
  /** The status line's label. */
  label: string;
  /** One honest sentence about what is known and from where. */
  sentence: string;
}

const HOST_NAMES: Record<string, string> = {
  "www.brenda-enzymes.org": "BRENDA",
  "rest.uniprot.org": "UniProt",
  "search.rcsb.org": "the RCSB search",
  "files.rcsb.org": "the RCSB files",
  "data.rcsb.org": "the RCSB data",
  "eutils.ncbi.nlm.nih.gov": "NCBI",
};

export function hostName(host: string): string {
  return HOST_NAMES[host] ?? host;
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
      };
    }
    return {
      state: "off",
      label: "network unreachable",
      sentence: `${net.reason ?? "A database could not be reached."} (${when}). That was a lookup you ran; check to test every host again.`,
    };
  }
  if (net.reachable) {
    return { state: "ok", label: "network reachable", sentence: `Every database host answered a check (${when}).` };
  }
  const failing = named(net.hosts, false);
  return {
    state: "off",
    label: "network unreachable",
    sentence: `${failing.length ? `${failing.join(", ")} did not answer a check` : (net.reason ?? "A check failed")} (${when}).`,
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
