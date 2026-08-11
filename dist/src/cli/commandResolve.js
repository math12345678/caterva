"use strict";
/**
 * `scientific resolve` — look up a kinetic constant in the literature and
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
Object.defineProperty(exports, "__esModule", { value: true });
exports.commandResolve = commandResolve;
const literatureResolver_1 = require("../literature/literatureResolver");
const BOLD = '[1m';
const DIM = '[2m';
const RED = '[31m';
const GREEN = '[32m';
const YELLOW = '[33m';
const RESET = '[0m';
/** Colour only when attached to a terminal, so piped output stays clean. */
const useColour = process.stdout.isTTY === true;
const c = (code, text) => useColour ? `${code}${text}${RESET}` : text;
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
async function commandResolve(options) {
    const { substrate, organism, quantity } = options;
    let result;
    try {
        result = await (0, literatureResolver_1.resolveKinetic)({
            enzymeName: options.enzyme,
            ecNumber: options.ec,
            substrate,
            organism,
            quantity,
            enzymeConc: options.enzymeConc,
        });
    }
    catch (err) {
        if (err instanceof literatureResolver_1.ResolverUnavailableError) {
            if (options.json) {
                process.stdout.write(JSON.stringify({ ok: false, status: 'unavailable', reason: err.message }, null, 2) + '\n');
            }
            else {
                process.stderr.write(`${c(RED, '✗')} Could not perform the lookup: ${err.message}\n` +
                    `${c(DIM, '  This is NOT the same as "no value exists". Nothing was learned about ')}\n` +
                    `${c(DIM, '  ' + quantity + ' for this system.')}\n`);
            }
            return 1;
        }
        throw err;
    }
    if (!result.found) {
        if (options.json) {
            process.stdout.write(JSON.stringify({ ok: true, status: 'not_found', quantity, logs: result.logs }, null, 2) + '\n');
        }
        else {
            process.stdout.write(`${c(YELLOW, '○')} No ${quantity} found for ` +
                `${c(BOLD, options.enzyme ?? options.ec ?? '?')} / ${substrate} / ${organism}.\n` +
                `${c(DIM, '  BRENDA and PubMed were searched and returned nothing. This is an')}\n` +
                `${c(DIM, '  answer, not a failure — no value has been invented to fill the gap.')}\n`);
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
    process.stdout.write(`\n${c(GREEN, '✓')} ${c(BOLD, `${label} = ${result.value} ${result.unit}`)}\n\n`);
    const rows = [
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
    }
    else {
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
        process.stdout.write(`\n${c(YELLOW, '⚠')} ${c(BOLD, 'Cross-species match.')} This was measured in ` +
            `${result.organism ?? 'another organism'}, not ${organism}.\n` +
            `${c(DIM, '  Real and citable, but do not report it as a ' + organism + ' measurement.')}\n`);
    }
    if (result.vmaxValidation?.flagged) {
        process.stdout.write(`\n${c(YELLOW, '⚠')} ${result.vmaxValidation.reason ?? 'Engine flagged this conversion.'}\n`);
    }
    if (quantity === 'kcat' && result.bridgedVmax === undefined) {
        process.stdout.write(`\n${c(DIM, 'A kcat alone is not a simulation parameter: the engine takes Vmax,')}\n` +
            `${c(DIM, 'and Vmax = kcat × [E]0. Pass --enzyme-conc to bridge it.')}\n`);
    }
    process.stdout.write('\n');
    return 0;
}
