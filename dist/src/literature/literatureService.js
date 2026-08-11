"use strict";
/**
 * Literature Database Service
 *
 * Manages curated scientific literature with:
 * - Parameter extraction
 * - Cross-verification
 * - Conflict detection
 * - Citation tracking
 *
 * PRINCIPLE: Every parameter is traceable to primary literature
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.LiteratureService = exports.CrossVerifier = exports.ParameterRecommender = exports.LiteratureDatabase = void 0;
const logger_1 = require("../logger");
const units_1 = require("../units");
const literatureResolver_1 = require("./literatureResolver");
/**
 * Convert a value between units of the same kind, choosing concentration or
 * rate handling by the shape of the unit string. Raises for anything it
 * cannot interpret -- see src/units.ts for why guessing is forbidden here.
 */
function convertToUnit(value, from, to) {
    const fromIsRate = from.includes('/');
    const toIsRate = to.includes('/');
    if (fromIsRate !== toIsRate) {
        throw new Error(`'${from}' and '${to}' are different kinds of quantity (one is a rate, ` +
            'one is not) and cannot be converted into each other.');
    }
    if (fromIsRate) {
        (0, units_1.parseRateUnit)(from);
        (0, units_1.parseRateUnit)(to);
        return (0, units_1.convertRate)(value, from, to);
    }
    return (0, units_1.convertConcentration)(value, from, to);
}
// ============================================================================
// LITERATURE DATABASE
// ============================================================================
class LiteratureDatabase {
    db = new Map();
    parameterIndex = new Map(); // parameter -> literature IDs
    /**
     * Add literature to database
     */
    add(literature) {
        if (this.db.has(literature.id)) {
            logger_1.logger.warn({ id: literature.id }, 'Literature already exists, updating');
        }
        this.db.set(literature.id, literature);
        // Index parameters
        for (const param of literature.extractedParameters) {
            const key = `${param.name}:${literature.domain}`;
            if (!this.parameterIndex.has(key)) {
                this.parameterIndex.set(key, new Set());
            }
            this.parameterIndex.get(key).add(literature.id);
        }
        logger_1.logger.info({
            id: literature.id,
            doi: literature.doi,
            parameters: literature.extractedParameters.length
        }, 'Literature added to database');
    }
    /**
     * Find all literature supporting a parameter
     */
    findByParameter(parameterName, domain) {
        const key = `${parameterName}:${domain}`;
        const ids = this.parameterIndex.get(key);
        if (!ids || ids.size === 0) {
            return [];
        }
        return Array.from(ids).map(id => this.db.get(id)).filter(Boolean);
    }
    /**
     * Find literature by DOI
     */
    findByDOI(doi) {
        for (const lit of this.db.values()) {
            if (lit.doi === doi)
                return lit;
        }
        return undefined;
    }
    /**
     * Get statistics on literature database
     */
    getStats() {
        const entries = Array.from(this.db.values());
        const byDomain = {};
        let totalImpactFactor = 0;
        let totalCitations = 0;
        let impactFactorCount = 0;
        let citationCount = 0;
        for (const lit of entries) {
            byDomain[lit.domain] = (byDomain[lit.domain] || 0) + 1;
            if (lit.impactFactor) {
                totalImpactFactor += lit.impactFactor;
                impactFactorCount++;
            }
            if (lit.citationCount) {
                totalCitations += lit.citationCount;
                citationCount++;
            }
        }
        return {
            totalEntries: entries.length,
            byDomain,
            peerReviewedCount: entries.filter(e => e.peerReviewed).length,
            averageImpactFactor: impactFactorCount > 0 ? totalImpactFactor / impactFactorCount : 0,
            averageCitations: citationCount > 0 ? totalCitations / citationCount : 0
        };
    }
}
exports.LiteratureDatabase = LiteratureDatabase;
// ============================================================================
// PARAMETER RECOMMENDATION
// ============================================================================
class ParameterRecommender {
    db;
    constructor(db) {
        this.db = db;
    }
    /**
     * Get recommended value for a parameter based on literature
     */
    recommend(parameterName, domain) {
        const literature = this.db.findByParameter(parameterName, domain);
        if (literature.length === 0) {
            throw new Error(`No literature found for parameter '${parameterName}' in domain '${domain}'`);
        }
        // Extract all values WITH their declared units.
        //
        // This previously mapped `p => ({ value: p.value, literature: lit })`,
        // dropping `p.unit` entirely, and then took a weighted mean across the
        // raw numbers. If one source reported Km in mM and another in uM -- a
        // completely routine occurrence, BRENDA carries both -- the "recommended
        // value" was the average of quantities in different units, which is not
        // a quantity at all. Nothing downstream could detect it, because the
        // result was then labelled with a unit guessed from the parameter's
        // NAME by `getDefaultUnit`, so it always looked self-consistent.
        const rawValues = literature.flatMap(lit => lit.extractedParameters
            .filter(p => p.name === parameterName)
            .map(p => ({ value: p.value, unit: p.unit, literature: lit })));
        if (rawValues.length === 0) {
            throw new Error(`No values extracted for parameter '${parameterName}'`);
        }
        // Everything is converted onto the first source's unit. Conversion is
        // driven by the declared strings, and an unrecognised or incompatible
        // unit raises rather than being averaged in as a bare number.
        const targetUnit = rawValues[0].unit;
        const values = rawValues.map(entry => {
            if (entry.unit === targetUnit) {
                return { value: entry.value, literature: entry.literature };
            }
            try {
                return {
                    value: convertToUnit(entry.value, entry.unit, targetUnit),
                    literature: entry.literature
                };
            }
            catch (error) {
                throw new Error(`Cannot combine literature values for '${parameterName}': source ` +
                    `${entry.literature.doi || entry.literature.id} reports ` +
                    `${entry.value} ${entry.unit} but ${rawValues[0].literature.doi || rawValues[0].literature.id} ` +
                    `reports ${targetUnit}. ` +
                    (error instanceof Error ? error.message : String(error)));
            }
        });
        // Calculate statistics
        const valueNumbers = values.map(v => v.value);
        const mean = valueNumbers.reduce((a, b) => a + b, 0) / valueNumbers.length;
        const stdDev = Math.sqrt(valueNumbers.reduce((sum, val) => sum + Math.pow(val - mean, 2), 0) / valueNumbers.length);
        // Detect outliers
        const outliers = valueNumbers.filter(v => Math.abs(v - mean) > 2 * stdDev);
        const warnings = [];
        if (outliers.length > 0) {
            warnings.push(`${outliers.length} outliers detected (>2σ from mean)`);
        }
        // Weighted mean by journal quality
        let weightedMean = 0;
        let totalWeight = 0;
        for (const { value, literature: lit } of values) {
            const weight = this.calculateSourceWeight(lit);
            weightedMean += value * weight;
            totalWeight += weight;
        }
        weightedMean /= totalWeight;
        // Calculate confidence
        const variance = stdDev / mean; // Coefficient of variation
        let confidence = 1.0;
        if (variance > 0.2)
            confidence -= 0.2; // High variance reduces confidence
        if (literature.length < 2)
            confidence -= 0.2; // Single source reduces confidence
        if (outliers.length > 0)
            confidence -= 0.1; // Outliers reduce confidence
        confidence = Math.max(0, Math.min(1, confidence));
        return {
            parameterName,
            recommendedValue: weightedMean,
            unit: targetUnit,
            range: [Math.min(...valueNumbers), Math.max(...valueNumbers)],
            sources: literature.map(l => l.doi || l.pubmedId || l.id),
            sourceCount: literature.length,
            confidence,
            warnings
        };
    }
    /**
     * Calculate source weight (higher for high-quality journals)
     */
    calculateSourceWeight(lit) {
        let weight = 1.0;
        // Boost for peer review
        if (lit.peerReviewed)
            weight *= 1.5;
        // Boost for high-impact journals
        if (lit.impactFactor) {
            if (lit.impactFactor > 5)
                weight *= 1.3;
            else if (lit.impactFactor > 2)
                weight *= 1.1;
        }
        // Boost for highly cited papers
        if (lit.citationCount) {
            if (lit.citationCount > 500)
                weight *= 1.2;
            else if (lit.citationCount > 100)
                weight *= 1.1;
        }
        return weight;
    }
}
exports.ParameterRecommender = ParameterRecommender;
// ============================================================================
// CROSS-VERIFICATION
// ============================================================================
class CrossVerifier {
    db;
    constructor(db) {
        this.db = db;
    }
    /**
     * Verify parameter consistency across multiple literature sources
     */
    verify(parameterName, domain) {
        const literature = this.db.findByParameter(parameterName, domain);
        if (literature.length < 2) {
            logger_1.logger.warn({ parameterName, domain }, 'Cross-verification requires at least 2 sources');
        }
        const values = literature
            .flatMap(lit => lit.extractedParameters
            .filter(p => p.name === parameterName)
            .map(p => p.value));
        const mean = values.reduce((a, b) => a + b, 0) / values.length;
        const variance = values.reduce((sum, val) => sum + Math.pow(val - mean, 2), 0) / values.length;
        const stdDev = Math.sqrt(variance);
        const relativeDeviation = (stdDev / mean) * 100;
        // Determine consensus
        let consensus = 'strong';
        if (relativeDeviation > 20)
            consensus = 'moderate';
        if (relativeDeviation > 50)
            consensus = 'weak';
        if (relativeDeviation > 100)
            consensus = 'conflicting';
        const recommendation = this.generateRecommendation(parameterName, values, mean, consensus);
        return {
            parameterName,
            values,
            sources: literature,
            mean,
            stdDev,
            min: Math.min(...values),
            max: Math.max(...values),
            relativeDeviation,
            consensus,
            recommendation
        };
    }
    generateRecommendation(parameterName, values, mean, consensus) {
        const consensusMap = {
            strong: 'HIGH - Use weighted mean with confidence',
            moderate: 'MEDIUM - Consider range, recommend additional validation',
            weak: 'LOW - Conflicting literature, manual review required',
            conflicting: 'VERY LOW - Significant conflicts detected, do not use'
        };
        return `${parameterName} consensus level: ${consensusMap[consensus]}. Mean: ${mean.toFixed(3)}`;
    }
    /**
     * Find conflicting values (outliers)
     */
    findConflicts(parameterName, domain) {
        const result = this.verify(parameterName, domain);
        const outliers = result.sources
            .flatMap(lit => lit.extractedParameters
            .filter(p => p.name === parameterName)
            .map(p => {
            const deviation = Math.abs(p.value - result.mean) / result.stdDev;
            return deviation > 2 ? {
                value: p.value,
                source: lit.doi || lit.id,
                deviation
            } : null;
        })
            .filter(Boolean))
            .filter(Boolean);
        return {
            hasConflicts: outliers.length > 0,
            outliers
        };
    }
}
exports.CrossVerifier = CrossVerifier;
// ============================================================================
// LITERATURE SERVICE (MAIN API)
// ============================================================================
class LiteratureService {
    db;
    recommender;
    verifier;
    constructor() {
        this.db = new LiteratureDatabase();
        this.recommender = new ParameterRecommender(this.db);
        this.verifier = new CrossVerifier(this.db);
    }
    /**
     * Add literature to database
     */
    addLiterature(lit) {
        this.db.add(lit);
    }
    /**
     * Get parameter recommendation from the in-memory database.
     *
     * Synchronous, and therefore limited to literature a caller has already
     * added. `resolveFromLiterature` is the one that actually reaches
     * BRENDA/PubMed.
     */
    getRecommendation(parameterName, domain) {
        return this.recommender.recommend(parameterName, domain);
    }
    /**
     * Resolve a kinetic constant against the REAL literature layer.
     *
     * Tries the in-memory database first -- a caller that supplied its own
     * sources meant them to be used, and it avoids a network round trip --
     * then falls back to `resolveKinetic`, which walks BRENDA exact match,
     * BRENDA cross-species, then PubMed candidates via the same
     * `science_agent_runner.py` bridge the production API server uses.
     *
     * Returns `null` when the literature genuinely has nothing. That is an
     * answer, and it is distinct from ResolverUnavailableError, which means
     * the lookup could not be performed -- "the registry says no" and "we
     * never asked" must not collapse into one another.
     */
    async resolveFromLiterature(parameterName, domain, query) {
        try {
            return this.recommender.recommend(parameterName, domain);
        }
        catch {
            // Nothing in the local database. Fall through to the real resolver
            // rather than treating an empty cache as an empty literature.
        }
        const quantity = parameterName.toLowerCase();
        if (quantity !== 'km' && quantity !== 'ki' && quantity !== 'kcat') {
            // Only these three resolve through BRENDA. Saying so is better than
            // issuing a lookup that cannot succeed and reporting its failure as
            // "no literature".
            logger_1.logger.info({ parameterName }, 'Parameter is not a BRENDA-resolvable kinetic constant; no lookup attempted');
            return null;
        }
        const result = await (0, literatureResolver_1.resolveKinetic)({ ...query, quantity });
        if (!result.found) {
            return null;
        }
        // A resolved kcat is a real, citable turnover number but is NOT a
        // simulation parameter: the MM engine takes Vmax, and
        // Vmax = kcat * [E]0 (ADR 0012 / 0013 / 0019). When the caller supplied
        // an enzyme concentration, the runner has already done that conversion
        // in Python using the same vmax_from_kcat the engine uses, and returned
        // it as `bridgedVmax`. Recomputing it here would be a second copy of
        // the arithmetic AND of its [E]0/Km flag threshold.
        if (quantity === 'kcat') {
            if (result.vmaxValidation && result.vmaxValidation.ok === false) {
                // The bridge REFUSED -- e.g. a non-positive [E]0. The runner omits
                // `vmax` in that case, and a refused conversion must not be
                // reported as a resolved parameter.
                logger_1.logger.warn({ reason: result.vmaxValidation.reason }, 'kcat resolved but the Vmax bridge refused the enzyme concentration');
                return null;
            }
            if (result.bridgedVmax === undefined) {
                logger_1.logger.info({ parameterName }, 'kcat resolved but no enzyme concentration was supplied, so it ' +
                    'cannot become a simulable Vmax (ADR 0019). Reporting no value ' +
                    'rather than inventing [E]0.');
                return null;
            }
        }
        return {
            parameterName,
            recommendedValue: result.value,
            // The unit BRENDA reported. This is the whole reason the resolver is
            // worth calling rather than assuming: the value and its unit arrive
            // together, from the same source.
            unit: result.unit,
            // A single resolved measurement, so the range is degenerate. Stated
            // rather than widened by an invented tolerance.
            range: [result.value, result.value],
            sources: result.citation?.reference_id
                ? [String(result.citation.reference_id)]
                : [],
            sourceCount: result.citation ? 1 : 0,
            // A cross-species value is real and citable but was measured in a
            // DIFFERENT organism than the one asked about, so it cannot carry the
            // same confidence as an exact match. The reduction is a policy
            // choice, and it is named as one rather than presented as a
            // measurement.
            confidence: result.crossSpecies ? 0.5 : 0.9,
            warnings: result.crossSpecies
                ? [
                    `Value measured in ${result.organism ?? 'a different organism'}, ` +
                        `not ${query.organism}. BRENDA cross-species match.`
                ]
                : []
        };
    }
    /**
     * Cross-verify parameter across sources
     */
    crossVerify(parameterName, domain) {
        return this.verifier.verify(parameterName, domain);
    }
    /**
     * Find conflicts in literature
     */
    findConflicts(parameterName, domain) {
        return this.verifier.findConflicts(parameterName, domain);
    }
    /**
     * Get database statistics
     */
    getStats() {
        return this.db.getStats();
    }
    /**
     * Get literature by DOI
     */
    getByDOI(doi) {
        return this.db.findByDOI(doi);
    }
}
exports.LiteratureService = LiteratureService;
// ============================================================================
// EXPORT
// ============================================================================
exports.default = {
    LiteratureDatabase,
    ParameterRecommender,
    CrossVerifier,
    LiteratureService
};
