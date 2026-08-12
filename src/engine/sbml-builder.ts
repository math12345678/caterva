/**
 * SBML Model Builder - Generates real SBML Level 3 Version 1 models
 *
 * SBML (Systems Biology Markup Language) is the standard for describing
 * biological models. This builder generates SBML that Terium/libroadrunner
 * can execute.
 *
 * Each model represents a real biochemical system:
 * - Michaelis-Menten: E + S ⇌ ES → E + P
 * - Competitive inhibition: I competes with S for active site
 * - Non-competitive inhibition: I reduces Vmax regardless of S
 * - Product inhibition: P reduces enzyme activity
 * - Allosteric: S binding enhances/reduces activity
 */

export interface SBMLModel {
  xml: string;
  species: string[];
  reactions: string[];
  parameters: string[];
}

/**
 * Michaelis-Menten Model
 *
 * Simplest case: E + S ⇌ ES → E + P
 *
 * Rate = (Vmax * [S]) / (Km + [S])
 *
 * Parameters:
 *   - Km: Michaelis constant (concentration)
 *   - Vmax: Maximum velocity (rate)
 *   - s0: Initial substrate concentration
 *   - e0: Enzyme concentration (optional)
 */
export function buildMichaelisMenten(params: {
  km: number;
  vmax: number;
  s0: number;
  e0?: number;
}): SBMLModel {
  const e0 = params.e0 ?? 1.0;

  const xml = `<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<sbml xmlns="http://www.sbml.org/sbml/level3/version1/core" level="3" version="1">
  <model id="michaelis_menten" metaid="meta_mm">
    <listOfCompartments>
      <compartment id="cell" constant="true" spatialDimensions="3" size="1"/>
    </listOfCompartments>

    <listOfSpecies>
      <species id="S" compartment="cell" initialConcentration="${params.s0}"
               hasOnlySubstanceUnits="false" boundaryCondition="false" constant="false"
               metaid="meta_S"/>
      <species id="P" compartment="cell" initialConcentration="0"
               hasOnlySubstanceUnits="false" boundaryCondition="false" constant="false"
               metaid="meta_P"/>
      <species id="E" compartment="cell" initialConcentration="${e0}"
               hasOnlySubstanceUnits="false" boundaryCondition="false" constant="false"
               metaid="meta_E"/>
    </listOfSpecies>

    <listOfParameters>
      <parameter id="km" value="${params.km}" constant="true" metaid="meta_km"/>
      <parameter id="vmax" value="${params.vmax}" constant="true" metaid="meta_vmax"/>
    </listOfParameters>

    <listOfReactions>
      <reaction id="r1" reversible="false" fast="false" metaid="meta_r1">
        <listOfReactants>
          <speciesReference species="S" stoichiometry="1" role="substrate"/>
        </listOfReactants>
        <listOfProducts>
          <speciesReference species="P" stoichiometry="1" role="product"/>
        </listOfProducts>
        <kineticLaw>
          <math xmlns="http://www.w3.org/1998/Math/MathML">
            <apply>
              <divide/>
              <apply>
                <times/>
                <ci>vmax</ci>
                <ci>S</ci>
              </apply>
              <apply>
                <plus/>
                <ci>km</ci>
                <ci>S</ci>
              </apply>
            </apply>
          </math>
        </kineticLaw>
      </reaction>
    </listOfReactions>
  </model>
</sbml>`;

  return {
    xml,
    species: ['S', 'P', 'E'],
    reactions: ['r1'],
    parameters: ['km', 'vmax']
  };
}

/**
 * Competitive Inhibition Model
 *
 * Inhibitor I competes with substrate S for the enzyme's active site.
 *
 * Rate = (Vmax * [S]) / (Km * (1 + [I] / Ki) + [S])
 *
 * Where Ki is the inhibition constant.
 *
 * Reference: Copeland, R. A. (2013). Enzymes: A Practical Introduction to
 * Structure, Mechanism, and Data Analysis (2nd ed.), Ch. 3 "Reversible
 * Modes of Inhibitor Interaction," competitive inhibition rate equation.
 *
 * Parameters:
 *   - km: Michaelis constant
 *   - vmax: Maximum velocity
 *   - ki: Inhibition constant
 *   - s0: Initial substrate
 *   - i0: Initial inhibitor
 *   - e0: Enzyme concentration
 */
export function buildCompetitiveInhibition(params: {
  km: number;
  vmax: number;
  ki: number;
  s0: number;
  i0: number;
  e0?: number;
}): SBMLModel {
  const e0 = params.e0 ?? 1.0;

  const xml = `<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<sbml xmlns="http://www.sbml.org/sbml/level3/version1/core" level="3" version="1">
  <model id="competitive_inhibition" metaid="meta_ci">
    <listOfCompartments>
      <compartment id="cell" constant="true" spatialDimensions="3" size="1"/>
    </listOfCompartments>

    <listOfSpecies>
      <species id="S" compartment="cell" initialConcentration="${params.s0}"
               hasOnlySubstanceUnits="false" boundaryCondition="false" constant="false"/>
      <species id="I" compartment="cell" initialConcentration="${params.i0}"
               hasOnlySubstanceUnits="false" boundaryCondition="false" constant="false"/>
      <species id="P" compartment="cell" initialConcentration="0"
               hasOnlySubstanceUnits="false" boundaryCondition="false" constant="false"/>
      <species id="E" compartment="cell" initialConcentration="${e0}"
               hasOnlySubstanceUnits="false" boundaryCondition="false" constant="false"/>
    </listOfSpecies>

    <listOfParameters>
      <parameter id="km" value="${params.km}" constant="true"/>
      <parameter id="vmax" value="${params.vmax}" constant="true"/>
      <parameter id="ki" value="${params.ki}" constant="true"/>
    </listOfParameters>

    <listOfReactions>
      <reaction id="r1" reversible="false" fast="false">
        <listOfReactants>
          <speciesReference species="S" stoichiometry="1" role="substrate"/>
        </listOfReactants>
        <listOfProducts>
          <speciesReference species="P" stoichiometry="1" role="product"/>
        </listOfProducts>
        <kineticLaw>
          <math xmlns="http://www.w3.org/1998/Math/MathML">
            <apply>
              <divide/>
              <apply>
                <times/>
                <ci>vmax</ci>
                <ci>S</ci>
              </apply>
              <apply>
                <plus/>
                <apply>
                  <times/>
                  <ci>km</ci>
                  <apply>
                    <plus/>
                    <cn>1</cn>
                    <apply>
                      <divide/>
                      <ci>I</ci>
                      <ci>ki</ci>
                    </apply>
                  </apply>
                </apply>
                <ci>S</ci>
              </apply>
            </apply>
          </math>
        </kineticLaw>
      </reaction>
    </listOfReactions>
  </model>
</sbml>`;

  return {
    xml,
    species: ['S', 'I', 'P', 'E'],
    reactions: ['r1'],
    parameters: ['km', 'vmax', 'ki']
  };
}

/**
 * Non-Competitive Inhibition Model
 *
 * Inhibitor I reduces Vmax regardless of substrate concentration.
 *
 * Rate = (Vmax * [S]) / ((Km + [S]) * (1 + [I] / Ki))
 *
 * Reference: Copeland, R. A. (2013). Enzymes: A Practical Introduction to
 * Structure, Mechanism, and Data Analysis (2nd ed.), Ch. 3, pure
 * non-competitive inhibition rate equation (inhibitor binds E and ES with
 * equal affinity, reducing Vmax without changing apparent Km).
 *
 * Parameters:
 *   - km: Michaelis constant
 *   - vmax: Maximum velocity
 *   - ki: Inhibition constant
 *   - s0: Initial substrate
 *   - i0: Initial inhibitor
 *   - e0: Enzyme concentration
 */
export function buildNonCompetitiveInhibition(params: {
  km: number;
  vmax: number;
  ki: number;
  s0: number;
  i0: number;
  e0?: number;
}): SBMLModel {
  const e0 = params.e0 ?? 1.0;

  const xml = `<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<sbml xmlns="http://www.sbml.org/sbml/level3/version1/core" level="3" version="1">
  <model id="noncompetitive_inhibition" metaid="meta_nci">
    <listOfCompartments>
      <compartment id="cell" constant="true" spatialDimensions="3" size="1"/>
    </listOfCompartments>

    <listOfSpecies>
      <species id="S" compartment="cell" initialConcentration="${params.s0}"
               hasOnlySubstanceUnits="false" boundaryCondition="false" constant="false"/>
      <species id="I" compartment="cell" initialConcentration="${params.i0}"
               hasOnlySubstanceUnits="false" boundaryCondition="false" constant="false"/>
      <species id="P" compartment="cell" initialConcentration="0"
               hasOnlySubstanceUnits="false" boundaryCondition="false" constant="false"/>
      <species id="E" compartment="cell" initialConcentration="${e0}"
               hasOnlySubstanceUnits="false" boundaryCondition="false" constant="false"/>
    </listOfSpecies>

    <listOfParameters>
      <parameter id="km" value="${params.km}" constant="true"/>
      <parameter id="vmax" value="${params.vmax}" constant="true"/>
      <parameter id="ki" value="${params.ki}" constant="true"/>
    </listOfParameters>

    <listOfReactions>
      <reaction id="r1" reversible="false" fast="false">
        <listOfReactants>
          <speciesReference species="S" stoichiometry="1" role="substrate"/>
        </listOfReactants>
        <listOfProducts>
          <speciesReference species="P" stoichiometry="1" role="product"/>
        </listOfProducts>
        <kineticLaw>
          <math xmlns="http://www.w3.org/1998/Math/MathML">
            <apply>
              <divide/>
              <apply>
                <times/>
                <ci>vmax</ci>
                <ci>S</ci>
              </apply>
              <apply>
                <times/>
                <apply>
                  <plus/>
                  <ci>km</ci>
                  <ci>S</ci>
                </apply>
                <apply>
                  <plus/>
                  <cn>1</cn>
                  <apply>
                    <divide/>
                    <ci>I</ci>
                    <ci>ki</ci>
                  </apply>
                </apply>
              </apply>
            </apply>
          </math>
        </kineticLaw>
      </reaction>
    </listOfReactions>
  </model>
</sbml>`;

  return {
    xml,
    species: ['S', 'I', 'P', 'E'],
    reactions: ['r1'],
    parameters: ['km', 'vmax', 'ki']
  };
}

/**
 * Product Inhibition Model
 *
 * Product P inhibits the enzyme, reducing activity over time.
 *
 * Rate = (Vmax * [S]) / ((Km + [S]) * (1 + [P] / Kp))
 *
 * Reference: Segel, I. H. (1975). Enzyme Kinetics: Behavior and Analysis
 * of Rapid Equilibrium and Steady-State Enzyme Systems, Wiley, Ch. 3-4
 * (product inhibition). This is the simplified mixed-type form (product
 * treated as a non-competitive-style inhibitor of Vmax); it does not model
 * product recompetition for the Km term, which Segel treats as a distinct,
 * more complex case (competitive product inhibition) -- use only where the
 * simplification is appropriate.
 *
 * Parameters:
 *   - km: Michaelis constant
 *   - vmax: Maximum velocity
 *   - kp: Product inhibition constant
 *   - s0: Initial substrate
 *   - e0: Enzyme concentration
 */
export function buildProductInhibition(params: {
  km: number;
  vmax: number;
  kp: number;
  s0: number;
  e0?: number;
}): SBMLModel {
  const e0 = params.e0 ?? 1.0;

  const xml = `<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<sbml xmlns="http://www.sbml.org/sbml/level3/version1/core" level="3" version="1">
  <model id="product_inhibition" metaid="meta_pi">
    <listOfCompartments>
      <compartment id="cell" constant="true" spatialDimensions="3" size="1"/>
    </listOfCompartments>

    <listOfSpecies>
      <species id="S" compartment="cell" initialConcentration="${params.s0}"
               hasOnlySubstanceUnits="false" boundaryCondition="false" constant="false"/>
      <species id="P" compartment="cell" initialConcentration="0"
               hasOnlySubstanceUnits="false" boundaryCondition="false" constant="false"/>
      <species id="E" compartment="cell" initialConcentration="${e0}"
               hasOnlySubstanceUnits="false" boundaryCondition="false" constant="false"/>
    </listOfSpecies>

    <listOfParameters>
      <parameter id="km" value="${params.km}" constant="true"/>
      <parameter id="vmax" value="${params.vmax}" constant="true"/>
      <parameter id="kp" value="${params.kp}" constant="true"/>
    </listOfParameters>

    <listOfReactions>
      <reaction id="r1" reversible="false" fast="false">
        <listOfReactants>
          <speciesReference species="S" stoichiometry="1" role="substrate"/>
        </listOfReactants>
        <listOfProducts>
          <speciesReference species="P" stoichiometry="1" role="product"/>
        </listOfProducts>
        <kineticLaw>
          <math xmlns="http://www.w3.org/1998/Math/MathML">
            <apply>
              <divide/>
              <apply>
                <times/>
                <ci>vmax</ci>
                <ci>S</ci>
              </apply>
              <apply>
                <times/>
                <apply>
                  <plus/>
                  <ci>km</ci>
                  <ci>S</ci>
                </apply>
                <apply>
                  <plus/>
                  <cn>1</cn>
                  <apply>
                    <divide/>
                    <ci>P</ci>
                    <ci>kp</ci>
                  </apply>
                </apply>
              </apply>
            </apply>
          </math>
        </kineticLaw>
      </reaction>
    </listOfReactions>
  </model>
</sbml>`;

  return {
    xml,
    species: ['S', 'P', 'E'],
    reactions: ['r1'],
    parameters: ['km', 'vmax', 'kp']
  };
}

/**
 * Export all builders
 */
export const SBMLBuilders = {
  michaelis_menten: buildMichaelisMenten,
  competitive_inhibition: buildCompetitiveInhibition,
  noncompetitive_inhibition: buildNonCompetitiveInhibition,
  product_inhibition: buildProductInhibition
};

/**
 * Helper function to select the right builder based on model type
 */
export function buildSBML(
  modelType: keyof typeof SBMLBuilders,
  params: Record<string, number>
): SBMLModel {
  const builder = SBMLBuilders[modelType];
  if (!builder) {
    throw new Error(`Unknown SBML model type: ${modelType}`);
  }
  return builder(params as any);
}
