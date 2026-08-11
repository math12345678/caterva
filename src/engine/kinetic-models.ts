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

import { logger } from '../logger';

export interface KineticModel {
  name: string;
  description: string;
  parameters: Record<string, number>;
  rateEquation(substrate: number, params: KineticParameters): number;
}

export interface KineticParameters {
  vmax: number;
  km: number;
  substrate: number;
  time: number;
  // Optional parameters for advanced models
  inhibitor?: number;
  ki?: number;
  product?: number;
  kp?: number;
  cooperativity?: number;
}

// ============================================================================
// MICHAELIS-MENTEN (CLASSIC)
// ============================================================================

export const michaelisMemten: KineticModel = {
  name: 'Michaelis-Menten',
  description: 'Classical single-substrate, single-product enzyme kinetics',
  parameters: { vmax: 12.8, km: 5.2 },
  rateEquation(s: number, params: KineticParameters): number {
    return (params.vmax * s) / (params.km + s);
  }
};

// ============================================================================
// COMPETITIVE INHIBITION
// ============================================================================

export const competitiveInhibition: KineticModel = {
  name: 'Competitive Inhibition',
  description: 'Inhibitor competes with substrate for active site',
  parameters: { vmax: 12.8, km: 5.2, ki: 2.0 },
  rateEquation(s: number, params: KineticParameters): number {
    const inhibitionFactor = 1 + (params.inhibitor || 0) / (params.ki || 1);
    const effectiveKm = params.km * inhibitionFactor;
    return (params.vmax * s) / (effectiveKm + s);
  }
};

// ============================================================================
// NON-COMPETITIVE INHIBITION
// ============================================================================

export const noncompetitiveInhibition: KineticModel = {
  name: 'Non-competitive Inhibition',
  description: 'Inhibitor binds to enzyme-substrate complex',
  parameters: { vmax: 12.8, km: 5.2, ki: 2.0 },
  rateEquation(s: number, params: KineticParameters): number {
    const inhibitionFactor = 1 + (params.inhibitor || 0) / (params.ki || 1);
    const effectiveVmax = params.vmax / inhibitionFactor;
    return (effectiveVmax * s) / (params.km + s);
  }
};

// ============================================================================
// PRODUCT INHIBITION
// ============================================================================

export const productInhibition: KineticModel = {
  name: 'Product Inhibition',
  description: 'Product accumulation inhibits further reaction',
  parameters: { vmax: 12.8, km: 5.2, kp: 3.0 },
  rateEquation(s: number, params: KineticParameters): number {
    const productFactor = 1 + (params.product || 0) / (params.kp || 1);
    return (params.vmax * s) / ((params.km + s) * productFactor);
  }
};

// ============================================================================
// ALLOSTERIC (HILL EQUATION)
// ============================================================================

export const allostericModel: KineticModel = {
  name: 'Allosteric (Hill)',
  description: 'Cooperative binding with positive or negative cooperativity',
  parameters: { vmax: 12.8, km: 5.2, cooperativity: 1.5 },
  rateEquation(s: number, params: KineticParameters): number {
    const n = params.cooperativity || 1.5;
    const k = Math.pow(params.km, n);
    const sn = Math.pow(s, n);
    return (params.vmax * sn) / (k + sn);
  }
};

// ============================================================================
// SUBSTRATE DEPLETION TRACKING
// ============================================================================

export interface SubstrateTrajectory {
  time: number;
  substrate: number;
  product: number;
  velocity: number;
}

export class KineticSimulator {
  constructor(private model: KineticModel) {}

  /**
   * Simulate kinetics over time with substrate depletion
   */
  simulateDepletion(
    initialSubstrate: number,
    params: KineticParameters,
    endTime: number = 10,
    points: number = 101
  ): SubstrateTrajectory[] {
    const trajectory: SubstrateTrajectory[] = [];
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
  getMaxVelocity(params: KineticParameters): number {
    return params.vmax;
  }

  /**
   * Calculate Km (substrate at half-max velocity)
   */
  getKm(params: KineticParameters): number {
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
  getFirstOrderKcat(params: KineticParameters): number {
    return params.vmax / (params.km * 1000); // Approximate kcat
  }
}

// ============================================================================
// MODEL REGISTRY
// ============================================================================

export const kinematicModels: Record<string, KineticModel> = {
  'michaelis-menten': michaelisMemten,
  'competitive-inhibition': competitiveInhibition,
  'non-competitive-inhibition': noncompetitiveInhibition,
  'product-inhibition': productInhibition,
  'allosteric': allostericModel
};

export function getModel(name: string): KineticModel {
  const model = kinematicModels[name.toLowerCase()];
  if (!model) {
    logger.warn(
      { requestedModel: name, available: Object.keys(kinematicModels) },
      'Model not found, using Michaelis-Menten'
    );
    return michaelisMemten;
  }
  return model;
}

export function listModels(): Array<{ name: string; description: string }> {
  return Object.values(kinematicModels).map(m => ({
    name: m.name,
    description: m.description
  }));
}
