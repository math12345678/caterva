/**
 * /: one line to start from, the runs opened last, and what this machine
 * can do.
 *
 * The primary action is the one-line ask: a mechanism written as a person
 * would say it, sent as `caterva compose "<line>"`, which opens on Compose
 * as soon as the run exists (so its link is the run's link). The shapes the
 * grammar recognises are offered under it as suggestions, from the server
 * (`GET /api/compose/shapes`), never from a list kept here; choosing one
 * writes it into the line and runs nothing.
 *
 * What this machine can do is said in sentences, one per capability, each
 * with the server's own reason when something is off (no literature layer,
 * no gmx, offline mode). With no runs yet the screen is a first lesson for a
 * teaching lab: what the marks on every number mean, and three questions
 * that open their screens with the form filled in.
 */
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, CornerDownLeft } from "lucide-react";
import { type FormEvent, useRef, useState } from "react";
import { Link, useLocation } from "wouter";

import { ApiRequestError, apiJson } from "@/api/client";
import { createRun } from "@/api/runs";
import type { ApiError, Capabilities, KindCapability, RunKind, ShapesResponse } from "@/api/types";
import { MarkLoader } from "@/components/brand/MarkLoader";
import { fieldError } from "@/components/forms/Field";
import { useCommand } from "@/components/palette/commands";
import { ProvenanceLegend } from "@/components/provenance/ProvenanceLegend";
import { CommandSlab } from "@/components/report/Report";
import { RunRow } from "@/components/run/RunRow";
import { Screen, Section } from "@/components/screen/Screen";
import { SkeletonRows } from "@/components/states/Loading";
import { ErrorState } from "@/components/states/States";
import { plural } from "@/lib/copy";
import { describeError } from "@/lib/errors";
import { runHref, useJobActionsOptional } from "@/lib/jobs";
import { useCapabilities, useRunList } from "@/lib/queries";
import { useSettings } from "@/lib/settings";
import { routeForKind } from "@/routes";

import { parseShapes, phraseFor } from "./kinetics/ShapeCatalogue";
import "./workspace/workspace.css";

/** Three first questions: real commands, each opening its screen with the form filled in. */
export const FIRST_QUESTIONS: { title: string; why: string; argv: string[]; href: string }[] = [
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

/** How many suggestions show before the whole catalogue is asked for. */
const SUGGESTIONS = 6;

function Ask({ caps }: { caps: Capabilities | undefined }) {
  const [line, setLine] = useState("");
  const [error, setError] = useState<ApiError | null>(null);
  const [sending, setSending] = useState(false);
  const [all, setAll] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const [, navigate] = useLocation();
  const jobs = useJobActionsOptional();
  const shapes = useQuery({ queryKey: ["compose-shapes"], queryFn: () => apiJson<ShapesResponse>("/api/compose/shapes"), staleTime: Infinity });
  const compose = caps?.kinds.compose;
  const unavailable = compose && !compose.available ? (compose.reason ?? "this installation cannot run compose") : null;

  const send = async () => {
    const description = line.trim();
    if (!description || sending || unavailable) return;
    setSending(true);
    setError(null);
    try {
      const { run } = await createRun("compose", { description });
      jobs?.track(run, "here");
      navigate(runHref(run));
    } catch (e) {
      setError(e instanceof ApiRequestError ? e.error : { code: "crash", message: describeError(e).message });
      setSending(false);
    }
  };
  const submit = (e: FormEvent) => {
    e.preventDefault();
    void send();
  };
  useCommand(
    line.trim()
      ? { id: "home.ask", title: `Compose "${line.trim()}"`, hint: "the line on Home, as caterva compose", run: () => void send(), disabled: Boolean(unavailable) || sending }
      : null,
  );

  const parsed = shapes.data ? parseShapes(shapes.data.shapes) : [];
  const shown = all ? parsed : parsed.slice(0, SUGGESTIONS);
  const message = error ? (fieldError(error, "description") ?? error.message) : null;

  return (
    <section className="home-ask" aria-labelledby="home-ask-label">
      <form onSubmit={submit} className="home-ask-form" noValidate>
        <label htmlFor="home-ask-input" id="home-ask-label" className="home-ask-label">
          Write one line.
        </label>
        <p className="home-ask-hint" id="home-ask-hint">
          The shape of a mechanism, as you would say it. It runs as <span className="font-mono">caterva compose</span>{" "}
          and opens on Compose, where an enzyme, an organism and a substrate turn its placeholders into cited
          constants.
        </p>
        <div className="home-ask-row">
          <input
            ref={input}
            id="home-ask-input"
            className="input home-ask-input"
            value={line}
            onChange={(e) => {
              setLine(e.target.value);
              setError(null);
            }}
            aria-describedby={`home-ask-hint${message ? " home-ask-error" : ""}`}
            aria-invalid={message ? true : undefined}
            autoComplete="off"
            spellCheck={false}
            disabled={Boolean(unavailable)}
            autoFocus
          />
          <button type="submit" className="btn btn-primary home-ask-go" disabled={!line.trim() || sending || Boolean(unavailable)}>
            {sending ? <MarkLoader size={14} /> : <CornerDownLeft size={14} aria-hidden="true" />}
            {sending ? "Starting" : "Compose"}
          </button>
        </div>
        {message ? (
          <p className="field-error" id="home-ask-error" role="alert">
            {message}
          </p>
        ) : null}
        {unavailable ? <p className="field-hint">Compose is not available here: {unavailable}</p> : null}
      </form>
      {shapes.isError ? null : (
        <div className="home-shapes">
          <p className="home-shapes-title">
            {shapes.data ? `Shapes it recognises (${parsed.length})` : "Reading the shapes it recognises"}
          </p>
          <ul className="home-shape-list" aria-label="Suggestions: shapes the grammar recognises">
            {shown.map((s) => (
              <li key={s.name}>
                <button
                  type="button"
                  className="home-shape"
                  onClick={() => {
                    setLine(phraseFor(s));
                    setError(null);
                    input.current?.focus();
                  }}
                >
                  {s.description}
                </button>
              </li>
            ))}
            {parsed.length > SUGGESTIONS ? (
              <li>
                <button type="button" className="home-shape home-shape-more" aria-expanded={all} onClick={() => setAll((a) => !a)}>
                  {all ? "Fewer" : `${parsed.length - SUGGESTIONS} more`}
                </button>
              </li>
            ) : null}
          </ul>
        </div>
      )}
    </section>
  );
}

function KindRow({ kind, cap }: { kind: RunKind; cap: KindCapability }) {
  const route = routeForKind(kind);
  return (
    <li className="kind-row" data-available={cap.available ? "true" : "false"}>
      <span className="status-dot" data-state={cap.available ? "ok" : "off"} aria-hidden="true" />
      <span className="kind-row-main">
        <span className="kind-row-command">
          {cap.title} <span className="font-mono muted">caterva {cap.command}</span>
        </span>
        <span className="kind-row-reason">
          {cap.available ? (cap.needs.length ? `needs ${cap.needs.join(" and ")}` : "runs offline") : (cap.reason ?? "not available")}
        </span>
      </span>
      {route && cap.available ? (
        <Link href={route.path} className="kind-row-link" aria-label={`Open ${route.title} for ${cap.title}`}>
          {route.title}
          <ArrowRight size={13} aria-hidden="true" />
        </Link>
      ) : null}
    </li>
  );
}

/** One plain sentence per capability, with the server's reason when it is off. */
export function machineSentences(caps: Capabilities, offline: boolean): { key: string; on: boolean | null; text: string }[] {
  const out: { key: string; on: boolean | null; text: string }[] = [];
  out.push({
    key: "literature",
    on: caps.literature.available,
    text: caps.literature.available
      ? "Looks constants up in the literature: the literature layer is installed."
      : `Cannot look constants up: ${caps.literature.reason ?? "the literature layer is not installed"}.`,
  });
  out.push({
    key: "network",
    on: offline ? false : caps.network.checked ? caps.network.reachable : null,
    text: offline
      ? "Offline mode is on: nothing contacts BRENDA, UniProt, the RCSB or NCBI, and runs that need them are refused."
      : caps.network.checked
        ? caps.network.reachable
          ? "Every database host answered when the network was last checked."
          : `Some database hosts did not answer: ${caps.network.reason ?? "see About for which"}.`
        : "The network has not been checked; About checks it when you ask.",
  });
  out.push({
    key: "gromacs",
    on: caps.gromacs.found,
    text: caps.gromacs.found
      ? `Finds GROMACS ${caps.gromacs.version ?? ""} at ${caps.gromacs.path ?? "gmx"}, for analysing trajectories.`.replace("  ", " ")
      : `No GROMACS: ${caps.gromacs.reason ?? "gmx was not found"}. Setups are still written; running them needs it.`,
  });
  out.push({
    key: "data",
    on: caps.data_dir.writable,
    text: caps.data_dir.writable
      ? `Keeps ${plural(caps.data_dir.runs, "run")} in ${caps.data_dir.path}.`
      : `Cannot write its workspace: ${caps.data_dir.reason ?? caps.data_dir.path}.`,
  });
  return out;
}

function Machine({ caps }: { caps: Capabilities }) {
  const settings = useSettings();
  const offline = Boolean(settings.data?.offline);
  const kinds = KIND_ORDER.filter((k) => caps.kinds[k] && (k !== "rates" || caps.rates.available));
  const available = kinds.filter((k) => caps.kinds[k].available);
  const off = kinds.filter((k) => !caps.kinds[k].available);
  return (
    <Section
      title="What this machine can do"
      aside={
        <span className="font-mono">
          {available.length} of {kinds.length} kinds
        </span>
      }
    >
      <ul className="home-capabilities">
        {machineSentences(caps, offline).map((s) => (
          <li key={s.key}>
            <span className="status-dot" data-state={s.on === null ? "unknown" : s.on ? "ok" : "off"} aria-hidden="true" />
            <span>{s.text}</span>
          </li>
        ))}
      </ul>
      <ul className="kind-list home-kinds" aria-label="Kinds of run">
        {[...available, ...off].map((k) => (
          <KindRow key={k} kind={k} cap={caps.kinds[k]} />
        ))}
      </ul>
      <p className="home-more">
        <Link href="/settings">Settings</Link> for offline mode and GROMACS; <Link href="/about">About</Link> to check the
        network and for the licences.
      </p>
    </Section>
  );
}

function FirstRun() {
  return (
    <div className="home-first">
      <Section title="Nothing has run here yet">
        <p className="home-lede">
          Every number on these screens wears a mark that says what kind of number it is. Activate a measured number
          for the paper it came from, its assay conditions and the source row&apos;s own words; activate a placeholder
          for the reason nobody has measured it here. Nothing is filled in for you.
        </p>
        <ProvenanceLegend layout="stack" />
        <p className="home-lede">
          Every run is saved, with the command that reproduces it in a terminal, so a result on a student&apos;s laptop
          can be checked at the bench.
        </p>
      </Section>
      <Section title="Three questions to start with">
        <ol className="question-list">
          {FIRST_QUESTIONS.map((q) => (
            <li key={q.href} className="question">
              <Link href={q.href} className="question-title">
                {q.title}
                <ArrowRight size={14} aria-hidden="true" />
              </Link>
              <p className="question-why">{q.why} The form opens filled in; nothing runs until you ask.</p>
              <CommandSlab argv={q.argv} title="The same question in a terminal" />
            </li>
          ))}
        </ol>
      </Section>
    </div>
  );
}

export default function HomeScreen() {
  const runs = useRunList({ limit: 8 });
  const caps = useCapabilities();
  const list = runs.data?.runs ?? [];
  const empty = runs.isSuccess && list.length === 0;
  return (
    <Screen
      title="Caterva Studio"
      purpose="Enzyme kinetics and molecular dynamics where every number says whether it was measured, fitted, computed or chosen, and where it came from."
      className="home"
    >
      <div className="home-grid">
        <div className="home-main">
          <Ask caps={caps.data} />
          {empty ? (
            <FirstRun />
          ) : (
            <Section title="Recent runs" aside={list.length ? <Link href="/history">All runs in History</Link> : undefined}>
              {runs.isPending ? (
                <SkeletonRows rows={4} label="Reading the workspace" />
              ) : runs.isError ? (
                <ErrorState error={runs.error} />
              ) : (
                <div className="run-list">
                  {list.map((r) => (
                    <RunRow key={r.id} run={r} />
                  ))}
                </div>
              )}
            </Section>
          )}
        </div>
        <div className="home-side">
          {caps.isPending ? (
            <div className="state" role="status" aria-label="Asking the server what it can do">
              <MarkLoader size={22} />
            </div>
          ) : caps.isError ? (
            <ErrorState error={caps.error} />
          ) : (
            <Machine caps={caps.data} />
          )}
        </div>
      </div>
    </Screen>
  );
}
