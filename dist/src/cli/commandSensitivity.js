"use strict";
/**
 * `scientific sensitivity` — how much does the answer depend on each
 * number, and how much do you trust that number?
 *
 * Sensitivity analysis on its own is ordinary; most simulation packages
 * have it. What makes it worth having here is that Terrium knows the
 * PROVENANCE of every parameter, so the two can be shown together:
 *
 *     km    0.14 mM   brenda_cross_species   47.2%   ← rabbit value, and
 *                                                      the answer rides on it
 *     s0    10 mM     user                    3.1%
 *
 * That pairing answers the question a scientist actually has when they
 * accept a substituted value: *does it matter?* A cross-species Km with
 * 0.1% sensitivity is harmless. The same substitution with 47% sensitivity
 * means the result should not be reported without measuring it properly.
 *
 * Neither number answers that alone. A sensitivity table without
 * provenance cannot tell you which parameters are shaky; a provenance
 * table without sensitivity cannot tell you which shakiness matters.
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.commandSensitivity = commandSensitivity;
const advanced_features_1 = require("./advanced-features");
const scientificValidator_1 = require("../validation/scientificValidator");
const BOLD = '\x1b[1m';
const DIM = '\x1b[2m';
const RED = '\x1b[31m';
const YELLOW = '\x1b[33m';
const RESET = '\x1b[0m';
const useColour = process.stdout.isTTY === true;
const c = (code, text) => useColour ? `${code}${text}${RESET}` : text;
/**
 * Sensitivity above which a substituted or assumed parameter is called
 * out as load-bearing.
 *
 * 10% is a reporting threshold for drawing a reader's eye, NOT a
 * scientific claim about acceptable error — there is no literature value
 * for "how much sensitivity is too much", because the answer depends
 * entirely on what conclusion is being drawn. It is named here rather than
 * buried so nobody mistakes it for a measured bound.
 */
const LOAD_BEARING_SENSITIVITY = 0.10;
async function commandSensitivity(options) {
    let results;
    try {
        results = await (0, advanced_features_1.sensitivityAnalysis)(options.query, options.parameters, options.perturbation, options.request);
    }
    catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        if (options.json) {
            process.stdout.write(JSON.stringify({ ok: false, status: 'baseline_failed', reason: message }, null, 2) + '\n');
        }
        else {
            process.stderr.write(`${c(RED, '✗')} ${message}\n`);
        }
        return 2;
    }
    if (options.json) {
        process.stdout.write(JSON.stringify({
            ok: true,
            perturbation: options.perturbation,
            loadBearingThreshold: LOAD_BEARING_SENSITIVITY,
            results,
            provenance: options.provenance,
        }, null, 2) + '\n');
        return 0;
    }
    const pct = (options.perturbation * 100).toFixed(0);
    process.stdout.write(`\n${c(BOLD, `Sensitivity  (±${pct}% on each parameter)`)}\n`);
    const rows = Object.entries(results).map(([name, entry]) => {
        const source = options.provenance.find((p) => p.name === name);
        return { name, entry, source };
    });
    // Most influential first: the point of the table is to show what the
    // answer rides on.
    rows.sort((a, b) => (b.entry.worst || 0) - (a.entry.worst || 0));
    const nameWidth = Math.max(...rows.map((r) => r.name.length), 4);
    for (const { name, entry, source } of rows) {
        if (entry.failed) {
            process.stdout.write(`  ${name.padEnd(nameWidth)}  ${c(RED, 'could not analyse')}  ${c(DIM, entry.failed)}\n`);
            continue;
        }
        const effect = `${(entry.worst * 100).toFixed(1)}%`.padStart(7);
        const origin = source ? source.origin : 'unknown';
        process.stdout.write(`  ${name.padEnd(nameWidth)}  ${effect}   ${c(DIM, origin)}\n`);
    }
    // The finding worth surfacing: an untrustworthy parameter the answer
    // depends on. This is the whole reason provenance and sensitivity are
    // printed in one table.
    // A weakly-sourced MEASUREMENT and a load-bearing CHOICE are different
    // problems with different remedies, and collapsing them is the same
    // category error that made Layer 1 demand a citation for s0. Nobody
    // measures "the initial substrate concentration of this enzyme" -- the
    // experimenter picks it -- so "no citation" is not a defect there. It is
    // still worth knowing that the answer rides on it, for a different
    // reason: it belongs in the methods section, precisely stated.
    const loadBearing = rows.filter(({ entry }) => !entry.failed && entry.worst >= LOAD_BEARING_SENSITIVITY);
    const shakyMeasurements = loadBearing.filter(({ name, source }) => !(0, scientificValidator_1.isExperimentalCondition)(name) &&
        (source?.crossSpecies || source?.unitAssumed || !source?.citation));
    const sensitiveChoices = loadBearing.filter(({ name }) => (0, scientificValidator_1.isExperimentalCondition)(name));
    if (shakyMeasurements.length > 0) {
        process.stdout.write(`\n${c(YELLOW, '⚠')} ${c(BOLD, 'Load-bearing and weakly sourced:')}\n`);
        for (const { name, entry, source } of shakyMeasurements) {
            const why = source?.crossSpecies
                ? `it was measured in ${source.organism ?? 'another organism'}`
                : source?.unitAssumed
                    ? `its unit was assumed (${source.unit})`
                    : 'it carries no literature citation';
            process.stdout.write(`    ${name}: the result moves ${(entry.worst * 100).toFixed(1)}% under a ±${pct}% change, and ${why}.\n`);
        }
        process.stdout.write(`${c(DIM, '    Measure these for your own system before reporting the result.')}\n`);
    }
    if (sensitiveChoices.length > 0) {
        process.stdout.write(`\n${c(YELLOW, '•')} ${c(BOLD, 'Your result depends on choices you made:')}\n`);
        for (const { name, entry } of sensitiveChoices) {
            process.stdout.write(`    ${name}: ±${pct}% moves the result ${(entry.worst * 100).toFixed(1)}%.\n`);
        }
        process.stdout.write(`${c(DIM, '    Not a data-quality problem — these are experimental conditions, not')}\n` +
            `${c(DIM, '    measurements. But state them precisely in your methods: another lab')}\n` +
            `${c(DIM, '    picking a different value will not reproduce your numbers.')}\n`);
    }
    if (shakyMeasurements.length === 0 && sensitiveChoices.length === 0) {
        process.stdout.write(`\n${c(DIM, 'No parameter is both load-bearing (>' + (LOAD_BEARING_SENSITIVITY * 100) + '%) and weakly sourced.')}\n`);
    }
    process.stdout.write(`\n${c(DIM, `The ${(LOAD_BEARING_SENSITIVITY * 100).toFixed(0)}% threshold is a reporting cue, not a measured bound —`)}\n` +
        `${c(DIM, 'how much sensitivity is acceptable depends on the conclusion you draw.')}\n\n`);
    return 0;
}
