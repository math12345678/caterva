/**
 * /bind: the measured binding free energy a simulation is held to, from
 * cited Ki rows (owner: sci-kinetics).
 *
 * Three questions, as `caterva bind` asks them: which compounds have a Ki
 * here (list), what is one compound's ΔG°bind band and does a computed
 * value agree with it (inhibitor), and which compounds could serve as a
 * benchmark at all (survey). Choosing a compound from the list fills the
 * inhibitor question with it.
 */
import { useState } from "react";

import type { BindRequest } from "@/api/types";
import { useRun } from "@/api/useRun";
import { Screen } from "@/components/screen/Screen";
import { EmptyState } from "@/components/states/States";

import { BindResultView } from "./kinetics/BindResult";
import { fieldError, NumberField, readNumber, RunForm, Segmented, TextField } from "./kinetics/form";
import "./kinetics/kinetics.css";
import { useReopenedRun } from "./kinetics/reopen";
import { cancelling, RunView } from "./kinetics/RunView";

interface Form {
  mode: BindRequest["mode"];
  ec: string;
  organism: string;
  inhibitor: string;
  state: "free" | "ternary";
  isoform: string;
  computed: string;
  error: string;
  unit: "kcal" | "kj";
}

export function bindRequest(f: Form): BindRequest {
  const request: BindRequest = { ec: f.ec.trim(), mode: f.mode };
  if (f.organism.trim()) request.organism = f.organism.trim();
  if (f.state !== "free") request.state = f.state;
  if (f.mode === "inhibitor") {
    request.inhibitor = f.inhibitor.trim();
    if (f.isoform.trim()) request.isoform = f.isoform.trim();
    const value = readNumber(f.computed);
    if (value !== undefined) {
      request.computed = { value, unit: f.unit };
      const error = readNumber(f.error);
      if (error !== undefined) request.computed.error = error;
    }
  }
  return request;
}

export default function BindScreen() {
  const [form, setForm] = useState<Form>({
    mode: "inhibitor",
    ec: "",
    organism: "",
    inhibitor: "",
    state: "free",
    isoform: "",
    computed: "",
    error: "",
    unit: "kcal",
  });
  const run = useRun("bind", useReopenedRun());
  const set = <K extends keyof Form>(key: K, value: Form[K]) => setForm((f) => ({ ...f, [key]: value }));
  const err = (field: string) => fieldError(run.requestError, field);
  const running = run.status === "queued" || run.status === "running";

  const pick = (compound: string) => {
    const next = { ...form, mode: "inhibitor" as const, inhibitor: compound };
    setForm(next);
    void run.submit(bindRequest(next));
  };

  const action = form.mode === "inhibitor" ? (form.computed.trim() ? "Judge" : "Build the target") : form.mode === "list" ? "List compounds" : "Survey";

  return (
    <Screen title="Binding" purpose="The measured binding free energy a simulation is held to, from cited Ki rows.">
      <div className="k-split">
        <RunForm label={action} onSubmit={() => void run.submit(bindRequest(form))} running={running} onCancel={cancelling(run)}>
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
          <div className="k-row2">
            <TextField label="EC number" value={form.ec} onChange={(v) => set("ec", v)} mono required error={err("ec")} />
            <TextField label="Organism" value={form.organism} onChange={(v) => set("organism", v)} error={err("organism")} />
          </div>
          {form.mode === "inhibitor" ? (
            <>
              <TextField
                label="Inhibitor"
                value={form.inhibitor}
                onChange={(v) => set("inhibitor", v)}
                required
                error={err("inhibitor")}
                hint="As BRENDA names it. Ask which compounds have a Ki to choose from the list."
              />
              <TextField label="Isoform simulated" value={form.isoform} onChange={(v) => set("isoform", v)} error={err("isoform")} hint="Rows naming another isoform are excluded." />
            </>
          ) : null}
          <Segmented
            label="State the simulation modelled"
            value={form.state}
            options={[
              { value: "free", label: "Inhibitor + apo enzyme" },
              { value: "ternary", label: "Inhibitor + E·S" },
            ]}
            onChange={(v) => set("state", v)}
          />
          {form.mode === "inhibitor" ? (
            <fieldset className="k-fieldset">
              <legend className="k-legend">Your computed ΔG°bind (optional)</legend>
              <div className="k-row2">
                <NumberField label="Value" value={form.computed} onChange={(v) => set("computed", v)} error={err("computed")} />
                <NumberField label="σ" value={form.error} onChange={(v) => set("error", v)} hint="from independent replicas" />
              </div>
              <Segmented
                label="Unit"
                value={form.unit}
                options={[
                  { value: "kcal", label: "kcal/mol" },
                  { value: "kj", label: "kJ/mol" },
                ]}
                onChange={(v) => set("unit", v)}
              />
            </fieldset>
          ) : null}
        </RunForm>
        <RunView<"bind">
          state={run}
          empty={
            <EmptyState title="Name an enzyme and an inhibitor">
              <p className="k-prose">
                Every cited Ki becomes ΔG°bind at its own assay temperature. Only rows whose inhibition mode fits the
                state the simulation modelled are kept, so the band is the measurement a computed value can honestly
                be judged against. A row that states no temperature is a range, never a guess.
              </p>
            </EmptyState>
          }
        >
          {(result) => <BindResultView result={result} onPick={pick} />}
        </RunView>
      </div>
    </Screen>
  );
}
