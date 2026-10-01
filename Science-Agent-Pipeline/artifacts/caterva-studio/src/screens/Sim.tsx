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
import { useState } from "react";

import type { SimRequest } from "@/api/types";
import { useRun } from "@/api/useRun";
import { Screen } from "@/components/screen/Screen";
import { EmptyState } from "@/components/states/States";

import { fieldError, NumberField, readNumber, RunForm, Segmented } from "./kinetics/form";
import "./kinetics/kinetics.css";
import { useReopenedRun } from "./kinetics/reopen";
import { cancelling, RunView } from "./kinetics/RunView";
import { SimResultView } from "./kinetics/SimResult";

function randomSeed(): string {
  const words = new Uint32Array(1);
  crypto.getRandomValues(words);
  return String(words[0] % 2_147_483_647);
}

interface Form {
  reaction: "decay" | "association";
  seed: string;
  a0: string;
  b0: string;
  k: string;
  end: string;
}

export function simRequest(f: Form): SimRequest {
  const request: SimRequest = { seed: readNumber(f.seed) as number };
  if (f.reaction === "association") request.bimolecular = true;
  for (const key of ["a0", "k", "end"] as const) {
    const v = readNumber(f[key]);
    if (v !== undefined) request[key] = v;
  }
  if (f.reaction === "association") {
    const b0 = readNumber(f.b0);
    if (b0 !== undefined) request.b0 = b0;
  }
  return request;
}

export default function SimScreen() {
  const [form, setForm] = useState<Form>(() => ({ reaction: "decay", seed: randomSeed(), a0: "", b0: "", k: "", end: "" }));
  const [kMissing, setKMissing] = useState(false);
  const run = useRun("sim", useReopenedRun());
  const set = <K extends keyof Form>(key: K, value: Form[K]) => setForm((f) => ({ ...f, [key]: value }));
  const err = (field: string) => fieldError(run.requestError, field);
  const running = run.status === "queued" || run.status === "running";

  const submit = () => {
    if (!form.k.trim()) {
      setKMissing(true);
      return;
    }
    setKMissing(false);
    void run.submit(simRequest(form));
  };

  return (
    <Screen
      title="Stochastic"
      purpose="Exact stochastic kinetics (Gillespie SSA), seeded so every trajectory can be reproduced."
    >
      <div className="k-split">
        <RunForm label="Simulate" onSubmit={submit} running={running} onCancel={cancelling(run)}>
          <Segmented
            label="Reaction"
            value={form.reaction}
            options={[
              { value: "decay", label: "A → B" },
              { value: "association", label: "A + B → C" },
            ]}
            onChange={(v) => set("reaction", v)}
          />
          <NumberField
            label="Rate constant k"
            value={form.k}
            onChange={(v) => set("k", v)}
            error={kMissing ? "Give k: the command's default for A + B → C disagrees with its own help text, so the page never relies on it." : err("k")}
            hint={form.reaction === "decay" ? "per molecule per time unit" : "per molecule pair per time unit"}
          />
          <div className="k-row2">
            <NumberField label="A at the start" value={form.a0} onChange={(v) => set("a0", v)} integer error={err("a0")} hint="molecules" />
            {form.reaction === "association" ? (
              <NumberField label="B at the start" value={form.b0} onChange={(v) => set("b0", v)} integer error={err("b0")} hint="molecules" />
            ) : null}
          </div>
          <NumberField label="Horizon" value={form.end} onChange={(v) => set("end", v)} error={err("end")} hint="time units" />
          <NumberField label="Seed" value={form.seed} onChange={(v) => set("seed", v)} integer error={err("seed")} hint="Recorded with the run; the same seed gives the same trajectory." />
        </RunForm>
        <RunView<"sim">
          state={run}
          empty={
            <EmptyState title="One reaction, molecule by molecule">
              <p className="k-prose">
                Each event is drawn from the exact propensities, so a small population fluctuates the way a real one
                does. The deterministic (ODE) expectation is printed beside the run to compare against. Empty
                amounts use the command's defaults, and the result says which were defaults.
              </p>
            </EmptyState>
          }
        >
          {(result) => <SimResultView result={result} />}
        </RunView>
      </div>
    </Screen>
  );
}
