"use strict";
/**
 * Advanced CLI Features for Terrium
 *
 * Additional capabilities:
 * - Batch processing (multiple simulations)
 * - Parameter search (find optimal parameters)
 * - Sensitivity analysis (how parameters affect results)
 * - Data export (CSV, JSON, Excel)
 * - Performance profiling
 */
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.batchSimulate = batchSimulate;
exports.parameterSweep = parameterSweep;
exports.sensitivityAnalysis = sensitivityAnalysis;
exports.exportToCSV = exportToCSV;
exports.exportToJSON = exportToJSON;
exports.profileSimulation = profileSimulation;
const scientificPipeline_1 = __importDefault(require("../integration/scientificPipeline"));
const logger_1 = require("../logger");
const fs = __importStar(require("fs"));
// ============================================================================
// BATCH PROCESSING
// ============================================================================
async function batchSimulate(scenarios) {
    const results = [];
    for (const scenario of scenarios) {
        try {
            const pipeline = new scientificPipeline_1.default();
            const response = await pipeline.execute({
                query: scenario.query,
                parameters: scenario.parameters
            });
            results.push({
                scenario: scenario.name,
                jobId: response.jobId,
                confidence: response.validationConfidence
            });
            logger_1.logger.info({ scenario: scenario.name, jobId: response.jobId }, 'Batch scenario completed');
        }
        catch (error) {
            logger_1.logger.error({ scenario: scenario.name, error }, 'Batch scenario failed');
        }
    }
    return results;
}
// ============================================================================
// PARAMETER SEARCH (SIMPLE SWEEP)
// ============================================================================
async function parameterSweep(query, parameter, min, max, step) {
    const results = [];
    for (let value = min; value <= max; value += step) {
        try {
            const pipeline = new scientificPipeline_1.default();
            const parameters = {};
            parameters[parameter] = value;
            const response = await pipeline.execute({
                query,
                parameters
            });
            if (response.results && response.results.trajectory) {
                const finalValue = response.results.trajectory[response.results.trajectory.length - 1]?.value || 0;
                results.push({
                    paramValue: value,
                    finalValue,
                    confidence: response.validationConfidence
                });
            }
            logger_1.logger.info({ parameter, value, finalValue: response.results.finalValue }, 'Sweep point completed');
        }
        catch (error) {
            logger_1.logger.warn({ parameter, value, error }, 'Sweep point failed');
        }
    }
    return results;
}
/**
 * How much does the answer depend on each parameter?
 *
 * Perturbs each one by ±`sensitivity` and measures the relative change in
 * the final value. Paired with provenance this answers the question that
 * actually matters to someone using a literature-sourced value: *my Km is
 * a cross-species substitute — does that change my conclusion?* A 40%
 * sensitivity on a cross-species parameter is a result that should not be
 * reported; a 0.1% sensitivity means the substitution is harmless.
 */
async function sensitivityAnalysis(query, baseParameters, sensitivity = 0.1, // 10% perturbation
request = {}) {
    const results = {};
    // Get baseline
    const baselinePipeline = new scientificPipeline_1.default();
    const baselineResponse = await baselinePipeline.execute({
        ...request,
        query,
        parameters: baseParameters
    });
    // A run that did not validate returns finalValue 0 and an empty
    // trajectory. Dividing by that produced Infinity or NaN for every
    // parameter, which then rendered as a confident-looking sensitivity
    // table for a simulation that never executed.
    if (!baselineResponse.validated) {
        throw new Error('Baseline run did not validate, so there is nothing to perturb: ' +
            baselineResponse.validationErrors.join('; '));
    }
    const baselineFinal = baselineResponse.results.finalValue;
    if (!Number.isFinite(baselineFinal) || baselineFinal === 0) {
        throw new Error(`Baseline final value is ${baselineFinal}; a relative sensitivity ` +
            'cannot be computed against it. Choose a shorter window or a larger ' +
            's0 so the substrate is not fully consumed.');
    }
    // Test each parameter
    for (const [param, value] of Object.entries(baseParameters)) {
        try {
            // Test with +sensitivity
            const increaseParams = { ...baseParameters };
            increaseParams[param] = value * (1 + sensitivity);
            const increasePipeline = new scientificPipeline_1.default();
            const increaseResponse = await increasePipeline.execute({
                ...request,
                query,
                parameters: increaseParams
            });
            const increaseEffect = Math.abs(increaseResponse.results.finalValue - baselineFinal) / baselineFinal;
            // Test with -sensitivity
            const decreaseParams = { ...baseParameters };
            decreaseParams[param] = value * (1 - sensitivity);
            const decreasePipeline = new scientificPipeline_1.default();
            const decreaseResponse = await decreasePipeline.execute({
                ...request,
                query,
                parameters: decreaseParams
            });
            const decreaseEffect = Math.abs(decreaseResponse.results.finalValue - baselineFinal) / baselineFinal;
            results[param] = {
                increase: increaseEffect,
                decrease: decreaseEffect,
                worst: Math.max(increaseEffect, decreaseEffect)
            };
            logger_1.logger.info({ parameter: param, increaseEffect, decreaseEffect }, 'Sensitivity analyzed');
        }
        catch (error) {
            // RECORDED, not swallowed. This logged a warning and moved on, so a
            // parameter whose analysis failed simply vanished from the table --
            // indistinguishable from one measured to have no influence, which is
            // the opposite conclusion.
            results[param] = {
                increase: Number.NaN,
                decrease: Number.NaN,
                worst: Number.NaN,
                failed: error instanceof Error ? error.message : String(error)
            };
            logger_1.logger.warn({ parameter: param, error }, 'Sensitivity analysis failed for parameter');
        }
    }
    return results;
}
// ============================================================================
// DATA EXPORT
// ============================================================================
function exportToCSV(results, filepath) {
    if (results.length === 0) {
        logger_1.logger.warn({}, 'No results to export');
        return;
    }
    // Get all unique keys
    const keys = Array.from(new Set(results.flatMap(r => Object.keys(r))));
    // Build CSV
    const header = keys.join(',');
    const rows = results.map(r => keys.map(k => {
        const value = r[k];
        if (value === null || value === undefined)
            return '';
        if (typeof value === 'string' && value.includes(','))
            return `"${value}"`;
        return String(value);
    }).join(','));
    const csv = [header, ...rows].join('\n');
    fs.writeFileSync(filepath, csv, 'utf-8');
    logger_1.logger.info({ filepath }, 'Data exported to CSV');
}
function exportToJSON(data, filepath) {
    const json = JSON.stringify(data, null, 2);
    fs.writeFileSync(filepath, json, 'utf-8');
    logger_1.logger.info({ filepath }, 'Data exported to JSON');
}
// ============================================================================
// PERFORMANCE PROFILING
// ============================================================================
async function profileSimulation(query, parameters, iterations = 5) {
    const times = [];
    for (let i = 0; i < iterations; i++) {
        const startTime = Date.now();
        try {
            const pipeline = new scientificPipeline_1.default();
            await pipeline.execute({ query, parameters });
            const endTime = Date.now();
            times.push(endTime - startTime);
        }
        catch (error) {
            logger_1.logger.warn({ iteration: i, error }, 'Iteration failed');
        }
    }
    if (times.length === 0) {
        throw new Error('No successful iterations for profiling');
    }
    const meanTimeMs = times.reduce((a, b) => a + b, 0) / times.length;
    const minTimeMs = Math.min(...times);
    const maxTimeMs = Math.max(...times);
    const variance = times.reduce((sum, t) => sum + Math.pow(t - meanTimeMs, 2), 0) / times.length;
    const stdDevMs = Math.sqrt(variance);
    return { meanTimeMs, minTimeMs, maxTimeMs, stdDevMs };
}
