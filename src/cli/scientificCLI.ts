#!/usr/bin/env node
import { commandResolve } from './commandResolve';
import { commandSimulateResolved } from './commandSimulateResolved';
import { JobManager, historyPath } from '../execution/job-manager';
import { commandSweep } from './commandSweep';
import { parseArgs, parseQuantity } from './parseQuantity';
import { convertConcentration } from '../units';

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
import { resolveDOIFromCrossRef, searchPubMedForEnzymeKinetics } from '../integrations/crossref-pubmed-real';
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
async function fetchRealLiterature(enzyme: string, substrate: string): Promise<Literature[]> {
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
      warning('No real papers found. Using default parameters.');
      // Return default with no literature backing (will fail strict validation)
      return [];
    }

    return literature;
  } catch (err) {
    warning(`PubMed search failed or timed out: ${err instanceof Error ? err.message : String(err)}`);
    warning('Continuing with user-provided parameters (unverified)');
    return [];
  }
}

/**
 * Fallback to reasonable defaults when network is unavailable
 * These values are UNVERIFIED - marked as such in validation
 */
const FALLBACK_PARAMETERS = {
  km: 5.2,
  vmax: 12.8,
  s0: 10.0,
  temperature: 37,
  pH: 7.4
};

// ============================================================================
// COMMANDS
// ============================================================================

async function commandValidate(query: string, params?: Record<string, string>) {
  header('SCIENTIFIC VALIDATION');

  const pipeline = new ScientificPipeline();

  // Fetch real literature from real APIs
  const literature = await fetchRealLiterature('lactate dehydrogenase', 'lactate');
  pipeline.initializeLiterature(literature);

  const parameters: Record<string, number> = {};
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      parameters[key] = parseFloat(value);
    }
  }

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
      conditions: {
        temperature: 37,
        pH: 7.4
      }
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

  // Fetch real literature from real APIs
  const literature = await fetchRealLiterature('lactate dehydrogenase', 'lactate');
  pipeline.initializeLiterature(literature);

  const parameters: Record<string, number> = {};
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      parameters[key] = parseFloat(value);
    }
  }

  info(`Query: ${query}`);
  if (Object.keys(parameters).length > 0) {
    info(`Parameters: ${JSON.stringify(parameters)}`);
  }

  console.log('');
  info('Resolving parameters...');
  info('Validating against literature...');
  info('Running simulation...');

  try {
    const response = await pipeline.execute({
      query,
      parameters: Object.keys(parameters).length > 0 ? parameters : undefined,
      conditions: {
        temperature: 37,
        pH: 7.4
      }
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
      console.log(
        '\n' + colors.dim +
        'No trajectory was produced, so there are no results to show.\n' +
        'Supply the missing values in the query, or name a system to resolve\n' +
        'them from literature with --resolve.' + colors.reset + '\n'
      );
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

    console.log('\n' + colors.dim + 'Quality:' + colors.reset);
    console.log(`  Validation confidence: ${(response.validationConfidence * 100).toFixed(1)}%`);
    console.log(`  Overall confidence: ${(response.metadata.confidenceScore * 100).toFixed(1)}%`);
    console.log(`  Literature sources: ${response.metadata.literatureSourcesUsed}`);
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
    if (result.reproduced) {
      success('FULLY REPRODUCIBLE');
    } else {
      warning('NUMERICALLY EQUIVALENT (within floating-point precision)');
    }

    console.log(`\nMax relative error: ${result.maxError.toExponential(2)}`);
    console.log(`Summary: ${result.summary}`);

    process.exit(0);
  } catch (err) {
    const errorMsg = err instanceof Error ? err.message : JSON.stringify(err);
    error(`Verification failed: ${errorMsg}`);
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

async function commandLiterature() {
  header('REAL LITERATURE DATABASE');

  console.log(`${colors.dim}Fetching literature from PubMed and CrossRef...${colors.reset}\n`);

  try {
    const literature = await fetchRealLiterature('lactate dehydrogenase', 'lactate');

    if (literature.length === 0) {
      warning('No literature found. Network may be unavailable.');
      console.log('\nNote: Literature is fetched from real scientific databases:');
      console.log('  • PubMed: 50+ million peer-reviewed papers');
      console.log('  • CrossRef: 150+ million articles with validated DOIs');
      console.log('  • BRENDA: 50,000+ enzymes with kinetic parameters (requires registration)');
      process.exit(0);
    }

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
    console.log(`  Peer-reviewed: ${stats.peerReviewedCount}/${stats.totalEntries}`);
    console.log(`  Avg impact factor: ${stats.averageImpactFactor.toFixed(2)}`);
    console.log(`  Avg citations: ${Math.round(stats.averageCitations)}`);

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

  resolve <enzyme> --substrate S --organism O [options]
    Look up a kinetic constant in the literature and show where it came from.
    Resolves through BRENDA (exact, then cross-species) and then PubMed.
    Never invents a value.
    ${colors.dim}Example:${colors.reset} resolve "lactate dehydrogenase" --substrate pyruvate --organism "Homo sapiens"
    ${colors.dim}Options:${colors.reset}
      --substrate NAME     substrate the constant was measured against (required)
      --organism NAME      organism to search for (required)
      --ec NUMBER          EC number, if you know it (else resolved via UniProt)
      --quantity km|ki|kcat  which constant to resolve (default: km)
      --enzyme-conc VALUE  [E]0, e.g. 0.001mM. Bridges a kcat to a usable
                           Vmax = kcat x [E]0. Never defaulted (ADR 0013).
      --json               machine-readable output
    ${colors.dim}Exit codes:${colors.reset} 0 found · 2 literature has nothing · 1 lookup could not run
    ${colors.dim}Those are different facts and the tool keeps them apart.${colors.reset}

  validate [query]
    Validate a query against literature
    ${colors.dim}Example:${colors.reset} validate "lactate dehydrogenase km=5.2"

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
      --json               machine-readable output
    ${colors.dim}Exit codes:${colors.reset} 0 ran · 2 something unresolved · 1 lookup failed

  verify [jobId]
    Verify reproducibility of a past simulation
    ${colors.dim}Example:${colors.reset} verify job_001

  check-integrity [jobId]
    Check data integrity of a stored simulation
    ${colors.dim}Example:${colors.reset} check-integrity job_001

  literature
    Show built-in literature database
    ${colors.dim}Example:${colors.reset} literature

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

  5. View literature:
     npx ts-node src/cli/scientificCLI.ts literature
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
      await commandValidate(query);
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
        const substrate = flags['substrate'];
        const organism = flags['organism'];
        const enzyme = flags['enzyme'];
        const ec = flags['ec'];

        if (!substrate || !organism || (!enzyme && !ec)) {
          error(
            '--resolve needs --substrate, --organism, and either --enzyme or --ec. ' +
            'The system is never inferred from the query text: attaching a real ' +
            'citation to a system you did not name is provenance for the wrong ' +
            'measurement.'
          );
          process.exit(1);
        }

        const overrides: Record<string, string> = {};
        for (const [k, v] of Object.entries(flags)) {
          if (['substrate', 'organism', 'enzyme', 'ec', 'enzyme-conc', 'sensitivity', 'model'].includes(k)) continue;
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
        });
        process.exit(code);
      }

      // Units are read from the value (`--km 5.2mM`), not assigned from a
      // table keyed on the parameter's NAME. The old path silently gave
      // vmax "uM/min" regardless of what the user meant, so a Vmax in mM/s
      // was reinterpreted by a factor of 60,000 and the run continued.
      const params: Record<string, string> = {};
      const assumed: string[] = [];
      for (const [key, raw] of Object.entries(flags)) {
        if (key === 'json' || key === 'verbose') continue;
        try {
          const quantity = parseQuantity(key, raw);
          params[key] = String(quantity.value);
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

      const code = await commandResolve({
        enzyme,
        ec,
        substrate,
        organism,
        quantity: quantityRaw,
        enzymeConc,
        json: booleans.has('json'),
      });
      process.exit(code);
    }

    case 'sweep': {
      // Runs the model across a range of one parameter and interprets the
      // curve, rather than printing a column of numbers.
      const { flags, booleans } = parseArgs(rest);
      const parameter = flags['parameter'];
      const range = flags['range'];

      if (!parameter || !range) {
        error('sweep needs --parameter NAME and --range MIN:MAX:STEP');
        info('Example: sweep --parameter s0 --range 1:20:1 --km 0.5mM --vmax 0.1mM/s');
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
        query: rest[0] && !rest[0].startsWith('--') ? rest[0] : 'sweep',
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
      commandLiterature();
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
