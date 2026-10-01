/**
 * /constants: an enzyme's measured constants, each with the paper that
 * measured it: `scripts/cite.py` (`make cite`) as a screen (owner:
 * sci-kinetics).
 *
 * cite.py lives in the source checkout, not in the app, so this screen says
 * so (the kind's capability reason) rather than offering a form that will
 * be refused. The two values a person supplies (S0, Vmax) are theirs:
 * empty sends nothing, and the result marks cite.py's default as a default.
 * Nothing here is ever pre-filled with a measured quantity.
 */
import { useState } from "react";

import type { ConstantsRequest } from "@/api/types";
import { useRun } from "@/api/useRun";
import { Checkbox, Field, fieldError, NumberInput, parseNumber, TextInput } from "@/components/forms/Field";
import { Segmented } from "@/components/forms/Segmented";
import { Screen } from "@/components/screen/Screen";
import { Loading } from "@/components/states/Loading";
import { EmptyState, ErrorState } from "@/components/states/States";
import { useCapabilities } from "@/lib/queries";

import { ConstantsResultView } from "./kinetics/ConstantsResult";
import { FieldGroup, KineticsLayout, KineticsRun, RunForm, text, useLinkedQuestion, usePrefill, useReopenedRun, useRunAddress } from "./kinetics/kit";
import "./kinetics/kinetics.css";

const QUANTITIES = [
  { key: "km", label: "Km", hint: "Michaelis constant" },
  { key: "kcat", label: "kcat", hint: "turnover number" },
  { key: "ki", label: "Ki", hint: "inhibition constant" },
] as const;

export interface ConstantsForm {
  by: "ec" | "enzyme";
  who: string;
  organism: string;
  substrate: string;
  quantities: Record<string, boolean>;
  s0: string;
  vmax: string;
  basis: string;
  seed: string;
}

export const EMPTY_CONSTANTS: ConstantsForm = {
  by: "ec",
  who: "",
  organism: "",
  substrate: "",
  quantities: { km: true },
  s0: "",
  vmax: "",
  basis: "",
  seed: "",
};

function num(t: string): number | undefined {
  const s = t.trim();
  if (!s) return undefined;
  const n = parseNumber(s);
  return n === null ? (s as unknown as number) : n;
}

export function constantsRequest(f: ConstantsForm): ConstantsRequest {
  const request: ConstantsRequest = { substrate: f.substrate.trim() };
  if (f.who.trim()) request[f.by] = f.who.trim();
  if (f.organism.trim()) request.organism = f.organism.trim();
  const quantities = QUANTITIES.filter((q) => f.quantities[q.key]).map((q) => q.key);
  if (quantities.length) request.quantities = quantities;
  const s0 = num(f.s0);
  const vmax = num(f.vmax);
  const seed = num(f.seed);
  if (s0 !== undefined) request.s0 = s0;
  if (vmax !== undefined) request.vmax = vmax;
  if (seed !== undefined) request.seed = seed;
  if (f.basis.trim()) request.basis = f.basis.trim();
  return request;
}

export function constantsForm(request: Record<string, unknown>): ConstantsForm {
  const r = request as Partial<ConstantsRequest>;
  const quantities: Record<string, boolean> = {};
  for (const q of r.quantities ?? ["km"]) quantities[q] = true;
  return {
    by: r.enzyme ? "enzyme" : "ec",
    who: text(r.enzyme ?? r.ec),
    organism: text(r.organism),
    substrate: text(r.substrate),
    quantities,
    s0: text(r.s0),
    vmax: text(r.vmax),
    basis: text(r.basis),
    seed: text(r.seed),
  };
}

export default function ConstantsScreen() {
  const [form, setForm] = useState<ConstantsForm>(EMPTY_CONSTANTS);
  const reopened = useReopenedRun();
  const linked = useLinkedQuestion(["ec", "enzyme", "organism", "substrate"]);
  const run = useRun("constants", reopened);
  const caps = useCapabilities();
  const set = <K extends keyof ConstantsForm>(key: K, value: ConstantsForm[K]) => setForm((f) => ({ ...f, [key]: value }));
  const err = (field: string) => fieldError(run.requestError, field);
  const running = run.submitting || run.status === "queued" || run.status === "running";
  const kind = caps.data?.kinds.constants;

  usePrefill(
    run.run,
    reopened,
    linked,
    (request) => setForm(constantsForm(request)),
    (fields) => setForm({ ...EMPTY_CONSTANTS, by: fields.enzyme ? "enzyme" : "ec", who: fields.enzyme ?? fields.ec ?? "", organism: fields.organism ?? "", substrate: fields.substrate ?? "" }),
  );
  useRunAddress("/constants", run.run, reopened);

  const formPane = (
    <RunForm
      id="constants.submit"
      label="Look up"
      hint="python3 scripts/cite.py, every row with its paper"
      onSubmit={() => void run.submit(constantsRequest(form))}
      running={running}
      onCancel={() => void run.cancel()}
    >
      <div className="field">
        <span className="field-label">Enzyme given as</span>
        <Segmented
          label="Enzyme given as"
          value={form.by}
          options={[
            { value: "ec", label: "EC number" },
            { value: "enzyme", label: "Name" },
          ]}
          onChange={(v) => set("by", v)}
        />
      </div>
      <Field
        label={form.by === "ec" ? "EC number" : "Enzyme name"}
        hint={form.by === "enzyme" ? "Looked up in UniProt, and refused if it names more than one enzyme." : "Four numbers, as 2.7.1.1."}
        error={err(form.by)}
      >
        <TextInput mono={form.by === "ec"} value={form.who} onChange={(e) => set("who", e.target.value)} />
      </Field>
      <Field label="Organism" hint="Required: the organism is never inferred." error={err("organism")}>
        <TextInput value={form.organism} onChange={(e) => set("organism", e.target.value)} />
      </Field>
      <Field label="Substrate" error={err("substrate")}>
        <TextInput value={form.substrate} onChange={(e) => set("substrate", e.target.value)} />
      </Field>
      <FieldGroup title="Constants">
        {QUANTITIES.map((q) => (
          <Checkbox
            key={q.key}
            label={q.label}
            hint={q.hint}
            checked={Boolean(form.quantities[q.key])}
            onChange={(v) => set("quantities", { ...form.quantities, [q.key]: v })}
          />
        ))}
      </FieldGroup>
      <FieldGroup title="Yours, not the literature's">
        <div className="k-row2">
          <Field label="S0" optional error={err("s0")}>
            <NumberInput value={form.s0} onChange={(e) => set("s0", e.target.value)} />
          </Field>
          <Field label="Vmax" optional error={err("vmax")}>
            <NumberInput value={form.vmax} onChange={(e) => set("vmax", e.target.value)} />
          </Field>
        </div>
        <Field label="Basis for them" optional hint="Printed beside them in the document.">
          <TextInput value={form.basis} onChange={(e) => set("basis", e.target.value)} />
        </Field>
        <Field
          label="Seed"
          optional
          hint="For a band across values the literature disagrees about; without one no band is produced."
          error={err("seed")}
        >
          <NumberInput inputMode="numeric" value={form.seed} onChange={(e) => set("seed", e.target.value)} />
        </Field>
      </FieldGroup>
    </RunForm>
  );

  return (
    <Screen title="Constants" purpose="Look up an enzyme's measured constants, each with the paper that measured it.">
      {caps.isPending ? (
        <Loading label="Asking what this installation can look up" />
      ) : kind && !kind.available ? (
        <ErrorState
          title="Constants are looked up from the source checkout"
          error={{ code: "unavailable", message: kind.reason ?? "This installation cannot look constants up." }}
        />
      ) : (
        <KineticsLayout
          id="constants"
          form={formPane}
          result={
            <KineticsRun<"constants">
              state={run}
              path="/constants"
              exports={() => [{ label: "JSON", artifact: "result.json", description: "the result exactly as the studio API sent it" }]}
              onRetry={() => void run.submit(constantsRequest(form))}
              idle={
                <EmptyState title="Name an enzyme, an organism and a substrate">
                  <p>
                    Each constant comes back with its BRENDA reference, the organism and assay conditions of the
                    row, and the row&apos;s own words, beside every other row the resolver read. A constant nobody
                    measured for that organism is reported as not found, with the organisms where it was measured.
                  </p>
                </EmptyState>
              }
            >
              {(result, record) => <ConstantsResultView result={result} request={record.request} />}
            </KineticsRun>
          }
        />
      )}
    </Screen>
  );
}
