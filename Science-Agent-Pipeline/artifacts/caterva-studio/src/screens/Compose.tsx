/**
 * /compose: build a model from the shape of a mechanism, and see where every
 * number in it came from (owner: sci-kinetics).
 *
 * The form is `caterva compose`'s flags; the request goes to the server,
 * whose adapter runs the command's own parser over it, so a question the
 * terminal would refuse is refused here in the same words, under the field
 * it names. Nothing numeric is pre-filled: an empty field is a flag not
 * given, and the result marks every default the command applied.
 */
import { useQuery } from "@tanstack/react-query";
import { useId, useState } from "react";

import { apiJson, apiPost } from "@/api/client";
import type { ComposeAnalyses, ComposeRequest, NormaliseOrganismResponse, ShapesResponse } from "@/api/types";
import { useRun } from "@/api/useRun";
import { Screen } from "@/components/screen/Screen";
import { EmptyState } from "@/components/states/States";

import { ComposeResultView } from "./kinetics/ComposeResult";
import { Check, fieldError, NumberField, readNumber, RunForm, TextField } from "./kinetics/form";
import "./kinetics/kinetics.css";
import { names, useReopenedRun } from "./kinetics/reopen";
import { cancelling, RunView } from "./kinetics/RunView";

const ANALYSES: { key: keyof ComposeAnalyses; label: string; hint: string }[] = [
  { key: "crnt", label: "Network structure", hint: "deficiency theorems; reads no parameter value" },
  { key: "scale", label: "Physical scale", hint: "units and magnitudes of every number" },
  { key: "predictions", label: "Predicted amounts", hint: "steady states and the transient, checked against physics" },
  { key: "reduction", label: "Timescale separation", hint: "which species could be eliminated" },
  { key: "identifiability", label: "Identifiability", hint: "which constants a measurement could pin down" },
  { key: "design", label: "What to measure next", hint: "observations ranked by what they would resolve" },
  { key: "validate", label: "Cross-checks", hint: "the modules checked against each other" },
  { key: "screen", label: "Knockout screen", hint: "every single knockout, compared" },
];

interface Form {
  description: string;
  subject: string;
  organism: string;
  substrate: string;
  inhibitor: string;
  isoform: string;
  any_mode: boolean;
  analyses: Partial<Record<keyof ComposeAnalyses, boolean>>;
  robustness: boolean;
  samples: string;
  stochastic: boolean;
  volume: string;
  stochasticEnd: string;
  stochasticSeed: string;
  knockout: string;
  overexpress: string;
  sweep: string;
  sweepLow: string;
  sweepHigh: string;
  sweepSteps: string;
  no_simulate: boolean;
  no_analysis: boolean;
  no_ranking: boolean;
}

const EMPTY: Form = {
  description: "",
  subject: "",
  organism: "",
  substrate: "",
  inhibitor: "",
  isoform: "",
  any_mode: false,
  analyses: {},
  robustness: false,
  samples: "",
  stochastic: false,
  volume: "",
  stochasticEnd: "",
  stochasticSeed: "",
  knockout: "",
  overexpress: "",
  sweep: "",
  sweepLow: "",
  sweepHigh: "",
  sweepSteps: "",
  no_simulate: false,
  no_analysis: false,
  no_ranking: false,
};

/** The request for a form; numbers the page could not read are sent as typed so the server names them. */
export function composeRequest(f: Form): ComposeRequest {
  const request: ComposeRequest = { description: f.description.trim() };
  for (const key of ["subject", "organism", "substrate", "inhibitor", "isoform"] as const) {
    if (f[key].trim()) request[key] = f[key].trim();
  }
  if (f.any_mode) request.any_mode = true;
  if (f.no_simulate) request.no_simulate = true;
  if (f.no_analysis) request.no_analysis = true;
  if (f.no_ranking) request.no_ranking = true;
  const analyses: ComposeAnalyses = {};
  for (const { key } of ANALYSES) if (f.analyses[key]) (analyses as Record<string, boolean>)[key] = true;
  if (f.robustness) analyses.robustness = { samples: readNumber(f.samples) ?? null };
  if (f.stochastic) {
    analyses.stochastic = { volume_l: readNumber(f.volume) as number };
    const end = readNumber(f.stochasticEnd);
    const seed = readNumber(f.stochasticSeed);
    if (end !== undefined) analyses.stochastic.end_s = end;
    if (seed !== undefined) analyses.stochastic.seed = seed;
  }
  if (names(f.knockout).length) analyses.knockout = names(f.knockout);
  if (names(f.overexpress).length) analyses.overexpress = names(f.overexpress);
  if (Object.keys(analyses).length) request.analyses = analyses;
  if (names(f.sweep).length) {
    request.sweep = { parameters: names(f.sweep) };
    const low = readNumber(f.sweepLow);
    const high = readNumber(f.sweepHigh);
    const steps = readNumber(f.sweepSteps);
    if (low !== undefined) request.sweep.low = low;
    if (high !== undefined) request.sweep.high = high;
    if (steps !== undefined) request.sweep.steps = steps;
  }
  return request;
}

export default function ComposeScreen() {
  const [form, setForm] = useState<Form>(EMPTY);
  const [organismNote, setOrganismNote] = useState<string | null>(null);
  const run = useRun("compose", useReopenedRun());
  const shapes = useQuery({ queryKey: ["compose-shapes"], queryFn: () => apiJson<ShapesResponse>("/api/compose/shapes") });
  const listId = useId();
  const set = <K extends keyof Form>(key: K, value: Form[K]) => setForm((f) => ({ ...f, [key]: value }));
  const err = (field: string) => fieldError(run.requestError, field);
  const running = run.status === "queued" || run.status === "running";

  const readOrganism = () => {
    const name = form.organism.trim();
    if (!name) return setOrganismNote(null);
    apiPost<NormaliseOrganismResponse>("/api/organisms/normalise", { name }).then(
      (r) => setOrganismNote(r.note),
      () => setOrganismNote(null),
    );
  };

  return (
    <Screen
      title="Compose"
      purpose="Build a model from the shape of a mechanism, and see where every number in it came from."
    >
      <div className="k-split">
        <RunForm label="Compose" onSubmit={() => void run.submit(composeRequest(form))} running={running} onCancel={cancelling(run)}>
          <TextField
            label="Mechanism"
            value={form.description}
            onChange={(v) => set("description", v)}
            list={listId}
            required
            error={err("description")}
            hint={`A shape, not a subject: ${shapes.data ? `${shapes.data.shapes.length} shapes are recognised` : "the recognised shapes are offered as you type"}.`}
          />
          <datalist id={listId}>{shapes.data?.shapes.map((s) => <option key={s} value={s} />)}</datalist>

          <fieldset className="k-fieldset">
            <legend className="k-legend">Constants from the literature</legend>
            <TextField
              label="Enzyme (EC number or name)"
              value={form.subject}
              onChange={(v) => set("subject", v)}
              mono
              error={err("subject")}
              hint="With an enzyme, Km, kcat and Ki are searched in BRENDA; without one the model keeps labelled placeholders."
            />
            <TextField
              label="Organism"
              value={form.organism}
              onChange={(v) => {
                set("organism", v);
                setOrganismNote(null);
              }}
              onBlur={readOrganism}
              error={err("organism")}
              hint={organismNote ?? undefined}
            />
            <div className="k-row2">
              <TextField label="Substrate" value={form.substrate} onChange={(v) => set("substrate", v)} error={err("substrate")} />
              <TextField label="Isoform" value={form.isoform} onChange={(v) => set("isoform", v)} error={err("isoform")} />
            </div>
            <TextField label="Inhibitor" value={form.inhibitor} onChange={(v) => set("inhibitor", v)} error={err("inhibitor")} />
            <Check
              label="Any inhibition mode"
              checked={form.any_mode}
              onChange={(v) => set("any_mode", v)}
              hint="Keep the resolver's Ki even when its row states another mode than the model's."
            />
          </fieldset>

          <fieldset className="k-fieldset">
            <legend className="k-legend">Analyses</legend>
            {ANALYSES.map((a) => (
              <Check
                key={a.key}
                label={a.label}
                hint={a.hint}
                checked={Boolean(form.analyses[a.key])}
                onChange={(v) => set("analyses", { ...form.analyses, [a.key]: v })}
              />
            ))}
            <Check
              label="Robustness to the placeholders"
              hint="Resample every unmeasured constant; empty samples uses the command's default count."
              checked={form.robustness}
              onChange={(v) => set("robustness", v)}
            />
            {form.robustness ? (
              <NumberField label="Samples" value={form.samples} onChange={(v) => set("samples", v)} integer error={err("analyses.robustness")} />
            ) : null}
            <Check label="Stochastic simulation" checked={form.stochastic} onChange={(v) => set("stochastic", v)} hint="Exact SSA in a stated volume." />
            {form.stochastic ? (
              <>
                <NumberField label="Volume (litres)" value={form.volume} onChange={(v) => set("volume", v)} error={err("analyses.stochastic")} />
                <div className="k-row2">
                  <NumberField label="Horizon (s)" value={form.stochasticEnd} onChange={(v) => set("stochasticEnd", v)} />
                  <NumberField label="Seed" value={form.stochasticSeed} onChange={(v) => set("stochasticSeed", v)} integer />
                </div>
              </>
            ) : null}
          </fieldset>

          <details className="k-details">
            <summary>Perturbations, sweeps and switches</summary>
            <div className="k-fieldset" style={{ marginTop: "0.75rem" }}>
              <TextField label="Knock out (species, comma separated)" value={form.knockout} onChange={(v) => set("knockout", v)} mono error={err("analyses.knockout")} />
              <TextField label="Overexpress (species)" value={form.overexpress} onChange={(v) => set("overexpress", v)} mono error={err("analyses.overexpress")} />
              <TextField label="Sweep (parameters)" value={form.sweep} onChange={(v) => set("sweep", v)} mono error={err("sweep")} />
              {names(form.sweep).length ? (
                <div className="k-row2">
                  <NumberField label="From (fold)" value={form.sweepLow} onChange={(v) => set("sweepLow", v)} />
                  <NumberField label="To (fold)" value={form.sweepHigh} onChange={(v) => set("sweepHigh", v)} />
                  <NumberField label="Steps" value={form.sweepSteps} onChange={(v) => set("sweepSteps", v)} integer />
                </div>
              ) : null}
              <Check label="No simulation" checked={form.no_simulate} onChange={(v) => set("no_simulate", v)} />
              <Check label="No stability analysis" checked={form.no_analysis} onChange={(v) => set("no_analysis", v)} />
              <Check label="No influence ranking" checked={form.no_ranking} onChange={(v) => set("no_ranking", v)} />
            </div>
          </details>
        </RunForm>

        <RunView<"compose">
          state={run}
          empty={
            <EmptyState title="Describe a mechanism">
              <p className="k-prose">
                Type a shape such as a cascade, a toggle switch or competitive inhibition. Name an enzyme, an
                organism and a substrate to have its constants looked up; each one then carries its BRENDA
                reference, and anything not found stays a placeholder that says so.
              </p>
            </EmptyState>
          }
        >
          {(result) => <ComposeResultView result={result} />}
        </RunView>
      </div>
    </Screen>
  );
}
