/**
 * /: what this installation can do, and the runs opened last.
 *
 * The first screen answers the two questions a reader arrives with: "what
 * was I doing" (the last runs, each one click from where it is shown) and
 * "what can this copy of Caterva do here" (every kind of run, from the
 * server's capabilities, with the reason in its own words when one cannot
 * run: no literature layer, no gmx, not built yet). With no runs yet it
 * offers three first questions as the commands they are; each opens its
 * screen with the form filled in, and nothing runs until the reader asks.
 */
import { ArrowRight } from "lucide-react";
import { Link } from "wouter";

import type { Capabilities, KindCapability, RunKind } from "@/api/types";
import { MarkLoader } from "@/components/brand/MarkLoader";
import { CommandSlab } from "@/components/report/Report";
import { RunRow } from "@/components/run/RunRow";
import { Screen, Section } from "@/components/screen/Screen";
import { SkeletonRows } from "@/components/states/Loading";
import { EmptyState, ErrorState } from "@/components/states/States";
import { useCapabilities, useRunList } from "@/lib/queries";
import { modKey } from "@/lib/keyboard";
import { routeForKind } from "@/routes";

/** Three first questions: real commands, each opening its screen with the form filled in. */
const FIRST_QUESTIONS: { title: string; why: string; argv: string[]; href: string }[] = [
  {
    title: "A model of hexokinase, every constant cited",
    why: "Compose builds the model from the shape of the mechanism and looks up each constant in BRENDA.",
    argv: ["caterva", "compose", "Michaelis Menten", "--subject", "2.7.1.1", "--organism", "human", "--substrate", "glucose"],
    href: "/compose?description=Michaelis%20Menten&subject=2.7.1.1&organism=human&substrate=glucose",
  },
  {
    title: "Which structures of human LDH-A to simulate",
    why: "Structures lists the PDB entries for the enzyme, each with its method, resolution and paper.",
    argv: ["caterva", "structure", "--subject", "1.1.1.27", "--organism", "human"],
    href: "/structure?subject=1.1.1.27&organism=human",
  },
  {
    title: "What a setup would get wrong in 1I10",
    why: "Prepare audits the entry: missing atoms, mutations, alternate locations, ranked by distance to the active site.",
    argv: ["caterva", "prepare", "1I10"],
    href: "/prepare?entry=1I10",
  },
];

const KIND_ORDER: RunKind[] = [
  "compose",
  "constants",
  "sim",
  "bind",
  "rates",
  "structure",
  "prepare",
  "md.setup",
  "md.summarise",
  "analyze",
  "fep.status",
  "complex.check",
];

function KindRow({ kind, cap }: { kind: RunKind; cap: KindCapability }) {
  const route = routeForKind(kind);
  return (
    <li className="kind-row" data-available={cap.available ? "true" : "false"}>
      <span className="status-dot" data-state={cap.available ? "ok" : "off"} aria-hidden="true" />
      <span className="kind-row-main">
        <span className="kind-row-command font-mono">{cap.command}</span>
        <span className="kind-row-reason">
          {cap.available ? (cap.needs.length ? `needs ${cap.needs.join(", ")}` : "runs offline") : (cap.reason ?? "not available")}
        </span>
      </span>
      {route && cap.available ? (
        <Link href={route.path} className="kind-row-link" aria-label={`Open ${route.title} for ${cap.command}`}>
          {route.title}
          <ArrowRight size={13} aria-hidden="true" />
        </Link>
      ) : null}
    </li>
  );
}

function Installation({ caps }: { caps: Capabilities }) {
  const kinds = KIND_ORDER.filter((k) => caps.kinds[k] && (k !== "rates" || caps.rates.available));
  const available = kinds.filter((k) => caps.kinds[k].available).length;
  return (
    <Section
      title="What this installation can run"
      aside={
        <span className="font-mono">
          {available} of {kinds.length}
        </span>
      }
    >
      <ul className="kind-list">
        {kinds.map((k) => (
          <KindRow key={k} kind={k} cap={caps.kinds[k]} />
        ))}
      </ul>
      <ul className="home-capabilities">
        <li>
          <span className="status-dot" data-state={caps.literature.available ? "ok" : "off"} aria-hidden="true" />
          <span>
            <strong>Literature layer</strong>{" "}
            {caps.literature.available ? "installed" : (caps.literature.reason ?? "not installed")}
          </span>
        </li>
        <li>
          <span className="status-dot" data-state={caps.gromacs.found ? "ok" : "off"} aria-hidden="true" />
          <span>
            <strong>GROMACS</strong>{" "}
            {caps.gromacs.found ? (
              <span className="font-mono">
                {caps.gromacs.version} at {caps.gromacs.path}
              </span>
            ) : (
              (caps.gromacs.reason ?? "not found")
            )}
          </span>
        </li>
        <li>
          <span
            className="status-dot"
            data-state={!caps.network.checked ? "unknown" : caps.network.reachable ? "ok" : "off"}
            aria-hidden="true"
          />
          <span>
            <strong>Network</strong>{" "}
            {caps.network.checked ? (caps.network.reachable ? "every database answered" : "some databases did not answer") : "not checked"}
            {" · "}
            <Link href="/about">check from About</Link>
          </span>
        </li>
      </ul>
    </Section>
  );
}

export default function HomeScreen() {
  const runs = useRunList({ limit: 8 });
  const caps = useCapabilities();
  const list = runs.data?.runs ?? [];
  return (
    <Screen
      title="Caterva Studio"
      purpose="Enzyme kinetics and molecular dynamics where every number says whether it was measured, fitted, computed or chosen, and where it came from."
      actions={
        <span className="home-hint">
          <kbd>{modKey()}</kbd>
          <kbd>K</kbd> to go anywhere or compose from a sentence
        </span>
      }
      className="home"
    >
      <div className="home-grid">
        <Section title="Recent runs" aside={list.length ? <Link href="/history">All runs</Link> : undefined}>
          {runs.isPending ? (
            <SkeletonRows rows={4} label="Reading the workspace" />
          ) : runs.isError ? (
            <ErrorState error={runs.error} />
          ) : list.length ? (
            <div className="run-list">
              {list.map((r) => (
                <RunRow key={r.id} run={r} />
              ))}
            </div>
          ) : (
            <div className="first-questions">
              <EmptyState title="Nothing has run here yet">
                <p>Three questions to start with. Each opens its screen with the form filled in; nothing runs until you ask.</p>
              </EmptyState>
              <ol className="question-list">
                {FIRST_QUESTIONS.map((q) => (
                  <li key={q.href} className="question">
                    <Link href={q.href} className="question-title">
                      {q.title}
                      <ArrowRight size={14} aria-hidden="true" />
                    </Link>
                    <p className="question-why">{q.why}</p>
                    <CommandSlab argv={q.argv} title="The same question in a terminal" />
                  </li>
                ))}
              </ol>
            </div>
          )}
        </Section>
        <div className="home-side">
          {caps.isPending ? (
            <div className="state">
              <MarkLoader size={22} />
            </div>
          ) : caps.isError ? (
            <ErrorState error={caps.error} />
          ) : (
            <Installation caps={caps.data} />
          )}
        </div>
      </div>
    </Screen>
  );
}
