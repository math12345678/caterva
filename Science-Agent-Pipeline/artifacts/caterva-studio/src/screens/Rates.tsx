/**
 * /rates: take your own measured rates to a result you can put in a report
 * (owner: sci-kinetics).
 *
 * One screen, three parts that read top to bottom and are all visible at
 * once, not a wizard: (1) your measurements, got in by dropping a file,
 * choosing one, or pasting from a spreadsheet, and shown as the server read
 * them, every decision and problem stated; (2) what to fit, with the
 * defaults filled from the table; (3) the result: a figure, the constants
 * with their intervals, the lack-of-fit test, the laws compared, and the
 * files to take away. Cmd or Ctrl Enter fits from anywhere on the screen.
 *
 * The browser sends the table as text and the mapping the server answered,
 * never a path, so a run reopened from History restores the table and the
 * mapping exactly (`?run=<id>`). `?example=puromycin` opens R's real
 * Puromycin table, which is what Home's second starting point links to.
 */
import { useEffect, useMemo, useState } from "react";
import { useSearch } from "wouter";

import { useTablePreview } from "@/api/rates";
import type { RatesMapping } from "@/api/types";
import { ApiRequestError } from "@/api/client";
import { useRun } from "@/api/useRun";
import { fieldError } from "@/components/forms/Field";
import { Screen, Section } from "@/components/screen/Screen";
import { EmptyState, ErrorState } from "@/components/states/States";
import { Loading } from "@/components/states/Loading";
import { describeError } from "@/lib/errors";
import { useCapabilities } from "@/lib/queries";
import { useSettings } from "@/lib/settings";

import { KineticsRun, RunForm, useReopenedRun, useRunAddress, usePrefill } from "./kinetics/kit";
import "./kinetics/kinetics.css";
import { DataStep } from "./rates/DataStep";
import { FitStep } from "./rates/FitStep";
import {
  defaultSigma,
  EMPTY_FIT,
  type FitForm,
  ratesRequest,
  requestState,
  sigmaAllowed,
  type Source,
} from "./rates/model";
import { PUROMYCIN_CSV, PUROMYCIN_FILENAME } from "./rates/puromycin";
import { RatesResultView } from "./rates/ResultView";
import "./rates/rates.css";

export default function RatesScreen() {
  const caps = useCapabilities();
  if (caps.isPending) {
    return (
      <Screen title="Rates" purpose="Fit the initial rates you measured, and take away a figure, a table and a methods paragraph.">
        <Loading label="Asking the server" />
      </Screen>
    );
  }
  if (caps.isError) {
    return (
      <Screen title="Rates" purpose="Fit the initial rates you measured, and take away a figure, a table and a methods paragraph.">
        <ErrorState error={caps.error} />
      </Screen>
    );
  }
  if (!caps.data.rates.available) {
    return (
      <Screen title="Rates" purpose="Fit the initial rates you measured, and take away a figure, a table and a methods paragraph.">
        <EmptyState title="Not in this installation">
          <p>{caps.data.rates.reason ?? "caterva rates is not available here."}</p>
        </EmptyState>
      </Screen>
    );
  }
  return <RatesWorkbench />;
}

function RatesWorkbench() {
  const caps = useCapabilities();
  const settings = useSettings();
  const reopened = useReopenedRun();
  const search = new URLSearchParams(useSearch());
  const wantsExample = search.get("example") === "puromycin" && !reopened;
  const [source, setSource] = useState<Source | null>(null);
  const [overrides, setOverrides] = useState<RatesMapping>({});
  const [form, setForm] = useState<FitForm>(EMPTY_FIT);
  const [literature, setLiterature] = useState(false);
  const run = useRun("rates", reopened);
  const query = useTablePreview(source?.text ?? null, source?.filename ?? null, overrides);
  const preview = source ? query.data : undefined;
  const mapping = preview?.mapping ?? overrides;
  const running = run.submitting || run.status === "queued" || run.status === "running";
  const set = <K extends keyof FitForm>(key: K, value: FitForm[K]) => setForm((f) => ({ ...f, [key]: value }));
  const err = (field: string) => fieldError(run.requestError, field);

  const open = (s: Source) => {
    setSource(s);
    setOverrides({});
    setForm((f) => ({ ...f, sigma: "", sigmaTouched: false }));
  };
  const openExample = () => open({ text: PUROMYCIN_CSV, filename: PUROMYCIN_FILENAME, origin: "example" });

  useEffect(() => {
    if (wantsExample && !source) openExample();
    // Opens once, from the address; later choices are the person's.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [wantsExample]);

  usePrefill(run.run, reopened, null, (request) => {
    const state = requestState(request);
    setSource(state.source);
    setOverrides(state.mapping);
    setForm(state.form);
    setLiterature(state.literature);
  }, () => {});
  useRunAddress("/rates", run.run, reopened);

  // The uncertainty a table offers first, until the person chooses.
  const options = preview?.sigma_options ?? null;
  useEffect(() => {
    if (!options) return;
    setForm((f) => (f.sigmaTouched && sigmaAllowed(f.sigma, options) === null ? f : { ...f, sigma: defaultSigma(options), sigmaTouched: false }));
  }, [options]);

  const ready = Boolean(source && preview?.ready && form.sigma !== "");
  const reason = !source
    ? "Add your measurements first."
    : !preview
      ? "Reading your table."
      : !preview.ready
        ? `The table cannot be fitted yet: ${preview.refusal ?? "see the problems listed"}`
        : form.sigma === ""
          ? "Choose where the uncertainty of each rate comes from."
          : undefined;
  const previewError = query.isError
    ? query.error instanceof ApiRequestError
      ? query.error.error.message
      : describeError(query.error).message
    : null;
  const submit = () => {
    if (!source || !ready) return;
    void run.submit(ratesRequest(source, preview, form, literature));
  };
  const offline = Boolean(settings.data?.offline);
  const summary = useMemo(() => preview?.summary ?? null, [preview]);

  return (
    <Screen
      title="Rates"
      purpose="Fit the initial rates you measured, and take away a figure, a table of constants with intervals, and a methods paragraph."
    >
      <div className="r-flow">
        <Section title="1. Your measurements" aside={summary ? <span className="font-mono">{summary.rows_used} measurements</span> : undefined}>
          <DataStep
            source={source}
            preview={preview}
            pending={Boolean(source) && query.isFetching}
            error={previewError}
            mapping={mapping}
            onMapping={setOverrides}
            onSource={open}
            onExample={openExample}
          />
        </Section>

        <Section title="2. What to fit">
          {source && preview?.ready ? (
            <RunForm
              id="rates.submit"
              label="Fit my data"
              hint="Fit the table above"
              onSubmit={submit}
              running={running}
              onCancel={() => void run.cancel()}
              disabled={!ready}
              disabledReason={reason}
            >
              <FitStep
                form={form}
                set={set}
                preview={preview}
                caps={caps.data}
                offline={offline}
                literature={literature}
                onLiterature={setLiterature}
                errorFor={err}
              />
            </RunForm>
          ) : (
            <p className="r-wait">{source ? "Fix what the table above says first; the choices appear here once it can be fitted." : "The choices appear here once there is a table."}</p>
          )}
        </Section>

        <Section title="3. Result">
          <KineticsRun<"rates">
            state={run}
            path="/rates"
            exports={() => [
              { label: "Report", artifact: "report.md", description: "the engine's report, as caterva rates prints it" },
              { label: "Methods", artifact: "methods.txt", description: "a methods paragraph generated from this run" },
              { label: "JSON", artifact: "result.json", description: "the result exactly as the studio API sent it" },
            ]}
            onRetry={submit}
            idle={
              <EmptyState title="Your figure, your constants, your methods paragraph">
                <p>
                  Open an example, or drop your own table above. The fit tests which rate law your data support, gives every constant a profile interval,
                  and says where the data cannot decide. Nothing is filled in for you: an uncertainty is never invented, and a constant the data do not
                  bound is shown as unbounded, not as a number.
                </p>
              </EmptyState>
            }
          >
            {(result, record) => <RatesResultView result={result} run={record} />}
          </KineticsRun>
        </Section>
      </div>
    </Screen>
  );
}
