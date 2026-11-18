import { readFileSync } from 'node:fs';
import path from 'node:path';

/**
 * One "0%" must not mean three different things.
 *
 * WHAT THIS COMES FROM
 * --------------------
 * `validationConfidence` is, at source (`scientificPipeline.ts`):
 *
 *     confidence: literatureSources.length > 1 ? 0.95
 *               : (literatureSources.length > 0 ? 0.92 : 0)
 *
 * a function of how many papers back the parameters and of **nothing
 * else**. It does not move when the numbers are dimensionally sound, inside
 * plausibility bounds, or when every model assumption held.
 *
 * So on the most common path in the product — a student typing three values
 * — it is structurally 0. The dashboard's results table printed that as
 * `0%`, and used the literal string `'0'` for **failed** runs and for
 * **errored** runs too. Three different outcomes, one cell, same text:
 *
 *   - the run failed                    → 0%
 *   - the run threw                     → 0%
 *   - the run was correct and unsourced → 0%
 *
 * A student cannot tell which happened, and the third is the common case.
 * The CLI had the same defect in words: "Validation confidence: 0.0%"
 * printed four lines after "✓ All validation layers passed".
 *
 * See ADR 0125.
 *
 * WHAT THIS CHECKS, AND WHAT IT CANNOT
 * ------------------------------------
 * This reads the shipped `dashboard.html` and asserts the SHAPE of the
 * three branches. It does not render the page and does not prove the cell
 * displays what the branch computes — `dashboardParameterGate.test.ts` has
 * the VM harness for behaviour, and this is deliberately the cheaper check
 * against the file that actually ships.
 *
 * A shape test is worth having here because the defect was a shape: one
 * literal reused across three outcomes.
 */

const DASHBOARD = path.join(__dirname, '..', 'dashboard.html');

function dashboardSource(): string {
  const html = readFileSync(DASHBOARD, 'utf8');
  // A floor: if the file stops being readable this must fail rather than
  // report every assertion below as satisfied by an empty string.
  expect(html.length).toBeGreaterThan(1000);
  return html;
}

describe('the results table distinguishes its three outcomes', () => {
  test('the confidence cell renders the value it was given', () => {
    const html = dashboardSource();
    // `<td>${result.confidence}%</td>` forced every value into a
    // percentage, so a non-numeric state could not be expressed at all.
    expect(html).toContain('${result.confidence}</td>');
    expect(html).not.toContain('${result.confidence}%</td>');
  });

  test('a run with no literature reports n/a rather than zero', () => {
    const html = dashboardSource();
    expect(html).toContain('literatureSourcesUsed');
    expect(html).toContain("'n/a'");
  });

  test('n/a is chosen by the zero-literature condition, not merely present', () => {
    // The two `toContain`s above pass on any file holding both strings, so
    // they cannot see the branch turned round (`!== 0` puts the score back
    // on exactly the unsourced runs, and `n/a` on the sourced ones) or a
    // missing count read as sourced (`?? 1` gives the hand-typed path a
    // score of nothing again). Measured: both mutations left
    // this file green until this assertion pinned the whole ternary. The
    // ADR's claim is "no literature -> n/a, literature -> the score"; this
    // is that sentence, as the code has to spell it.
    const html = dashboardSource();
    expect(html).toMatch(
      /confidence: \(result\.metadata\?\.literatureSourcesUsed \?\? 0\) === 0\s*\?\s*'n\/a'\s*:\s*result\.validationConfidence\.toFixed\(2\),/,
    );
  });

  test('failed and errored runs no longer borrow the same zero', () => {
    const html = dashboardSource();
    expect(html).not.toContain("confidence: '0'");
  });

  test('the em dash is used for the two failure paths', () => {
    const html = dashboardSource();
    const dashes = html.match(/confidence: '\\u2014'/g) ?? [];
    expect(dashes.length).toBe(2);
  });

  test('a sourced score is not shown as a percentage', () => {
    // The score's constants were never fitted to outcomes, so "92.0%"
    // beside the word "confidence" reads as a probability nothing has
    // measured. The CLI prints it 0-1 with that said (scientificCLI.ts
    // literatureScoreLines); the dashboard must not say otherwise.
    const html = dashboardSource();
    expect(html).not.toContain('validationConfidence * 100');
    expect(html).not.toMatch(/<td>\$\{result\.confidence\}%/);
  });

  test('the column says the score is a heuristic, not a probability', () => {
    // Wording is the fix here: a bare "Confidence" header puts the
    // probability reading back on an unchanged number.
    const html = dashboardSource();
    expect(html).not.toContain('<th>Confidence</th>');
    expect(html).toMatch(/<th[^>]*>Literature agreement \(heuristic, not a probability\)<\/th>/);
  });
});

describe('the Avg Literature Agreement tile', () => {
  // It showed '--' and nothing wrote to it. Now addResult() averages the
  // scores the table shows for sourced runs. Run here, not just matched:
  // the function is lifted out of the page and handed a stub document.
  function tile(cells: string[]): string {
    const html = dashboardSource();
    const decl = html.match(/const sourcedScores = \[\];/);
    const fn = html.match(/function addResult\(result\) \{[\s\S]*?\n {8}\}\n/);
    expect(decl).not.toBeNull();
    expect(fn).not.toBeNull();
    const els: Record<string, { textContent: string }> = {};
    const table = {
      innerHTML: '',
      firstChild: null,
      querySelector: () => null,
      querySelectorAll: () => ({ length: 0 }),
      insertBefore: () => undefined,
    };
    const document = {
      createElement: () => ({ innerHTML: '' }),
      getElementById: (id: string) =>
        id === 'resultsTable' ? table : (els[id] ??= { textContent: '' }),
    };
    const addResult = new Function('document', `${decl![0]}\n${fn![0]}\nreturn addResult;`)(document);
    for (const confidence of cells) addResult({ confidence });
    return els.avgConfidence.textContent;
  }

  test('it is the mean over sourced runs, and n/a and failures are not zeros', () => {
    // 0.92 and 0.95 are the two values validationConfidence takes on a
    // sourced run (scientificPipeline.ts, pinned below); 0.92, 0.92, 0.95
    // average 0.93. The n/a and the dash averaged in as 0 would give 0.56.
    expect(tile(['0.92', 'n/a', '0.92', '—', '0.95'])).toBe('0.93');
  });

  test('with no sourced run it says n/a, not 0.00', () => {
    expect(tile(['n/a', '—'])).toBe('n/a');
  });

  test('the label says heuristic and the tooltip says not a probability', () => {
    const html = dashboardSource();
    expect(html).toMatch(
      /<span class="metric-label" title="[^"]*backed by literature only[^"]*not a probability[^"]*">Avg Literature Agreement \(heuristic\)<\/span>/,
    );
    expect(html).toContain('<span class="metric-value" id="avgConfidence">n/a</span>');
  });
});

describe('the source of the score still justifies the treatment', () => {
  test('validationConfidence is still literature-only', () => {
    // If confidence ever starts reflecting dimensional or assumption
    // checks, "not applicable" becomes the wrong label and this file's
    // premise expires. Pinned so that change forces a decision here.
    const pipeline = readFileSync(
      path.join(__dirname, '..', '..', 'integration', 'scientificPipeline.ts'),
      'utf8',
    );
    expect(pipeline).toContain(
      'confidence: literatureSources.length > 1 ? 0.95 : (literatureSources.length > 0 ? 0.92 : 0)',
    );
  });
});
