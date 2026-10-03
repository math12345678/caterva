/**
 * /bind: the measured binding free energy a simulation is held to, from
 * cited Ki rows (owner: sci-kinetics).
 *
 * Three questions, as `caterva bind` asks them: which compounds have a Ki
 * here (list), what is one compound's ΔG°bind band and does a computed
 * value agree with it (inhibitor), and which compounds could serve as a
 * benchmark at all (survey). Choosing a compound from the list or the
 * survey asks the inhibitor question about it at once: that is the
 * question the reader just chose.
 */
import { useState } from "react";

import { isCompleteEc, subjectFields } from "@/api/enzymes";
import type { BindRequest } from "@/api/types";
import { useRun } from "@/api/useRun";
import { Field, fieldError, NumberInput, parseNumber, TextInput } from "@/components/forms/Field";
import { Segmented } from "@/components/forms/Segmented";
import { EnzymeFinder } from "@/components/enzyme/EnzymeFinder";
import { Screen } from "@/components/screen/Screen";
import { EmptyState } from "@/components/states/States";

import { BindResultView } from "./kinetics/BindResult";
import { FieldGroup, KineticsLayout, KineticsRun, RunForm, text, useLinkedQuestion, usePrefill, useReopenedRun, useRunAddress } from "./kinetics/kit";
import "./kinetics/kinetics.css";

export interface BindForm {
  mode: BindRequest["mode"];
  /** The chosen enzyme's EC number; the request carries nothing else. */
  ec: string;
  /** A name a link carried, to start the finder from; never sent. */
  ecSeed: string;
  organism: string;
  inhibitor: string;
  state: "free" | "ternary";
  isoform: string;
  computed: string;
  error: string;
  unit: "kcal" | "kj";
}

export const EMPTY_BIND: BindForm = {
  mode: "inhibitor",
  ec: "",
  ecSeed: "",
  organism: "",
  inhibitor: "",
  state: "free",
  isoform: "",
  computed: "",
  error: "",
  unit: "kcal",
};

function num(t: string): number | undefined {
  const s = t.trim();
  if (!s) return undefined;
  const n = parseNumber(s);
  return n === null ? (s as unknown as number) : n;
}

export function bindRequest(f: BindForm): BindRequest {
  const request: BindRequest = { ec: isCompleteEc(f.ec) ? f.ec.trim() : "", mode: f.mode };
  if (f.organism.trim()) request.organism = f.organism.trim();
  if (f.state !== "free") request.state = f.state;
  if (f.mode === "inhibitor") {
    request.inhibitor = f.inhibitor.trim();
    if (f.isoform.trim()) request.isoform = f.isoform.trim();
    const value = num(f.computed);
    if (value !== undefined) {
      request.computed = { value, unit: f.unit };
      const error = num(f.error);
      if (error !== undefined) request.computed.error = error;
    }
  }
  return request;
}

export function bindForm(request: Record<string, unknown>): BindForm {
  const r = request as Partial<BindRequest>;
  return {
    mode: r.mode ?? "inhibitor",
    ec: subjectFields(text(r.ec)).subject,
    ecSeed: subjectFields(text(r.ec)).subjectSeed,
    organism: text(r.organism),
    inhibitor: text(r.inhibitor),
    state: r.state === "ternary" ? "ternary" : "free",
    isoform: text(r.isoform),
    computed: text(r.computed?.value),
    error: text(r.computed?.error),
    unit: r.computed?.unit === "kj" ? "kj" : "kcal",
  };
}

export default function BindScreen() {
  const [form, setForm] = useState<BindForm>(EMPTY_BIND);
  const reopened = useReopenedRun();
  const linked = useLinkedQuestion(["ec", "organism", "inhibitor"]);
  const run = useRun("bind", reopened);
  const set = <K extends keyof BindForm>(key: K, value: BindForm[K]) => setForm((f) => ({ ...f, [key]: value }));
  const err = (field: string) => fieldError(run.requestError, field);
  const running = run.submitting || run.status === "queued" || run.status === "running";

  usePrefill(run.run, reopened, linked, (request) => setForm(bindForm(request)), (fields) => {
      const { ec, ...rest } = fields;
      const { subject, subjectSeed } = subjectFields(ec ?? "");
      setForm({ ...EMPTY_BIND, ...rest, ec: subject, ecSeed: subjectSeed });
    });
  useRunAddress("/bind", run.run, reopened);

  const pick = (compound: string) => {
    const next = { ...form, mode: "inhibitor" as const, inhibitor: compound, computed: "", error: "" };
    setForm(next);
    void run.submit(bindRequest(next));
  };

  const action =
    form.mode === "inhibitor" ? (form.computed.trim() ? "Judge" : "Build the target") : form.mode === "list" ? "List compounds" : "Survey";

  const formPane = (
    <RunForm id="bind.submit" label={action} hint="caterva bind" onSubmit={() => void run.submit(bindRequest(form))} running={running} onCancel={() => void run.cancel()}>
      <div className="field">
        <span className="field-label">Question</span>
        <Segmented
          label="Question"
          value={form.mode}
          options={[
            { value: "inhibitor", label: "One inhibitor" },
            { value: "list", label: "Which compounds" },
            { value: "survey", label: "Survey" },
          ]}
          onChange={(v) => set("mode", v)}
        />
      </div>
      <EnzymeFinder
        value={form.ec}
        onChange={(ec) => setForm((f) => ({ ...f, ec, ecSeed: "" }))}
        organism={form.organism}
        seed={form.ecSeed}
        hint="A name, an abbreviation or an EC number. Choose one from the list: the binding data are read for its EC number."
        error={err("ec")}
      />
      <Field label="Organism" optional error={err("organism")}>
        <TextInput value={form.organism} onChange={(e) => set("organism", e.target.value)} />
      </Field>
      {form.mode === "inhibitor" ? (
        <>
          <Field label="Inhibitor" hint="As BRENDA names it. Ask which compounds have a Ki to choose from the list." error={err("inhibitor")}>
            <TextInput value={form.inhibitor} onChange={(e) => set("inhibitor", e.target.value)} />
          </Field>
          <Field label="Isoform simulated" optional hint="Rows naming another isoform are excluded." error={err("isoform")}>
            <TextInput value={form.isoform} onChange={(e) => set("isoform", e.target.value)} />
          </Field>
        </>
      ) : null}
      <div className="field">
        <span className="field-label">State the simulation modelled</span>
        <Segmented
          label="State the simulation modelled"
          value={form.state}
          options={[
            { value: "free", label: "Inhibitor + apo enzyme" },
            { value: "ternary", label: "Inhibitor + E·S" },
          ]}
          onChange={(v) => set("state", v)}
        />
      </div>
      {form.mode === "inhibitor" ? (
        <FieldGroup title="Your computed ΔG°bind" aside={<span className="field-optional">optional</span>}>
          <div className="k-row2">
            <Field label="Value" error={err("computed")}>
              <NumberInput value={form.computed} onChange={(e) => set("computed", e.target.value)} />
            </Field>
            <Field label="σ" optional hint="From independent replicas.">
              <NumberInput value={form.error} onChange={(e) => set("error", e.target.value)} />
            </Field>
          </div>
          <div className="field">
            <span className="field-label">Unit</span>
            <Segmented
              label="Unit"
              size="sm"
              value={form.unit}
              options={[
                { value: "kcal", label: "kcal/mol" },
                { value: "kj", label: "kJ/mol" },
              ]}
              onChange={(v) => set("unit", v)}
            />
          </div>
        </FieldGroup>
      ) : null}
    </RunForm>
  );

  return (
    <Screen title="Binding" purpose="The measured binding free energy a simulation is held to, from cited Ki rows.">
      <KineticsLayout
        id="bind"
        form={formPane}
        result={
          <KineticsRun<"bind">
            state={run}
            path="/bind"
            exports={() => [{ label: "JSON", artifact: "result.json", description: "the result exactly as the studio API sent it" }]}
            onRetry={() => void run.submit(bindRequest(form))}
            idle={
              <EmptyState title="Name an enzyme and an inhibitor">
                <p>
                  Every cited Ki becomes ΔG°bind at its own assay temperature, and the arithmetic is shown row by row.
                  Only rows whose inhibition mode fits the state the simulation modelled are kept, so the band is the
                  measurement a computed value can honestly be judged against. A row that states no temperature is a
                  range, never a guess.
                </p>
              </EmptyState>
            }
          >
            {(result, record) => <BindResultView result={result} run={record} onPick={pick} />}
          </KineticsRun>
        }
      />
    </Screen>
  );
}
