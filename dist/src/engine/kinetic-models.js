"use strict";
/**
 * Advanced Kinetic Models for Enzyme Catalysis
 *
 * Supports:
 * 1. Michaelis-Menten (basic)
 * 2. Competitive Inhibition
 * 3. Non-competitive Inhibition
 * 4. Product Inhibition
 * 5. Allosteric Regulation
 * 6. Multi-substrate (ordered, random)
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.kinematicModels = exports.KineticSimulator = exports.allostericModel = exports.productInhibition = exports.noncompetitiveInhibition = exports.competitiveInhibition = exports.michaelisMemten = void 0;
exports.getModel = getModel;
exports.listModels = listModels;
const logger_1 = require("../logger");
// ============================================================================
// MICHAELIS-MENTEN (CLASSIC)
// ============================================================================
exports.michaelisMemten = {
    name: 'Michaelis-Menten',
    description: 'Classical single-substrate, single-product enzyme kinetics',
    parameters: { vmax: 12.8, km: 5.2 },
    rateEquation(s, params) {
        return (params.vmax * s) / (params.km + s);
    }
};
// ============================================================================
// COMPETITIVE INHIBITION
// ============================================================================
exports.competitiveInhibition = {
    name: 'Competitive Inhibition',
    description: 'Inhibitor competes with substrate for active site',
    parameters: { vmax: 12.8, km: 5.2, ki: 2.0 },
    rateEquation(s, params) {
        const inhibitionFactor = 1 + (params.inhibitor || 0) / (params.ki || 1);
        const effectiveKm = params.km * inhibitionFactor;
        return (params.vmax * s) / (effectiveKm + s);
    }
};
// ============================================================================
// NON-COMPETITIVE INHIBITION
// ============================================================================
exports.noncompetitiveInhibition = {
    name: 'Non-competitive Inhibition',
    description: 'Inhibitor binds to enzyme-substrate complex',
    parameters: { vmax: 12.8, km: 5.2, ki: 2.0 },
    rateEquation(s, params) {
        const inhibitionFactor = 1 + (params.inhibitor || 0) / (params.ki || 1);
        const effectiveVmax = params.vmax / inhibitionFactor;
        return (effectiveVmax * s) / (params.km + s);
    }
};
// ============================================================================
// PRODUCT INHIBITION
// ============================================================================
exports.productInhibition = {
    name: 'Product Inhibition',
    description: 'Product accumulation inhibits further reaction',
    parameters: { vmax: 12.8, km: 5.2, kp: 3.0 },
    rateEquation(s, params) {
        const productFactor = 1 + (params.product || 0) / (params.kp || 1);
        return (params.vmax * s) / ((params.km + s) * productFactor);
    }
};
// ============================================================================
// ALLOSTERIC (HILL EQUATION)
// ============================================================================
exports.allostericModel = {
    name: 'Allosteric (Hill)',
    description: 'Cooperative binding with positive or negative cooperativity',
    parameters: { vmax: 12.8, km: 5.2, cooperativity: 1.5 },
    rateEquation(s, params) {
        const n = params.cooperativity || 1.5;
        const k = Math.pow(params.km, n);
        const sn = Math.pow(s, n);
        return (params.vmax * sn) / (k + sn);
    }
};
class KineticSimulator {
    model;
    constructor(model) {
        this.model = model;
    }
    /**
     * Simulate kinetics over time with substrate depletion
     */
    simulateDepletion(initialSubstrate, params, endTime = 10, points = 101) {
        const trajectory = [];
        const dt = endTime / (points - 1);
        let currentSubstrate = initialSubstrate;
        let currentProduct = 0;
        for (let i = 0; i < points; i++) {
            const time = i * dt;
            // Calculate velocity at current substrate concentration
            const velocity = this.model.rateEquation(currentSubstrate, {
                ...params,
                substrate: currentSubstrate
            });
            trajectory.push({
                time,
                substrate: Math.max(0, currentSubstrate),
                product: currentProduct,
                velocity
            });
            // Update substrate and product (forward Euler)
            currentSubstrate = Math.max(0, currentSubstrate - velocity * dt);
            currentProduct += velocity * dt;
        }
        return trajectory;
    }
    /**
     * Calculate maximum velocity
     */
    getMaxVelocity(params) {
        return params.vmax;
    }
    /**
     * Calculate Km (substrate at half-max velocity)
     */
    getKm(params) {
        // For basic MM: v_max/2 occurs at [S] = Km
        // For competitive inhibition: Km_app = Km(1 + [I]/Ki)
        if (params.inhibitor && params.ki) {
            return params.km * (1 + params.inhibitor / params.ki);
        }
        return params.km;
    }
    /**
     * Calculate reaction order at low substrate concentration
     */
    getFirstOrderKcat(params) {
        return params.vmax / (params.km * 1000); // Approximate kcat
    }
}
exports.KineticSimulator = KineticSimulator;
// ============================================================================
// MODEL REGISTRY
// ============================================================================
exports.kinematicModels = {
    'michaelis-menten': exports.michaelisMemten,
    'competitive-inhibition': exports.competitiveInhibition,
    'non-competitive-inhibition': exports.noncompetitiveInhibition,
    'product-inhibition': exports.productInhibition,
    'allosteric': exports.allostericModel
};
function getModel(name) {
    const model = exports.kinematicModels[name.toLowerCase()];
    if (!model) {
        logger_1.logger.warn({ requestedModel: name, available: Object.keys(exports.kinematicModels) }, 'Model not found, using Michaelis-Menten');
        return exports.michaelisMemten;
    }
    return model;
}
function listModels() {
    return Object.values(exports.kinematicModels).map(m => ({
        name: m.name,
        description: m.description
    }));
}
