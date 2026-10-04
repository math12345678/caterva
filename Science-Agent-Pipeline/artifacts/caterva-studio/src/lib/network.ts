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
  "pubchem.ncbi.nlm.nih.gov": "PubChem",
  "rest.kegg.jp": "KEGG",
};

export function hostName(host: string): string {
  return HOST_NAMES[host] ?? host;
}

/** The hosts whose own latest outcome was `outcome` (true answered, false did not, null never checked), named. */
function named(hosts: Record<string, boolean | null>, outcome: boolean | null): string[] {
  return Object.entries(hosts)
    .filter(([, ok]) => ok === outcome)
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
  const answered = named(net.hosts, true);
  const failing = named(net.hosts, false);
  const unchecked = named(net.hosts, null);
  const allFromChecks = Object.values(net.host_status ?? {}).every((s) => s.source === "probe");
  // What each host's own latest outcome was, never more: one that failed does not make another unreachable.
  const parts: string[] = [];
  if (answered.length) parts.push(`${answered.join(", ")} answered`);
  if (failing.length) parts.push(`${failing.join(", ")} did not answer`);
  if (unchecked.length) parts.push(`${unchecked.join(", ")} not checked yet`);
  if (!failing.length && !unchecked.length && allFromChecks) {
    return { state: "ok", label: "network reachable", sentence: `Every database host answered a check (${when}).` };
  }
  const tail = unchecked.length || !allFromChecks ? " Some of this is from lookups you ran; check to test every host." : "";
  if (failing.length) {
    return {
      state: "off",
      label: answered.length ? "some hosts unreachable" : "network unreachable",
      sentence: `${parts.join("; ")} (${when}).${tail}`,
    };
  }
  return {
    state: "ok",
    label: unchecked.length ? "some hosts reachable" : "network reachable",
    sentence: `${parts.join("; ")} (${when}).${tail}`,
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
