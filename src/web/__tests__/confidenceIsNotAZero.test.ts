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

  test('failed and errored runs no longer borrow the same zero', () => {
    const html = dashboardSource();
    expect(html).not.toContain("confidence: '0'");
  });

  test('the em dash is used for the two failure paths', () => {
    const html = dashboardSource();
    const dashes = html.match(/confidence: '\\u2014'/g) ?? [];
    expect(dashes.length).toBe(2);
  });

  test('the percentage sign travels with the number, not the cell', () => {
    // Otherwise "n/a" would render as "n/a%" the moment the cell puts it
    // back — the failure this test exists to keep out.
    const html = dashboardSource();
    expect(html).toContain(".toFixed(1) + '%'");
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
