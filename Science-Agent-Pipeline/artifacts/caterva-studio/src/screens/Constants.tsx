/**
 * /constants: an enzyme's measured constants, each with the paper that
 * measured it: `scripts/cite.py` (`make cite`) as a screen (owner:
 * sci-kinetics).
 *
 * cite.py lives in the source checkout, not in the app, so this screen says
 * so (the kind's capability reason) rather than offering a form that will
 * be refused. The two values a person supplies (S0, Vmax) are theirs:
 * empty sends nothing, and the result marks cite.py's default as a default.
 */
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { apiJson } from "@/api/client";
import type { Capabilities, ConstantsRequest } from "@/api/types";
import { useRun } from "@/api/useRun";
import { Screen } from "@/components/screen/Screen";
import { EmptyState, ErrorState } from "@/components/states/States";

import { ConstantsResultView } from "./kinetics/ConstantsResult";
import { Check, fieldError, NumberField, readNumber, RunForm, Segmented, TextField } from "./kinetics/form";
import "./kinetics/kinetics.css";
import { useReopenedRun } from "./kinetics/reopen";
import { cancelling, RunView } from "./kinetics/RunView";

const QUANTITIES = [
  { key: "km", label: "Km" },
  { key: "kcat", label: "kcat" },
  { key: "ki", label: "Ki" },
] as const;

interface Form {
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

export function constantsRequest(f: Form): ConstantsRequest {
  const request: ConstantsRequest = { substrate: f.substrate.trim() };
  if (f.who.trim()) request[f.by] = f.who.trim();
  if (f.organism.trim()) request.organism = f.organism.trim();
  const quantities = QUANTITIES.filter((q) => f.quantities[q.key]).map((q) => q.key);
  if (quantities.length) request.quantities = quantities;
  const s0 = readNumber(f.s0);
  const vmax = readNumber(f.vmax);
  const seed = readNumber(f.seed);
  if (s0 !== undefined) request.s0 = s0;
  if (vmax !== undefined) request.vmax = vmax;
  if (seed !== undefined) request.seed = seed;
  if (f.basis.trim()) request.basis = f.basis.trim();
  return request;
}

export default function ConstantsScreen() {
  const [form, setForm] = useState<Form>({
    by: "ec",
    who: "",
    organism: "",
    substrate: "",
    quantities: { km: true },
    s0: "",
    vmax: "",
    basis: "",
    seed: "",
  });
  const run = useRun("constants", useReopenedRun());
  const capabilities = useQuery({ queryKey: ["capabilities"], queryFn: () => apiJson<Capabilities>("/api/capabilities") });
  const set = <K extends keyof Form>(key: K, value: Form[K]) => setForm((f) => ({ ...f, [key]: value }));
  const err = (field: string) => fieldError(run.requestError, field);
  const running = run.status === "queued" || run.status === "running";
  const kind = capabilities.data?.kinds.constants;

  return (
    <Screen title="Constants" purpose="Look up an enzyme's measured constants, each with the paper that measured it.">
      {kind && !kind.available ? (
        <ErrorState error={{ code: "unavailable", message: kind.reason ?? "This installation cannot look constants up." }} />
      ) : (
        <div className="k-split">
          <RunForm label="Look up" onSubmit={() => void run.submit(constantsRequest(form))} running={running} onCancel={cancelling(run)}>
            <Segmented
              label="Enzyme given as"
              value={form.by}
              options={[
                { value: "ec", label: "EC number" },
                { value: "enzyme", label: "Name" },
              ]}
              onChange={(v) => set("by", v)}
            />
            <TextField
              label={form.by === "ec" ? "EC number" : "Enzyme name"}
              value={form.who}
              onChange={(v) => set("who", v)}
              mono={form.by === "ec"}
              required
              error={err(form.by)}
              hint={form.by === "enzyme" ? "Looked up in UniProt, and refused if it names more than one enzyme." : undefined}
            />
            <TextField label="Organism" value={form.organism} onChange={(v) => set("organism", v)} error={err("organism")} hint="Required: the organism is never inferred." />
            <TextField label="Substrate" value={form.substrate} onChange={(v) => set("substrate", v)} required error={err("substrate")} />
            <fieldset className="k-fieldset">
              <legend className="k-legend">Constants</legend>
              {QUANTITIES.map((q) => (
                <Check
                  key={q.key}
                  label={q.label}
                  checked={Boolean(form.quantities[q.key])}
                  onChange={(v) => set("quantities", { ...form.quantities, [q.key]: v })}
                />
              ))}
            </fieldset>
            <fieldset className="k-fieldset">
              <legend className="k-legend">Yours, not the literature's</legend>
              <div className="k-row2">
                <NumberField label="S0" value={form.s0} onChange={(v) => set("s0", v)} error={err("s0")} />
                <NumberField label="Vmax" value={form.vmax} onChange={(v) => set("vmax", v)} error={err("vmax")} />
              </div>
              <TextField label="Basis for them" value={form.basis} onChange={(v) => set("basis", v)} hint="Printed beside them in the document." />
              <NumberField
                label="Seed"
                value={form.seed}
                onChange={(v) => set("seed", v)}
                integer
                error={err("seed")}
                hint="For a band across values the literature disagrees about; without one no band is produced."
              />
            </fieldset>
          </RunForm>
          <RunView<"constants">
            state={run}
            empty={
              <EmptyState title="Name an enzyme, an organism and a substrate">
                <p className="k-prose">
                  Each constant comes back with its BRENDA reference, the organism and assay conditions of the row,
                  and the row's own words. A constant nobody measured for that organism is reported as not found,
                  with the organisms where it was measured.
                </p>
              </EmptyState>
            }
          >
            {(result) => <ConstantsResultView result={result} />}
          </RunView>
        </div>
      )}
    </Screen>
  );
}
