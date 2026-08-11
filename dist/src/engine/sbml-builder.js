"use strict";
/**
 * SBML Model Builder - Generates real SBML Level 3 Version 1 models
 *
 * SBML (Systems Biology Markup Language) is the standard for describing
 * biological models. This builder generates SBML that Tellurium/libroadrunner
 * can execute.
 *
 * Each model represents a real biochemical system:
 * - Michaelis-Menten: E + S ⇌ ES → E + P
 * - Competitive inhibition: I competes with S for active site
 * - Non-competitive inhibition: I reduces Vmax regardless of S
 * - Product inhibition: P reduces enzyme activity
 * - Allosteric: S binding enhances/reduces activity
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.SBMLBuilders = void 0;
exports.buildMichaelisMenten = buildMichaelisMenten;
exports.buildCompetitiveInhibition = buildCompetitiveInhibition;
exports.buildNonCompetitiveInhibition = buildNonCompetitiveInhibition;
exports.buildProductInhibition = buildProductInhibition;
exports.buildSBML = buildSBML;
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
function buildMichaelisMenten(params) {
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
 * Parameters:
 *   - km: Michaelis constant
 *   - vmax: Maximum velocity
 *   - ki: Inhibition constant
 *   - s0: Initial substrate
 *   - i0: Initial inhibitor
 *   - e0: Enzyme concentration
 */
function buildCompetitiveInhibition(params) {
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
 * Parameters:
 *   - km: Michaelis constant
 *   - vmax: Maximum velocity
 *   - ki: Inhibition constant
 *   - s0: Initial substrate
 *   - i0: Initial inhibitor
 *   - e0: Enzyme concentration
 */
function buildNonCompetitiveInhibition(params) {
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
 * Parameters:
 *   - km: Michaelis constant
 *   - vmax: Maximum velocity
 *   - kp: Product inhibition constant
 *   - s0: Initial substrate
 *   - e0: Enzyme concentration
 */
function buildProductInhibition(params) {
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
exports.SBMLBuilders = {
    michaelis_menten: buildMichaelisMenten,
    competitive_inhibition: buildCompetitiveInhibition,
    noncompetitive_inhibition: buildNonCompetitiveInhibition,
    product_inhibition: buildProductInhibition
};
/**
 * Helper function to select the right builder based on model type
 */
function buildSBML(modelType, params) {
    const builder = exports.SBMLBuilders[modelType];
    if (!builder) {
        throw new Error(`Unknown SBML model type: ${modelType}`);
    }
    return builder(params);
}
