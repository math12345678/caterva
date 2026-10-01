/**
 * /about: which Caterva this is, under which licences, and what this
 * installation can reach.
 *
 * The network is checked only when the reader asks: the probe contacts
 * five third-party hosts (BRENDA, UniProt, the RCSB's search and files,
 * NCBI), and a page that did that on every open would be reporting the
 * reader's activity to them. Each host's answer is shown separately, so
 * "PubMed is down" is distinguishable from "you are offline".
 */
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { Lockup } from "@/components/brand/Mark";
import { useCommand } from "@/components/palette/commands";
import { Screen, Section } from "@/components/screen/Screen";
import { Loading } from "@/components/states/Loading";
import { ErrorState } from "@/components/states/States";
import { formatDateTime } from "@/lib/format";
import { CAPABILITIES_KEY, probeNetwork, useCapabilities, useHealth } from "@/lib/queries";

const LICENCES = [
  { name: "Caterva", licence: "Apache License 2.0", href: "https://www.apache.org/licenses/LICENSE-2.0" },
  { name: "Spectral (display type)", licence: "SIL Open Font License 1.1", href: "/licenses/spectral-OFL-1.1.txt" },
  {
    name: "Atkinson Hyperlegible Next (text)",
    licence: "SIL Open Font License 1.1",
    href: "/licenses/atkinson-hyperlegible-next-OFL-1.1.txt",
  },
  { name: "DM Mono (numbers and code)", licence: "SIL Open Font License 1.1", href: "/licenses/dm-mono-OFL-1.1.txt" },
];

export default function AboutScreen() {
  const health = useHealth();
  const caps = useCapabilities();
  const client = useQueryClient();
  const probe = useMutation({
    mutationFn: probeNetwork,
    onSuccess: (fresh) => client.setQueryData(CAPABILITIES_KEY, fresh),
  });
  useCommand({
    id: "about.probe",
    title: "Check the network",
    hint: "Contacts BRENDA, UniProt, the RCSB and NCBI once",
    run: () => probe.mutate(),
    disabled: probe.isPending,
  });
  const net = caps.data?.network;

  return (
    <Screen
      title="About"
      purpose="Version, licences, and what this installation can and cannot reach."
      actions={
        <button type="button" className="btn btn-primary" onClick={() => probe.mutate()} disabled={probe.isPending}>
          {probe.isPending ? "Checking" : "Check the network"}
        </button>
      }
    >
      <div className="about-lockup">
        <Lockup size={34} />
      </div>
      <Section title="This installation">
        {health.data && caps.data ? (
          <dl className="dl">
            <dt>Caterva</dt>
            <dd className="font-mono">{health.data.version}</dd>
            <dt>Studio API</dt>
            <dd className="font-mono">{health.data.api_version}</dd>
            <dt>Python</dt>
            <dd className="font-mono">{caps.data.python}</dd>
            <dt>Platform</dt>
            <dd className="font-mono">{caps.data.platform}</dd>
            <dt>Packaged app</dt>
            <dd>{caps.data.frozen ? "yes (the frozen Caterva.app engine)" : "no (running from a Python installation)"}</dd>
            <dt>Server started</dt>
            <dd className="font-mono">{formatDateTime(health.data.started_at)}</dd>
          </dl>
        ) : caps.isError ? (
          <ErrorState error={caps.error} />
        ) : (
          <Loading label="Asking the server" />
        )}
      </Section>

      <Section
        title="Network"
        aside={net?.checked_at ? <span className="font-mono">checked {formatDateTime(net.checked_at)}</span> : undefined}
      >
        {probe.isPending ? (
          <Loading label="Contacting the five database hosts" />
        ) : probe.isError ? (
          <ErrorState error={probe.error} />
        ) : net ? (
          <>
            {!net.checked ? <p className="soft">{net.reason ?? "Not checked."}</p> : null}
            <ul className="host-list">
              {Object.entries(net.hosts).map(([host, ok]) => (
                <li key={host}>
                  <span className="status-dot" data-state={ok === null ? "unknown" : ok ? "ok" : "off"} aria-hidden="true" />
                  <span className="font-mono">{host}</span>
                  <span className="muted">{ok === null ? "not checked" : ok ? "answered" : "did not answer"}</span>
                </li>
              ))}
            </ul>
            {net.checked && !net.reachable && net.reason ? <p className="soft">{net.reason}</p> : null}
          </>
        ) : null}
      </Section>

      <Section title="Licences">
        <ul className="licence-list">
          {LICENCES.map((l) => (
            <li key={l.name}>
              <span>{l.name}</span>
              <a href={l.href} target="_blank" rel="noopener noreferrer">
                {l.licence}
              </a>
            </li>
          ))}
        </ul>
        <p className="soft prose-measure">
          Measured constants come from BRENDA, used under its own terms of use, and are cited on every number that
          carries one; structures come from the RCSB PDB. Each is linked from the value it supplied.
        </p>
      </Section>
    </Screen>
  );
}
