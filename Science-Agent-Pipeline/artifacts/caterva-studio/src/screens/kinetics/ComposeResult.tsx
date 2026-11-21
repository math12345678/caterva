/**
 * A `caterva compose` result, in the order a reader decides whether to
 * trust it: a field that contradicts the description, as a warning, first;
 * the verdict (what the model can answer, and the worst thing wrong with
 * it); how many constants are measured, and what Caterva chose for a field
 * left blank with the alternatives one click away (ADR 0182); then where
 * every number came from, then the claims
 * behind those numbers with the action that re-checks them (Recheck.tsx),
 * then what the model does (time course, influence, steady states,
 * sweeps), then each analysis that was asked for under its own heading
 * with its chart, then the report the terminal prints.
 *
 * Every number drawn as a value is a SourcedValue from the server and goes
 * through <Value>, so it wears its provenance mark and its citation or
 * reason is one click away. Numbers the library computed inside a section
 * (a steady state, a sensitivity) are labelled computed where they are
 * drawn. The library's own sentences (the verdict, the concerns, each
 * section's text, a placeholder's reason) are shown as the library wrote
 * them: a paraphrase of a caveat is a second, weaker caveat.
 */
import { AlertTriangle, ArrowRight, RotateCw } from "lucide-react";
import { useState } from "react";

import { choicesOf, mismatchOf, rerunPatch, rowsLine, type Mismatch, type RerunPatch, type SearchChoice } from "@/api/choices";
import type { ComposeResult as Result, Concern, FixedPointView, RunRecord, SourcedValue, StabilityView, StructuredSection } from "@/api/types";
import { TimeCourseChart } from "@/components/charts/TimeCourseChart";
import { NameRefusalChoices } from "@/components/enzyme/NameRefusal";
import { Disclosure } from "@/components/forms/Disclosure";
import { Citation } from "@/components/provenance/Citation";
import { countKinds, ProvenanceLegend } from "@/components/provenance/ProvenanceLegend";
import { ProvenanceMark } from "@/components/provenance/ProvenanceMark";
import { Value } from "@/components/provenance/Value";
import { MarkdownReport } from "@/components/report/Report";
import { Section } from "@/components/screen/Screen";
import { NetworkState, RefusalState } from "@/components/states/States";
import { networkFailureOf, plural, PLACEHOLDER_SHARED, plain, placeholderRowReason, readPlaceholder, withoutUrls } from "@/lib/copy";
import { formatNumber } from "@/lib/format";

import type { ExportChoice } from "./kit";
import { ClaimsSection } from "./Recheck";
import { constantName, halfSaturationOf, ResultMap, startsAreDefaults } from "./ResultMap";
import { SectionFigure, SweepFigure } from "./sections";

/** compose.verdict: broken names a defect; structural rests on placeholders. */
const VERDICT_TONE: Record<string, string | undefined> = {
  broken: "danger",
  structural: "caution",
};

const EXPORT_LABEL: Record<string, string> = {
  methods: "Methods",
  csv: "CSV",
  sbml: "SBML",
  antimony: "Antimony",
};

/** The exports a compose run wrote, in the order a methods section needs them, then the result as JSON. */
export function composeExports(result: Result, run: RunRecord): ExportChoice[] {
  const out: ExportChoice[] = [];
  for (const format of ["methods", "csv", "sbml", "antimony"]) {
    const e = result.exports[format];
    if (!e?.available || !e.artifact) continue;
    const recorded = run.artifacts.find((a) => a.name === e.artifact);
    if (!recorded) continue;
    out.push({ label: EXPORT_LABEL[format], artifact: e.artifact, description: recorded.description });
  }
  out.push({ label: "JSON", artifact: "result.json", description: "the result exactly as the studio API sent it" });
  return out;
}

function ConcernLine({ c }: { c: Concern }) {
  return (
    <>
      <span className="chip chip-mono">{c.source}</span> <span>{plain(c.detail)}</span>
      {c.remedy ? <span className="k-remedy">{plain(c.remedy)}</span> : null}
    </>
  );
}

/** The refused sections a partly refused compose run names, linked to where each says why. */
function PartRefusal({ result, run, onChooseEnzyme }: { result: Result; run: RunRecord; onChooseEnzyme?: (ec: string) => void }) {
  const refused = result.sections.filter((s) => s.status !== "answered");
  const outcome = run.outcome;
  if (outcome?.meaning === "network") {
    return <NetworkState failure={outcome.network ?? networkFailureOf(outcome.reason)} raw={outcome.reason ?? undefined} again="run it again" inset={false} />;
  }
  if (!outcome || outcome.meaning !== "refused") return null;
  return (
    <div className="k-part-refusal" role="note">
      <span className="state-kicker">Refused in part</span>
      <p className="k-part-refusal-reason">{plain(withoutUrls(outcome.reason ?? ""))}</p>
      {outcome.name_refusal ? <NameRefusalChoices refusal={outcome.name_refusal} onChoose={onChooseEnzyme} /> : null}
      {refused.length ? (
        <ul className="k-anchors">
          {refused.map((s) => (
            <li key={s.key}>
              <a href={`#k-section-${s.key}`}>
                {s.title}
                <ArrowRight size={12} aria-hidden="true" />
              </a>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

export function Verdict({ result, run, onChooseEnzyme }: { result: Result; run: RunRecord; onChooseEnzyme?: (ec: string) => void }) {
  const v = result.verdict;
  if (!v) {
    return (
      <section className="k-verdict" aria-label="Verdict">
        <p className="k-eyebrow">Verdict</p>
        <p className="k-verdict-licence">The command gave no verdict for this request (its stability analysis or simulation was switched off).</p>
        <PartRefusal result={result} run={run} onChooseEnzyme={onChooseEnzyme} />
      </section>
    );
  }
  const isozymes = v.concerns.find((c) => c.source === "isozymes");
  const qualified = v.concerns.filter((c) => c.qualifier);
  const [worst, ...allRest] = v.concerns;
  const rest = allRest.filter((c) => c !== isozymes);
  const checked = Object.entries(v.consulted);
  const unexamined = Object.entries(v.unavailable);
  return (
    <section className="k-verdict" aria-labelledby="k-verdict-word">
      <div className="k-verdict-head">
        <p className="k-eyebrow">Verdict</p>
        <h2 className="k-verdict-word" id="k-verdict-word" data-tone={VERDICT_TONE[v.verdict]}>
          {v.verdict}
        </h2>
      </div>
      <p className="k-verdict-licence">
        <span className="k-label-inline">What it supports</span> {plain(v.licence)}
      </p>
      {qualified.map((c) => (
        <p className="k-verdict-qualified" key={`${c.source}-q`}>
          <span className="k-label-inline">Qualified</span> {plain(c.qualifier ?? "")}.
        </p>
      ))}
      {isozymes && isozymes !== worst ? (
        <div className="k-worst" data-severity={isozymes.severity} data-source="isozymes">
          <p className="k-eyebrow">Which isozyme</p>
          <p className="k-worst-detail">
            <span>{plain(isozymes.detail)}</span>
            {isozymes.remedy ? <span className="k-remedy">{plain(isozymes.remedy)}</span> : null}
          </p>
        </div>
      ) : null}
      {worst ? (
        <div className="k-worst" data-severity={worst.severity}>
          <p className="k-eyebrow">The worst thing wrong with it</p>
          <p className="k-worst-detail">
            <ConcernLine c={worst} />
          </p>
        </div>
      ) : null}
      {v.behaviour ? (
        <p className="k-verdict-behaviour">
          <span className="k-label-inline">What it does</span> {plain(v.behaviour)}
        </p>
      ) : null}
      {v.next_step && v.next_step !== worst?.remedy ? (
        <p className="k-verdict-next">
          <span className="k-label-inline">Do this next</span> {plain(v.next_step)}
        </p>
      ) : null}
      <PartRefusal result={result} run={run} onChooseEnzyme={onChooseEnzyme} />
      {rest.length || checked.length || unexamined.length ? (
        <div className="k-verdict-more">
          {rest.length ? (
            <Disclosure title="Other concerns, worst first" aside={<span className="font-mono">{rest.length}</span>}>
              <ul className="k-concerns">
                {rest.map((c) => (
                  <li key={`${c.source}-${c.detail}`}>
                    <ConcernLine c={c} />
                  </li>
                ))}
              </ul>
            </Disclosure>
          ) : null}
          {checked.length || unexamined.length ? (
            <Disclosure
              title="What the verdict consulted"
              aside={
                <span className="font-mono">
                  {checked.length} checked{unexamined.length ? `, ${unexamined.length} not run` : ""}
                </span>
              }
            >
              <dl className="k-consulted">
                {checked.map(([k, why]) => (
                  <div key={k}>
                    <dt className="font-mono">{k}</dt>
                    <dd>{plain(why)}</dd>
                  </div>
                ))}
                {unexamined.map(([k, why]) => (
                  <div key={k} data-state="unexamined">
                    <dt className="font-mono">{k}</dt>
                    <dd>{plain(why)}</dd>
                  </div>
                ))}
              </dl>
            </Disclosure>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

/** A long sentence of the library's, three lines tall until asked for whole. */
function Clamp({ children }: { children: string }) {
  const [open, setOpen] = useState(false);
  const long = children.length > 220;
  return (
    <span className="k-clamp" data-open={open || !long ? "true" : undefined}>
      <span className="k-clamp-text">{children}</span>
      {long ? (
        <button type="button" className="k-clamp-toggle" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
          {open ? "show less" : "show all"}
        </button>
      ) : null}
    </span>
  );
}

function Conditions({ v }: { v: SourcedValue }) {
  const c = v.provenance.conditions;
  if (!c) return null;
  const parts: string[] = [];
  if (c.ph !== null) parts.push(`pH ${c.ph}`);
  if (c.temperature_c !== null) parts.push(`${c.temperature_c} °C`);
  if (c.buffer) parts.push(c.buffer);
  const missing = c.unreported.length ? `not reported: ${c.unreported.join(", ")}` : null;
  if (!parts.length && !missing) return null;
  return (
    <span className="k-conditions">
      {parts.length ? <span className="font-mono">{parts.join(", ")}</span> : null}
      {parts.length && missing ? " · " : null}
      {missing ? <span className="text-caution">{missing}</span> : null}
    </span>
  );
}

/**
 * Where one number came from, inline: the facts the provenance detail carries, laid out for a table row.
 *
 * A measured row leads with what a reader checks first, in this order: the organism, the compound the row was
 * measured for (`compound`, when the ledger can say it: "substrate D-glucose", "inhibitor gossypol"), then the
 * citation ("BRENDA ref 641068"), then the assay conditions. The value and its unit stand in the column before.
 */
export function Origin({ v, compound }: { v: SourcedValue; compound?: string | null }) {
  const p = v.provenance;
  switch (p.kind) {
    case "measured":
      return (
        <div className="k-origin">
          <div className="k-origin-line">
            {p.organism ? (
              <span>
                <em>{p.organism}</em>
                {p.cross_species ? <span className="text-caution"> (another organism than the model's)</span> : null}
              </span>
            ) : null}
            {compound ? <span className="k-origin-compound">{compound}</span> : null}
            {p.citation ? <Citation citation={p.citation} /> : null}
            <Conditions v={v} />
          </div>
          {p.commentary ? <blockquote className="k-row-says">{p.commentary}</blockquote> : null}
          {p.scope?.length ? (
            <ul className="k-scope" aria-label="Where this could be the wrong number for this model">
              {p.scope.map((s) => (
                <li key={s}>{plain(s)}</li>
              ))}
            </ul>
          ) : null}
          {p.spread ? (
            <p className="k-spread">
              <Clamp>{plain(p.spread.sentence)}</Clamp>
            </p>
          ) : null}
          {p.chosen_because ? (
            <p className="k-spread">
              <span className="muted">Chosen because </span>
              {plain(p.chosen_because)}
            </p>
          ) : null}
        </div>
      );
    case "placeholder": {
      const reading = p.reason ? readPlaceholder(p.reason) : null;
      return (
        <div className="k-origin">
          <p className="k-origin-reason" title={reading?.identifier}>
            {reading ? placeholderRowReason(reading) : <Clamp>{plain(p.reason ?? "no reason was recorded")}</Clamp>}
          </p>
          {p.table && !reading ? (
            <p className="k-spread muted">
              The measurement that would replace it is in BRENDA&apos;s <span className="font-mono">{p.table}</span> table.
            </p>
          ) : null}
        </div>
      );
    }
    case "computed":
      return (
        <div className="k-origin">
          <p className="k-origin-reason">{plain(p.method ?? "computed by Caterva")}</p>
          {p.inputs?.length ? <p className="k-spread muted font-mono">from {p.inputs.join(", ")}</p> : null}
        </div>
      );
    case "fitted":
      return <p className="k-origin-reason">{p.fit?.method ?? "fitted"}</p>;
    case "chosen":
      return (
        <p className="k-origin-reason">
          {p.by === "user" ? "Chosen by you in this request" : "A stated default of the command"}
          {p.reason ? <span className="muted">: {plain(p.reason)}</span> : null}
        </p>
      );
  }
}

function LedgerRows({ values, name }: { values: { key: string; name: string; v: SourcedValue; compound?: string | null }[]; name: string }) {
  return (
    <div className="table-wrap">
      <table className="table k-ledger">
        <thead>
          <tr>
            <th scope="col">{name}</th>
            <th scope="col" data-align="end">
              Value
            </th>
            <th scope="col">Where it came from</th>
          </tr>
        </thead>
        <tbody>
          {values.map(({ key, name: label, v, compound }) => (
            <tr key={key} data-kind={v.provenance.kind}>
              <th scope="row" className="k-ledger-name">
                <span className="font-mono">{label}</span>
                {v.label && v.label !== label ? <span className="k-ledger-sub">{constantName(v)}</span> : null}
                {halfSaturationOf(v) ? (
                  <span className="k-ledger-sub" data-testid="ledger-k05">
                    a K0.5{halfSaturationOf(v)?.hill != null ? ` (Hill coefficient ${halfSaturationOf(v)?.hill})` : ""}, not a Km
                  </span>
                ) : null}
              </th>
              <td data-align="end" className="k-ledger-value">
                <Value v={v} />
              </td>
              <td>
                <Origin v={v} compound={compound} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/**
 * The compound a measured constant was measured for, when the ledger can say so without guessing: a Km or kcat
 * of a one-enzyme model was looked up for the search's substrate, and its Ki for the one inhibitor the search
 * named. The engine takes a row only for exactly that compound (ADR 0182), so this repeats what it searched for;
 * a model with two Km constants (two enzymes) gets nothing, because which substrate is whose is not in the row.
 *
 * ONLY WHEN NO OTHER COMPOUND COULD HAVE BEEN SEARCHED. The engine looks a constant up under the compound
 * named for its own port first (`--compound S=D-fructose`, caterva/compose/pipeline.py `compound_for`), and
 * only then under the substrate or "@inhibitor"; a product's constant goes under "@product". None of that is
 * in the row. So once the search used any compound but "@inhibitor", a lone Km may have been measured for a
 * compound other than `search.substrate`, and a lone Ki for another than "@inhibitor": the ledger names
 * nothing rather than print a compound beside a number that was not measured for it.
 */
export function compoundOf(v: SourcedValue, result: Result): string | null {
  if (v.provenance.kind !== "measured" || !v.label) return null;
  const same = result.model.parameters.filter((p) => p.label === v.label).length;
  if (same !== 1) return null;
  const s = result.search;
  const searched = Object.keys(s.compounds ?? {});
  if (searched.some((port) => port !== "@inhibitor")) return null;
  if ((v.label === "Km" || v.label === "kcat") && s.substrate) return `substrate ${s.substrate}`;
  const inhibitor = s.compounds?.["@inhibitor"];
  if (v.label === "Ki" && inhibitor) return `inhibitor ${inhibitor}`;
  return null;
}

/** How many of the model's constants are measured, and from where: the page's one-glance answer to "is this real data?". */
export function measuredTally(result: Result): { measured: number; placeholders: number; total: number; brenda: boolean; crossSpecies: number } {
  const constants = result.model.parameters;
  const measured = constants.filter((p) => p.provenance.kind === "measured");
  return {
    measured: measured.length,
    placeholders: constants.filter((p) => p.provenance.kind === "placeholder").length,
    total: constants.length,
    brenda: measured.length > 0 && measured.every((p) => (p.provenance.citation?.registry ?? "").toUpperCase() === "BRENDA"),
    crossSpecies: measured.filter((p) => p.provenance.cross_species).length,
  };
}

/**
 * "3 of 3 constants measured from BRENDA". Placed at the top, beside the search, so whether the model rests on
 * the literature or on placeholders is the first thing read and not something to count down a table for. The
 * tone is the provenance mark's: signal when every constant is measured, caution when any is a placeholder.
 */
export function MeasuredBadge({ result }: { result: Result }) {
  const t = measuredTally(result);
  if (t.total === 0) return null;
  const source = t.brenda ? " from BRENDA" : "";
  const tone = t.placeholders === 0 && t.measured === t.total ? "signal" : t.placeholders > 0 ? "caution" : undefined;
  return (
    <p className="k-measured" data-testid="measured-badge" data-tone={tone}>
      <span className="k-measured-count">
        {t.measured} of {plural(t.total, "constant")} measured{source}
      </span>
      {/* "Measured" alone would read as measured in the model's organism; a row from another one says so in the
          ledger, and the count here says so before the ledger is reached. */}
      {t.crossSpecies ? <span className="text-caution">{` (${t.crossSpecies} in another organism than the model's)`}</span> : null}
      {t.placeholders ? (
        <>
          {" · "}
          <a href="#k-numbers">
            {plural(t.placeholders, "placeholder")}, each saying why and what would replace it
          </a>
        </>
      ) : null}
    </p>
  );
}

export function NumbersLedger({ result }: { result: Result }) {
  const { parameters, species, concentration_unit } = result.model;
  const all = [...parameters, ...species.map((s) => s.initial)];
  const counts = countKinds(all);
  const sharedPlaceholder = all.some((v) => v.provenance.kind === "placeholder" && v.provenance.reason && readPlaceholder(v.provenance.reason));
  return (
    <Section
      title="Where the numbers come from"
      id="k-numbers"
      aside={<ProvenanceLegend counts={counts} only={Object.keys(counts) as (keyof typeof counts)[]} />}
    >
      <p className="k-lede">
        Activate a number for its paper, its assay conditions and the source row&apos;s own words, or for the reason it is
        a placeholder. Concentrations are in <span className="font-mono">{concentration_unit}</span>.
      </p>
      {sharedPlaceholder ? (
        <p className="k-shared-note">
          <ProvenanceMark provenance={{ kind: "placeholder" }} decorative /> {PLACEHOLDER_SHARED}
        </p>
      ) : null}
      <LedgerRows
        name="Constant"
        values={parameters.map((p) => ({ key: p.id ?? p.label ?? "", name: p.id ?? p.label ?? "", v: p, compound: compoundOf(p, result) }))}
      />
      {species.length ? (
        <Disclosure title="Starting amounts" aside={<span className="font-mono">{species.length}</span>}>
          <LedgerRows name="Species" values={species.map((s) => ({ key: s.id, name: s.id, v: s.initial }))} />
        </Disclosure>
      ) : null}
    </Section>
  );
}

function Search({ result }: { result: Result }) {
  const s = result.search;
  if (!s.asked) return null;
  return (
    <div className="k-search" aria-label="The literature search">
      <p>
        <span className="k-label-inline">Searched</span>
        EC <span className="font-mono">{s.ec ?? s.subject}</span>
        {s.organism ? (
          <>
            {", "}
            <em>{s.organism}</em>
          </>
        ) : null}
        {s.substrate ? `, substrate ${s.substrate}` : ""}
        {s.isoform ? `, isoform ${s.isoform}` : ""}
        {Object.entries(s.compounds).map(([port, name]) => `, ${port.replace(/^@/, "")} ${name}`)}
        {". "}
        <span className="font-mono">{s.measured}</span> measured, <span className="font-mono">{s.placeholders}</span> still
        placeholders{s.refused ? "; the search could not run" : ""}.
      </p>
      {s.note ? <p className="muted">{plain(s.note)}</p> : null}
      {Object.keys(s.unused_compounds ?? {}).length ? (
        <p className="muted" data-testid="unused-compounds">
          Not used: {Object.entries(s.unused_compounds).map(([port, name]) => `${port.replace(/^@/, "")} ${name}`).join(", ")}.
          This mechanism has no step that compound could belong to, so no constant was looked up for it. To search for an
          inhibitor&apos;s Ki, ask for a mechanism with an inhibition step, such as competitive inhibition, and name the inhibitor
          again.
        </p>
      ) : null}
    </div>
  );
}

/** The engine writes a choice's why as a clause ("of the 12 substrates BRENDA lists ..."); shown alone, it is a sentence. */
function sentence(clause: string): string {
  const t = clause.trim();
  if (!t) return t;
  const head = t[0].toUpperCase() + t.slice(1);
  return /[.!?]$/.test(head) ? head : `${head}.`;
}

const ROLE_WORD: Record<SearchChoice["role"], string> = {
  substrate: "substrate",
  inhibitor: "inhibitor",
  organism: "organism",
  enzyme: "enzyme",
};

/**
 * One automatic choice (ADR 0182): "Caterva chose the substrate D-glucose", the engine's own why, and every
 * alternative it listed as a chip with BRENDA's row counts. A chip runs compose again with that value set (and
 * the choices made before this one kept: `rerunPatch`), so switching is one click, not a trip back to the form.
 * Without `onRerun` (a screen that cannot run compose) the alternatives are listed, not offered.
 */
function ChoicePanel({
  choice,
  index,
  choices,
  onRerun,
}: {
  choice: SearchChoice;
  index: number;
  choices: readonly SearchChoice[];
  onRerun?: (patch: RerunPatch) => void;
}) {
  const role = ROLE_WORD[choice.role];
  const kept = choices.slice(0, index);
  const listed = choice.alternatives.filter((a) => a.name !== choice.chosen);
  const unlisted = choice.considered - listed.length - 1;
  return (
    <section className="k-choice" aria-label={`Caterva chose the ${role}`} data-role={choice.role}>
      <p className="k-choice-head">
        <span className="k-eyebrow">Caterva chose the {role}</span>{" "}
        <span className={choice.role === "enzyme" ? "k-choice-value font-mono" : "k-choice-value"}>
          {choice.role === "organism" ? <em>{choice.chosen}</em> : choice.chosen}
        </span>
      </p>
      {choice.why ? <p className="k-choice-why">{sentence(plain(choice.why))}</p> : null}
      {listed.length ? (
        <div className="k-choice-alts">
          <p className="k-choice-alts-label muted">
            {onRerun ? `Run it with another ${role} instead:` : `Other ${role}s BRENDA has rows for:`}
          </p>
          <ul className="k-choice-chips">
            {listed.map((a) => {
              const rows = rowsLine(a.rows);
              const label = rows ? `${a.name} · ${rows}` : a.name;
              const keeping = kept.length ? `, keeping ${kept.map((k) => `the ${ROLE_WORD[k.role]} ${k.chosen}`).join(" and ")}` : "";
              return (
                <li key={a.name}>
                  {onRerun ? (
                    <button
                      type="button"
                      className="chip k-choice-chip"
                      title={`Runs compose again with the ${role} ${a.name}${keeping}`}
                      aria-label={`Run again with the ${role} ${a.name}${rows ? ` (${rows} rows in BRENDA)` : ""}`}
                      onClick={() => onRerun(rerunPatch(choices, index, a.name))}
                    >
                      <RotateCw size={11} aria-hidden="true" />
                      {label}
                    </button>
                  ) : (
                    <span className="chip">{label}</span>
                  )}
                </li>
              );
            })}
          </ul>
          {unlisted > 0 ? (
            <p className="muted k-choice-more">
              {plural(unlisted, "more option")} weighed and not listed; name one in the {role} field to use it.
            </p>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

/** Every automatic choice of the run, in the order the engine made them; nothing for a run with none (or an old run). */
export function Choices({ result, onRerun }: { result: Result; onRerun?: (patch: RerunPatch) => void }) {
  const choices = choicesOf(result);
  if (!choices.length) return null;
  return (
    <div className="k-choices" data-testid="choices">
      {choices.map((c, i) => (
        <ChoicePanel key={`${c.role}-${i}`} choice={c} index={i} choices={choices} onRerun={onRerun} />
      ))}
    </div>
  );
}

/**
 * A field the person set that contradicts the enzyme or organism the description names. The engine runs with
 * the field ("a flag wins over the description") and notes it; that note was a line among the notes at the
 * bottom of the page, which is how a run "about granzyme B" went out with the constants of tert-amyl alcohol
 * desaturase. Here it is a warning at the top, with the one-click run the description asked for.
 */
function MismatchWarnings({ result, onRerun }: { result: Result; onRerun?: (patch: RerunPatch) => void }) {
  const found = result.notes.map(mismatchOf).filter((m): m is Mismatch => m !== null);
  if (!found.length) return null;
  return (
    <>
      {found.map((m) => (
        <div className="k-mismatch" role="alert" key={m.note} data-field={m.field}>
          <p className="k-mismatch-text">
            <AlertTriangle size={14} aria-hidden="true" />
            <span>
              {m.field === "subject" ? (
                <>
                  Your description names <strong>{m.named}</strong> (EC <span className="font-mono">{m.readAs}</span>), but this run used
                  EC <span className="font-mono">{m.used}</span> from the enzyme field. Every constant below belongs to EC{" "}
                  <span className="font-mono">{m.used}</span>.
                </>
              ) : (
                <>
                  Your description names <strong>{m.named}</strong> (<em>{m.readAs}</em>), but this run used <em>{m.used}</em> from the
                  organism field.
                </>
              )}
            </span>
          </p>
          {onRerun ? (
            <button type="button" className="btn btn-sm" onClick={() => onRerun({ [m.field]: m.readAs })}>
              {m.field === "subject" ? `Use EC ${m.readAs} (${m.named}) instead` : `Use ${m.readAs} instead`}
            </button>
          ) : null}
        </div>
      ))}
    </>
  );
}

function TimeCourse({ result }: { result: Result }) {
  const t = result.trajectory;
  if (!t) return null;
  const broken = t.invariants.filter((i) => !i.held);
  const shapeOnly = startsAreDefaults(result);
  return (
    <Section title="Time course" id="k-time" aside={<ComputedNote />}>
      {shapeOnly ? (
        <p className="k-shape-only" role="note" data-testid="shape-only">
          <strong>Shape only.</strong> Starting amounts are not set, so the axes carry no numbers.
        </p>
      ) : null}
      <TimeCourseChart
        shapeOnly={shapeOnly}
        title={shapeOnly ? "The shape of every species over time" : "Every species over the simulated window"}
        caption={
          shapeOnly
            ? `${t.points} points. Simulated by Caterva from the constants above and stand-in starting amounts.`
            : `${t.points} points; the window is ${t.window_basis}. Simulated by Caterva from the values in the table above.`
        }
        times={t.times}
        series={t.columns}
        timeUnit="s"
        unit={result.model.concentration_unit}
      />
      {t.invariants.length ? (
        <p className={broken.length ? "k-invariants text-caution" : "k-invariants muted"}>
          {broken.length
            ? `${plural(broken.length, "conservation law")} did not hold over the run: ${broken.map((i) => i.law).join("; ")}`
            : `Every conservation law held over the run: ${t.invariants.map((i) => i.law).join("; ")}.`}
        </p>
      ) : null}
      {t.unmeasured.length ? (
        <p className="k-invariants muted">Drawn with placeholders standing in for: {t.unmeasured.join(", ")}.</p>
      ) : null}
    </Section>
  );
}

function ComputedNote() {
  return (
    <span className="k-computed-note">
      <ProvenanceMark provenance={{ kind: "computed" }} decorative /> computed by Caterva
    </span>
  );
}

function Influence({ result }: { result: Result }) {
  const s = result.sensitivity;
  if (!s || s.sensitivities.length === 0) return null;
  const max = Math.max(0, ...s.sensitivities.map((r) => (r.relative === null ? 0 : Math.abs(r.relative))));
  return (
    <Section title="Which constants matter" id="k-influence" aside={<ComputedNote />}>
      <p className="k-lede">
        Relative sensitivity of {s.quantity} to each constant: the fraction it moves for a fraction moved in the
        constant. Measure the top of this list first.
      </p>
      <div className="table-wrap">
        <table className="table k-influence">
          <thead>
            <tr>
              <th scope="col">Constant</th>
              <th scope="col" data-align="end">
                Relative sensitivity
              </th>
              <th scope="col" aria-hidden="true" />
            </tr>
          </thead>
          <tbody>
            {s.sensitivities.map((row) => (
              <tr key={row.parameter}>
                <th scope="row" className="font-mono k-ledger-name">
                  {row.parameter}
                </th>
                <td data-align="end" data-numeric="true">
                  {row.relative === null ? "not computed" : formatNumber(row.relative)}
                  {row.unresolvable ? <span className="muted"> below resolution</span> : row.negligible ? <span className="muted"> negligible</span> : null}
                </td>
                <td className="k-bar-cell" aria-hidden="true">
                  {row.relative !== null && max > 0 ? (
                    <span className="k-bar" data-sign={row.relative < 0 ? "neg" : "pos"} style={{ width: `${(Math.abs(row.relative) / max) * 100}%` }} />
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {Object.keys(s.skipped).length ? (
        <p className="k-invariants muted">
          Not ranked: {Object.entries(s.skipped).map(([k, why]) => `${k} (${why})`).join("; ")}
        </p>
      ) : null}
    </Section>
  );
}

/**
 * The steady states the search found. Only physical ones are states: a
 * solution with a negative amount solves the equations and cannot occur, so
 * it is not listed as a found state. The report prints the same split ("10
 * more at negative concentrations, which the equations have and the system
 * cannot reach"); this says it once, in the same words, and keeps those
 * solutions behind a disclosure with the engine's own labels.
 */
/** A steady-state amount. A physical point's amount that is below zero by less than the search's tolerance is rounding: shown as 0, with what was reported. */
function Amount({ value, tolerance, physical }: { value: number | null | undefined; tolerance: number; physical: boolean }) {
  if (value === null || value === undefined) return <>none</>;
  if (physical && value < 0 && value > -tolerance) {
    return (
      <span title={`Reported as ${formatNumber(value)}: rounds to zero within the search's tolerance (${formatNumber(tolerance)})`} data-rounded-to-zero="true">
        0
      </span>
    );
  }
  return <>{formatNumber(value)}</>;
}

function FixedPointTable({ result, points }: { result: Result; points: FixedPointView[] }) {
  const st = result.stability as StabilityView;
  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            <th scope="col">State</th>
            {st.species.map((sp) => (
              <th scope="col" key={sp} data-align="end" className="font-mono">
                {sp}
              </th>
            ))}
            <th scope="col" data-align="end">
              Slowest timescale (s)
            </th>
          </tr>
        </thead>
        <tbody>
          {points.map((fp, i) => (
            <tr key={i}>
              <th scope="row">
                <span className="k-state-class" data-stable={fp.stable ? "true" : "false"}>
                  {fp.classification}
                </span>
              </th>
              {st.species.map((sp) => (
                <td key={sp} data-align="end" data-numeric="true">
                  <Amount value={fp.state[sp]} tolerance={st.rounding_tolerance} physical={fp.physical} />
                </td>
              ))}
              <td data-align="end" data-numeric="true">
                {fp.slowest_timescale === null ? "none" : formatNumber(fp.slowest_timescale)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SteadyStates({ result }: { result: Result }) {
  const st = result.stability;
  if (!st) return null;
  const physical = st.fixed_points.filter((fp) => fp.physical);
  const unphysical = st.fixed_points.filter((fp) => !fp.physical);
  return (
    <Section
      title="Steady states"
      id="k-steady"
      aside={
        <span className="font-mono">
          {physical.length} found from {st.starts_tried} starts
          {st.count_caveat ? ": the count depends on where the starts fell" : ""}
        </span>
      }
    >
      {st.count_caveat ? (
        <p className="k-invariants" data-testid="count-caveat">
          A line of equilibria. {st.count_caveat}
        </p>
      ) : null}
      {physical.length ? (
        <FixedPointTable result={result} points={physical} />
      ) : (
        <p className="k-invariants">
          {st.fixed_points.length
            ? "No steady state with non-negative amounts was found."
            : `No steady state was found from ${st.starts_tried} starting points. That is not proof there is none: a root find reports where it converged.`}
        </p>
      )}
      {unphysical.length ? (
        <>
          <p className="k-nonphysical" data-testid="nonphysical-sentence">
            {unphysical.length} more {unphysical.length === 1 ? "solution is" : "solutions are"} at negative concentrations, which
            the equations have and the system cannot reach. {unphysical.length === 1 ? "It is" : "They are"} not listed as steady
            states.
          </p>
          <Disclosure title={`The ${unphysical.length} solutions at negative concentrations`} aside={<span className="font-mono">not states</span>}>
            <FixedPointTable result={result} points={unphysical} />
            <ul className="k-nonphysical-labels">
              {unphysical.map((fp, i) => (
                <li key={i} className="font-mono">
                  {fp.description ?? `${fp.classification}: negative concentrations, not physically reachable`}
                </li>
              ))}
            </ul>
          </Disclosure>
        </>
      ) : null}
      {physical.some((fp) => st.species.some((sp) => fp.state[sp] != null && (fp.state[sp] as number) < 0)) ? (
        <p className="k-invariants muted" data-testid="rounded-to-zero">
          An amount shown as 0 was reported as a negative number smaller than {formatNumber(st.rounding_tolerance)} in size: that is rounding within
          the search&apos;s tolerance, and hovering it shows the value reported.
        </p>
      ) : null}
      <p className="k-invariants muted">
        Amounts in {result.model.concentration_unit}, computed by Caterva
        <ProvenanceMark provenance={{ kind: "computed" }} />.
        {st.notes.length ? ` ${plain(st.notes.join(" "))}` : ""}
      </p>
      <Disclosure title="As the report prints it">
        <pre className="report-text">{plain(st.text)}</pre>
      </Disclosure>
    </Section>
  );
}

const STATUS_WORD: Record<StructuredSection["status"], string> = {
  answered: "answered",
  refused: "refused",
  partly_refused: "partly refused",
};

function AnalysisSection({ section }: { section: StructuredSection }) {
  return (
    <section className="k-analysis" id={`k-section-${section.key}`} aria-labelledby={`k-section-${section.key}-title`}>
      <div className="k-analysis-head">
        <h3 className="k-analysis-title" id={`k-section-${section.key}-title`}>
          {section.title}
        </h3>
        <span className="chip" data-tone={section.status === "answered" ? "signal" : undefined}>
          {STATUS_WORD[section.status]}
        </span>
      </div>
      {section.status === "refused" && section.refusals.length ? (
        <RefusalState title="Refused, and why" reason={section.refusals.join("\n\n")} />
      ) : null}
      {section.status === "partly_refused" ? (
        <p className="k-partly">
          <span className="state-kicker">Refused in part</span> {section.refusals.length} of the questions in this section
          {section.refusals.length === 1 ? " was" : " were"} refused; each says why, and what it would need, where it stands in the text below.
        </p>
      ) : null}
      <SectionFigure section={section} />
      {section.status !== "refused" || !section.refusals.length ? <MarkdownReport source={section.text} className="k-analysis-text" prose /> : null}
    </section>
  );
}

export function ComposeResultView({
  result,
  run,
  onChooseEnzyme,
  onRerun,
}: {
  result: Result;
  run: RunRecord;
  onChooseEnzyme?: (ec: string) => void;
  /** Run compose again with the same request and these fields set (a choice's chip, the mismatch warning's button). */
  onRerun?: (patch: RerunPatch) => void;
}) {
  const refusedExports = Object.entries(result.exports).filter(([, e]) => !e.available);
  return (
    <div className="k-results">
      <MismatchWarnings result={result} onRerun={onRerun} />
      <Verdict result={result} run={run} onChooseEnzyme={onChooseEnzyme} />
      <ResultMap result={result} />
      <p className="k-reading">
        Read <span className="font-mono">{result.query}</span> as {result.recognition.reading}{" "}
        <span className="muted font-mono">({result.recognition.rule})</span>
      </p>
      <MeasuredBadge result={result} />
      <Choices result={result} onRerun={onRerun} />
      <Search result={result} />
      <NumbersLedger result={result} />
      <ClaimsSection result={result} run={run} />
      <TimeCourse result={result} />
      <Influence result={result} />
      <SteadyStates result={result} />
      {result.sweeps.length ? (
        <Section title="Sweeps" id="k-sweeps" aside={<ComputedNote />}>
          {result.sweeps.map((s, i) => (
            <SweepFigure key={i} sweep={s} unit={result.model.concentration_unit} />
          ))}
        </Section>
      ) : null}
      {result.sections.length ? (
        <Section title="Analyses you asked for" id="k-sections" aside={<span className="font-mono">{result.sections.length}</span>}>
          {result.sections.map((s) => (
            <AnalysisSection key={s.key} section={s} />
          ))}
        </Section>
      ) : null}
      {result.notes.length ? (
        <Section title="Notes" id="k-notes">
          <ul className="k-notes">
            {result.notes.map((n) => (
              <li key={n}>{plain(n)}</li>
            ))}
          </ul>
        </Section>
      ) : null}
      {refusedExports.length ? (
        <Section title="Not exported" id="k-not-exported">
          <ul className="k-notes">
            {refusedExports.map(([format, e]) => (
              <li key={format}>
                <span className="font-mono">{format}</span> {plain(e.refused ?? "")}
              </li>
            ))}
          </ul>
        </Section>
      ) : null}
      <Disclosure title="The report as the command prints it">
        <MarkdownReport source={result.report_markdown} />
      </Disclosure>
    </div>
  );
}
