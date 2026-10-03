/**
 * /sim: exact stochastic kinetics (Gillespie SSA), seeded so every
 * trajectory can be produced again (owner: sci-kinetics).
 *
 * The seed is filled in with a random one when the screen opens, shown and
 * editable, because a trajectory whose seed is not recorded cannot be
 * reproduced. The rate constant is always asked for: the command's default
 * for the bimolecular reaction disagrees with its own help text, so the
 * page never relies on it. Amounts and the horizon may be left empty, and
 * the result then marks the command's defaults as defaults.
 */
import { Shuffle } from "lucide-react";
import { useState } from "react";

import type { SimRequest } from "@/api/types";
import { useRun } from "@/api/useRun";
import { Field, fieldError, NumberInput, parseNumber } from "@/components/forms/Field";
import { Segmented } from "@/components/forms/Segmented";
import { Screen } from "@/components/screen/Screen";
import { EmptyState } from "@/components/states/States";

import { KineticsLayout, KineticsRun, RunForm, text, usePrefill, useReopenedRun, useRunAddress } from "./kinetics/kit";
import "./kinetics/kinetics.css";
import { SimResultView } from "./kinetics/SimResult";

export function randomSeed(): string {
  const words = new Uint32Array(1);
  crypto.getRandomValues(words);
  return String(words[0] % 2_147_483_647);
}

export interface SimForm {
  reaction: "decay" | "association";
  seed: string;
  a0: string;
  b0: string;
  k: string;
  end: string;
}

function num(t: string): number | undefined {
  const s = t.trim();
  if (!s) return undefined;
  const n = parseNumber(s);
  return n === null ? (s as unknown as number) : n;
}

export function simRequest(f: SimForm): SimRequest {
  const request: SimRequest = { seed: num(f.seed) as number };
  if (f.reaction === "association") request.bimolecular = true;
  for (const key of ["a0", "k", "end"] as const) {
    const v = num(f[key]);
    if (v !== undefined) request[key] = v;
  }
  if (f.reaction === "association") {
    const b0 = num(f.b0);
    if (b0 !== undefined) request.b0 = b0;
  }
  return request;
}

export function simForm(request: Record<string, unknown>): SimForm {
  const r = request as Partial<SimRequest>;
  return {
    reaction: r.bimolecular ? "association" : "decay",
    seed: text(r.seed),
    a0: text(r.a0),
    b0: text(r.b0),
    k: text(r.k),
    end: text(r.end),
  };
}

export default function SimScreen() {
  const [form, setForm] = useState<SimForm>(() => ({ reaction: "decay", seed: randomSeed(), a0: "", b0: "", k: "", end: "" }));
  const [kMissing, setKMissing] = useState(false);
  const reopened = useReopenedRun();
  const run = useRun("sim", reopened);
  const set = <K extends keyof SimForm>(key: K, value: SimForm[K]) => setForm((f) => ({ ...f, [key]: value }));
  const err = (field: string) => fieldError(run.requestError, field);
  const running = run.submitting || run.status === "queued" || run.status === "running";

  usePrefill(run.run, reopened, null, (request) => setForm(simForm(request)), () => {});
  useRunAddress("/sim", run.run, reopened);

  const submit = () => {
    if (!form.k.trim()) {
      setKMissing(true);
      return;
    }
    setKMissing(false);
    void run.submit(simRequest(form));
  };
  const timeUnit = "time units";

  const formPane = (
    <RunForm id="sim.submit" label="Simulate" hint="Stochastic simulation, with a seed" onSubmit={submit} running={running} onCancel={() => void run.cancel()}>
      <div className="field">
        <span className="field-label">Reaction</span>
        <Segmented
          label="Reaction"
          value={form.reaction}
          options={[
            { value: "decay", label: "A → B" },
            { value: "association", label: "A + B → C" },
          ]}
          onChange={(v) => set("reaction", v)}
        />
      </div>
      <Field
        label="Rate constant k"
        hint={form.reaction === "decay" ? "Per molecule per time unit." : "Per molecule pair per time unit."}
        error={kMissing ? "Give k: the command's default for A + B → C disagrees with its own help text, so the page never relies on it." : err("k")}
      >
        <NumberInput value={form.k} onChange={(e) => set("k", e.target.value)} />
      </Field>
      <div className="k-row2">
        <Field label="A at the start" optional error={err("a0")}>
          <NumberInput inputMode="numeric" unit="molecules" value={form.a0} onChange={(e) => set("a0", e.target.value)} />
        </Field>
        {form.reaction === "association" ? (
          <Field label="B at the start" optional error={err("b0")}>
            <NumberInput inputMode="numeric" unit="molecules" value={form.b0} onChange={(e) => set("b0", e.target.value)} />
          </Field>
        ) : null}
      </div>
      <Field label="Horizon" optional error={err("end")}>
        <NumberInput unit={timeUnit} value={form.end} onChange={(e) => set("end", e.target.value)} />
      </Field>
      <Field label="Seed" hint="Recorded with the run; the same seed gives the same trajectory." error={err("seed")}>
        <span className="k-seed">
          <NumberInput inputMode="numeric" value={form.seed} onChange={(e) => set("seed", e.target.value)} />
          <button type="button" className="btn btn-icon" aria-label="Draw another seed" title="Draw another seed" onClick={() => set("seed", randomSeed())}>
            <Shuffle size={14} aria-hidden="true" />
          </button>
        </span>
      </Field>
    </RunForm>
  );

  return (
    <Screen title="Stochastic" purpose="Exact stochastic kinetics (Gillespie SSA), seeded so every trajectory can be reproduced.">
      <KineticsLayout
        id="sim"
        form={formPane}
        result={
          <KineticsRun<"sim">
            state={run}
            path="/sim"
            exports={(_, record) => [
              ...(record.artifacts.some((a) => a.name === "trajectory.csv")
                ? [{ label: "CSV", artifact: "trajectory.csv", description: record.artifacts.find((a) => a.name === "trajectory.csv")?.description }]
                : []),
              { label: "JSON", artifact: "result.json", description: "the result exactly as the studio API sent it" },
            ]}
            onRetry={submit}
            idle={
              <EmptyState title="One reaction, molecule by molecule">
                <p>
                  Each event is drawn from the exact propensities, so a small population fluctuates the way a real one
                  does. The deterministic (ODE) expectation is printed beside the run to compare against. Empty amounts
                  use the command&apos;s defaults, and the result says which were defaults.
                </p>
              </EmptyState>
            }
          >
            {(result) => <SimResultView result={result} />}
          </KineticsRun>
        }
      />
    </Screen>
  );
}
