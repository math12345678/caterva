/**
 * /compose: build a model from the shape of a mechanism, and see where every
 * number in it came from (owner: sci-kinetics).
 *
 * The form is `caterva compose`'s flags; the request goes to the server,
 * whose adapter runs the command's own parser over it, so a question the
 * terminal would refuse is refused here in the same words, under the field
 * it names. Nothing numeric is pre-filled: an empty field is a flag not
 * given, and the result marks every default the command applied.
 *
 * The form is filled, never run, from the address: `?run=<id>` reopens a
 * saved run with its question beside its answer, and a link that carries a
 * question (Home's first questions, Constants' "Use in Compose") fills the
 * fields and waits for the button.
 */
import { useQuery } from "@tanstack/react-query";
import { useRef, useState } from "react";

import { apiJson, apiPost } from "@/api/client";
import type { ComposeAnalyses, ComposeRequest, NormaliseOrganismResponse, ShapesResponse } from "@/api/types";
import { useRun } from "@/api/useRun";
import { Disclosure } from "@/components/forms/Disclosure";
import { Checkbox, Field, fieldError, NumberInput, parseNumber, TextInput } from "@/components/forms/Field";
import { Screen } from "@/components/screen/Screen";
import { EmptyState } from "@/components/states/States";

import { ComposeProgress } from "./kinetics/ComposeProgress";
import { composeExports, ComposeResultView } from "./kinetics/ComposeResult";
import { FieldGroup, KineticsLayout, KineticsRun, names, RunForm, text, useLinkedQuestion, usePrefill, useReopenedRun } from "./kinetics/kit";
import { ShapeCatalogue } from "./kinetics/ShapeCatalogue";
import "./kinetics/kinetics.css";

export const ANALYSES: { key: keyof ComposeAnalyses & string; label: string; hint: string }[] = [
  { key: "crnt", label: "Network structure", hint: "deficiency theorems; reads no parameter value" },
  { key: "scale", label: "Physical scale", hint: "units and magnitudes of every number" },
  { key: "predictions", label: "Predicted amounts", hint: "steady states and the transient, checked against physics" },
  { key: "reduction", label: "Timescale separation", hint: "which species could be eliminated" },
  { key: "identifiability", label: "Identifiability", hint: "which constants a measurement could pin down" },
  { key: "design", label: "What to measure next", hint: "observations ranked by what they would resolve" },
  { key: "validate", label: "Cross-checks", hint: "the modules checked against each other" },
  { key: "screen", label: "Knockout screen", hint: "every single knockout, compared" },
];

export interface ComposeForm {
  description: string;
  subject: string;
  organism: string;
  substrate: string;
  inhibitor: string;
  isoform: string;
  any_mode: boolean;
  analyses: Partial<Record<string, boolean>>;
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

export const EMPTY_COMPOSE: ComposeForm = {
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

const LINK_KEYS = ["description", "subject", "organism", "substrate", "inhibitor", "isoform"] as const;

/** A number field's text as the request's number; unreadable text is sent as typed so the server names it. */
function num(textValue: string): number | undefined {
  const t = textValue.trim();
  if (t === "") return undefined;
  const n = parseNumber(t);
  return n === null ? (t as unknown as number) : n;
}

/** The request for a form. */
export function composeRequest(f: ComposeForm): ComposeRequest {
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
  if (f.robustness) analyses.robustness = { samples: num(f.samples) ?? null };
  if (f.stochastic) {
    analyses.stochastic = { volume_l: num(f.volume) as number };
    const end = num(f.stochasticEnd);
    const seed = num(f.stochasticSeed);
    if (end !== undefined) analyses.stochastic.end_s = end;
    if (seed !== undefined) analyses.stochastic.seed = seed;
  }
  if (names(f.knockout).length) analyses.knockout = names(f.knockout);
  if (names(f.overexpress).length) analyses.overexpress = names(f.overexpress);
  if (Object.keys(analyses).length) request.analyses = analyses;
  if (names(f.sweep).length) {
    request.sweep = { parameters: names(f.sweep) };
    const low = num(f.sweepLow);
    const high = num(f.sweepHigh);
    const steps = num(f.sweepSteps);
    if (low !== undefined) request.sweep.low = low;
    if (high !== undefined) request.sweep.high = high;
    if (steps !== undefined) request.sweep.steps = steps;
  }
  return request;
}

/** The form a stored request was made from: the inverse of composeRequest. */
export function composeForm(request: Record<string, unknown>): ComposeForm {
  const r = request as Partial<ComposeRequest>;
  const a = (r.analyses ?? {}) as ComposeAnalyses;
  const flags: Record<string, boolean> = {};
  for (const { key } of ANALYSES) if ((a as Record<string, unknown>)[key] === true) flags[key] = true;
  return {
    ...EMPTY_COMPOSE,
    description: text(r.description),
    subject: text(r.subject),
    organism: text(r.organism),
    substrate: text(r.substrate),
    inhibitor: text(r.inhibitor),
    isoform: text(r.isoform),
    any_mode: r.any_mode === true,
    analyses: flags,
    robustness: a.robustness !== undefined,
    samples: text(a.robustness?.samples),
    stochastic: a.stochastic !== undefined,
    volume: text(a.stochastic?.volume_l),
    stochasticEnd: text(a.stochastic?.end_s),
    stochasticSeed: text(a.stochastic?.seed),
    knockout: (a.knockout ?? []).join(", "),
    overexpress: (a.overexpress ?? []).join(", "),
    sweep: (r.sweep?.parameters ?? []).join(", "),
    sweepLow: text(r.sweep?.low),
    sweepHigh: text(r.sweep?.high),
    sweepSteps: text(r.sweep?.steps),
    no_simulate: r.no_simulate === true,
    no_analysis: r.no_analysis === true,
    no_ranking: r.no_ranking === true,
  };
}

export default function ComposeScreen() {
  const [form, setForm] = useState<ComposeForm>(EMPTY_COMPOSE);
  const [organismNote, setOrganismNote] = useState<string | null>(null);
  const reopened = useReopenedRun();
  const linked = useLinkedQuestion(LINK_KEYS);
  const run = useRun("compose", reopened);
  const shapes = useQuery({ queryKey: ["compose-shapes"], queryFn: () => apiJson<ShapesResponse>("/api/compose/shapes"), staleTime: Infinity });
  const descriptionRef = useRef<HTMLInputElement>(null);
  const set = <K extends keyof ComposeForm>(key: K, value: ComposeForm[K]) => setForm((f) => ({ ...f, [key]: value }));
  const err = (field: string) => fieldError(run.requestError, field);
  const running = run.submitting || run.status === "queued" || run.status === "running";

  usePrefill(
    run.run,
    reopened,
    linked,
    (request) => setForm(composeForm(request)),
    (fields) => setForm({ ...EMPTY_COMPOSE, ...fields }),
  );

  const readOrganism = () => {
    const name = form.organism.trim();
    if (!name) return setOrganismNote(null);
    apiPost<NormaliseOrganismResponse>("/api/organisms/normalise", { name }).then(
      (r) => setOrganismNote(r.note),
      () => setOrganismNote(null),
    );
  };
  const chosen = ANALYSES.filter((a) => form.analyses[a.key]).length + (form.robustness ? 1 : 0) + (form.stochastic ? 1 : 0);

  const formPane = (
    <RunForm
      id="compose.submit"
      label="Compose"
      hint={form.description.trim() ? `caterva compose "${form.description.trim()}"` : "Write a mechanism first"}
      onSubmit={() => void run.submit(composeRequest(form))}
      running={running}
      onCancel={() => void run.cancel()}
    >
      <Field label="Mechanism" hint="A shape, not a pathway: “Michaelis-Menten with a competitive inhibitor”, “a toggle switch”." error={err("description")}>
        <TextInput
          ref={descriptionRef}
          value={form.description}
          onChange={(e) => set("description", e.target.value)}
          required
        />
      </Field>
      <ShapeCatalogue
        shapes={shapes.data?.shapes}
        error={shapes.isError}
        onPick={(phrase) => {
          set("description", phrase);
          descriptionRef.current?.focus();
        }}
      />

      <FieldGroup title="Constants from the literature">
        <Field
          label="Enzyme"
          optional
          hint="An EC number (1.1.1.27) or a name. With one, Km, kcat and Ki are searched in BRENDA; without one the model keeps labelled placeholders."
          error={err("subject")}
        >
          <TextInput mono value={form.subject} onChange={(e) => set("subject", e.target.value)} />
        </Field>
        <Field label="Organism" optional hint={organismNote ?? "Never inferred; a measurement in another organism is never substituted."} error={err("organism")}>
          <TextInput
            value={form.organism}
            onChange={(e) => {
              set("organism", e.target.value);
              setOrganismNote(null);
            }}
            onBlur={readOrganism}
           
          />
        </Field>
        <div className="k-row2">
          <Field label="Substrate" optional error={err("substrate")}>
            <TextInput value={form.substrate} onChange={(e) => set("substrate", e.target.value)} />
          </Field>
          <Field label="Isoform" optional error={err("isoform")}>
            <TextInput value={form.isoform} onChange={(e) => set("isoform", e.target.value)} />
          </Field>
        </div>
        <Field label="Inhibitor" optional error={err("inhibitor")}>
          <TextInput value={form.inhibitor} onChange={(e) => set("inhibitor", e.target.value)} />
        </Field>
        <Checkbox
          label="Any inhibition mode"
          checked={form.any_mode}
          onChange={(v) => set("any_mode", v)}
          hint="Keep the resolver's Ki even when its row states another mode than the model's."
        />
      </FieldGroup>

      <FieldGroup title="Analyses" aside={chosen ? <span className="font-mono">{chosen}</span> : undefined}>
        {ANALYSES.map((a) => (
          <Checkbox
            key={a.key}
            label={a.label}
            hint={a.hint}
            checked={Boolean(form.analyses[a.key])}
            onChange={(v) => set("analyses", { ...form.analyses, [a.key]: v })}
          />
        ))}
        <Checkbox
          label="Robustness to the placeholders"
          hint="Resample every unmeasured constant; empty samples uses the command's default count."
          checked={form.robustness}
          onChange={(v) => set("robustness", v)}
        />
        {form.robustness ? (
          <Field label="Samples" optional error={err("analyses.robustness")}>
            <NumberInput inputMode="numeric" value={form.samples} onChange={(e) => set("samples", e.target.value)} />
          </Field>
        ) : null}
        <Checkbox label="Stochastic simulation" checked={form.stochastic} onChange={(v) => set("stochastic", v)} hint="Exact SSA in a volume you state." />
        {form.stochastic ? (
          <>
            <Field label="Volume" error={err("analyses.stochastic")}>
              <NumberInput unit="L" value={form.volume} onChange={(e) => set("volume", e.target.value)} />
            </Field>
            <div className="k-row2">
              <Field label="Horizon" optional>
                <NumberInput unit="s" value={form.stochasticEnd} onChange={(e) => set("stochasticEnd", e.target.value)} />
              </Field>
              <Field label="Seed" optional>
                <NumberInput inputMode="numeric" value={form.stochasticSeed} onChange={(e) => set("stochasticSeed", e.target.value)} />
              </Field>
            </div>
          </>
        ) : null}
      </FieldGroup>

      <Disclosure title="Perturbations, sweeps and switches">
        <div className="k-group-body">
          <Field label="Knock out" optional hint="Species, comma separated." error={err("analyses.knockout")}>
            <TextInput mono value={form.knockout} onChange={(e) => set("knockout", e.target.value)} />
          </Field>
          <Field label="Overexpress" optional hint="Species, comma separated." error={err("analyses.overexpress")}>
            <TextInput mono value={form.overexpress} onChange={(e) => set("overexpress", e.target.value)} />
          </Field>
          <Field label="Sweep" optional hint="Parameter ids, comma separated, as the result's table names them." error={err("sweep")}>
            <TextInput mono value={form.sweep} onChange={(e) => set("sweep", e.target.value)} />
          </Field>
          {names(form.sweep).length ? (
            <div className="k-row3">
              <Field label="From" optional>
                <NumberInput unit="fold" value={form.sweepLow} onChange={(e) => set("sweepLow", e.target.value)} />
              </Field>
              <Field label="To" optional>
                <NumberInput unit="fold" value={form.sweepHigh} onChange={(e) => set("sweepHigh", e.target.value)} />
              </Field>
              <Field label="Steps" optional>
                <NumberInput inputMode="numeric" value={form.sweepSteps} onChange={(e) => set("sweepSteps", e.target.value)} />
              </Field>
            </div>
          ) : null}
          <Checkbox label="No simulation" checked={form.no_simulate} onChange={(v) => set("no_simulate", v)} />
          <Checkbox label="No stability analysis" checked={form.no_analysis} onChange={(v) => set("no_analysis", v)} />
          <Checkbox label="No influence ranking" checked={form.no_ranking} onChange={(v) => set("no_ranking", v)} />
        </div>
      </Disclosure>
    </RunForm>
  );

  return (
    <Screen title="Compose" purpose="Build a model from the shape of a mechanism, and see where every number in it came from.">
      <KineticsLayout
        id="compose"
        form={formPane}
        result={
          <KineticsRun<"compose">
            state={run}
            path="/compose"
            exports={composeExports}
            onRetry={() => void run.submit(composeRequest(form))}
            progress={<ComposeProgress stages={run.stages} />}
            idle={
              <EmptyState title="Describe a mechanism, not a pathway">
                <p>
                  A shape such as a cascade, a toggle switch or competitive inhibition. Name an enzyme, an organism
                  and a substrate to have its constants looked up: each one then carries its BRENDA reference, and
                  anything not found stays a placeholder that says why.
                </p>
                <p className="muted">
                  The verdict comes first: what the model can answer, and the worst thing wrong with it.
                </p>
              </EmptyState>
            }
          >
            {(result, record) => <ComposeResultView result={result} run={record} />}
          </KineticsRun>
        }
      />
    </Screen>
  );
}
