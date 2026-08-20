#!/usr/bin/env node
import { commandResolve } from './commandResolve';
import { commandSimulateResolved } from './commandSimulateResolved';
import { JobManager, historyPath } from '../execution/job-manager';
import { commandSweep } from './commandSweep';
import { spawnSync } from 'child_process';

import { REPO_ROOT, resolvePythonExecutable } from '../engine/teriumBridge';
import { parseArgs, parseQuantity } from './parseQuantity';
import { parsePhysiological } from './physiologicalReference';
import { collectRepeated, parseUserCitations } from './userCitations';
import { convertConcentration } from '../units';
import {
  parseSystemFromQuery,
  formatResolveCommand,
} from './suggestResolveCommand';
import { confirmSystem, terminalIO } from './confirmSystem';
import { commandDomains } from './commandDomains';
import { commandEnsemble } from './commandEnsemble';

/**
 * Scientific Pipeline CLI
 *
 * Executable command-line tool for scientific validation
 * Usage:
 *   npx ts-node src/cli/scientificCLI.ts validate --query "lactate dehydrogenase km=5"
 *   npx ts-node src/cli/scientificCLI.ts simulate --query "michaelis menten" --km 5.2 --vmax 12.8
 *   npx ts-node src/cli/scientificCLI.ts verify-reproducibility --job-id job_001
 */

/**
 * Scientific Pipeline CLI
 *
 * Phase 4: Real Data from Real APIs
 * ✓ CrossRef API for DOI validation and metadata
 * ✓ PubMed API for literature search
 * ✓ Real kinetics parameters from BRENDA (optional)
 *
 * NO FAKE DATA - All citations verified against real registries
 */

import * as fs from 'fs';
import * as path from 'path';
import ScientificPipeline from '../integration/scientificPipeline';
import { LiteratureService } from '../literature/literatureService';
import {
  PubMedUnavailableError,
  resolveDOIFromCrossRef,
  searchPubMedForEnzymeKinetics,
} from '../integrations/crossref-pubmed-real';
import type { Literature } from '../literature/literatureService';

// ============================================================================
// CLI COLORS & FORMATTING
// ============================================================================

const colors = {
  reset: '\x1b[0m',
  bright: '\x1b[1m',
  dim: '\x1b[2m',
  red: '\x1b[31m',
  green: '\x1b[32m',
  yellow: '\x1b[33m',
  blue: '\x1b[34m',
  cyan: '\x1b[36m'
};

/**
 * The value after a flag, or undefined.
 *
 * A missing value returns undefined rather than the NEXT FLAG:
 * `--out --json` must not silently write a file called "--json".
 */
function flagValue(args: string[], flag: string): string | undefined {
  const at = args.indexOf(flag);
  if (at < 0) return undefined;
  const next = args[at + 1];
  if (next === undefined || next.startsWith('--')) return undefined;
  return next;
}

function success(msg: string) {
  console.log(`${colors.green}✓${colors.reset} ${msg}`);
}

function error(msg: string) {
  console.error(`${colors.red}✗${colors.reset} ${msg}`);
}

function warning(msg: string) {
  console.warn(`${colors.yellow}⚠${colors.reset} ${msg}`);
}

function info(msg: string) {
  console.log(`${colors.blue}ℹ${colors.reset} ${msg}`);
}

function header(msg: string) {
  console.log(`\n${colors.bright}${colors.cyan}═══════════════════════════════════════${colors.reset}`);
  console.log(`${colors.bright}${colors.cyan}${msg}${colors.reset}`);
  console.log(`${colors.bright}${colors.cyan}═══════════════════════════════════════${colors.reset}\n`);
}

// ============================================================================
// REAL LITERATURE FROM REAL APIs
// ============================================================================

/**
 * Fetch real literature from PubMed and CrossRef
 *
 * NO FAKE DATA - All DOIs are verified against CrossRef
 * All papers are from PubMed (50+ million papers)
 *
 * Timeout: 10 seconds max (to avoid hanging)
 */
/**
 * Three outcomes, not two — the same discipline `resolve` exits on.
 *
 * This returned `Literature[]` and gave `[]` both when PubMed genuinely had
 * nothing and when the search could not be performed at all. The caller could
 * not tell them apart, so it exited 0 for both: a network failure was
 * reported as a successful search that found no papers.
 *
 * "We looked and there is nothing" and "we could not look" are different
 * facts, and collapsing them teaches a reader to take an absence of evidence
 * for evidence of absence. Every other lookup in this tool keeps them apart
 * and exits 0 / 2 / 1 accordingly; this one is now no exception.
 */
type LiteratureSearch =
  | { outcome: 'found'; papers: Literature[] }
  | { outcome: 'empty' }
  | { outcome: 'unavailable'; reason: string };

async function fetchRealLiterature(
  enzyme: string,
  substrate: string,
): Promise<LiteratureSearch> {
  const literature: Literature[] = [];
  let counter = 0;

  info(`Searching PubMed for real papers on "${enzyme} kinetics" (timeout: 10s)...`);

  try {
    // Add timeout to prevent hanging
    const timeoutPromise = new Promise<never>((_, reject) =>
      setTimeout(() => reject(new Error('PubMed search timeout (10s)')), 10000)
    );

    const papers = await Promise.race([
      searchPubMedForEnzymeKinetics(enzyme, substrate, 5),
      timeoutPromise
    ]);

    for (const paper of papers) {
      if (!paper.doi) continue; // Skip papers without DOIs

      try {
        const resolvedPaper = await resolveDOIFromCrossRef(paper.doi);
        if (!resolvedPaper) continue;

        counter++;
        literature.push({
          id: `lit_pmid_${paper.pmid}`,
          doi: paper.doi,
          pubmedId: paper.pmid.toString(),
          title: paper.title,
          authors: paper.authors || [],
          year: paper.year,
          journal: paper.journal || 'Unknown',
          // NOT "peer-reviewed by definition". PubMed indexes preprints
          // (the NIH preprint pilot), editorials, letters, comments and
          // retracted articles. Asserting peer review from mere PubMed
          // membership is a fabricated claim, and this field feeds
          // LiteratureVerifier, which trusts it. The DOI is what gets
          // checked; review status is left unasserted rather than invented.
          peerReviewed: false,
          abstract: paper.abstract || '',
          domain: 'mm',
          extractedParameters: [] // Would be filled by full-text extraction
        });

        success(`✓ ${counter}. ${paper.title.substring(0, 60)}...`);
      } catch (err) {
        // Skip papers that can't be resolved
        continue;
      }
    }

    if (literature.length === 0) {
      // Said "Using default parameters." until ADR 0055 deleted
      // FALLBACK_PARAMETERS. The defaults were removed; the sentence
      // announcing them was not, so the message went on describing a
      // substitution that no longer happened.
      //
      // That direction of staleness is the dangerous one. A message
      // promising defaults that are not applied teaches a reader to distrust
      // a refusal that is actually working correctly -- and if they believe
      // it, they will go looking for which numbers were slipped in.
      return { outcome: 'empty' };
    }

    return { outcome: 'found', papers: literature };
  } catch (err) {
    // Classified by TYPE, not by reading the message.
    //
    // `PubMedUnavailableError` means no query strategy reached the registry,
    // so nothing was learned. Any other throw is a genuine fault in this
    // code path and is also not evidence of absence — but it is a different
    // fault, and saying "the registry was unreachable" about a bug here
    // would send someone to check their network for a problem in ours.
    //
    // "Continuing with user-provided parameters (unverified)" stood here,
    // written for the fallback ADR 0055 deleted; this function returns
    // papers, holds no parameters, and cannot continue with anything.
    if (err instanceof PubMedUnavailableError) {
      return { outcome: 'unavailable', reason: err.message };
    }
    return {
      outcome: 'unavailable',
      reason: `the search failed unexpectedly: ${
        err instanceof Error ? err.message : String(err)
      }`,
    };
  }
}

// ADR 0055 deleted FALLBACK_PARAMETERS from here:
//
//     /** Fallback to reasonable defaults when network is unavailable
//      *  These values are UNVERIFIED - marked as such in validation */
//     const FALLBACK_PARAMETERS = {
//       km: 5.2, vmax: 12.8, s0: 10.0, temperature: 37, pH: 7.4
//     };
//
// `km: 5.2` and `vmax: 12.8` are the same two numbers ADR 0044 removed from
// the dashboard's simulation form, and ADR 0024 names 5.2 specifically as the
// default this project must not have. They were still here, in the CLI,
// months later.
//
// Nothing referenced the constant. It was dead, which is why nobody noticed --
// and why no test could have found it. `check_no_unsourced_ui_numbers.py`
// scans HTML pages only, so a forbidden default in TypeScript was outside
// every guard the project had. `check_no_hardcoded_assay_conditions.py` found
// it on its first run, via the `temperature: 37` two lines below the Km.
//
// "Marked as UNVERIFIED in validation" is not a defence. A number that was
// never measured does not become admissible by being labelled; it becomes a
// number a reader has to remember to distrust.
//
// There is no replacement. A network failure means the parameters could not
// be resolved, and the honest response is to say so and stop.

// ============================================================================
// COMMANDS
// ============================================================================

/**
 * Read `--km 5.2mM --vmax 12.8mM/s` into numbers AND the units they declared.
 *
 * WHAT THIS REPLACED, AND WHY IT MATTERED
 *
 * Both `validate` and `simulate` did:
 *
 *     parameters[key] = parseFloat(value);
 *
 * `parseFloat('12.8mM/s')` is `12.8`. The unit was dropped on the floor.
 * `SimulationRequest.parameters` is `Record<string, number>`, so nothing
 * downstream could recover it, and the pipeline fell back to
 * `getAssumedUnitForUserInput` — a table keyed on the parameter's NAME,
 * which answers `μM/min` for vmax whatever the user wrote.
 *
 * So `--vmax 12.8mM/s` was computed as 12.8 μM/min. **A factor of 60,000**,
 * silently, on the first example in `help`. And the run then logged
 *
 *     "User supplied a bare number; unit was ASSUMED, not declared"
 *
 * which told the user they had omitted a unit they had in fact typed.
 *
 * `parseQuantity` was written to fix exactly this — its own docstring names
 * the 60,000 — and was wired into `--resolve` and `sweep` while these two
 * commands, the ones `help` leads with, kept `parseFloat`.
 *
 * The units channel already existed too: `providedProvenance[key].unit` is
 * preferred over the assumption at `scientificPipeline.ts:718`. Nothing had
 * to be invented; the declared unit only had to be carried the last inch.
 *
 * Only DECLARED units are forwarded. A bare `--km 5.2` still gets the
 * conventional unit and still warns, because that warning is now true.
 */
function readQuantities(params?: Record<string, string>): {
  parameters: Record<string, number>;
  provenance: Record<string, { source: string; unit: string }> | undefined;
} {
  const parameters: Record<string, number> = {};
  const provenance: Record<string, { source: string; unit: string }> = {};

  for (const [key, raw] of Object.entries(params ?? {})) {
    let quantity;
    try {
      quantity = parseQuantity(key, raw);
    } catch (err) {
      // Exit rather than fall back. A number whose unit could not be read
      // is the input this whole path exists to stop being guessed at.
      error(err instanceof Error ? err.message : String(err));
      process.exit(1);
    }
    parameters[key] = quantity.value;
    if (quantity.unitDeclared) {
      provenance[key] = { source: 'user', unit: quantity.unit };
    }
  }

  return {
    parameters,
    provenance: Object.keys(provenance).length > 0 ? provenance : undefined
  };
}

async function commandValidate(query: string, params?: Record<string, string>) {
  header('SCIENTIFIC VALIDATION');

  const pipeline = new ScientificPipeline();

  // NO LITERATURE IS FETCHED HERE, and that is a correction rather than a
  // limitation. This line used to be:
  //
  //     fetchRealLiterature('lactate dehydrogenase', 'lactate')
  //
  // so `validate "acetylcholinesterase km=5.2"` fetched papers about lactate
  // dehydrogenase and reported them as `Literature sources: N` beside the
  // user's own query. A provenance count attributing another system's papers
  // to your question is worse than no count at all.
  //
  // Fetching the *right* papers instead was considered and rejected: every
  // entry `fetchRealLiterature` builds carries `extractedParameters: []`, and
  // every consumer in literatureService reads exactly that field, so the
  // fetch has never contributed a single value to a verdict. Wiring it to
  // the user's enzyme would produce a truthful-looking source count backing
  // nothing — the same illusion, harder to spot.
  //
  // So the honest state is reported: zero sources, and a pointer to the
  // command that does resolve literature.
  pipeline.initializeLiterature([]);

  const { parameters, provenance } = readQuantities(params);

  info(`Query: ${query}`);
  if (Object.keys(parameters).length > 0) {
    info(`Parameters: ${JSON.stringify(parameters)}`);
  }

  console.log('');
  info('Running 4-layer validation...');

  try {
    const response = await pipeline.execute({
      query,
      parameters: Object.keys(parameters).length > 0 ? parameters : undefined,
      // Carries the unit the user actually typed. Without this the
      // pipeline falls back to a table keyed on the parameter NAME and
      // reads every vmax as uM/min -- 60,000x wrong for one in mM/s.
      providedProvenance: provenance
    });

    console.log('');

    if (!response.validated) {
      error('VALIDATION FAILED');
      console.log('\nErrors:');
      response.validationErrors.forEach((err, i) => {
        console.log(`  ${i + 1}. ${err}`);
      });
      process.exit(1);
    }

    success('VALIDATION PASSED');
    console.log(`\nConfidence: ${(response.validationConfidence * 100).toFixed(1)}%`);
    console.log(`Literature sources: ${response.metadata.literatureSourcesUsed}`);
    console.log(`Execution time: ${response.metadata.executionTimeMs}ms`);

    console.log('\n' + colors.dim + 'Reproducibility Key:' + colors.reset);
    console.log(`  ${response.reproducibilityKey.slice(0, 40)}...`);

    process.exit(0);
  } catch (err) {
    const errorMsg = err instanceof Error ? err.message : JSON.stringify(err);
    error(`Validation error: ${errorMsg}`);
    process.exit(1);
  }
}

async function commandSimulate(query: string, params?: Record<string, string>) {
  header('SCIENTIFIC SIMULATION');

  const pipeline = new ScientificPipeline();

  // Same correction as commandValidate: this fetched lactate dehydrogenase
  // papers for every query, and they carried no extracted parameters, so
  // they backed nothing while being counted as `Literature sources`.
  //
  // `simulate --resolve` is the literature-backed path — it goes through the
  // BRENDA/PubMed resolver, which returns values with units, organisms and
  // citations. This one runs the numbers you supply.
  pipeline.initializeLiterature([]);

  const { parameters, provenance } = readQuantities(params);

  info(`Query: ${query}`);
  if (Object.keys(parameters).length > 0) {
    info(`Parameters: ${JSON.stringify(parameters)}`);
  }

  console.log('');
  // THESE THREE LINES DESCRIBED A DIFFERENT COMMAND.
  //
  // They read "Resolving parameters... / Validating against literature... /
  // Running simulation..." — printed unconditionally, fifteen lines below
  // `pipeline.initializeLiterature([])`, which hands the pipeline an EMPTY
  // literature database on purpose. Nothing was resolved. No literature was
  // consulted. The comment above that call says so plainly: "This one runs
  // the numbers you supply."
  //
  // So the most-seen output in the product told a student it had searched
  // the literature, and then reported "no literature match" for every
  // parameter. A reader can only conclude Terrium looked and found nothing,
  // which is false — and it is false in the direction that makes the
  // product look empty rather than misconfigured.
  //
  // Same class as the CLI line that claimed "BRENDA and PubMed were
  // searched and returned nothing" while holding the papers (ADR 0109): a
  // reassuring progress message that is not true, in the exact spot where
  // the reader has no way to check.
  //
  // What this path actually does is now what it says.
  info('Checking the query and the values you supplied...');
  info('Running simulation...');

  try {
    const response = await pipeline.execute({
      query,
      parameters: Object.keys(parameters).length > 0 ? parameters : undefined,
      // Carries the unit the user actually typed. Without this the
      // pipeline falls back to a table keyed on the parameter NAME and
      // reads every vmax as uM/min -- 60,000x wrong for one in mM/s.
      providedProvenance: provenance
    });

    console.log('');

    // `validated: false` means NO SIMULATION RAN.
    //
    // A previous edit turned this branch into a warning and let the code
    // fall through to the results block. But the pipeline returns
    // `trajectory: []` on a validation failure, so falling through printed:
    //
    //     Results:
    //       Trajectory points: 0
    //       Initial value: undefined
    //       Final value: 0.000
    //
    // and exited 0. That is success-on-failure -- the same defect this CLI
    // was corrected for once already -- and it is worse than the strictness
    // it was trying to relax, because it reports a run that did not happen.
    //
    // The instinct behind that edit was right and is preserved below.
    // Refusing to run merely because a value is unbacked WAS wrong: an
    // experimental condition (s0, temperature, pH) is chosen by the
    // experimenter and cannot be cited, so blocking on it is a category
    // error (Stage 10 Part 16). But that was fixed where it belonged, in
    // Layer 1. `validated: false` no longer means "unbacked" -- a run on
    // entirely user-supplied values validates fine and simply scores zero
    // confidence. It now means the run could not be performed at all.
    //
    // So the honest split is: cannot run -> stop; ran but nothing backs it
    // -> report loudly, in the success path, where there are real numbers
    // to caveat.
    if (!response.validated) {
      error('SIMULATION DID NOT RUN');
      console.log('\nValidation errors:');
      response.validationErrors.forEach((err, i) => {
        console.log(`  ${i + 1}. ${err}`);
      });
      // THE OLD ADVICE ASKED FOR SOMETHING THE STUDENT HAD ALREADY GIVEN.
      //
      // It said "name a system to resolve them from literature with
      // --resolve" — to a reader who had just typed
      //
      //     simulate "michaelis menten of lactate dehydrogenase on pyruvate
      //               in Homo sapiens"
      //
      // The enzyme, the substrate and the organism are all in that sentence.
      // The tool asked them to say it again, in a syntax it did not show.
      //
      // Offering the command is NOT the silent inference the pipeline
      // forbids. Nothing is resolved here and no citation is attached; a
      // command is printed, and the student names the system explicitly by
      // running it. The guess never becomes provenance without a human in
      // between, which is the whole of the constraint.
      const system = parseSystemFromQuery(query);
      if (system !== null) {
        console.log(
          '\n' + colors.dim +
          'No trajectory was produced, so there are no results to show.\n' +
          'Your question names a system, so Terrium can look these up — it\n' +
          'just will not guess them out of a sentence. Run this and it will:' +
          colors.reset + '\n\n' +
          // `params` — the flags they already typed — is passed so the
          // suggestion carries them through instead of replacing them with a
          // template. Omitting it dropped a supplied `--vmax` and produced a
          // command that exits 2.
          formatResolveCommand(system, params ?? {}) + '\n\n' +
          colors.dim +
          'Check the three names first. They were read from your question,\n' +
          'and a citation attached to the wrong system is worse than none.' +
          colors.reset + '\n'
        );
      } else {
        // PLACEHOLDERS, NOT ANOTHER ENZYME'S NAME.
        //
        // This printed a fully-formed command naming `lactate dehydrogenase`,
        // whatever the student had typed. Measured:
        //
        //   $ simulate "acetylcholinesterase"
        //   -> scientific simulate "michaelis menten" --resolve \
        //        --enzyme "lactate dehydrogenase" --substrate pyruvate ...
        //
        // A student who copies that gets LDH results while believing they
        // asked about acetylcholinesterase — a real citation attached to a
        // system they never named, which this repository calls worse than no
        // provenance and which ADR 0059 already found three times over.
        //
        // It is worse than a generic example precisely because it looks
        // tailored: a complete command with a specific enzyme in it reads as
        // an answer rather than a template.
        //
        // The `if` branch above builds the command from the student's own
        // sentence when it can be parsed. This is the branch where it could
        // not, and the honest thing there is a slot they must fill: a
        // placeholder is never the wrong enzyme.
        console.log(
          '\n' + colors.dim +
          'No trajectory was produced, so there are no results to show.\n' +
          'Either supply the values in the query — e.g. --km 5.2 --vmax 12.8\n' +
          '--s0 10 — or name a system and let Terrium resolve them:\n' +
          colors.reset + '\n' +
          '  scientific simulate "michaelis menten" --resolve \\\n' +
          '    --enzyme "<enzyme>" --substrate "<substrate>" \\\n' +
          '    --organism "<organism>" --s0 10mM --enzyme-conc 0.001mM\n' +
          '\n' + colors.dim +
          'Replace the three names with your system. Terrium does not read\n' +
          'them out of your question, because a citation attached to a system\n' +
          'you did not name is worse than no citation at all.\n' +
          colors.reset
        );
      }
      process.exit(1);
    }

    if (response.validationConfidence === 0 || response.metadata.literatureSourcesUsed === 0) {
      // Ran, and is real, but nothing in the literature backs the numbers.
      // This is the state the earlier edit was reaching for.
      warning('SIMULATION COMPLETE — NO LITERATURE BACKING');
      console.log('  The run used your values. They are not literature-backed,');
      console.log('  and must not be reported as such.\n');
    } else {
      success('SIMULATION COMPLETE — LITERATURE BACKED');
    }

    console.log('\n' + colors.dim + 'Results:' + colors.reset);
    console.log(`  Trajectory points: ${response.results.trajectory.length}`);
    console.log(`  Initial value: ${response.results.trajectory[0]?.value.toFixed(3)} mM`);
    console.log(`  Final value: ${response.results.finalValue.toFixed(3)} mM`);
    console.log(`  Total consumed: ${(response.results.trajectory[0]?.value - response.results.finalValue).toFixed(3)} mM`);

    // ZERO PER CENT WAS NOT A MEASUREMENT.
    //
    // `validationConfidence` is, at source:
    //
    //     confidence: literatureSources.length > 1 ? 0.95
    //               : (literatureSources.length > 0 ? 0.92 : 0)
    //
    // a function of how many papers back the parameters, and of nothing
    // else. It does not move when the numbers are dimensionally sound,
    // inside plausibility bounds, or when every model assumption held.
    //
    // So on the most common path in the product -- a student typing three
    // values -- it is structurally 0, and this block printed
    //
    //     Quality:
    //       Validation confidence: 0.0%
    //       Overall confidence: 0.0%
    //
    // four lines after the pipeline logged "✓ All validation layers
    // passed". A number that can take exactly one value on a path is not a
    // score, and presenting it as one under the heading "Quality" tells a
    // student their correct simulation is worthless.
    //
    // Three states, the same discipline as resolved / unresolvable /
    // not_reported everywhere else here: a literature score, no literature
    // claim to score, or a failure. Not a zero standing in for the middle
    // one.
    console.log('\n' + colors.dim + 'Quality:' + colors.reset);
    if (response.metadata.literatureSourcesUsed === 0) {
      console.log('  Literature agreement: not applicable — this run made no');
      console.log('                        literature claim to check.');
      console.log('  What was checked:     units and dimensions, plausibility');
      console.log('                        bounds, and the model assumptions');
      console.log('                        listed above. All passed.');
      console.log(colors.dim +
        '  A literature score needs a literature claim. To make one:\n' +
        '  simulate mm --resolve --enzyme "<enzyme>" --substrate "<substrate>" \\\n' +
        '    --organism "<organism>" --s0 10mM --enzyme-conc 0.001mM' +
        colors.reset);
    } else {
      console.log(`  Literature agreement: ${(response.validationConfidence * 100).toFixed(1)}%`);
      console.log(`  Overall confidence: ${(response.metadata.confidenceScore * 100).toFixed(1)}%`);
      console.log(`  Literature sources: ${response.metadata.literatureSourcesUsed}`);
    }
    console.log(`  Execution time: ${response.metadata.executionTimeMs}ms`);

    console.log('\n' + colors.dim + 'Job ID (for reproducibility):' + colors.reset);
    console.log(`  ${response.jobId}`);

    console.log('\n' + colors.dim + 'Reproducibility Key:' + colors.reset);
    console.log(`  ${response.reproducibilityKey.slice(0, 40)}...`);

    // Show sample trajectory points
    console.log('\n' + colors.dim + 'Sample trajectory (every 10 points):' + colors.reset);
    console.log('  Time (s)  | Substrate (mM)');
    console.log('  ' + '-'.repeat(25));
    const step = Math.ceil(response.results.trajectory.length / 10);
    for (let i = 0; i < response.results.trajectory.length; i += step) {
      const point = response.results.trajectory[i];
      console.log(
        `  ${point.time.toFixed(1).padStart(8)} | ${point.value.toFixed(3).padStart(14)}`
      );
    }

    process.exit(0);
  } catch (err) {
    const errorMsg = err instanceof Error ? err.message : JSON.stringify(err);
    error(`Simulation error: ${errorMsg}`);
    process.exit(1);
  }
}

async function commandVerifyReproducibility(jobId: string) {
  header('REPRODUCIBILITY VERIFICATION');

  const pipeline = new ScientificPipeline();

  info(`Job ID: ${jobId}`);
  console.log('');
  info('Attempting to reproduce simulation...');

  try {
    const result = await pipeline.verifyReproducibility(jobId);

    console.log('');

    // THREE OUTCOMES, AND THE MIDDLE ONE USED TO SWALLOW THE THIRD.
    //
    // This was:
    //
    //     if (result.reproduced) success('FULLY REPRODUCIBLE');
    //     else warning('NUMERICALLY EQUIVALENT (within floating-point precision)');
    //     ...
    //     process.exit(0);
    //
    // `reproduced` is `verification.passed`, which already accounts for the
    // solver's declared tolerance. So the `else` branch was the FAILURE
    // branch, and it announced the failure as "numerically equivalent within
    // floating-point precision" and exited 0.
    //
    // Measured, by perturbing one recorded trajectory point: a replay
    // disagreeing by 33% printed "NUMERICALLY EQUIVALENT (within
    // floating-point precision)" and returned success. The engine had it
    // right the whole time — its own summary said "✗ NOT REPRODUCIBLE (max
    // relative error: 3.33e-1 exceeds the solver's declared tolerance)" —
    // and that line was printed two rows below the reassurance contradicting
    // it. A script checking the exit code saw a pass.
    //
    // Exit codes follow `resolve`: 0 verified, 2 a real negative answer,
    // 1 the check could not be performed.
    if (result.outputsIdentical) {
      success('FULLY REPRODUCIBLE — outputs are bit-for-bit identical');
    } else if (result.reproduced) {
      // A genuine middle state, and now it means what it says: the replay
      // differed, and the difference is inside the tolerance the solver
      // itself declares. That is a real and common outcome for floating
      // point, which is why the phrase existed — it was simply attached to
      // the wrong branch.
      success('REPRODUCIBLE — within the solver\'s declared tolerance');
      console.log(
        `${colors.dim}  Not bit-identical. Floating-point summation order is not${colors.reset}\n` +
          `${colors.dim}  guaranteed across runs; the disagreement is below the tolerance${colors.reset}\n` +
          `${colors.dim}  the solver declares for this problem.${colors.reset}`,
      );
    } else {
      error('NOT REPRODUCIBLE');
      console.log(
        `${colors.dim}  The replay used the recorded inputs and did not reproduce the${colors.reset}\n` +
          `${colors.dim}  recorded output, by more than the solver's declared tolerance.${colors.reset}`,
      );
    }

    console.log(`\nMax relative error: ${result.maxError.toExponential(2)}`);
    console.log(`Summary: ${result.summary}`);

    if (result.differences) {
      // Computed by the verifier and dropped at the pipeline boundary until
      // now, so a failing verification had nothing to say about why.
      console.log(`\n${colors.dim}Possible causes:${colors.reset}`);
      for (const cause of result.differences.possibleCauses) {
        console.log(`  • ${cause}`);
      }
      console.log(`\n${result.differences.conclusion}`);
    }

    process.exit(result.reproduced ? 0 : 2);
  } catch (err) {
    // Exit 1: the verification could not be performed. Distinct from exit 2,
    // which means it ran and the answer was no.
    const errorMsg = err instanceof Error ? err.message : JSON.stringify(err);
    error(`Verification could not be performed: ${errorMsg}`);
    process.exit(1);
  }
}

async function commandCheckIntegrity(jobId: string) {
  header('DATA INTEGRITY CHECK');

  const pipeline = new ScientificPipeline();

  info(`Job ID: ${jobId}`);
  console.log('');
  info('Checking data integrity...');

  try {
    const result = pipeline.checkIntegrity(jobId);

    console.log('');
    if (result.intact) {
      success('DATA INTACT - No corruption detected');
    } else {
      error('DATA CORRUPTION DETECTED');
      console.log('\nIssues:');
      result.issues.forEach((issue, i) => {
        console.log(`  ${i + 1}. ${issue}`);
      });
    }

    process.exit(result.intact ? 0 : 1);
  } catch (err) {
    const errorMsg = err instanceof Error ? err.message : JSON.stringify(err);
    error(`Integrity check failed: ${errorMsg}`);
    process.exit(1);
  }
}

/**
 * `literature <enzyme> --substrate S` — papers for a named system.
 *
 * THE ENZYME IS AN ARGUMENT NOW. IT USED TO BE A CONSTANT.
 * -------------------------------------------------------
 * This function took no parameters and called
 * `fetchRealLiterature('lactate dehydrogenase', 'lactate')`. Whatever the
 * user typed was discarded: `literature "acetylcholinesterase"` printed
 * papers about lactate dehydrogenase, under a heading naming no system, with
 * nothing on screen to say the results were for a different enzyme.
 *
 * That is the same hardcoded call the `simulate --resolve` header describes
 * as the old broken behaviour. It was fixed there and survived here, in the
 * one command whose entire output is a list of papers.
 *
 * The system is not inferred from free text, for the reason `resolve` gives:
 * attaching real papers to a system the user did not name is provenance for
 * the wrong measurement. Both parts must be stated, or the command refuses.
 */
async function commandLiterature(enzyme?: string, substrate?: string) {
  if (!enzyme || !substrate) {
    error('literature needs an enzyme and --substrate.');
    console.log(
      `\n${colors.dim}  Example: literature "lactate dehydrogenase" --substrate pyruvate${colors.reset}\n` +
        `${colors.dim}  The system is never inferred from free text: showing papers for a${colors.reset}\n` +
        `${colors.dim}  system you did not name is provenance for the wrong measurement.${colors.reset}\n`,
    );
    process.exit(1);
  }

  header(`PUBMED / CROSSREF — ${enzyme} / ${substrate}`);

  console.log(`${colors.dim}Fetching literature from PubMed and CrossRef...${colors.reset}\n`);

  try {
    const search = await fetchRealLiterature(enzyme, substrate);

    // "PubMed: 50+ million peer-reviewed papers" stood in this block, ten
    // lines below the code that deliberately sets `peerReviewed: false`
    // because PubMed indexes preprints, editorials, letters and retracted
    // articles. The blurb asserted exactly what the field refuses to. The
    // round counts are gone with it: unsourced numbers in a tool whose rule
    // is that numbers carry citations, and ones that go stale silently.
    const sources = () => {
      console.log('\nNote: literature is fetched live from:');
      console.log('  • PubMed — indexed biomedical literature. Indexing is not');
      console.log('    peer review: preprints, editorials, letters and retracted');
      console.log('    articles are all indexed, so review status is not asserted.');
      console.log('  • CrossRef — DOI resolution, used to confirm each paper exists.');
      console.log('  • BRENDA — enzyme kinetics, used by `resolve` (requires registration).');
    };

    // Exit 2: the search ran and this system has no indexed papers.
    if (search.outcome === 'empty') {
      warning(`PubMed returned no papers for ${enzyme} / ${substrate}.`);
      console.log(
        `\n${colors.dim}  The search completed — this is an answer, not a failure.${colors.reset}`,
      );
      sources();
      process.exit(2);
    }

    // Exit 1: the search could not be performed, so nothing was learned.
    // Reporting this as "no papers" would be an absence of evidence dressed
    // as evidence of absence, which is the one thing this tool must not do.
    if (search.outcome === 'unavailable') {
      error(`The literature search could not be performed: ${search.reason}`);
      console.log(
        `\n${colors.dim}  This is NOT "no papers exist". Nothing was learned about${colors.reset}\n` +
          `${colors.dim}  ${enzyme} / ${substrate} — the lookup itself did not run.${colors.reset}`,
      );
      sources();
      process.exit(1);
    }

    const literature = search.papers;
    const literatureService = new LiteratureService();
    for (const lit of literature) {
      literatureService.addLiterature(lit);
    }

    literature.forEach((lit, i) => {
      console.log(`${colors.bright}${i + 1}. ${lit.title}${colors.reset}`);
      console.log(`   Authors: ${lit.authors.join(', ')}`);
      console.log(`   Journal: ${lit.journal} (${lit.year})`);
      console.log(`   PMID: ${lit.pubmedId}`);
      console.log(`   DOI: ${lit.doi}`);
      console.log(`   URL: https://pubmed.ncbi.nlm.nih.gov/${lit.pubmedId}/`);
      console.log('');
    });

    const stats = literatureService.getStats();
    console.log(`${colors.dim}Statistics:${colors.reset}`);
    console.log(`  Total entries: ${stats.totalEntries}`);

    // Impact factor and citation count are NOT printed, because nothing
    // populates them.
    //
    // `fetchRealLiterature` never sets `impactFactor` or `citationCount` --
    // PubMed's esummary does not carry either, and no second source is
    // consulted. `getStats()` averages over the entries that have them,
    // finds none, and returns its `: 0` fallback. So this block printed
    //
    //     Avg impact factor: 0.00
    //     Avg citations: 0
    //
    // on every run since the command existed. Both read as findings about
    // the papers -- that these are uncited articles in journals with no
    // measurable impact -- when the true statement is that Terrium does not
    // know. It is the same zero-for-null inversion already corrected in the
    // perf collector, the response cache and the sweep analyser, reached
    // here through a helper's default rather than through a literal.
    //
    // Not printed at all rather than printed as "unknown": a statistics
    // block is read as a summary of what was measured, and a permanent
    // "unknown" line is a field asking to be filled by someone who assumes
    // the plumbing works.
    console.log(
      `  ${colors.dim}Impact factor and citation counts are not shown: PubMed's` +
        ` summary${colors.reset}`,
    );
    console.log(
      `  ${colors.dim}endpoint does not report them and Terrium does not` +
        ` estimate them.${colors.reset}`,
    );

    // Review status is likewise NOT summarised. `peerReviewed` is set to
    // `false` on every entry -- deliberately, because PubMed membership does
    // not establish peer review (see fetchRealLiterature). Printing
    // "Peer-reviewed: 0/5" would report that as a finding about the papers
    // rather than as Terrium declining to assert it.
    console.log(
      `  ${colors.dim}Review status is left unasserted; PubMed indexes preprints,` +
        `${colors.reset}`,
    );
    console.log(
      `  ${colors.dim}editorials, letters and retracted articles.${colors.reset}`,
    );

    process.exit(0);
  } catch (err) {
    error(`Failed to fetch literature: ${err instanceof Error ? err.message : String(err)}`);
    process.exit(1);
  }
}

function showHelp() {
  console.log(`
${colors.bright}Scientific Pipeline CLI${colors.reset}

${colors.dim}Validate and simulate scientific queries with literature backing${colors.reset}

${colors.bright}Usage:${colors.reset}
  npx ts-node src/cli/scientificCLI.ts <command> [options]

${colors.bright}Commands:${colors.reset}

  report --ec N --organism O --substrate S [--out PATH]
    ONE document you can hand in: the parameters with their sources and
    the conditions they were measured under, the values you chose marked
    as yours, what the literature disagrees about, the citations, and —
    the part no other tool prints — what Terrium would not do, and why.
    Written to PATH, or to stdout.
    ${colors.dim}Example:${colors.reset} report --ec 1.1.1.27 --organism "Homo sapiens" \\
      --substrate "(S)-lactate" --s0 10 --vmax 0.25 --out report.md

  catalog <ec-number> | --enzyme NAME [--json]
    What BRENDA actually reports for an enzyme, before you ask it for a
    value: which substrates, under the database's own labels; which
    organisms have rows; and which of km/ki/kcat it holds at all.
    Start here. BRENDA calls lactate "(S)-lactate", so a first query
    guessing "L-lactate" comes back empty and looks like the literature
    has nothing.
    ${colors.dim}Example:${colors.reset} catalog 1.1.1.27

  corpus <path-to-brenda-download.tsv> [--json]
    How much of BRENDA actually reports the pH and temperature a value was
    measured under, across a bulk download you fetched yourself.
    Nothing is downloaded automatically -- BRENDA asked that tools be gentle
    with their servers, and a statistics command that silently pulls a
    multi-megabyte export is not gentle.
    ${colors.dim}Example:${colors.reset} corpus ~/Downloads/brenda_km.tsv

  ensemble --enzyme E --substrate S --seed N [options]
    What the literature ACTUALLY supports, as a band rather than one number.
    Every other command picks a single value; when the published
    measurements disagree, this shows all of them -- weighted by how well
    evidenced each is -- and runs the model once per draw so you can see
    whether the disagreement changes the answer.
    ${colors.dim}Example:${colors.reset} ensemble --enzyme "lactate dehydrogenase" \\
               --substrate pyruvate --seed 1 --simulate michaelis_menten
    ${colors.dim}Options:${colors.reset}
      --seed N           required. An ensemble nobody can re-derive is not
                         evidence, so there is no default.
      --simulate DOMAIN  run the model per draw, e.g. michaelis_menten.
                         Without it you get the parameter spread and no
                         trajectory.
      --organism NAME    default "Homo sapiens"
      --fixture PATH     read a saved BRENDA table instead of looking
                         it up. Offline and checkable; the live path
                         is the one a student without a saved table has.
      --draws N          how many times to sample (default 2000)
      --json             machine-readable

  resolve <enzyme> --substrate S --organism O [options]
    Look up a measured kinetic parameter in the literature and show where it
    came from.
    Resolves through BRENDA (exact, then cross-species) and then PubMed.
    Never invents a value.
    ${colors.dim}Example:${colors.reset} resolve "lactate dehydrogenase" --substrate pyruvate --organism "Homo sapiens"
    ${colors.dim}Options:${colors.reset}
      --substrate NAME     substrate the constant was measured against (required)
      --organism NAME      organism to search for (required)
      --ec NUMBER          EC number, if you know it (else resolved via UniProt)
      --quantity km|ki|kcat  which constant to resolve (default: km)
      --cite NAME="SOURCE"  Attach a source to a value YOU supplied, e.g.
                           --cite km="Smith 2019, PMID 12345". Repeatable.
                           Terrium does not check that the source reports the
                           value — it records that the claim is yours, which is
                           still far better than the number arriving from
                           nowhere.
      --export-model PATH  Write the model with every parameter's origin
                           inside it, so the provenance travels with the file
                           rather than staying in this terminal.
                           .omex -> a COMBINE archive (Bergmann et al. 2014):
                           the annotated SBML, the simulation experiment as
                           SED-ML, and the citations. The only export a third
                           party can actually RE-RUN -- a model says what the
                           system is, not which time course was integrated.
                           .xml / .sbml -> SBML with MIRIAM RDF annotations,
                           the form other tools read without being told to.
                           Any other extension -> Antimony with the origin in
                           a comment. Comments are not part of the SBML data
                           model, so they are deleted by translation -- which
                           is why the SBML path exists.
      --export-citations PATH
                           Write every source behind the run as .bib or .ris,
                           importable into Zotero, Mendeley or EndNote. Author,
                           year and journal are absent rather than invented.
      --physiological "pH,tempC"
                           The conditions your model represents, e.g. "7.4,37"
                           for a human-like model or "7.0,70" for a thermophile.
                           Grades how far each measurement was taken from them.
                           No default: "physiological" means something different
                           for every organism.
      --physiological-basis TEXT
                           Where those conditions come from. Required with
                           --physiological — the yardstick needs provenance too.
      --physiological-tolerance "pH,tempC"
                           How far a measurement may drift and still count as
                           near. Defaults to 0.5 and 5 °C.
      --allow-cross-species
                           Accept a value measured in a DIFFERENT organism when
                           the one you asked for has none. Off by default.
                           Candidates must still pass an NCBI Taxonomy
                           relatedness check, so this permits a related
                           organism's value -- not any organism's. Whatever it
                           returns is still not a measurement of your organism.
      --enzyme-conc VALUE  [E]0, e.g. 0.001mM. Bridges a kcat to a usable
                           Vmax = kcat x [E]0. Never defaulted (ADR 0013).
      --json               machine-readable output
    ${colors.dim}Exit codes:${colors.reset} 0 found · 2 literature has nothing · 1 lookup could not run
    ${colors.dim}Those are different facts and the tool keeps them apart.${colors.reset}

  validate <model> [--km ... --vmax ... --s0 ...]
    Check that a model's parameters are present, plausible and dimensionally
    sound, without running it. The model must be named (${colors.dim}mm${colors.reset}, ${colors.dim}sir${colors.reset}); it is
    never inferred from free text. Parameters are supplied as flags, not
    written into the query string.
    ${colors.dim}Example:${colors.reset} validate "michaelis menten" --km 5.2 --vmax 12.8 --s0 10

  simulate [query] [options]
    Run a full simulation with validation
    ${colors.dim}Example:${colors.reset} simulate "michaelis menten" --km 5.2 --vmax 12.8 --s0 10
    ${colors.dim}Options:${colors.reset}
      --km VALUE       Michaelis constant, e.g. 5.2mM
      --vmax VALUE     Maximum velocity, e.g. 12.8uM/min or 0.01mM/s
      --s0 VALUE       Initial substrate concentration, e.g. 10mM
      --verbose        show the pipeline's structured logs

    ${colors.dim}Write the unit onto the number. A bare value is accepted but the${colors.reset}
    ${colors.dim}assumed unit is reported -- vmax in mM/s read as uM/min is off by 60,000x.${colors.reset}

  simulate <query> --resolve --enzyme E --substrate S --organism O [options]
    Look up the kinetics from literature, run the simulation, and print
    where every number came from. Refuses to run on anything it could not
    source -- no parameter is ever defaulted.
    ${colors.dim}Example:${colors.reset}
      simulate mm --resolve --enzyme "lactate dehydrogenase" \\
        --substrate pyruvate --organism "Homo sapiens" \\
        --s0 10mM --enzyme-conc 0.001mM
    ${colors.dim}Options:${colors.reset}
      --enzyme / --ec      which enzyme (never inferred from the query)
      --substrate NAME     substrate (required)
      --organism NAME      organism (required)
      --s0 VALUE           initial substrate -- an experimental condition
                           you choose, so it cannot be looked up
      --enzyme-conc VALUE  [E]0, needed for Vmax = kcat x [E]0
      --km / --vmax        supply either yourself; user values win
      --model NAME         michaelis-menten (default) or a competitive /
                           uncompetitive / non-competitive inhibition model,
                           which additionally resolves a Ki
      --sensitivity FRAC   report each parameter's influence at ±FRAC instead
                           of running a single trajectory, e.g. 0.1 for ±10%
      --allow-cross-species
                           as in \`resolve\`: permits a related organism's
                           value, still never any organism's
      --cite NAME="SOURCE" attach your own source to a value you supplied
      --physiological "pH,tempC" (with --physiological-basis TEXT)
                           the conditions your model represents. Without it
                           the condition-proximity axis reports not_assessed,
                           because "physiological" has no organism-independent
                           value (ADR 0012/0013)
      --export-model PATH  the model with its provenance inside it. The format
                           follows the extension:
                             .omex        a COMBINE archive — the model, the
                                          experiment that produced this result
                                          as SED-ML, and the sources, in one
                                          file somebody else can RE-RUN
                             .xml/.sbml   SBML with standard MIRIAM annotations
                                          that COPASI and JWS Online read
                             anything else Antimony, origin in a comment
                           Antimony comments do NOT survive translation to
                           SBML, so the three are not interchangeable.
      --export-citations PATH
                           every source behind the run as .bib or .ris
      --json               machine-readable output
    ${colors.dim}Exit codes:${colors.reset} 0 ran · 2 something unresolved · 1 lookup failed
    ${colors.dim}These options were all accepted here before they were listed here.${colors.reset}
    ${colors.dim}An undocumented flag is as unreachable as an unimplemented one.${colors.reset}

  sweep <model> --parameter NAME --range MIN:MAX:STEP [--km ... --vmax ... --s0 ...]
    Run the model across a range of one parameter and interpret the curve,
    rather than printing a column of numbers for you to squint at.
    Every other flag is read as a parameter with its unit, exactly as
    ${colors.dim}simulate${colors.reset} reads them, and its origin is reported the same way.
    ${colors.dim}Example:${colors.reset} sweep mm --parameter s0 --range 1:20:1 --km 0.5mM --vmax 0.1mM/s
    ${colors.dim}Options:${colors.reset}
      --parameter NAME     which parameter to vary (required)
      --range MIN:MAX:STEP three numbers, positive step, max > min (required)
      --json               machine-readable output

  history
    List past ${colors.dim}simulate --resolve${colors.reset} runs, most recent first, with how many of
    each run's parameters carried a literature citation. The run id printed
    at the end of a simulation is only useful if something can resolve it
    later; this is that something.
    ${colors.dim}Example:${colors.reset} history

  verify [jobId]
    Verify reproducibility of a past simulation
    ${colors.dim}Example:${colors.reset} verify job_001

  check-integrity [jobId]
    Check data integrity of a stored simulation
    ${colors.dim}Example:${colors.reset} check-integrity job_001

  literature <enzyme> --substrate S
    Search PubMed and CrossRef for papers on a named system, and list them
    with their PMIDs and DOIs. This is a LIVE search, not a bundled
    database -- it needs the network, and it reports nothing it did not
    fetch. Impact factors, citation counts and review status are not shown,
    because the endpoint does not report them.
    ${colors.dim}Example:${colors.reset} literature "lactate dehydrogenase" --substrate pyruvate

  help
    Show this help message

${colors.bright}Examples:${colors.reset}

  1. Validate parameters:
     npx ts-node src/cli/scientificCLI.ts validate "lactate dehydrogenase km=5"

  2. Run simulation with user parameters:
     npx ts-node src/cli/scientificCLI.ts simulate "michaelis menten" --km 5.2 --vmax 12.8

  3. Run simulation, let literature fill in missing parameters:
     npx ts-node src/cli/scientificCLI.ts simulate "lactate dehydrogenase"

  4. Verify reproducibility:
     npx ts-node src/cli/scientificCLI.ts verify job_001

  5. Find papers on a system:
     npx ts-node src/cli/scientificCLI.ts literature "lactate dehydrogenase" --substrate pyruvate
  `);
}

// ============================================================================
// MAIN
// ============================================================================

async function main() {
  const args = process.argv.slice(2);

  // Quiet by default. The pipeline logs a dozen structured lines per run;
  // on a terminal they buried the actual answer, which is the one thing a
  // CLI exists to show. `--verbose` restores them, and LOG_LEVEL still
  // wins if set explicitly. stderr already carries them, so `2>/dev/null`
  // works too -- this just makes the default sane.
  if (!args.includes('--verbose') && !process.env['LOG_LEVEL']) {
    process.env['LOG_LEVEL'] = 'fatal';
  }

  if (args.length === 0 || args[0] === 'help' || args[0] === '--help' || args[0] === '-h') {
    showHelp();
    process.exit(0);
  }

  const command = args[0];
  const rest = args.slice(1);

  switch (command) {
    case 'validate': {
      const query = rest[0];
      if (!query) {
        error('Query required');
        showHelp();
        process.exit(1);
      }

      // THE PARAMETERS WERE PARSED BY NOBODY AND DISCARDED.
      //
      // This was `await commandValidate(query)`. `commandValidate` declares
      // `params?: Record<string, string>` and builds its `parameters` object
      // from it — but no caller ever passed one, so `params` was always
      // `undefined`, `parameters` was always `{}`, and every required
      // parameter was reported missing:
      //
      //     ✗ VALIDATION FAILED
      //     1. Parameter 'km': Required parameter 'km' for domain 'mm' has no
      //        user-supplied value and no literature match
      //
      // even when the user had typed `--km 5.2 --vmax 12.8 --s0 10`. So
      // `validate` could not succeed for any input: the branch that reads the
      // user's numbers was unreachable, which is why it never looked wrong.
      //
      // An optional argument that every call site omits is a dead parameter,
      // and dead code is not merely unused — it is unexercised, which is
      // where confidently wrong behaviour lives. `simulate` two cases below
      // has always built and passed this; the two drifted apart silently
      // because nothing compared them.
      const { flags: validateFlags } = parseArgs(rest.slice(1));
      await commandValidate(query, validateFlags);
      break;
    }

    case 'simulate': {
      const query = rest[0];
      if (!query) {
        error('Query required');
        showHelp();
        process.exit(1);
      }

      // Was a hand-rolled `i += 2` loop, which advanced unconditionally --
      // so `--verbose --km 5` consumed "--km" as --verbose's value and
      // dropped km entirely. parseArgs handles boolean flags properly.
      const { flags, booleans } = parseArgs(rest.slice(1));

      // --resolve: look up what wasn't supplied, from the real literature
      // layer, and print the provenance of every number used.
      if (booleans.has('resolve')) {
        let substrate = flags['substrate'];
        let organism = flags['organism'];
        let enzyme = flags['enzyme'];
        const ec = flags['ec'];

        if (!substrate || !organism || (!enzyme && !ec)) {
          // SIX FLAGS TO RUN ONE SIMULATION WAS THE PROBLEM.
          //
          // This used to refuse outright, with a reason that is still
          // correct: "attaching a real citation to a system you did not name
          // is provenance for the wrong measurement." The constraint is
          // about a system NOBODY NAMED — so the question it actually asks
          // is whether a person named it, not whether a regex was involved.
          //
          // A confirmation answers that. The three names are read out of the
          // sentence, printed, and nothing is resolved until a human agrees
          // to them. At the instant a citation is attached, somebody has
          // read "lactate dehydrogenase / pyruvate / Homo sapiens" and said
          // yes — which is more explicit than three flags, because flags are
          // typed once and never re-read.
          //
          // With no terminal there is nobody to ask, so a pipe or a CI job
          // gets the old refusal plus the exact command. A default-confirm
          // would be the silent inference this forbids, with a prompt in the
          // code that nobody ever sees.
          const parsed = parseSystemFromQuery(query);
          const decision = parsed
            ? await confirmSystem(parsed, terminalIO(), {
                assumeYes: booleans.has('yes'),
              })
            : null;

          if (parsed && decision?.confirmed === true) {
            enzyme = parsed.enzyme;
            substrate = parsed.substrate;
            organism = parsed.organism;
          } else {
            error(
              '--resolve needs --substrate, --organism, and either --enzyme or --ec. ' +
              'The system is never inferred from the query text without your ' +
              'confirmation: attaching a real citation to a system you did not ' +
              'name is provenance for the wrong measurement.'
            );
            if (parsed) {
              // The parse succeeded and was refused, or could not be put. Say
              // which, because "declined" and "nobody was there to ask" are
              // different facts and only one of them means try again.
              console.error(
                '\n' + colors.dim +
                (decision?.confirmed === false && decision.reason === 'no-terminal'
                  ? 'Your question names a system, but nothing is attached to this\n' +
                    'terminal, so there was nobody to confirm it with. Either run\n' +
                    'this interactively, add --yes, or name it explicitly:'
                  : 'Not resolved. If the names below are right, run this:') +
                colors.reset + '\n\n' +
                formatResolveCommand(parsed) + '\n'
              );
            }
            process.exit(1);
          }
        }

        const overrides: Record<string, string> = {};
        for (const [k, v] of Object.entries(flags)) {
          if (['substrate', 'organism', 'enzyme', 'ec', 'enzyme-conc', 'sensitivity', 'model',
             'allow-cross-species', 'export-model', 'export-citations', 'cite',
             'physiological', 'physiological-basis', 'physiological-tolerance',
            ].includes(k)) continue;
          overrides[k] = v;
        }

        // --sensitivity[=0.1]: perturb each parameter and report the
        // effect beside where the parameter came from.
        let sensitivity: number | undefined;
        if (booleans.has('sensitivity')) {
          sensitivity = 0.1;
        } else if (flags['sensitivity']) {
          const parsed = Number(flags['sensitivity']);
          if (!Number.isFinite(parsed) || parsed <= 0 || parsed >= 1) {
            error(`--sensitivity must be a fraction between 0 and 1 (got '${flags['sensitivity']}')`);
            process.exit(1);
          }
          sensitivity = parsed;
        }

        const modelRaw = (flags['model'] ?? 'mm').toLowerCase();
        if (!['mm', 'competitive', 'noncompetitive', 'product'].includes(modelRaw)) {
          error(`--model must be mm, competitive, noncompetitive or product (got '${modelRaw}')`);
          process.exit(1);
        }

        // `--cite` is REPEATABLE, so it is read from raw argv rather than
        // from parseArgs' flat record -- where a second --cite would
        // silently overwrite the first and two citations would vanish
        // without a word.
        // The proximity axis was unreachable from the command that
        // actually runs simulations: `--physiological` was parsed only in
        // the `resolve` branch below. Same parser, same errors, so the two
        // commands cannot disagree about what a valid reference is.
        const simPhysiological = parsePhysiological(
          flags['physiological'],
          flags['physiological-tolerance'],
          flags['physiological-basis'],
        );
        if (simPhysiological.error) {
          error(simPhysiological.error);
          process.exit(1);
        }

        const citationResult = parseUserCitations(
          collectRepeated(rest, 'cite'),
          Object.keys(overrides),
        );
        if (citationResult.error) {
          error(citationResult.error);
          process.exit(1);
        }

        const code = await commandSimulateResolved({
          model: modelRaw as 'mm' | 'competitive' | 'noncompetitive' | 'product',
          enzyme,
          ec,
          substrate,
          organism,
          overrides,
          enzymeConc: flags['enzyme-conc'],
          json: booleans.has('json'),
          sensitivity,
          exportModel: flags['export-model'],
          exportCitations: flags['export-citations'],
          userCitations: citationResult.citations,
          physiologicalReference: simPhysiological.reference,
        });
        process.exit(code);
      }

      // Units are read from the value (`--km 5.2mM`), not assigned from a
      // table keyed on the parameter's NAME. The old path silently gave
      // vmax "uM/min" regardless of what the user meant, so a Vmax in mM/s
      // was reinterpreted by a factor of 60,000 and the run continued.
      //
      // THE VALUE IS FORWARDED AS TYPED, unit and all. This line read
      //
      //     params[key] = String(quantity.value);
      //
      // which parsed the unit, checked it, used it to decide whether to
      // warn -- and then threw it away before `commandSimulate` was
      // called. Downstream saw "12.8" and the pipeline assigned uM/min from
      // the parameter's name, so the 60,000x reinterpretation this comment
      // says was fixed was still happening, one level below the fix.
      //
      // Validating a unit and discarding it is the harder failure to see,
      // because every visible symptom of the original bug is gone: the
      // typo check works, the assumed-unit message is right, and the number
      // is still wrong.
      const params: Record<string, string> = {};
      const assumed: string[] = [];
      for (const [key, raw] of Object.entries(flags)) {
        if (key === 'json' || key === 'verbose') continue;
        try {
          const quantity = parseQuantity(key, raw);
          params[key] = raw;
          if (!quantity.unitDeclared) {
            assumed.push(`--${key} (assumed ${quantity.unit})`);
          }
        } catch (err) {
          error(err instanceof Error ? err.message : String(err));
          process.exit(1);
        }
      }

      // Named out loud rather than logged at debug level: the user needs to
      // know which of their numbers the tool interpreted rather than read.
      if (assumed.length > 0) {
        info(
          `Units not given for ${assumed.join(', ')}. Write them explicitly ` +
          `(e.g. --km 5.2mM) to remove the guess.`
        );
      }

      await commandSimulate(query, params);
      break;
    }

    // The first command a student should run, and the last one to exist.
    // Terrium advertises fifteen teaching domains and, until this, nothing
    // could tell anybody what they are: `help` listed nine commands, all
    // enzyme kinetics or generic, and the engine's own subcommands lived
    // behind a second CLI that `help` never mentions. See ADR 0122.
    // What the literature actually supports, as a band rather than one
    // number chosen by min(). Bakker's weighted sampling and Sauro's
    // "you can sample and get an ensemble distribution". See ADR 0135.
    case 'ensemble': {
      const { flags, booleans } = parseArgs(rest);
      const substrate = flags['substrate'];
      const seed = flags['seed'];
      // `--fixture` is optional now. Without it the ordinary resolver runs,
      // which is the only path a student who has no saved BRENDA table can
      // take -- and they are the person this command is for.
      if (!substrate || !seed || (!flags['fixture'] && !flags['enzyme'] && !flags['ec'])) {
        error(
          'ensemble needs --substrate <name> --seed <n>, and either ' +
          '--enzyme/--ec to look it up or --fixture <brenda.html> to read a ' +
          'saved table. The seed is required, not defaulted: an ensemble ' +
          'nobody can re-derive is not evidence.'
        );
        process.exit(1);
      }
      process.exit(commandEnsemble({
        ...(flags['fixture'] ? { fixture: flags['fixture'] } : {}),
        ...(flags['enzyme'] ? { enzyme: flags['enzyme'] } : {}),
        substrate,
        seed: Number(seed),
        ...(flags['organism'] ? { organism: flags['organism'] } : {}),
        ...(flags['ec'] ? { ec: flags['ec'] } : {}),
        ...(flags['draws'] ? { draws: Number(flags['draws']) } : {}),
        ...(flags['simulate'] ? { simulate: flags['simulate'] } : {}),
        ...(flags['points'] ? { points: Number(flags['points']) } : {}),
        json: booleans.has('json'),
      }));
      break;
    }

    case 'domains': {
      const { booleans } = parseArgs(rest);
      process.exit(commandDomains({ json: booleans.has('json') }));
      break;
    }

    case 'verify': {
      const jobId = rest[0];
      if (!jobId) {
        error('Job ID required');
        showHelp();
        process.exit(1);
      }
      await commandVerifyReproducibility(jobId);
      break;
    }

    case 'check-integrity': {
      const jobId = rest[0];
      if (!jobId) {
        error('Job ID required');
        showHelp();
        process.exit(1);
      }
      await commandCheckIntegrity(jobId);
      break;
    }

    case 'resolve': {
      const { flags, booleans } = parseArgs(rest);
      const substrate = flags['substrate'];
      const organism = flags['organism'];
      const enzyme = flags['enzyme'] ?? rest.find(a => !a.startsWith('--'));
      const ec = flags['ec'];

      if (!substrate || !organism || (!enzyme && !ec)) {
        error(
          'resolve needs a substrate, an organism, and either an enzyme name ' +
          'or an EC number.'
        );
        info('Example: resolve "lactate dehydrogenase" --substrate pyruvate --organism "Homo sapiens"');
        // Nothing is guessed from the query text: attaching a real citation
        // to a system the user never named is provenance for the wrong
        // measurement.
        process.exit(1);
      }

      const quantityRaw = (flags['quantity'] ?? 'km').toLowerCase();
      if (quantityRaw !== 'km' && quantityRaw !== 'ki' && quantityRaw !== 'kcat') {
        error(`--quantity must be km, ki or kcat (got '${quantityRaw}')`);
        process.exit(1);
      }

      let enzymeConc: number | undefined;
      if (flags['enzyme-conc']) {
        const parsed = parseQuantity('e0', flags['enzyme-conc']);
        // The Python bridge takes [E]0 in mM (ADR 0013), so convert rather
        // than assuming the user typed mM.
        enzymeConc = convertConcentration(parsed.value, parsed.unit, 'mM');
      }

      // `--allow-cross-species` is a boolean, but parseArgs decides that by
      // looking at the NEXT token: `--allow-cross-species lactate` parses as
      // the flag taking the value "lactate", and the opt-in silently does
      // not happen. For most flags that is a minor annoyance. For this one
      // it is the difference between a student getting a refusal they can
      // act on and getting one that ignores the action they already took --
      // so it is an error, not a shrug.
      if (flags['allow-cross-species'] !== undefined) {
        error(
          `--allow-cross-species takes no value (got '${flags['allow-cross-species']}'). ` +
          'It was probably written before a positional argument. Move it to the ' +
          'end, or after another flag, so it is not read as taking one.'
        );
        process.exit(1);
      }

      const physiological = parsePhysiological(
        flags['physiological'],
        flags['physiological-tolerance'],
        flags['physiological-basis'],
      );
      if (physiological.error) {
        error(physiological.error);
        process.exit(1);
      }

      const code = await commandResolve({
        enzyme,
        ec,
        substrate,
        organism,
        quantity: quantityRaw,
        enzymeConc,
        json: booleans.has('json'),
        allowCrossSpecies: booleans.has('allow-cross-species'),
        physiologicalReference: physiological.reference,
      });
      process.exit(code);
    }

    case 'report': {
      // ONE DOCUMENT A STUDENT CAN HAND IN.
      //
      // Terrium could resolve a value, record its provenance, parse the
      // assay conditions, grade it, run an ensemble, export BibTeX,
      // annotate a model and integrate it — nine capabilities, and nothing
      // a person could give a teacher. Each answered a question nobody
      // asks in isolation.
      //
      // Spawns the Python for the same reason every other export does:
      // one definition of what a resolved parameter is, and no second
      // place that can drift from it.
      const reportEc = flagValue(rest, '--ec');
      const reportOrganism = flagValue(rest, '--organism');
      const reportSubstrate = flagValue(rest, '--substrate');
      const destination = flagValue(rest, '--out');

      if (!reportEc || !reportOrganism || !reportSubstrate) {
        error(
          'report needs an enzyme, an organism and a substrate, e.g.\n' +
          '  scientific report --ec 1.1.1.27 --organism "Homo sapiens" \\\n' +
          '      --substrate "(S)-lactate" --s0 10 --vmax 0.25 --out report.md\n\n' +
          'Run `scientific catalog 1.1.1.27` first to see the substrate ' +
          "labels BRENDA actually uses — its label for lactate is " +
          '"(S)-lactate", so a reasonable guess comes back empty.',
        );
        process.exit(1);
      }

      const reportPayload = {
        title: flagValue(rest, '--title'),
        question: flagValue(rest, '--question'),
        ec: reportEc,
        organism: reportOrganism,
        parameters: [
          {
            name: flagValue(rest, '--quantity') ?? 'km',
            substrate: reportSubstrate,
            quantity: flagValue(rest, '--quantity') ?? 'km',
            allowCrossSpecies: rest.includes('--allow-cross-species'),
          },
        ],
        supplied: [
          ...(flagValue(rest, '--s0')
            ? [{ name: 's0', value: Number(flagValue(rest, '--s0')), unit: 'mM',
                 basis: flagValue(rest, '--s0-basis') }]
            : []),
          ...(flagValue(rest, '--vmax')
            ? [{ name: 'vmax', value: Number(flagValue(rest, '--vmax')) }]
            : []),
        ],
        s0: flagValue(rest, '--s0') ? Number(flagValue(rest, '--s0')) : undefined,
        vmax: flagValue(rest, '--vmax') ? Number(flagValue(rest, '--vmax')) : undefined,
      };

      const reportProc = spawnSync(
        resolvePythonExecutable(REPO_ROOT),
        [path.join(REPO_ROOT, 'scripts', 'report_lab.py')],
        { cwd: REPO_ROOT, input: JSON.stringify(reportPayload), encoding: 'utf-8' },
      );

      let reportParsed: { ok?: boolean; markdown?: string; error?: string;
                          refusals?: string[] };
      try {
        reportParsed = JSON.parse((reportProc.stdout ?? '').trim());
      } catch {
        error(
          'The report builder returned output this command could not read:\n' +
          `  ${(reportProc.stdout ?? reportProc.stderr ?? '').slice(0, 200)}`,
        );
        process.exit(1);
      }

      if (!reportParsed.ok || typeof reportParsed.markdown !== 'string') {
        error(reportParsed.error ?? 'The report could not be built.');
        process.exit(1);
      }

      if (destination) {
        fs.writeFileSync(path.join(process.cwd(), destination),
                         reportParsed.markdown, 'utf-8');
        // The refusal count goes on screen even when the document is
        // written to a file. A student who never opens it should still know
        // the report has something in it they need to read.
        const withheld = reportParsed.refusals?.length ?? 0;
        process.stdout.write(
          `Wrote ${destination}` +
          (withheld
            ? ` — ${withheld} thing(s) Terrium would not do are recorded in it.\n`
            : ' — nothing was withheld.\n'),
        );
      } else {
        process.stdout.write(reportParsed.markdown);
      }
      process.exit(0);
    }

    case 'catalog': {
      // WHAT THIS IS FOR
      //
      // Measured through the real resolver: `--substrate lactate` resolves
      // to 10.73 and `--substrate L-lactate` returns nothing, because
      // BRENDA's label is `(S)-lactate`. A student's first query guesses
      // three things at once — the substrate's exact label, an organism
      // that actually has rows, and whether the enzyme has that quantity
      // at all — and a wrong guess on any of them is indistinguishable
      // from "the literature has nothing".
      //
      // ADR 0118 made the miss name the substrates. This is the other
      // side: the first command need not be a refusal.
      //
      // Spawns the Python rather than reimplementing the parse, for the
      // same reason `corpus` does: one definition of BRENDA's page format,
      // and no second place that can drift from it.
      const ecNumber = rest.find((arg) => !arg.startsWith('--'));
      // A NAME is accepted too, and resolved through UniProt — but a name
      // is not an enzyme. "lactate dehydrogenase" is EC 1.1.1.27 (L-) and
      // EC 1.1.1.28 (D-), different proteins on different stereoisomers.
      // The Python side refuses and names both rather than picking, for
      // the reason a wrong EC is worse than a wrong value: it is a real
      // citation for the wrong enzyme.
      const enzymeAt = rest.indexOf('--enzyme');
      const enzyme = enzymeAt >= 0 ? rest[enzymeAt + 1] : undefined;

      if (!ecNumber && !enzyme) {
        error(
          'catalog needs an EC number or an enzyme name, e.g.\n' +
          '  scientific catalog 1.1.1.27\n' +
          '  scientific catalog --enzyme "alcohol dehydrogenase"\n\n' +
          'It reports which substrates, organisms and quantities BRENDA ' +
          'holds for that enzyme, so your first `resolve` can use the ' +
          "database's own labels instead of guessing them.",
        );
        process.exit(1);
      }

      const catalogProc = spawnSync(
        resolvePythonExecutable(REPO_ROOT),
        [path.join(REPO_ROOT, 'scripts', 'report_enzyme_catalog.py')],
        { cwd: REPO_ROOT, input: JSON.stringify({ ecNumber, enzyme }), encoding: 'utf-8' },
      );

      let parsed: { ok?: boolean; summary?: string; error?: string };
      try {
        parsed = JSON.parse((catalogProc.stdout ?? '').trim());
      } catch {
        error(
          'The catalog reader returned output this command could not read:\n' +
          `  ${(catalogProc.stdout ?? catalogProc.stderr ?? '').slice(0, 200)}`,
        );
        process.exit(1);
      }

      if (!parsed.ok) {
        error(parsed.error ?? 'The catalog could not be read.');
        process.exit(1);
      }

      if (rest.includes('--json')) {
        process.stdout.write(catalogProc.stdout ?? '');
      } else {
        // The sentence is built in Python, where the wording was argued
        // over. Rebuilding it here would be a second renderer of one fact
        // (ADR 0003), and the two would drift.
        process.stdout.write(`${parsed.summary}\n`);
      }
      process.exit(0);
    }

    case 'corpus': {
      // Spawns scripts/brenda_corpus_stats.py rather than reimplementing
      // the parser in TypeScript. There is one definition of BRENDA's bulk
      // format (Tests/brenda_bulk.py) and one place that can drift from it:
      // none.
      const target = rest.find((arg) => !arg.startsWith('--'));
      if (!target) {
        error(
          'corpus needs a path to a BRENDA bulk download, e.g.\n' +
          '  scientific corpus ~/Downloads/brenda_km.tsv\n\n' +
          'Nothing is fetched for you. The download URLs are in ' +
          'docs/EXPERT_FEEDBACK.md, section 1d.',
        );
        process.exit(1);
      }

      const args = [
        path.join(REPO_ROOT, 'scripts', 'brenda_corpus_stats.py'),
        target,
      ];
      if (rest.includes('--json')) args.push('--json');

      const proc = spawnSync(resolvePythonExecutable(REPO_ROOT), args, {
        cwd: REPO_ROOT,
        stdio: 'inherit',
      });
      process.exit(proc.status ?? 1);
    }

    case 'sweep': {
      // Runs the model across a range of one parameter and interprets the
      // curve, rather than printing a column of numbers.
      const { flags, booleans } = parseArgs(rest);
      const parameter = flags['parameter'];
      const range = flags['range'];

      // THE MODEL IS REQUIRED, AND THE DEFAULT USED TO BE UNRUNNABLE.
      //
      // This was `query: rest[0] && !rest[0].startsWith('--') ? rest[0] : 'sweep'`
      // — with no query, the literal string `'sweep'` was passed as the model
      // name. `'sweep'` is not a domain, so EVERY point in the sweep failed:
      //
      //     ✗ Every point in the sweep failed. The first reason was:
      //         Query 'sweep' does not name a domain this pipeline knows
      //
      // and the tool's own documented example — `sweep --parameter s0
      // --range 1:20:1 --km 0.5mM --vmax 0.1mM/s`, printed in `help` and
      // again in this command's own error message — omitted the query and so
      // could only ever produce that failure. Anyone following it concluded
      // the feature was broken, which was a fair reading.
      //
      // A default that is guaranteed to fail is worse than a required
      // argument: it defers the refusal past the point of running N
      // simulations, and it reports a usage mistake as a modelling failure.
      const query = rest[0] && !rest[0].startsWith('--') ? rest[0] : undefined;
      if (!query) {
        error('sweep needs a model to sweep, as its first argument.');
        info('Example: sweep mm --parameter s0 --range 1:20:1 --km 0.5mM --vmax 0.1mM/s');
        console.log(
          `${colors.dim}  The model is never inferred: sweeping the wrong system is not a${colors.reset}\n` +
            `${colors.dim}  partial answer, it is a different answer.${colors.reset}`,
        );
        process.exit(1);
      }

      if (!parameter || !range) {
        error('sweep needs --parameter NAME and --range MIN:MAX:STEP');
        info('Example: sweep mm --parameter s0 --range 1:20:1 --km 0.5mM --vmax 0.1mM/s');
        process.exit(1);
      }

      const bounds = range.split(':').map(Number);
      if (bounds.length !== 3 || bounds.some(n => !Number.isFinite(n))) {
        error(`--range must be MIN:MAX:STEP with three numbers (got '${range}')`);
        process.exit(1);
      }
      const [min, max, step] = bounds as [number, number, number];
      if (step <= 0 || max <= min) {
        error(`--range needs a positive step and max > min (got '${range}')`);
        process.exit(1);
      }

      const baseParameters: Record<string, number> = {};
      const provenance: Array<{ name: string; value: number; unit: string; origin: string; unitAssumed?: boolean }> = [];
      for (const [key, raw] of Object.entries(flags)) {
        if (['parameter', 'range'].includes(key)) continue;
        try {
          const quantity = parseQuantity(key, raw);
          baseParameters[key] = quantity.value;
          provenance.push({
            name: key,
            value: quantity.value,
            unit: quantity.unit,
            origin: 'user',
            unitAssumed: !quantity.unitDeclared,
          });
        } catch (err) {
          error(err instanceof Error ? err.message : String(err));
          process.exit(1);
        }
      }

      const code = await commandSweep({
        query,
        parameter,
        min,
        max,
        step,
        baseParameters,
        provenance,
        request: {},
        json: booleans.has('json'),
      });
      process.exit(code);
    }

    case 'history': {
      // Reads the on-disk store that `simulate --resolve` writes. Before
      // this existed, the CLI printed a job id at the end of every run
      // that no later command could resolve.
      const runs = JobManager.readHistory();
      if (runs.length === 0) {
        info(`No runs recorded yet (${historyPath()}).`);
        info('Run `simulate ... --resolve` and it will be saved here.');
        process.exit(0);
      }

      console.log(`\n${colors.bright}Past runs${colors.reset}  ${colors.dim}${historyPath()}${colors.reset}\n`);
      for (const run of runs.slice(-20).reverse()) {
        const cited = Array.isArray(run.provenance)
          ? run.provenance.filter((p: any) => p?.citation).length
          : 0;
        const total = Array.isArray(run.provenance) ? run.provenance.length : 0;
        console.log(
          `  ${run.jobId}  ${colors.dim}${run.at.slice(0, 19).replace('T', ' ')}${colors.reset}  ${run.query}`
        );
        console.log(
          `  ${' '.repeat(run.jobId.length)}  ${colors.dim}final ${run.finalValue?.toFixed?.(4) ?? '?'} · ${cited}/${total} parameters cited${colors.reset}`
        );
      }
      console.log('');
      process.exit(0);
    }

    case 'literature': {
      const query = rest[0];
      const { flags } = parseArgs(rest.slice(1));
      commandLiterature(query, flags['substrate']);
      break;
    }

    default:
      error(`Unknown command: ${command}`);
      showHelp();
      process.exit(1);
  }
}

main().catch(err => {
  error(`Fatal error: ${err}`);
  process.exit(1);
});
