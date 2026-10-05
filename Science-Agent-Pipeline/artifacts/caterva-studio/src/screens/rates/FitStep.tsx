/**
 * Step two of Rates: what to fit.
 *
 * Four choices, each with the one sentence that says what it changes:
 *
 * - The rate law. By default the engine fits every law that applies to the
 *   table (three without an inhibitor, four with one) and tests which the
 *   data support; any one of the seven can be forced. A law that does not
 *   apply to the table (an inhibition law for rates with no inhibitor) is
 *   listed and disabled with its reason, because the engine refuses it.
 * - How uncertain each rate is. The fit never invents an error bar, so one
 *   of three honest sources is chosen: the table's own sigma column, the
 *   scatter of replicates, or the scatter about the fitted curve. Which are
 *   possible depends on the table, and what each costs is said in a
 *   sentence under the choice.
 * - Groups are compared when the table has a group column; nothing to choose
 *   here but the page says so, so a comparison is never a surprise.
 * - The literature, optionally: an enzyme (the shared finder), an organism
 *   and the names to look the constants up under. Offered only when the
 *   literature layer and the network are available, and said so when not.
 *
 * Optional extras (an enzyme concentration for kcat, the confidence level)
 * sit behind a disclosure so the defaults are not a form to fill in.
 */
import { EnzymeFinder } from "@/components/enzyme/EnzymeFinder";
import { IsoformChooser } from "@/components/enzyme/IsoformChooser";
import { Disclosure } from "@/components/forms/Disclosure";
import { Field, NumberInput, Select, TextInput } from "@/components/forms/Field";
import { Segmented } from "@/components/forms/Segmented";
import type { Capabilities, RatesPreview } from "@/api/types";

import { type FitForm, RATE_LAWS, type SigmaChoice, sigmaAllowed } from "./model";

const SIGMA_OPTIONS: { value: Exclude<SigmaChoice, "">; label: string; hint: string }[] = [
  {
    value: "column",
    label: "From the sigma column in my table",
    hint: "Your own error bars are taken as known, so every interval and test is expressed in them: if they are too small, the intervals are too narrow.",
  },
  {
    value: "replicates",
    label: "From the scatter of my replicates",
    hint: "The spread between repeats of one condition sets the error bar. It does not assume the rate law is right, and it lets the lack-of-fit test ask whether the law is.",
  },
  {
    value: "residuals",
    label: "From the scatter about the fitted curve",
    hint: "The distance of your points from the fitted curve sets the error bar, as R's nls does. It assumes the law is right: a law of the wrong shape widens every interval instead of failing a test.",
  },
];

export function FitStep({
  form,
  set,
  preview,
  caps,
  offline,
  literature,
  onLiterature,
  errorFor,
}: {
  form: FitForm;
  set: <K extends keyof FitForm>(key: K, value: FitForm[K]) => void;
  preview: RatesPreview | undefined;
  caps: Capabilities | undefined;
  offline: boolean;
  literature: boolean;
  onLiterature: (on: boolean) => void;
  errorFor: (field: string) => string | null;
}) {
  const options = preview?.sigma_options ?? null;
  const hasInhibitor = Boolean(preview?.summary?.inhibitor);
  const groups = preview?.summary?.groups ?? [];
  const literatureOff = !caps
    ? "Asking the server what it can reach."
    : offline
      ? "Offline mode is on, so nothing contacts BRENDA."
      : !caps.literature.available
        ? (caps.literature.reason ?? "The literature layer is not installed here.")
        : caps.network.checked && !caps.network.reachable
          ? "The network was not reachable when it was last checked."
          : null;
  const rateConvertible = preview?.summary?.rate_kind === "concentration per time";
  return (
    <div className="r-fit">
      <fieldset className="k-group">
        <legend className="k-group-title">Rate law</legend>
        <div className="k-group-body">
          <Field label="Which law" hint={form.model === "auto" ? `Fits every law that applies to this table (${hasInhibitor ? "the four inhibition laws" : "Michaelis-Menten, substrate inhibition and Hill"}) and tests which the data support. A law the data cannot separate from the others is reported with them, not chosen for you.` : (RATE_LAWS.find((l) => l.name === form.model)?.equation ?? "")} error={errorFor("model")}>
            <Select value={form.model} onChange={(e) => set("model", e.target.value)}>
              <option value="auto">Test the laws, and say which the data support</option>
              {RATE_LAWS.map((l) => {
                const wrong = l.inhibitor !== hasInhibitor && Boolean(preview?.summary);
                return (
                  <option key={l.name} value={l.name} disabled={wrong}>
                    Only {l.title}
                    {wrong ? (l.inhibitor ? " (needs an inhibitor column)" : " (the table has an inhibitor)") : ""}
                  </option>
                );
              })}
            </Select>
          </Field>
        </div>
      </fieldset>

      <fieldset className="k-group">
        <legend className="k-group-title">How uncertain is each rate</legend>
        <div className="k-group-body" role="radiogroup" aria-label="Where the uncertainty of each rate comes from">
          {SIGMA_OPTIONS.map((o) => {
            const blocked = sigmaAllowed(o.value, options);
            const count =
              o.value === "replicates" && options?.replicates
                ? ` (${options.replicate_sets} replicate sets, ${options.replicate_dof} degrees of freedom)`
                : "";
            return (
              <label key={o.value} className="r-radio" data-disabled={blocked ? "true" : undefined}>
                <input
                  type="radio"
                  name="sigma-source"
                  value={o.value}
                  checked={form.sigma === o.value}
                  disabled={Boolean(blocked)}
                  onChange={() => {
                    set("sigma", o.value);
                    set("sigmaTouched", true);
                  }}
                />
                <span>
                  <span className="r-radio-label">
                    {o.label}
                    {count}
                  </span>
                  {blocked ? <span className="field-hint r-radio-why">Not available: {blocked}.</span> : form.sigma === o.value ? <span className="field-hint r-radio-why">{o.hint}</span> : null}
                </span>
              </label>
            );
          })}
          {errorFor("sigma_from") ? (
            <p className="field-error" role="alert">
              {errorFor("sigma_from")}
            </p>
          ) : null}
          {form.sigma === "replicates" ? (
            <Field label="How the spread is pooled" hint={form.errorModel === "constant" ? "One standard deviation for every rate." : "One coefficient of variation: the error bar grows with the rate, as it does in assays whose noise follows their signal."}>
              <Segmented
                label="Error model"
                value={form.errorModel}
                options={[
                  { value: "constant", label: "Constant spread" },
                  { value: "proportional", label: "Grows with the rate" },
                ]}
                onChange={(v) => set("errorModel", v)}
              />
            </Field>
          ) : null}
        </div>
      </fieldset>

      {groups.length >= 2 ? (
        <p className="r-groups-note">
          Your table has groups ({groups.map((g) => `${g.label}, ${g.rows} rows`).join("; ")}). Each is fitted on its own, and the engine tests which constants
          differ between them. To fit them as one, set the group column to Not used above.
        </p>
      ) : null}

      <fieldset className="k-group">
        <legend className="k-group-title">Against the literature</legend>
        <div className="k-group-body">
          {literatureOff ? (
            <p className="field-hint">Comparing with BRENDA is not available now: {literatureOff} The fit does not need it.</p>
          ) : (
            <label className="r-toggle">
              <input type="checkbox" checked={literature} onChange={(e) => onLiterature(e.target.checked)} />
              <span>Compare my Km (and Ki) with the values BRENDA cites</span>
            </label>
          )}
          {literature && !literatureOff ? (
            <>
              <EnzymeFinder
                optional
                value={form.ec}
                onChange={(ec) => {
                  set("ec", ec);
                  if (ec !== form.ec) set("isoform", "");
                }}
                organism={form.organism}
                hint="A name, an abbreviation or an EC number. The engine is sent the EC number you choose."
                error={errorFor("ec")}
              />
              <Field label="Organism" hint="Required: a Km belongs to one organism's enzyme, and another's is never substituted." error={errorFor("organism")}>
                <TextInput value={form.organism} onChange={(e) => set("organism", e.target.value)} />
              </Field>
              <Field label="Substrate's name" hint="As BRENDA would name it, to look its Km up." error={errorFor("substrate")}>
                <TextInput value={form.substrate} onChange={(e) => set("substrate", e.target.value)} />
              </Field>
              {hasInhibitor ? (
                <Field label="Inhibitor's name" optional error={errorFor("inhibitor")}>
                  <TextInput value={form.inhibitor} onChange={(e) => set("inhibitor", e.target.value)} />
                </Field>
              ) : null}
              <Field label="Isoform" optional hint="So a row measured on another isoform is not compared as though it were this one." error={errorFor("isoform")}>
                <TextInput value={form.isoform} onChange={(e) => set("isoform", e.target.value)} />
              </Field>
              <IsoformChooser ec={form.ec} organism={form.organism} value={form.isoform} onChange={(v) => set("isoform", v)} />
              {!preview?.summary?.substrate_convertible ? (
                <p className="field-hint">
                  Your substrate unit ({preview?.summary?.substrate_unit ?? "none"}) is not a molar unit, so a Km cannot be held against a cited one; the engine will
                  say so and still fit.
                </p>
              ) : null}
            </>
          ) : null}
        </div>
      </fieldset>

      <Disclosure title="Turnover number and confidence level" aside={form.enzymeConc.trim() ? "kcat on" : undefined}>
        <div className="k-group-body">
          <Field
            label="Enzyme concentration"
            optional
            hint={rateConvertible ? "Give the molar concentration of active enzyme in the assay to get kcat = Vmax / [E]. It is taken as exact." : `kcat needs the rate in a molar unit per time; yours is ${preview?.summary?.rate_unit ?? "not read yet"}.`}
            error={errorFor("enzyme_concentration")}
          >
            <span className="r-unit-row">
              <NumberInput value={form.enzymeConc} onChange={(e) => set("enzymeConc", e.target.value)} disabled={!rateConvertible} />
              <Select aria-label="Enzyme concentration unit" value={form.enzymeUnit} disabled={!rateConvertible} onChange={(e) => set("enzymeUnit", e.target.value)}>
                {["M", "mM", "uM", "nM", "pM"].map((u) => (
                  <option key={u} value={u}>
                    {u.replace("u", "µ")}
                  </option>
                ))}
              </Select>
            </span>
          </Field>
          <div className="k-row2">
            <Field label="Confidence level" optional hint="Empty is 0.95." error={errorFor("level")}>
              <NumberInput value={form.level} onChange={(e) => set("level", e.target.value)} placeholder="0.95" />
            </Field>
            <Field label="Ruled out below p of" optional hint="A convention; every p is shown. Empty is 0.05." error={errorFor("significance")}>
              <NumberInput value={form.significance} onChange={(e) => set("significance", e.target.value)} placeholder="0.05" />
            </Field>
          </div>
        </div>
      </Disclosure>
    </div>
  );
}
