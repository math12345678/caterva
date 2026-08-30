/**
 * `scientific simulate --resolve` — look up what the simulation needs, run
 * it, and show where every number came from.
 *
 * This is the command that makes Terrium a tool rather than a validator.
 * The old `simulate` path could not succeed through literature at all:
 *
 *   - `fetchRealLiterature('lactate dehydrogenase', 'lactate')` was called
 *     with those two strings HARDCODED, so every simulation of every system
 *     fetched papers about lactate dehydrogenase regardless of the query.
 *   - It built `Literature` objects with `extractedParameters: []`, so the
 *     recommender had no values to recommend and validation always failed
 *     with NO_LITERATURE.
 *   - It set `peerReviewed: true` with the comment "Papers in PubMed are
 *     peer-reviewed by definition". That is false — PubMed indexes
 *     preprints, editorials, letters and retracted papers — and the field
 *     feeds a verifier that trusts it.
 *
 * This path uses the resolver that returns actual measurements: BRENDA
 * exact, BRENDA cross-species, then PubMed candidates, each carrying a
 * value, a unit, an organism and a citation.
 *
 * THE PROVENANCE TABLE IS THE POINT. A number on screen with no source is
 * what every other tool gives you. Every parameter printed here says where
 * it came from, and anything that could not be sourced stops the run rather
 * than being defaulted.
 */

import { ScientificPipeline } from '../integration/scientificPipeline';
import {
  ResolverUnavailableError,
  resolveKinetic,
} from '../literature/literatureResolver';
import { convertConcentration } from '../units';
import {
  exportCitations,
  exportModel,
  type CitedValue,
  type ExportProvenance,
} from './exportArtifacts';
import type { ReliabilityAxes } from '../literature/literatureResolver';
import { USER_CITATION_CAVEAT } from './userCitations';
import { parseQuantity } from './parseQuantity';
import { commandSensitivity } from './commandSensitivity';
import { JobManager } from '../execution/job-manager';
import {
  INHIBITION_MODELS,
  runInhibitionModel,
  suggestModel,
  PRODUCT_INHIBITION_CAVEAT,
  type InhibitionModel,
} from './inhibitionModels';

const BOLD = '\x1b[1m';
const DIM = '\x1b[2m';
const RED = '\x1b[31m';
const GREEN = '\x1b[32m';
const YELLOW = '\x1b[33m';
const RESET = '\x1b[0m';

const useColour = process.stdout.isTTY === true;
const c = (code: string, text: string): string =>
  useColour ? `${code}${text}${RESET}` : text;

/** How a parameter's value was obtained. Printed for every one. */
export interface ParameterProvenance {
  name: string;
  value: number;
  unit: string;
  /** 'user' | 'brenda_exact' | 'brenda_cross_species' | ... */
  origin: string;
  citation?: string;
  organism?: string;
  crossSpecies?: boolean;
  /** true when the CLI had to assume the unit rather than being told. */
  unitAssumed?: boolean;
  /** Bakker's axes as (axis -> grade), for the exported model file. */
  reliability?: Record<string, string>;
  /** The same axes as (axis -> why). Carried separately from the grades
   *  rather than folded into one string, because the exported model renders
   *  them as a list and the terminal renders only the ones worth reading
   *  aloud. */
  reliabilityReasons?: Record<string, string>;
  /** NCBI Taxonomy id of the organism this value was MEASURED in. Absent
   *  when nothing resolved it; never inferred from `organism`, which is a
   *  name rather than an identifier. */
  taxonId?: string;
  /** Taxon of the organism the user ASKED about. Differs from `taxonId`
   *  exactly when the value is a cross-species substitution. */
  requestedTaxonId?: string;
  /** The conditions this value was measured under, for the exported model.
   *  Jeske's "fantasy numbers" sentence names pH, temperature and buffers
   *  as what decides whether mixing values is legitimate; the file a
   *  student shares is where that has to survive. */
  assayConditions?: {
    ph?: number;
    temperatureC?: number;
    buffer?: string;
    unreported?: string[];
  };
}

/**
 * A resolved result's conditions, normalised for the export payload.
 *
 * `null` becomes `undefined` rather than travelling as-is: the resolver
 * uses `null` for "not reported" and the export payload is JSON, where a
 * present `"ph": null` and an absent `ph` reach Python as the same thing
 * but read very differently to anyone inspecting the payload.
 *
 * Returns undefined when there is nothing to say at all, so a parameter
 * whose conditions were never parsed carries no key rather than an empty
 * object that looks like a failed lookup.
 */
function assayConditionsFor(
  result: { assayConditions?: {
    ph?: number | null;
    temperatureC?: number | null;
    buffer?: string | null;
    unreported?: string[];
  } },
): ParameterProvenance['assayConditions'] {
  const conditions = result.assayConditions;
  if (!conditions) return undefined;

  const normalised = {
    ph: conditions.ph ?? undefined,
    temperatureC: conditions.temperatureC ?? undefined,
    buffer: conditions.buffer ?? undefined,
    unreported: conditions.unreported?.length ? conditions.unreported : undefined,
  };
  const anything = Object.values(normalised).some((v) => v !== undefined);
  return anything ? normalised : undefined;
}

/**
 * A reason the run could not proceed, in a form the CLI can act on.
 *
 * WHY THIS EXISTS BESIDE THE PROSE LIST
 * ------------------------------------
 * `unresolved` holds sentences for a human. Building the command that would
 * fix the run needs the parameter name and the flag, and recovering those by
 * parsing the sentences would be parsing our own output — the
 * duplicate-source-of-truth defect this repository keeps finding, with a
 * formatting step in between (see the `splitCitation` note above, where
 * exactly that produced zero MIRIAM annotations).
 *
 * So the structure is collected alongside the prose rather than extracted
 * from it.
 *
 * THE DISTINCTION THAT MATTERS
 * ----------------------------
 * `condition` — a value the USER chooses. `s0`, `i0` and `[E]0` describe the
 * experiment being run, not the enzyme, so no database can report them and
 * refusing to default them is not a gap in Terrium's coverage. The honest
 * response is to say "this one is yours to pick".
 *
 * `literature` — a measured quantity that BRENDA/PubMed did not yield. Here
 * the refusal IS about coverage, and the useful next step is different: cite
 * a source yourself, or accept a related organism.
 *
 * Telling a student "vmax is unresolved" without saying which kind of
 * problem it is leaves them stuck in the same place either way.
 */
interface Blocker {
  parameter: string;
  kind: 'condition' | 'literature';
  /** Flag that supplies it, with a usable example — `--s0 10mM`. */
  suggestion?: string;
  /** One line the reader can act on. */
  why: string;
}

/**
 * The command that would have worked, printed after a refusal.
 *
 * WHY THIS EXISTS
 * ---------------
 * Used as a student uses it, Terrium took three attempts and six flags
 * before producing a single number, and the refusal at each step named what
 * was missing without saying what to type next.
 *
 * That is Sauro's objection in ADR 0024, which is still open: a tool that
 * refuses pushes people to "hardcode a number with no warning at all". A
 * student stuck on `[E]0` will search for a plausible enzyme concentration,
 * paste it in, and now hold an unsourced parameter with no record of where
 * it came from — which is worse than anything Terrium was protecting them
 * from.
 *
 * The refusal stands. Nothing is defaulted, nothing is invented. What
 * changes is that the way forward is on screen instead of left as an
 * exercise, and the two kinds of blocker are told apart, because they need
 * opposite responses:
 *
 *   condition   you pick it — it describes your experiment
 *   literature  the databases had nothing — cite a source, or widen the search
 *
 * A refusal a reader cannot act on is the defect this project fixes
 * everywhere else. This is the same fix applied to its own front door.
 */
function renderNextStep(
  options: SimulateResolvedOptions,
  blockers: Blocker[],
  emit: (text: string) => void,
): void {
  if (blockers.length === 0) return;

  const conditions = blockers.filter((b) => b.kind === 'condition');
  const gaps = blockers.filter((b) => b.kind === 'literature');

  emit(`\n${c(BOLD, 'What to do next')}\n\n`);

  if (conditions.length > 0) {
    emit(
      `${c(DIM, '  These describe YOUR experiment, so no database can report them.')}\n` +
        `${c(DIM, '  Choosing them is not guessing — it is stating your conditions.')}\n\n`,
    );
    for (const b of conditions) {
      emit(`    ${c(BOLD, b.suggestion ?? `--${b.parameter}`)}\n`);
      emit(`${c(DIM, '      ' + b.why)}\n`);
    }
    emit('\n');
  }

  if (gaps.length > 0) {
    emit(
      `${c(DIM, '  These are measured quantities the literature did not yield.')}\n\n`,
    );
    for (const b of gaps) {
      emit(`    ${c(BOLD, b.suggestion ?? `--${b.parameter}`)}\n`);
      emit(`${c(DIM, '      ' + b.why)}\n`);
    }
    emit(
      `\n${c(DIM, '  If you have a source for one of these, record it rather than')}\n` +
        `${c(DIM, '  typing a bare number — the value then travels with its citation:')}\n\n` +
        `    ${c(BOLD, `--cite ${gaps[0]!.parameter}="Smith 2019, PMID 12345"`)}\n` +
        `${c(DIM, '      Terrium does not verify the source; it records that you supplied it.')}\n` +
        `\n${c(DIM, '  Or widen the search, understanding what you are accepting:')}\n\n` +
        `    ${c(BOLD, '--allow-cross-species')}\n` +
        `${c(DIM, '      a value measured in a related organism, still checked for')}\n` +
        `${c(DIM, '      taxonomic proximity and reported as a substitution.')}\n`,
    );
  }

  // The whole command, so it can be copied rather than reassembled. Built
  // from `options`, which is what the run actually used -- not from the
  // argv this process was handed, which may have been reordered or come
  // from a script.
  const parts = [
    'scientific simulate "michaelis menten" --resolve',
    `  --enzyme ${JSON.stringify(options.enzyme ?? '<enzyme>')}`,
    `  --substrate ${JSON.stringify(options.substrate)}`,
    `  --organism ${JSON.stringify(options.organism)}`,
    ...blockers.map((b) => `  ${b.suggestion ?? `--${b.parameter} <value>`}`),
  ];
  emit(
    `\n${c(DIM, '  In full, with the example values above:')}\n\n` +
      parts.map((p) => `    ${p}`).join(' \\\n') +
      '\n',
  );
}

export interface SimulateResolvedOptions {
  enzyme?: string;
  ec?: string;
  substrate: string;
  organism: string;
  /** Explicit values from the command line. These WIN over literature. */
  overrides: Record<string, string>;
  /** [E]0 with its unit, if given. Bridges kcat to Vmax. */
  enzymeConc?: string;
  json: boolean;
  /** Fractional perturbation for a sensitivity sweep (e.g. 0.1 = ±10%).
   *  When set, reports sensitivity beside each parameter's provenance
   *  instead of running a single simulation. */
  sensitivity?: number;
  /** Which kinetic model. Inhibition models resolve a Ki from BRENDA and
   *  run through the engine (directly, or as SBML when the engine has no
   *  first-class domain). */
  model?: InhibitionModel;
  /** --export-model PATH: write the Antimony with provenance in comments. */
  exportModel?: string;
  /** --export-citations PATH: write every source as .bib or .ris. */
  exportCitations?: string;
  /**
   * The conditions the model represents, for Bakker's proximity axis.
   *
   * `--physiological` reached only `scientific resolve` until now, so the
   * PRIMARY workflow — the one that actually runs a simulation — could
   * never state what it was modelling, and `conditionProximity` came back
   * `not_assessed` on every run of it. An axis that cannot fire in the main
   * command is decoration in the main command.
   */
  physiologicalReference?: {
    ph: number;
    temperatureC: number;
    basis: string;
    phTolerance: number;
    temperatureToleranceC: number;
  };
  /**
   * `--cite km="Smith 2019"` — sources for values the user supplied.
   *
   * Keyed by lower-case parameter name. Never verified by Terrium, and
   * carried as `user_cited` rather than `resolved` so no surface can
   * present it with the authority of a BRENDA reference.
   */
  userCitations?: Map<string, string>;
}

/** Exit codes mirror `resolve`: 0 ran, 1 could not look up, 2 no data. */
/**
 * Bakker's three axes, flattened to (axis -> grade) for the provenance row.
 *
 * WHY THIS FUNCTION EXISTS AT ALL
 * -------------------------------
 * `ParameterProvenance.reliability` was declared, and read when building the
 * exported model, and never once written. The Python resolver graded every
 * value, the score crossed the subprocess boundary, `literatureResolver`
 * carried it into `ResolvedKinetic` — and this file, the last step, dropped
 * it. Every exported model therefore carried an empty reliability block
 * while the whole chain upstream worked.
 *
 * That is the fourth time in this repository that a value has been
 * computed, transported, and discarded by a consumer with nowhere to put
 * it, and the second time in this exact feature. It produces no error on
 * either side: the producer sees a successful write, the consumer sees a
 * complete object.
 *
 * Grades only, not reasons. The exported model annotates each parameter on
 * one line, and three paragraphs of justification per parameter would bury
 * the model in its own provenance. The reasons stay in `scientific resolve`
 * and in the API response, where there is room to read them.
 */
/**
 * "BRENDA ref 740253" -> { source: 'BRENDA', referenceId: '740253' }.
 *
 * Lifted out of the citations branch, where it was inline. The model
 * export could not reach it, so the SBML annotator re-derived identifiers
 * by regex from the display string — a string produced by this same file.
 * Parsing your own output is the duplicate-source-of-truth defect with a
 * formatting step in between: the first end-to-end run wrote **zero**
 * MIRIAM annotations because "PubMed ref 12345678" has a five-character
 * gap and the pattern allowed four.
 *
 * The structured value is now passed through instead of reconstructed.
 */
export function splitCitation(
  citation: string,
  origin: string,
): { source: string; referenceId?: string } {
  if (origin === 'user_cited') return { source: 'user-supplied' };
  return {
    source: citation.split(' ')[0] ?? 'unknown',
    referenceId: citation.match(/ref\s+(\S+)/)?.[1],
  };
}

/** The three axes as (label, grade, reason), in one order everywhere. */
function reliabilityAxes(
  result: { reliability?: ReliabilityAxes },
): Array<{ label: string; grade: string; reason: string }> | undefined {
  const axes = result.reliability;
  if (!axes) return undefined;
  return [
    { label: 'assay completeness', ...axes.assayCompleteness },
    { label: 'conditions vs model', ...axes.conditionProximity },
    { label: 'organism match', ...axes.organismMatch },
  ];
}

function reliabilityGrades(
  result: { reliability?: ReliabilityAxes },
): Record<string, string> | undefined {
  const axes = reliabilityAxes(result);
  if (!axes) return undefined;
  return Object.fromEntries(axes.map((axis) => [axis.label, axis.grade]));
}

/**
 * The reason behind each grade, for the parameters that have one.
 *
 * `scientific resolve` has printed these since the axes existed.
 * `simulate --resolve` -- the command a student actually runs -- printed
 * the bare grades and nothing else, so the screen said
 * `assay completeness complete` and never what that meant.
 *
 * For a teaching tool the reason IS the teaching. "complete" is a token;
 * "reports pH 7.4 and 25 C, meeting STRENDA's minimum, so the measurement
 * can be compared against another lab's figure" is the sentence a student
 * learns something from. Computing it and dropping it before it reaches
 * anyone is the same defect this codebase has now found at five different
 * layers.
 */
function reliabilityReasons(
  result: { reliability?: ReliabilityAxes },
): Record<string, string> | undefined {
  const axes = reliabilityAxes(result);
  if (!axes) return undefined;
  return Object.fromEntries(axes.map((axis) => [axis.label, axis.reason]));
}

/**
 * The artifacts a run can leave behind.
 *
 * Called AFTER the run reports, and its failures never change the exit code
 * of the run itself: a simulation that succeeded did succeed, and reporting
 * otherwise because a file could not be written would make the exit code
 * mean two different things. The failure is printed loudly instead — a
 * silently missing export is how someone submits a paper believing they
 * attached a bibliography.
 *
 * `runnable: false` means the simulation was REFUSED — a parameter could not
 * be resolved and nothing was invented to fill the gap. That is not a reason
 * to ignore the flags the user typed, which is what happened before: the
 * refusal path returned two screens earlier, so `--export-model` and
 * `--export-citations` produced no file and no message. The user asked for
 * an artifact, got silence, and had nothing to distinguish "refused to write
 * it" from "wrote it somewhere I am not looking".
 *
 * The two exports are treated DIFFERENTLY on refusal, and the difference is
 * the point:
 *
 * - **Citations are still written.** A resolved Km with a BRENDA reference is
 *   a real finding, and it stays a real finding when a *different* parameter
 *   is missing. The refusal message effectively tells the student to go read
 *   the literature; withholding the bibliography at that exact moment is the
 *   worst possible time to withhold it.
 *
 * - **The model is not written, and the refusal says so.** An Antimony file
 *   missing `vmax` is not a model — it is a file shaped like one, which
 *   loads into anything that reads Antimony and fails there instead of here.
 *   Writing it would be the same error the tool refuses to make with numbers:
 *   emitting something that looks complete because it looks generated.
 *
 * One function rather than two so there is one place that knows what exports
 * exist. A separate refusal-path exporter would be a second list to keep in
 * step, and it would be wrong the first time a third export is added.
 */
async function writeExports(
  options: SimulateResolvedOptions,
  domain: string,
  parameters: Record<string, number>,
  rows: ParameterProvenance[],
  runnable = true,
  /**
   * The time course that ACTUALLY ran, for the SED-ML inside a COMBINE
   * archive. Passed in rather than restated here: this function does not
   * run the simulation and must not invent the experiment that produced
   * the result it is describing.
   *
   * Absent on the refusal path, where no simulation happened — and an
   * archive is then refused rather than written with a made-up time
   * course.
   */
  experiment?: { endTime?: number; points: number },
  /**
   * Reports, per requested file, whether the write actually happened.
   *
   * `null` means "not requested" and is deliberately distinct from
   * `false`, "requested and did not arrive" -- collapsing those two is how
   * a caller comes to read a run that produced nothing as a run that was
   * asked for nothing.
   *
   * This used to be `Promise<void>`, which is the defect: both failure
   * branches below print a red line and fall through, so the verdict
   * existed and reached nobody. `exportModel` had already returned
   * `{ ok: false, error }` -- it was observed, then dropped.
   *
   * Measured with `libsedml` absent: `simulate --resolve --export-model
   * out.omex` printed a raw Python traceback, wrote no archive, and the
   * `--json` document reported `exports.model: "out.omex"` exactly as it
   * does on success.
   */
): Promise<{ model: boolean | null; citations: boolean | null }> {
  /**
   * Everything this function tells the user goes through here.
   *
   * Under `--json`, stdout carries ONE machine-readable document and nothing
   * else. These messages are prose, and appending them after the JSON
   * produced output no parser could read:
   *
   *     $ simulate ... --json --export-citations refs.bib
   *     json.decoder.JSONDecodeError: Extra data: line 39 column 1
   *
   * The files are still written and the outcomes still reported — as
   * `exports` inside the document (see the call sites), which is where a
   * script can actually act on them. Suppressing the prose without reporting
   * the outcome would trade a corrupt document for a silent one.
   */
  const say = (text: string): void => {
    // `process.stdout.write`, NOT `say` — this is the one place in this
    // function that must call the real sink. A blanket rewrite of
    // `process.stdout.write` -> `say` across the body caught this line too
    // and made it recurse: `RangeError: Maximum call stack size exceeded`,
    // surfacing as `✗ Fatal error` with the refusal already printed, so the
    // run looked like it had merely failed late.
    if (!options.json) process.stdout.write(text);
  };

  /**
   * Per-file verdicts. `null` until the corresponding export is attempted,
   * so a file nobody asked for stays `null` rather than becoming `false`.
   *
   * The model stays `null` on the `!runnable` path below, and that is the
   * point: a model deliberately withheld because the simulation was
   * refused is a decision Terrium made and explained, not a write that
   * failed. `false` there would make "I declined to run" and "the file
   * system said no" the same fact.
   */
  let modelWritten: boolean | null = null;
  let citationsWritten: boolean | null = null;

  if (options.exportModel && !runnable) {
    say(
      `\n${c(YELLOW, '⚠')} ${c(BOLD, 'Model not written')} ${c(DIM, options.exportModel)}\n` +
        `${c(DIM, '  The run was refused above, so at least one parameter has no value.')}\n` +
        `${c(DIM, '  An Antimony file with a hole in it is not a model — it would load')}\n` +
        `${c(DIM, '  and fail in whatever opened it, instead of here where the reason is.')}\n` +
        `${c(DIM, '  Supply the missing value and re-run, and the model will be written.')}\n`,
    );
  } else if (options.exportModel) {
    const provenance: Record<string, ExportProvenance> = {};
    for (const row of rows) {
      provenance[row.name] = {
        // Three origins, not two. Folding `user_cited` into `resolved`
        // would let an unverified citation acquire the authority of a
        // BRENDA reference by passing through a tool that promises
        // provenance -- the most damaging thing this feature could do.
        origin:
          row.origin === 'user'
            ? 'user'
            : row.origin === 'user_cited'
              ? 'user_cited'
              : 'resolved',
        citation: row.citation,
        unit: row.unit,
        organism: row.organism,
        taxonId: row.taxonId,
        source: row.origin,
        crossSpecies: row.crossSpecies,
        reliability: row.reliability,
        reliabilityReasons: row.reliabilityReasons,
        // Forwarded, not re-derived. The row already holds what the
        // resolver reported; deriving the conditions a second time here
        // would be a second place the same fact is decided (ADR 0027).
        assayConditions: row.assayConditions,
        // Structured, so the SBML annotator can decide whether a
        // resolvable URI exists without re-parsing prose.
        ...(row.citation
          ? (() => {
              const split = splitCitation(row.citation, row.origin);
              return {
                citationSource: split.source,
                referenceId: split.referenceId,
              };
            })()
          : {}),
      };
    }

    // The taxon the MODEL is about, as distinct from the taxon each value
    // was measured in. Supplying it is what makes a cross-species
    // substitution detectable by a consumer that never renders notes: the
    // model carries one `bqbiol:hasTaxon`, each parameter carries its own,
    // and the two disagree.
    //
    // Taken from a row that reports it rather than resolved again here.
    // Re-resolving would be a second lookup of one fact, and the two could
    // return different answers if the caller's organism string and the
    // resolver's differed by a synonym.
    const modelTaxonId = rows.find((row) => row.requestedTaxonId)?.requestedTaxonId;

    // The experiment as it actually ran, for the SED-ML inside a COMBINE
    // archive. Read off the trajectory rather than restated: a constant
    // here would describe a time course nobody performed the moment the
    // engine's defaults changed, and the archive's entire purpose is that
    // someone else re-runs the SAME experiment.
    const outcome = await exportModel(
      {
        domain,
        parameters,
        provenance,
        query: options.substrate,
        modelTaxonId,
        endTime: experiment?.endTime,
        points: experiment?.points,
      },
      options.exportModel,
    );
    if (outcome.ok) {
      // Antimony carries provenance in comments, which translation to SBML
      // deletes outright -- measured, not assumed. So the SBML export says
      // something different, because it IS something different: standard
      // MIRIAM annotations that other tools read without being told to.
      const blurb =
        outcome.format === 'omex'
          ? `${c(DIM, `  A COMBINE archive: ${(outcome.entries ?? []).join(', ')}.`)}\n` +
            `${c(DIM, '  The model, the experiment that produced this result, and the')}\n` +
            `${c(DIM, '  sources behind every number — in one file somebody else can re-run.')}\n`
          : outcome.format === 'sbml'
          ? (outcome.cvterms ?? 0) > 0
            ? `${c(DIM, `  ${outcome.cvterms} MIRIAM annotation(s) written. Readable by COPASI, JWS`)}\n` +
              `${c(DIM, '  Online and anything else that reads SBML — the provenance is in the')}\n` +
              `${c(DIM, '  file as data, not only as prose.')}\n`
            // Saying "the provenance is in the file as data" over zero
            // annotations is the kind of confident wrong sentence this
            // project exists to not emit. The notes are still there; the
            // machine-readable half is not, and the reason follows below.
            : `${c(YELLOW, '  ⚠ no MIRIAM annotations were written.')}` +
              `${c(DIM, ' The origins are in the notes,')}\n` +
              `${c(DIM, '  which a person reads and a pipeline does not.')}\n`
          : `${c(DIM, '  Loadable by anything that reads Antimony. Every parameter carries')}\n` +
            `${c(DIM, '  its origin in a comment, so the provenance travels with the file.')}\n`;
      modelWritten = true;
      say(`\n${c(BOLD, 'Model written')} ${outcome.path}\n` + blurb);

      // The units verdict, delivered rather than left in the JSON detail.
      // Three states (ADR 0150): declared, refused-with-reasons, and
      // absent -- an exporter that never reported, which must not print
      // as either of the other two.
      if (outcome.format === 'sbml' || outcome.format === 'omex') {
        if (outcome.unitsDeclared && outcome.unitsDeclared.length > 0) {
          say(
            `${c(DIM, `  Units declared on ${outcome.unitsDeclared.join(', ')} — the file`)}\n` +
            `${c(DIM, '  states its own unit system, and libSBML can check it.')}\n`,
          );
        } else if (outcome.unitsRefused && outcome.unitsRefused.length > 0) {
          say(
            `${c(YELLOW, '  ⚠ no units declared:')} ${c(DIM, outcome.unitsRefused[0]!.reason)}\n`,
          );
          for (const refusal of outcome.unitsRefused.slice(1)) {
            say(`${c(DIM, `    also ${refusal.symbol}: ${refusal.reason}`)}\n`);
          }
        }
      }

      // An identifier Terrium declined to mint a URI for is NOT a missing
      // annotation — the source is real, it just has no resolvable form.
      // Saying so is the difference between "we had nothing" and "we had
      // something and refused to dress it up as a link".
      for (const refused of outcome.refusedUris ?? []) {
        say(
          `${c(DIM, `  no URI for ${refused.parameter}: ${refused.reason}`)}\n`,
        );
      }
      if (outcome.unsourced && outcome.unsourced.length > 0) {
        say(
          `${c(YELLOW, '  ⚠ ' + outcome.unsourced.join(', '))}` +
            `${c(DIM, ' carry no clean literature source in that file.')}\n`,
        );
      }
    } else {
      modelWritten = false;
      say(
        `\n${c(RED, '✗')} Model not written: ${outcome.error}\n`,
      );
    }
  }

  if (options.exportCitations) {
    const cited: CitedValue[] = rows
      .filter((row) => row.citation)
      .map((row) => ({
        parameter: row.name,
        // The display citation is "BRENDA ref 740253". The source and the
        // identifier are split back out rather than passed as one string,
        // because a bibliography entry needs them as separate fields.
        // A user citation is free text, not "SOURCE ref ID". Marked as
        // such so the exported entry cannot be mistaken for a database
        // record.
        citationSource: splitCitation(row.citation!, row.origin).source,
        title: row.origin === 'user_cited' ? row.citation : undefined,
        referenceId: splitCitation(row.citation!, row.origin).referenceId,
        value: row.value,
        unit: row.unit,
        organism: row.organism,
      }));

    const outcome = await exportCitations(cited, options.exportCitations);
    if (outcome.ok) {
      citationsWritten = true;
      say(
        `\n${c(BOLD, 'Citations written')} ${outcome.path}\n` +
          `${c(DIM, `  ${cited.length} source(s), importable into Zotero, Mendeley or EndNote.`)}\n` +
          `${c(DIM, '  Author, year and journal are absent, not omitted — Terrium knows')}\n` +
          `${c(DIM, '  the identifier and does not invent the rest.')}\n`,
      );
    } else {
      citationsWritten = false;
      say(
        `\n${c(RED, '✗')} Citations not written: ${outcome.error}\n`,
      );
    }
  }

  return { model: modelWritten, citations: citationsWritten };
}

export async function commandSimulateResolved(
  options: SimulateResolvedOptions,
): Promise<number> {
  /**
   * Every PROSE message this function prints goes through here. The JSON
   * documents call `process.stdout.write` directly, because they are the
   * thing `--json` promises.
   *
   * Eleven prose writes were reachable while `options.json` was true — the
   * model suggestion, the product-inhibition caveat, the sensitivity table,
   * the warnings list — each of which put a sentence on stdout ahead of the
   * document:
   *
   *     $ simulate ... --resolve --ki 5mM --i0 1mM --json
   *     • Did you mean --model competitive? ...
   *     { "ok": true, ... }
   *     -> Expecting value: line 2 column 1 (char 1)
   *
   * ADR 0077 fixed the same fault inside `writeExports` and stopped there.
   * That fixed the instance and not the class: `--json` remained corruptible
   * by any of eleven other branches, and the test written for it passed
   * because the scenario it ran happened to trigger none of them.
   *
   * The sink is per-function rather than per-message so that a message added
   * later is quiet by default. Getting this right by remembering to wrap
   * each new `process.stdout.write` is the arrangement that just failed.
   */
  const say = (text: string): void => {
    // `process.stdout.write`, NOT `say`. See ADR 0077 — a scripted rewrite
    // of the calls in `writeExports` caught that function's own sink and
    // made it recurse.
    if (!options.json) process.stdout.write(text);
  };

  const provenance: ParameterProvenance[] = [];
  const unresolved: string[] = [];
  //: Same refusals as `unresolved`, structured so the next command can be
  //: built rather than described. See the Blocker docstring.
  const blockers: Blocker[] = [];

  // ---- user-supplied values first -------------------------------------
  //
  // A value the user typed is not a guess and must not be overwritten by a
  // lookup. It is still recorded with its origin so the table is complete.
  const userValues: Record<string, { value: number; unit: string }> = {};
  for (const [name, raw] of Object.entries(options.overrides)) {
    const quantity = parseQuantity(name, raw);
    userValues[name] = { value: quantity.value, unit: quantity.unit };

    // A value the user typed may still have a real source in the world.
    // Sauro predicted that a refusing tool pushes people to "hardcode a
    // number with no warning at all" -- and Terrium's own error message
    // told them to. If they can say where it came from, that is recorded
    // rather than discarded.
    const cited = options.userCitations?.get(name.toLowerCase());
    provenance.push({
      name,
      value: quantity.value,
      unit: quantity.unit,
      origin: cited ? 'user_cited' : 'user',
      citation: cited,
      unitAssumed: !quantity.unitDeclared,
    });
  }

  let enzymeConcMM: number | undefined;
  if (options.enzymeConc) {
    const parsed = parseQuantity('e0', options.enzymeConc);
    // The Python bridge takes [E]0 in mM (ADR 0013). Converted rather than
    // assumed, so `--enzyme-conc 1uM` is not read as 1 mM.
    enzymeConcMM = convertConcentration(parsed.value, parsed.unit, 'mM');
    provenance.push({
      name: 'e0',
      value: parsed.value,
      unit: parsed.unit,
      origin: 'user',
      unitAssumed: !parsed.unitDeclared,
    });
  }

  // ---- resolve what is missing ----------------------------------------
  const needed: Array<'km' | 'vmax'> = ['km', 'vmax'];

  for (const name of needed) {
    if (userValues[name]) continue;

    try {
      if (name === 'km') {
        const result = await resolveKinetic({
          enzymeName: options.enzyme,
          ecNumber: options.ec,
          substrate: options.substrate,
          organism: options.organism,
          quantity: 'km',
          physiologicalReference: options.physiologicalReference,
        });
        if (!result.found) {
          unresolved.push('km');
          blockers.push({
            parameter: 'km',
            kind: 'literature',
            suggestion: '--km 10.7mM',
            why: 'BRENDA and PubMed returned no Km for this system.',
          });
          continue;
        }
        userValues['km'] = { value: result.value, unit: result.unit };
        provenance.push({
          name: 'km',
          value: result.value,
          unit: result.unit,
          origin: result.source,
          citation: result.citation
            ? `${result.citation.source} ref ${result.citation.reference_id ?? '?'}`
            : undefined,
          organism: result.organism ?? undefined,
          crossSpecies: result.crossSpecies,
          taxonId: result.taxonId ?? undefined,
          requestedTaxonId: result.requestedTaxonId ?? undefined,
          reliability: reliabilityGrades(result),
          reliabilityReasons: reliabilityReasons(result),
          assayConditions: assayConditionsFor(result),
        });
      } else {
        // Vmax is not a BRENDA table. It is kcat x [E]0, and [E]0 is a
        // caller input BRENDA does not supply per row (ADR 0012/0013).
        // Without it, a resolved kcat is a citable number that cannot
        // reach a simulation -- said out loud rather than defaulted.
        if (enzymeConcMM === undefined) {
          unresolved.push(
            'vmax (needs --enzyme-conc: Vmax = kcat x [E]0, and BRENDA does ' +
              'not report [E]0)',
          );
          blockers.push({
            parameter: 'enzyme-conc',
            kind: 'condition',
            suggestion: '--enzyme-conc 0.01mM',
            why:
              'Vmax = kcat x [E]0. BRENDA reports kcat but never [E]0, ' +
              'because how much enzyme you put in the tube is your ' +
              'experiment, not a property of the enzyme.',
          });
          continue;
        }
        const result = await resolveKinetic({
          enzymeName: options.enzyme,
          ecNumber: options.ec,
          substrate: options.substrate,
          organism: options.organism,
          quantity: 'kcat',
          enzymeConc: enzymeConcMM,
          physiologicalReference: options.physiologicalReference,
        });
        if (!result.found || result.bridgedVmax === undefined) {
          unresolved.push('vmax (no kcat found to bridge)');
          blockers.push({
            parameter: 'vmax',
            kind: 'literature',
            suggestion: '--vmax 1.2mM/s',
            why:
              'No kcat was found for this system, so there is nothing to ' +
              'multiply by [E]0 to obtain Vmax.',
          });
          continue;
        }
        userValues['vmax'] = { value: result.bridgedVmax, unit: 'mM/s' };
        provenance.push({
          name: 'vmax',
          value: result.bridgedVmax,
          unit: 'mM/s',
          origin: `${result.source} → kcat x [E]0`,
          citation: result.citation
            ? `${result.citation.source} ref ${result.citation.reference_id ?? '?'}`
            : undefined,
          organism: result.organism ?? undefined,
          crossSpecies: result.crossSpecies,
          taxonId: result.taxonId ?? undefined,
          requestedTaxonId: result.requestedTaxonId ?? undefined,
          // The score describes the KCAT that was resolved. Vmax is that
          // kcat times a caller-supplied [E]0, so the assay and organism
          // axes still describe where the measured half came from -- and
          // the [E]0 half has its own row, marked `user`.
          reliability: reliabilityGrades(result),
          reliabilityReasons: reliabilityReasons(result),
          assayConditions: assayConditionsFor(result),
        });
      }
    } catch (err) {
      if (err instanceof ResolverUnavailableError) {
        if (options.json) {
          process.stdout.write(
            JSON.stringify(
              { ok: false, status: 'unavailable', parameter: name, reason: err.message },
              null,
              2,
            ) + '\n',
          );
        } else {
          process.stderr.write(
            `${c(RED, '✗')} Could not look up ${name}: ${err.message}\n` +
              `${c(DIM, '  Nothing was learned about this system. This is not the same as')}\n` +
              `${c(DIM, '  the literature having no value.')}\n`,
          );
        }
        return 1;
      }
      throw err;
    }
  }

  // Ki, for inhibition models. A BRENDA table exactly like Km, resolved by
  // its OWN call so a cross-species Ki can never inherit a verified Km's
  // provenance (ADR 0008).
  const model: InhibitionModel = options.model ?? 'mm';
  if (model !== 'mm' && !userValues['ki']) {
    try {
      const result = await resolveKinetic({
        enzymeName: options.enzyme,
        ecNumber: options.ec,
        substrate: options.substrate,
        organism: options.organism,
        quantity: 'ki',
      });
      if (result.found) {
        userValues['ki'] = { value: result.value, unit: result.unit };
        provenance.push({
          name: 'ki',
          value: result.value,
          unit: result.unit,
          origin: result.source,
          citation: result.citation
            ? `${result.citation.source} ref ${result.citation.reference_id ?? '?'}`
            : undefined,
          organism: result.organism ?? undefined,
          crossSpecies: result.crossSpecies,
          taxonId: result.taxonId ?? undefined,
          requestedTaxonId: result.requestedTaxonId ?? undefined,
        });
      } else {
        unresolved.push('ki (no inhibition constant in the literature for this system)');
        blockers.push({
          parameter: 'ki',
          kind: 'literature',
          suggestion: '--ki 5mM',
          why: 'No inhibition constant in the literature for this system.',
        });
      }
    } catch (err) {
      if (err instanceof ResolverUnavailableError) {
        process.stderr.write(
          `${c(RED, '✗')} Could not look up ki: ${err.message}\n`,
        );
        return 1;
      }
      throw err;
    }
  }

  // Requirements differ per model, so check the model's own list.
  for (const required of INHIBITION_MODELS[model].requires) {
    if (required === 'km' || required === 'vmax' || required === 'ki') continue;
    if (!userValues[required]) {
      unresolved.push(
        `${required} (an experimental condition — supply it, e.g. --${required} 10mM)`,
      );
      blockers.push({
        parameter: required,
        kind: 'condition',
        suggestion: `--${required} 10mM`,
        why:
          `${required} describes the experiment you are running, not the ` +
          'enzyme. No database can report it for you.',
      });
    }
  }

  // Supplying a Ki and then running plain `mm` silently discards the
  // inhibitor: the run succeeds and the inhibition being studied is simply
  // absent from the result.
  if (model === 'mm') {
    const suggestion = suggestModel({
      ki: userValues['ki']?.value,
      i0: userValues['i0']?.value,
    });
    if (suggestion) {
      say(
        `\n${c(YELLOW, '•')} ${c(BOLD, `Did you mean --model ${suggestion.model}?`)} ` +
          `${c(DIM, suggestion.why + '.')}\n`,
      );
    }
  }

  // s0 is NOT checked here. It is in every model's `requires` list, so the
  // loop above already reports it — and this block used to report it a
  // second time, with a byte-identical sentence, so every refusal that was
  // missing s0 printed the same line twice:
  //
  //     s0 (an experimental condition — supply it, e.g. --s0 10mM)
  //     s0 (an experimental condition — supply it, e.g. --s0 10mM)
  //
  // A reader has no way to tell that from two genuinely different missing
  // things, and the obvious reading — that there are two s0s — is wrong.
  // The block predates the generic loop and was left behind when the loop
  // took over. Deleted rather than de-duplicated at the print site: the
  // duplicate was a second source of truth, and suppressing its output
  // would have kept the second source and hidden it.

  if (unresolved.length > 0) {
    // ORDER MATTERS, AND IT DIFFERS BY OUTPUT MODE.
    //
    // Human: the refusal is printed first, then the export messages — one of
    // which says "the run was refused above", which has to be true.
    // JSON: stdout must carry ONE document, so the exports (silent under
    // --json, see `say`) happen first and are reported inside it. Appending
    // their prose after the document produced output no parser could read:
    //
    //     json.decoder.JSONDecodeError: Extra data: line 39 column 1
    //
    // One `writeExports` call either way. Two calls would be two lists of
    // which exports exist, and they would disagree the first time a third
    // export is added — ADR 0025's two-collectors problem.
    if (!options.json) {
      printProvenance(provenance);
      say(
        `\n${c(RED, '✗')} ${c(BOLD, 'Cannot run.')} These are unresolved:\n`,
      );
      for (const item of unresolved) {
        say(`    ${item}\n`);
      }
      say(
        `\n${c(DIM, 'No value has been invented to fill the gap. A simulation on a')}\n` +
          `${c(DIM, 'defaulted parameter produces a result that looks measured and is not.')}\n`,
      );
      // The refusal is correct. Leaving the reader there is not — that is
      // how a student ends up pasting a number they found in a search
      // result, which is the outcome the refusal exists to prevent.
      //
      // Routed through `say`, so under --json it stays off stdout and the
      // document remains the only thing there (ADR 0077).
      renderNextStep(options, blockers, say);
    }

    // The flags the user typed are honoured even though the run was refused.
    // Citations found are still citations found; the model is withheld with
    // a reason rather than silently skipped. See writeExports.
    //
    // `parameters` is what WAS resolved, which is a subset — it is only used
    // for the model, and the model is not written on this path.
    await writeExports(
      options,
      options.model === 'competitive' ? 'mm_competitive_inhibition' : 'mm',
      Object.fromEntries(provenance.map((row) => [row.name, row.value] as const)),
      provenance,
      false,
    );

    if (options.json) {
      process.stdout.write(
        JSON.stringify(
          {
            ok: false,
            status: 'unresolved',
            unresolved,
            provenance,
            // `model: null` whatever was requested: an incomplete model is
            // not written on this path, so reporting the requested path
            // would imply a file that does not exist. The reason is given
            // separately rather than left for the caller to infer.
            exports: {
              model: null,
              citations: options.exportCitations ?? null,
              modelWithheld: options.exportModel
                ? 'the run was refused, so at least one parameter has no value'
                : null,
            },
          },
          null,
          2,
        ) + '\n',
      );
    }

    return 2;
  }

  // ---- run it ----------------------------------------------------------
  const pipeline = new ScientificPipeline();
  const numeric: Record<string, number> = {};
  for (const [name, v] of Object.entries(userValues)) {
    numeric[name] = v.value;
  }

  // The pipeline resolves through the SAME resolver used above, and
  // returns provenance for everything it touched. Passing `system` lets it
  // attach citations to what it resolves; passing the values we already
  // resolved as `parameters` keeps user overrides authoritative.
  // Hand the pipeline the provenance for everything resolved above, so a
  // BRENDA-sourced Km arrives as sourced rather than as a hand-typed number.
  const providedProvenance: Record<
    string,
    { source: string; citations?: string[]; unit?: string }
  > = {};
  for (const row of provenance) {
    providedProvenance[row.name] = {
      source: row.origin,
      unit: row.unit,
      ...(row.citation ? { citations: [row.citation] } : {}),
    };
  }

  const response = await pipeline.execute({
    query: `${options.enzyme ?? options.ec} / ${options.substrate}`,
    // Stated, not inferred. `options.model` is what the caller asked for
    // with --model; the query string here is "<enzyme> / <substrate>",
    // which names a SYSTEM and not a MODEL. Leaving the pipeline to read a
    // domain out of an enzyme name is asking it to re-derive something the
    // caller already knew — and every inhibition model shares the same
    // Michaelis-Menten parameter requirements (km, vmax, s0), so they map
    // to the same required set here; the inhibition-specific terms (ki, i0)
    // are validated by runInhibitionModel at dispatch.
    domain: 'mm',
    parameters: numeric,
    providedProvenance,
    system: {
      enzymeName: options.enzyme,
      ecNumber: options.ec,
      substrate: options.substrate,
      organism: options.organism,
    },
    ...(options.enzymeConc
      ? {
          enzymeConcentration: {
            value: parseQuantity('e0', options.enzymeConc).value,
            unit: parseQuantity('e0', options.enzymeConc).unit,
          },
        }
      : {}),
  });

  // The pipeline returns a fully-shaped response even when validation
  // STOPS the run -- empty trajectory, finalValue 0, blank reproducibility
  // key. Printing that as a result rendered "initial undefined, points 0"
  // and exited 0, which is a success report for a simulation that never
  // executed. Checked before anything is presented.
  if (!response.validated) {
    if (options.json) {
      process.stdout.write(
        JSON.stringify(
          {
            ok: false,
            status: 'validation_failed',
            errors: response.validationErrors,
            provenance,
          },
          null,
          2,
        ) + '\n',
      );
    } else {
      printProvenance(provenance);
      say(
        `\n${c(RED, '✗')} ${c(BOLD, 'Validation stopped the run.')} No simulation was executed.\n`,
      );
      for (const message of response.validationErrors) {
        say(`    ${message}\n`);
      }
      say('\n');
    }
    return 2;
  }

  // Inhibition models run through the engine directly (competitive) or as
  // SBML (non-competitive, product) -- the same solver either way, never a
  // second simulator in TypeScript.
  if (model !== 'mm') {
    printProvenance(provenance);

    if (model === 'product') {
      say(`\n${c(YELLOW, '⚠')} ${PRODUCT_INHIBITION_CAVEAT}\n`);
    }

    try {
      const run = await runInhibitionModel(model, {
        km: userValues['km']!.value,
        vmax: userValues['vmax']!.value,
        s0: userValues['s0']!.value,
        ki: userValues['ki']?.value,
        i0: userValues['i0']?.value,
        end: 10,
        points: 101,
      });

      const series = run.trajectory;
      const first = series[0] ?? {};
      const last = series[series.length - 1] ?? {};
      const substrateKey = Object.keys(first).find((k) => k.includes('S')) ?? '';

      say(
        `\n${c(BOLD, 'Result')}  ${c(DIM, INHIBITION_MODELS[model].description)}\n`,
      );
      say(
        `  ${c(DIM, 'engine    ')} ${run.domain}${run.viaSbml ? c(DIM, '  (via SBML — no first-class domain for this model)') : ''}\n`,
      );
      if (substrateKey) {
        say(
          `  ${c(DIM, 'initial   ')} ${Number(first[substrateKey]).toFixed(4)}\n`,
        );
        say(
          `  ${c(DIM, 'final     ')} ${Number(last[substrateKey]).toFixed(4)}\n`,
        );
      }
      say(`  ${c(DIM, 'points    ')} ${series.length}\n\n`);
      return 0;
    } catch (err) {
      process.stderr.write(
        `${c(RED, '✗')} ${err instanceof Error ? err.message : String(err)}\n`,
      );
      return 2;
    }
  }

  // Sensitivity runs on the SAME resolved parameters, with the SAME
  // provenance. That pairing is the point: it can then say which weakly
  // sourced number the answer actually rides on.
  if (options.sensitivity !== undefined) {
    // `printProvenance` writes prose directly, and `commandSensitivity`
    // emits its own JSON document — so unguarded, this put the whole
    // provenance table on stdout ahead of it and `--sensitivity --json`
    // parsed as nothing at all. The table is the human framing for the
    // sensitivity figures; under --json the same rows are already inside
    // the document as `provenance`.
    if (!options.json) printProvenance(provenance);
    return commandSensitivity({
      query: `${options.enzyme ?? options.ec} / ${options.substrate}`,
      parameters: numeric,
      provenance,
      perturbation: options.sensitivity,
      request: {
        // Same reasoning as the execute() call above: the sensitivity run
        // must be the SAME model as the run it is analysing, so the domain
        // travels with it rather than being re-inferred from a system name.
        domain: 'mm',
        providedProvenance,
        system: {
          enzymeName: options.enzyme,
          ecNumber: options.ec,
          substrate: options.substrate,
          organism: options.organism,
        },
      },
      json: options.json,
    });
  }

  if (options.json) {
    // THE EXPORTS ARE WRITTEN BEFORE THIS RETURNS, not after.
    //
    // `writeExports` is the last statement of this function, and this block
    // `return`ed above it — so under `--json`, `--export-model` and
    // `--export-citations` produced NO FILE AND NO MESSAGE. Exactly the
    // defect ADR 0049 fixed for the human path, still live for anyone
    // scripting the tool, and quieter there: a script does not notice a
    // missing file the way a person reading a terminal does.
    //
    // Under `--json` these calls print nothing (see `say` in writeExports),
    // so the document below stays the only thing on stdout. The outcome is
    // reported inside it instead, which is where a script can act on it.
    const exportOutcomes = await writeExports(
      options,
      options.model === 'competitive' ? 'mm_competitive_inhibition' : 'mm',
      Object.fromEntries(provenance.map((row) => [row.name, row.value] as const)),
      provenance,
      true,
    );
    process.stdout.write(
      JSON.stringify(
        {
          ok: true,
          status: 'ran',
          provenance,
          response,
          // Paths REQUESTED, and — since this pass — whether each write
          // actually happened.
          //
          // The previous version carried only the paths, on the reasoning
          // that "stating `written: true` here would be this function
          // asserting the success of a write it does not observe." That is
          // the one thing it is not: `exportModel` returns
          // `{ ok: false, error }`, `writeExports` reads it, prints a red
          // line, and threw the verdict away. An observed outcome dropped
          // before it reaches the reader is this project's house defect,
          // and the comment ten lines above already promised the opposite —
          // "the outcome is reported inside it instead, which is where a
          // script can act on it." It was not. Now it is.
          //
          // `stat()` was the suggested substitute and it cannot answer the
          // question: a stale file from an earlier run at the same path
          // exists and is wrong, so "the file is there" and "this run wrote
          // it" are different facts. Only the writer knows which.
          //
          // Null path -> null outcome, never `false`: not requested and
          // requested-but-failed must not collapse into one value.
          exports: {
            model: options.exportModel ?? null,
            citations: options.exportCitations ?? null,
            written: exportOutcomes,
          },
        },
        null,
        2,
      ) + '\n',
    );
    return 0;
  }

  // Merge in what the pipeline reported. Anything it resolved carries the
  // citations that our own pass could not (the CLI hands it plain numbers,
  // so provenance has to come back rather than go in).
  for (const [name, resolved] of Object.entries(response.parameterProvenance ?? {})) {
    const existing = provenance.find((row) => row.name === name);
    if (existing && !existing.citation && resolved.citations?.length) {
      existing.citation = resolved.citations.join(', ');
    }
  }

  // Persist the run so `verify` and `check-integrity` can find it in a
  // LATER process. Without this the CLI printed a job id that no
  // subsequent command could resolve, because the store was in memory and
  // the process had exited.
  const written = JobManager.recordRun({
    jobId: response.jobId,
    at: new Date().toISOString(),
    query: `${options.enzyme ?? options.ec} / ${options.substrate}`,
    provenance,
    reproducibilityKey: response.reproducibilityKey,
    dataIntegrityHash: response.dataIntegrityHash,
    finalValue: response.results.finalValue,
    validated: response.validated,
  });

  printProvenance(provenance);

  const substrateUnit = userValues['s0']?.unit ?? '';
  const first = response.results.trajectory[0];
  say(`\n${c(BOLD, 'Result')}\n`);
  say(
    `  ${c(DIM, 'initial   ')} ${first?.value.toFixed(4)} ${substrateUnit}\n`,
  );
  say(
    `  ${c(DIM, 'final     ')} ${response.results.finalValue.toFixed(4)} ${substrateUnit}\n`,
  );
  say(
    `  ${c(DIM, 'consumed  ')} ${((first?.value ?? 0) - response.results.finalValue).toFixed(4)} ${substrateUnit}\n`,
  );
  say(`  ${c(DIM, 'points    ')} ${response.results.trajectory.length}\n`);
  say(`\n  ${c(DIM, 'job       ')} ${response.jobId}\n`);
  // The line below used to read `repro key`, showing a hash built from
  // the inputs, the outputs, `Date.now()` and a random UUID. It is a
  // correct unique run identifier and it CANNOT be reproduced -- two
  // identical runs differ by construction. Printing it under that name
  // invited a student to compare two runs' "repro keys" and conclude the
  // tool was non-deterministic.
  //
  // `inputs` is the hash that does match: same query, same parameters,
  // same conditions, same string, on any machine. It was computed and
  // stored from the start and never shown.
  say(
    `  ${c(DIM, 'inputs    ')} ${response.inputsHash.slice(0, 32)}…` +
      `${c(DIM, '  (same inputs give the same value)')}\n`,
  );
  say(
    `  ${c(DIM, 'run id    ')} ${response.reproducibilityKey.slice(0, 32)}…` +
      `${c(DIM, '  (unique per run, never repeats)')}\n`,
  );

  if (written.ok) {
    say(
      `\n${c(DIM, `  Saved. Re-check it later with:  scientific check-integrity ${response.jobId}`)}\n\n`,
    );
  } else {
    // Reported rather than swallowed: a user who is told a job id, then
    // finds `verify` cannot see it, has no way to know why.
    say(
      `\n${c(YELLOW, '  ⚠ Run history could not be written')} ${c(DIM, '(' + (written.reason ?? '') + ')')}\n` +
        `${c(DIM, '    The simulation is valid; it just will not appear in `history`.')}\n\n`,
    );
  }

  // The artifacts a run should be able to leave behind. Written last, and
  // their failure never changes this function's exit code -- a simulation
  // that succeeded did succeed, and a file that could not be written is a
  // different fact reported separately.
  await writeExports(
    options,
    options.model === 'competitive' ? 'mm_competitive_inhibition' : 'mm',
    Object.fromEntries(
      provenance.map((row) => [row.name, row.value] as const),
    ),
    provenance,
    true,
    // The experiment that produced the numbers printed above, read off the
    // trajectory that was actually integrated. Not a constant: a constant
    // here would go on describing the old time course the moment the
    // engine's defaults changed, and every archive after that would
    // reproduce a curve nobody had run.
    {
      endTime:
        response.results.trajectory[response.results.trajectory.length - 1]?.time,
      points: response.results.trajectory.length,
    },
  );

  return 0;
}

/**
 * The provenance table.
 *
 * Units are printed from each parameter's own `unit` field, not from a
 * hardcoded "mM" -- the previous output appended "mM" to every number
 * regardless of what the parameter actually was, so a Vmax in mM/s and a
 * Km in µM both rendered as millimolar.
 */
/** Break `text` into lines of at most `width`, on word boundaries. */
function wrap(text: string, width: number): string[] {
  const lines: string[] = [];
  let current = '';
  for (const word of text.split(/\s+/)) {
    if (current && current.length + word.length + 1 > width) {
      lines.push(current);
      current = word;
    } else {
      current = current ? `${current} ${word}` : word;
    }
  }
  if (current) lines.push(current);
  return lines;
}

function printProvenance(rows: ParameterProvenance[]): void {
  if (rows.length === 0) return;

  process.stdout.write(`\n${c(BOLD, 'Parameters and where they came from')}\n`);

  const nameWidth = Math.max(...rows.map((r) => r.name.length), 4);
  const valueStrings = rows.map((r) => `${r.value} ${r.unit}`);
  const valueWidth = Math.max(...valueStrings.map((v) => v.length), 5);

  rows.forEach((row, index) => {
    const value = valueStrings[index]!.padEnd(valueWidth);
    let line = `  ${row.name.padEnd(nameWidth)}  ${value}  ${c(DIM, row.origin)}`;
    if (row.citation) line += c(DIM, `  ${row.citation}`);
    process.stdout.write(line + '\n');

    if (row.origin === 'user_cited') {
      process.stdout.write(
        `  ${' '.repeat(nameWidth)}  ${c(DIM, USER_CITATION_CAVEAT)}\n`,
      );
    }
    if (row.crossSpecies) {
      process.stdout.write(
        `  ${' '.repeat(nameWidth)}  ${c(YELLOW, '⚠ measured in ' + (row.organism ?? 'another organism') + ', not the organism requested')}\n`,
      );
    }
    if (row.unitAssumed) {
      process.stdout.write(
        `  ${' '.repeat(nameWidth)}  ${c(YELLOW, `⚠ unit not given; ${row.unit} assumed`)}\n`,
      );
    }
    // The axes were computed, carried, and written into the exported model
    // file -- and never shown to the person at the terminal, who is the
    // one deciding whether to trust the number. A grade that only appears
    // in a file you have to know to ask for is a grade most users never
    // see. Printed for every resolved row, including the good ones: a
    // caveat that only appears when something is wrong teaches readers
    // that silence means "not assessed" rather than "assessed and fine".
    if (row.reliability) {
      const parts = Object.entries(row.reliability).map(
        ([axis, grade]) => `${axis} ${grade}`,
      );
      process.stdout.write(
        `  ${' '.repeat(nameWidth)}  ${c(DIM, `reliability: ${parts.join(' · ')}`)}\n`,
      );

      // ...and the REASON, for any axis that is reporting a limitation.
      //
      // All three grades are printed above whatever they say, so silence
      // here never means "not assessed" -- the axis is on the line above
      // either way. What varies is the explanation, and printing three
      // paragraphs per parameter on every run would bury the answer the
      // command exists to give (there is an output-hygiene test about
      // exactly that).
      //
      // Nothing is lost: every reason, including the good ones, is written
      // into the exported model's notes.
      const settled = new Set(['complete', 'exact', 'near']);
      for (const [axis, grade] of Object.entries(row.reliability)) {
        if (settled.has(grade)) continue;
        const reason = row.reliabilityReasons?.[axis];
        if (!reason) continue;
        for (const line of wrap(reason, 66)) {
          process.stdout.write(`  ${' '.repeat(nameWidth)}    ${c(DIM, line)}\n`);
        }
      }
    }
  });

  const sourced = rows.filter((r) => r.citation).length;
  process.stdout.write(
    `\n  ${c(DIM, `${sourced} of ${rows.length} parameter(s) carry a literature citation.`)}\n`,
  );
  if (sourced < rows.length) {
    process.stdout.write(
      `  ${c(DIM, 'The rest are user inputs or experimental conditions, which is fine —')}\n` +
        `  ${c(DIM, 'but they are not literature-backed and must not be reported as such.')}\n`,
    );
  }
}
