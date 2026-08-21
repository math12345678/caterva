/**
 * `scientific resolve` — look up a measured kinetic parameter in the
 * literature and
 * show where it came from.
 *
 * This is the command the tool exists for. Everything else in this CLI
 * either validates numbers you already have or runs a simulation; this is
 * the one that answers the question a student or bench scientist actually
 * starts with: *what is the Km of this enzyme for this substrate, and who
 * measured it?*
 *
 * It resolves through Terrium's real literature layer — BRENDA exact match,
 * then BRENDA cross-species, then PubMed candidates — via the same
 * `science_agent_runner.py` bridge the production API server uses. It never
 * fabricates a number, and it distinguishes three outcomes that most tools
 * collapse into one:
 *
 *   found          a real measurement, with its unit, organism and citation
 *   not found      the literature genuinely has nothing for this system
 *   unavailable    the lookup could not be performed at all
 *
 * The third is the one that matters. "BRENDA has no Km for this" and "we
 * could not reach BRENDA" are different facts, and a tool that reports them
 * identically teaches its user to trust an absence of evidence as evidence
 * of absence.
 */

import {
  ResolverUnavailableError,
  resolveKinetic,
  type KineticQuantity,
} from '../literature/literatureResolver';

const BOLD = '[1m';
const DIM = '[2m';
const RED = '[31m';
const GREEN = '[32m';
const YELLOW = '[33m';
const RESET = '[0m';

/** Colour only when attached to a terminal, so piped output stays clean. */
const useColour = process.stdout.isTTY === true;
const c = (code: string, text: string): string =>
  useColour ? `${code}${text}${RESET}` : text;

export interface ResolveOptions {
  enzyme?: string;
  ec?: string;
  substrate: string;
  organism: string;
  quantity: KineticQuantity;
  /** [E]0 in mM, only meaningful for kcat -> Vmax (ADR 0013). */
  enzymeConc?: number;
  /** --allow-cross-species. Off unless the flag is present (ADR 0024). */
  allowCrossSpecies?: boolean;
  /** --physiological "7.4,37" [--physiological-tolerance "0.4,5"] */
  physiologicalReference?: {
    ph: number;
    temperatureC: number;
    basis: string;
    phTolerance: number;
    temperatureToleranceC: number;
  };
  json: boolean;
}

/**
 * Returns a process exit code.
 *
 * 0 = a value was resolved. 1 = the lookup could not be performed.
 * 2 = the lookup ran and the literature has nothing.
 *
 * Distinct codes because a script piping this needs to tell "no data" from
 * "no network", and an exit code is the only channel that survives `--json`
 * being parsed by something else.
 */
export async function commandResolve(options: ResolveOptions): Promise<number> {
  const { substrate, organism, quantity } = options;

  let result;
  try {
    result = await resolveKinetic({
      enzymeName: options.enzyme,
      ecNumber: options.ec,
      substrate,
      organism,
      quantity,
      enzymeConc: options.enzymeConc,
      allowCrossSpecies: options.allowCrossSpecies === true,
      physiologicalReference: options.physiologicalReference,
    });
  } catch (err) {
    if (err instanceof ResolverUnavailableError) {
      if (options.json) {
        process.stdout.write(
          JSON.stringify(
            { ok: false, status: 'unavailable', reason: err.message },
            null,
            2,
          ) + '\n',
        );
      } else {
        process.stderr.write(
          `${c(RED, '✗')} Could not perform the lookup: ${err.message}\n` +
            `${c(DIM, '  This is NOT the same as "no value exists". Nothing was learned about ')}\n` +
            `${c(DIM, '  ' + quantity + ' for this system.')}\n`,
        );
      }
      return 1;
    }
    throw err;
  }

  if (!result.found) {
    if (options.json) {
      process.stdout.write(
        JSON.stringify(
          {
            ok: true,
            status: 'not_found',
            quantity,
            logs: result.logs,
            // Machine-readable too, not only in the prose above. A script
            // driving `resolve --json` is exactly the caller who would go
            // and fetch these.
            candidates: result.candidates,
          },
          null,
          2,
        ) + '\n',
      );
    } else {
      const papers = result.candidates;
      process.stdout.write(
        `${c(YELLOW, '○')} No ${quantity} found for ` +
          `${c(BOLD, options.enzyme ?? options.ec ?? '?')} / ${substrate} / ${organism}.\n`,
      );
      // THE OLD SENTENCE WAS FALSE EXACTLY WHEN THE FALLBACK WORKED.
      //
      // It read: "BRENDA and PubMed were searched and returned nothing."
      // PubMed had not returned nothing -- it had returned papers, which
      // this command then discarded. The most reassuring line the CLI
      // prints was untrue in the one case where the student most needed
      // somewhere to go next.
      //
      // Two messages now, because they are two different facts, and ADR
      // 0065's rule applies: a search that found nothing and a search that
      // found something nobody used must not share a rendering.
      if (papers.length === 0) {
        process.stdout.write(
          `${c(DIM, '  BRENDA and PubMed were searched and returned nothing. This is an')}\n` +
            `${c(DIM, '  answer, not a failure — no value has been invented to fill the gap.')}\n`,
        );
      } else {
        process.stdout.write(
          `${c(DIM, '  BRENDA had no value, and no number has been invented to fill the gap.')}\n` +
            `${c(DIM, `  The literature search did find ${papers.length} paper(s) that may report it.`)}\n` +
            `${c(DIM, '  Terrium does not read numbers out of full text, so these are for you:')}\n\n`,
        );
        for (const paper of papers) {
          const locator = paper.pmid
            ? `PMID ${paper.pmid}`
            : paper.doi
              ? `doi ${paper.doi}`
              : (paper.url ?? '');
          process.stdout.write(
            `    ${c(BOLD, paper.title)}\n` +
              `${c(DIM, `      ${locator}${paper.source ? `  ·  ${paper.source}` : ''}`)}\n`,
          );
        }
        process.stdout.write(
          `\n${c(DIM, `  Found one? Pass it with --${quantity} and record where it came from`)}\n` +
            `${c(DIM, `  with --cite ${quantity}="..." so the value keeps its source.`)}\n`,
        );
      }
      if (result.logs.length > 0) {
        process.stdout.write(`\n${c(DIM, '  Search path:')}\n`);
        for (const line of result.logs) {
          process.stdout.write(`${c(DIM, '    ' + line)}\n`);
        }
      }
    }
    return 2;
  }

  if (options.json) {
    process.stdout.write(JSON.stringify({ ok: true, status: 'found', ...result }, null, 2) + '\n');
    return 0;
  }

  const label = quantity.toUpperCase();
  process.stdout.write(
    `\n${c(GREEN, '✓')} ${c(BOLD, `${label} = ${result.value} ${result.unit}`)}\n\n`,
  );

  const rows: Array<[string, string]> = [
    ['System', `${options.enzyme ?? options.ec ?? '?'} / ${substrate}`],
    ['Organism', result.organism ?? '(not reported)'],
    ['Source', result.source],
  ];

  if (result.citation) {
    const ref = result.citation.reference_id;
    rows.push(['Citation', `${result.citation.source}${ref ? ` ref ${ref}` : ''}`]);
    if (typeof result.citation.url === 'string') {
      rows.push(['URL', result.citation.url]);
    }
  } else {
    rows.push(['Citation', '(none returned — treat as unverified)']);
  }

  if (result.bridgedVmax !== undefined) {
    rows.push([
      'Vmax',
      `${result.bridgedVmax} mM/s  ${DIM}= kcat × [E]0, computed by the engine${RESET}`,
    ]);
  }

  const width = Math.max(...rows.map(([k]) => k.length));
  for (const [key, value] of rows) {
    process.stdout.write(`  ${c(DIM, key.padEnd(width))}  ${value}\n`);
  }

  // The warning that must never be buried. A cross-species value is real
  // and citable, but it was measured in a DIFFERENT organism than the one
  // asked about, and presenting it as an exact match is how a number ends
  // up in a report attributed to the wrong species.
  if (result.crossSpecies) {
    process.stdout.write(
      `\n${c(YELLOW, '⚠')} ${c(BOLD, 'Cross-species match.')} This was measured in ` +
        `${result.organism ?? 'another organism'}, not ${organism}.\n` +
        `${c(DIM, '  Real and citable, but do not report it as a ' + organism + ' measurement.')}\n`,
    );
  }

  // WHAT EACH SURVIVING VALUE IS WORTH (Bakker; ADR 0137)
  //
  // The tie block below says the evidence did not choose. This says how much
  // each alternative WEIGHS -- the three axes graded per candidate, which is
  // what an ensemble samples by.
  //
  // Printed on the ordinary `resolve` path, not only inside `scientific
  // ensemble`, because a finding built for one front end reaches half the
  // users. The API renders the same grades into provenance.flags; this is
  // the other half of that pair, and `check_both_front_ends_read_it.py`
  // fails the build when only one of them exists.
  if (result.ensembleCandidates && result.ensembleCandidates.length > 1) {
    const rows = result.ensembleCandidates;
    process.stdout.write(
      `\n${c(DIM, `${rows.length} published values survive the evidence ranking:`)}\n`,
    );
    for (const row of rows) {
      const unit = row.unit ? ` ${row.unit}` : '';
      const ref = row.reference_id ? c(DIM, `  [ref ${row.reference_id}]`) : '';
      process.stdout.write(`    ${row.value}${unit}${ref}\n`);
      process.stdout.write(
        c(DIM, `        ${row.grades.assay_completeness} / ` +
          `${row.grades.condition_proximity} / ${row.grades.organism_match}\n`),
      );
    }
    // Named, not described. A reader shown a spread with no way to act on it
    // is left where ADR 0115 found them.
    process.stdout.write(
      c(DIM, '  These grades are the weights an ensemble samples by. To see\n') +
      c(DIM, '  whether the disagreement changes the answer:\n') +
      `    ${c(BOLD, 'scientific ensemble --enzyme ... --substrate ... --seed 1 --simulate michaelis_menten')}\n`,
    );
  }

  // THE EVIDENCE DID NOT CHOOSE THIS NUMBER (Bakker; ADR 0048/0051)
  //
  // Printed high, next to the cross-species warning, because it is the same
  // class of caveat: something about the ANSWER that a reader would
  // otherwise assume away. A value shown alone reads as "the" value.
  //
  // `evidence_rank.py` narrows candidates to the non-dominated frontier --
  // no row survives that another beats on every axis -- and among those
  // nothing is beaten outright, so `min()` chooses. That choice is
  // arbitrary, and until now it was arbitrary and SILENT on this front end.
  // The API path has said so since ADR 0051; the CLI said nothing, which is
  // the defect `check_both_front_ends_read_it.py` was written to find.
  //
  // On the LDH turnover table: six rows from 21.1 to 6467, every one
  // wild-type with pH and temperature reported. The CLI printed 21.1.
  if (result.selectionTie && result.selectionTie.candidates.length > 1) {
    const tie = result.selectionTie;
    const span =
      tie.low !== null && tie.high !== null
        ? `${tie.low} to ${tie.high}` +
          (tie.fold_range !== null ? `, a ${tie.fold_range.toPrecision(3)}-fold range` : '')
        : 'a range the resolver did not report';
    process.stdout.write(
      `\n${c(YELLOW, '⚠')} ${c(BOLD, 'The evidence did not choose this value.')}\n` +
        `${c(DIM, `  ${tie.candidates.length} rows were ranked equally well evidenced, spanning ${span}.`)}\n` +
        // The resolver's own sentence, verbatim. Rewording it here would
        // make this a second place the finding's wording can drift, and the
        // Python module is where it was argued over.
        `${c(DIM, '  ' + tie.reason)}\n\n`,
    );
    for (const cand of tie.candidates) {
      // Named alternatives, because a bare count is unactionable: the
      // reader has to be able to go and look at the row that was not
      // returned. Same reasoning as the API flag, same fields.
      const mark = cand.selected ? c(BOLD, '  → ') : '    ';
      const ref = cand.reference_id ? c(DIM, `  [ref ${cand.reference_id}]`) : '';
      const returned = cand.selected ? c(DIM, '  (returned)') : '';
      process.stdout.write(
        `${mark}${cand.value}${cand.unit ? ' ' + cand.unit : ''}${ref}${returned}\n` +
          (cand.conditions ? `${c(DIM, '        ' + cand.conditions)}\n` : ''),
      );
    }
  }

  // WHAT PROTEIN THIS WAS MEASURED ON (ADR 0029)
  //
  // Printed directly under the cross-species warning because it is the same
  // question one step in: not "was this a different organism" but "was this
  // a different protein". A Y337A mutant's kcat is real, cited, and not the
  // enzyme's — substitutions are chosen precisely because they change the
  // kinetics.
  //
  // `unstated` gets a line too, and that is the deliberate part. It is the
  // majority of BRENDA, it is NOT wild-type, and a reader shown nothing
  // would assume the row was the enzyme as found. Absence of a warning is
  // not a statement; only one of the two is checkable.
  if (result.variant) {
    const v = result.variant;
    if (v.status === 'variant') {
      const what = v.kind === 'isozyme' ? 'a named isozyme' : 'a sequence variant';
      process.stdout.write(
        `\n${c(YELLOW, '⚠')} ${c(BOLD, 'Measured on ' + what + '.')} ` +
          `The source says ${v.evidence ?? '(unnamed)'}.\n` +
          `${c(DIM, '  ' + v.reason)}\n`,
      );
    } else if (v.status === 'wild_type') {
      process.stdout.write(
        `\n${c(GREEN, '✓')} ${c(DIM, 'Source states the enzyme as found (' + (v.evidence ?? 'wild-type') + ').')}\n`,
      );
    } else {
      process.stdout.write(
        `\n${c(DIM, '·')} ${c(DIM, 'The source does not say whether this was the wild-type enzyme')}\n` +
          `${c(DIM, '  or a variant. That is not the same as it being wild-type.')}\n`,
      );
    }
    if (v.recombinant) {
      process.stdout.write(
        `${c(DIM, '  Expressed recombinantly — same sequence, different host.')}\n`,
      );
    }
  }

  // COFACTORS AND EFFECTORS (ADR 0032)
  //
  // Jeske named four things that make values incomparable: pH, temperature,
  // cofactors and buffers. This is the third of them reaching a reader.
  //
  // "in the absence of X" is printed as loudly as "in the presence of X",
  // because an absence is a deliberate experimental statement rather than a
  // gap — and a Km measured without a required cofactor is a different
  // measurement, not a noisier one.
  if (result.effectors && result.effectors.length > 0) {
    const present = result.effectors.filter((e) => e.presence === 'present');
    const absent = result.effectors.filter((e) => e.presence === 'absent');
    process.stdout.write(`\n${c(BOLD, 'Measured with')}\n`);
    for (const e of present) {
      const conc = e.concentration_text ? `${e.concentration_text} ` : '';
      process.stdout.write(`  ${c(GREEN, '+')} ${conc}${e.compound_text}\n`);
    }
    for (const e of absent) {
      process.stdout.write(
        `  ${c(YELLOW, '−')} ${c(BOLD, 'without')} ${e.compound_text}` +
          `${c(DIM, '  — stated deliberately by the source')}\n`,
      );
    }
    const unstated = result.effectors.filter(
      (e) => e.presence !== 'present' && e.presence !== 'absent',
    );
    for (const e of unstated) {
      process.stdout.write(`  ${c(DIM, '?')} ${c(DIM, e.raw)}\n`);
    }
  }

  // THE BUFFER, AS CHEMISTRY RATHER THAN AS A STRING (ADR 0028)
  //
  // Only printed when the identity resolved to something. An unresolved
  // buffer is shown as the raw string in the conditions row above, which is
  // the honest rendering: the source said a thing, and we could not turn it
  // into a compound.
  const bufferIdentity = result.assayConditions?.bufferIdentity;
  if (bufferIdentity && bufferIdentity.status === 'resolved') {
    const conc = bufferIdentity.concentration_text;
    process.stdout.write(
      `\n${c(DIM, 'Buffer  ' + (bufferIdentity.species ?? bufferIdentity.raw) +
        ' (PubChem ' + bufferIdentity.parent_cid + ')')}\n`,
    );
    if (conc) {
      process.stdout.write(
        `${c(DIM, '  Reported at ' + conc + '. Concentration is not compared against')}\n` +
          `${c(DIM, '  other values — same species at a different strength reads as a match.')}\n`,
      );
    }
  }

  // Bakker's three axes, printed in full.
  //
  // The score existed for a day before anything displayed it. A grade
  // computed, serialised, and shown to nobody is the same as no grade -- and
  // it is worse than none, because the repository can point at a module and
  // claim the capability.
  //
  // Printed as three separate lines with no total, matching the module's
  // own refusal to combine them. "0.61" cannot tell a reader WHICH axis was
  // weak, and that is the only part they can act on.
  if (result.reliability) {
    const axes: Array<[string, { grade: string; reason: string }]> = [
      ['assay completeness', result.reliability.assayCompleteness],
      ['conditions vs model', result.reliability.conditionProximity],
      ['organism match', result.reliability.organismMatch],
    ];
    const labelWidth = Math.max(...axes.map(([label]) => label.length));

    process.stdout.write(`\n${c(BOLD, 'How much to trust this value')}\n`);
    for (const [label, axis] of axes) {
      const colour =
        axis.grade === 'complete' || axis.grade === 'exact' || axis.grade === 'near'
          ? GREEN
          : axis.grade === 'absent' || axis.grade === 'distant'
            ? RED
            : YELLOW;
      process.stdout.write(
        `  ${c(DIM, label.padEnd(labelWidth))}  ${c(colour, axis.grade)}\n`,
      );
    }
    process.stdout.write(
      `\n${c(DIM, 'Reasons:')}\n` +
        axes
          .map(([label, axis]) => `${c(DIM, '  ' + label + ': ' + axis.reason)}`)
          .join('\n') +
        '\n',
    );
    process.stdout.write(
      `\n${c(DIM, 'No overall score is offered, on purpose. Combining these needs a')}\n` +
        `${c(DIM, 'trade-off between them that nobody has measured yet.')}\n`,
    );
  }

  if (result.vmaxValidation?.flagged) {
    process.stdout.write(
      `\n${c(YELLOW, '⚠')} ${result.vmaxValidation.reason ?? 'Engine flagged this conversion.'}\n`,
    );
  }

  if (quantity === 'kcat' && result.bridgedVmax === undefined) {
    process.stdout.write(
      `\n${c(DIM, 'A kcat alone is not a simulation parameter: the engine takes Vmax,')}\n` +
        `${c(DIM, 'and Vmax = kcat × [E]0. Pass --enzyme-conc to bridge it.')}\n`,
    );
  }

  process.stdout.write('\n');
  return 0;
}
