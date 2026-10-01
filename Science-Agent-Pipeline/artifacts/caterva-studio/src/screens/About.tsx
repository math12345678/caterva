/**
 * /about: which Caterva this is, how it decides what kind of number a
 * number is, where its measurements come from and how to cite them, under
 * which licences, and what this installation can reach.
 *
 * The data sources are read from docs/data-sources.json, the one table the
 * SBML, Antimony and CSV exports already take their attribution from
 * (caterva/core/data_sources.py says why there is one table): this page
 * imports it at build time rather than restating a licence, so the page and
 * the exports cannot come to disagree about one.
 *
 * The network is checked only when the reader asks: the probe contacts
 * five third-party hosts (BRENDA, UniProt, the RCSB's search and files,
 * NCBI), and a page that did that on every open would be reporting the
 * reader's activity to them. Each host's answer is shown separately, so
 * "PubMed is down" is distinguishable from "you are offline".
 */
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ExternalLink } from "lucide-react";
import type { ReactNode } from "react";

import dataSources from "../../../../../docs/data-sources.json";
import { Lockup } from "@/components/brand/Mark";
import { useCommand } from "@/components/palette/commands";
import { PROVENANCE_MEANING, PROVENANCE_ORDER, ProvenanceMark, provenanceLabel } from "@/components/provenance/ProvenanceMark";
import { Screen, Section } from "@/components/screen/Screen";
import { Loading } from "@/components/states/Loading";
import { ErrorState } from "@/components/states/States";
import { formatDateTime } from "@/lib/format";
import { CAPABILITIES_KEY, probeNetwork, useCapabilities, useHealth } from "@/lib/queries";

import "./workspace/workspace.css";

/** The public repository (CITATION.cff's repository-code). */
export const REPOSITORY = "https://github.com/math12345678/caterva";

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

/** Where the rules this page states in a line are written out in full. */
const DOCS = [
  {
    title: "How every parameter gets its origin",
    note: "ADR 0008: measured, fitted, computed, placeholder, chosen, and who decides",
    path: "docs/adr/0008-parameter-provenance.md",
  },
  {
    title: "Why an unsourced number is refused, not defaulted",
    note: "ADR 0024",
    path: "docs/adr/0024-refusing-versus-defaulting-an-unsourced-parameter.md",
  },
  {
    title: "Why kcat is cited but does not drive the simulation alone",
    note: "ADR 0012 and 0013",
    path: "docs/adr/0012-kcat-resolved-but-not-simulated.md",
  },
  { title: "The user's guide to the commands", note: "every screen here runs one of them", path: "docs/USING_CATERVA.md" },
  { title: "Using the studio", note: "this app, its runs and its workspace", path: "docs/studio/USING_STUDIO.md" },
];

interface DataSource {
  tokens: string[];
  creator: string;
  source_uri: string;
  licence: string;
  licence_uri: string | null;
  modifications: string;
  notice_uri: string;
  citation_request: string | null;
}

const SOURCES = (dataSources as { sources: DataSource[] }).sources;

function External({ href, children }: { href: string; children: ReactNode }) {
  return (
    <a href={href} target="_blank" rel="noopener noreferrer">
      {children}
      <ExternalLink size={11} aria-hidden="true" />
    </a>
  );
}

/** "how to cite Caterva": the version this server runs and the repository, as CITATION.cff asks. */
export function citeCaterva(version: string): string {
  return `Caterva, version ${version}. Apache-2.0. ${REPOSITORY} (see CITATION.cff in the repository).`;
}

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
      purpose="Version, how a number is decided, where measurements come from and how to cite them, licences, and what this installation can reach."
      actions={
        <button type="button" className="btn btn-primary" onClick={() => probe.mutate()} disabled={probe.isPending}>
          {probe.isPending ? "Checking" : "Check the network"}
        </button>
      }
    >
      <div className="about-lockup">
        <Lockup size={34} />
      </div>
      <div className="about-grid">
        <div>
          <Section title="How Caterva decides a number">
            <ul className="about-kinds">
              {PROVENANCE_ORDER.map((kind) => (
                <li key={kind}>
                  <ProvenanceMark provenance={{ kind, by: kind === "chosen" ? "user" : undefined }} decorative />
                  <span>
                    <strong>{kind === "chosen" ? "chosen" : provenanceLabel({ kind })}</strong>: {PROVENANCE_MEANING[kind]}.
                  </span>
                </li>
              ))}
            </ul>
            <p className="soft prose-measure">
              The kind is decided where the number is made, by the code that made it, and travels with it to this page.
              A constant nobody measured for your organism stays a placeholder that says why; a measurement from
              another organism is never substituted for yours.
            </p>
            <ul className="about-docs">
              {DOCS.map((d) => (
                <li key={d.path}>
                  <External href={`${REPOSITORY}/blob/main/${d.path}`}>{d.title}</External>
                  <span>
                    {d.note} · <span className="font-mono">{d.path}</span>
                  </span>
                </li>
              ))}
            </ul>
          </Section>

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
        </div>

        <div>
          <Section title="Where the measurements come from">
            <ul className="about-sources">
              {SOURCES.map((s) => (
                <li key={s.tokens.join("-")} className="about-source">
                  <span className="about-source-name">{s.creator}</span>
                  <p>
                    {s.licence_uri ? <External href={s.licence_uri}>{s.licence}</External> : s.licence}
                    {s.source_uri ? (
                      <>
                        {" · "}
                        <External href={s.source_uri}>{s.source_uri.replace(/^https?:\/\//, "").replace(/\/$/, "")}</External>
                      </>
                    ) : null}
                  </p>
                  <p>What Caterva does to the rows: {s.modifications}</p>
                  {s.citation_request ? <p>How to cite it: {s.citation_request}</p> : null}
                </li>
              ))}
            </ul>
            <p className="soft prose-measure">
              Every value that came from one of them carries its own reference on the number itself, and the exported
              SBML and Antimony models carry this attribution. Structures come from the RCSB PDB, cited on each entry;
              UniProt and PubMed resolve enzyme names and papers.
            </p>
          </Section>

          <Section title="How to cite Caterva">
            {health.data ? <p className="about-cite">{citeCaterva(health.data.version)}</p> : <Loading label="Asking the server" />}
            <p className="soft prose-measure">
              Cite the version you ran, and the papers behind the numbers you used: a compose run&apos;s methods export
              and every run&apos;s bundle carry them.
            </p>
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
          </Section>
        </div>
      </div>
    </Screen>
  );
}
