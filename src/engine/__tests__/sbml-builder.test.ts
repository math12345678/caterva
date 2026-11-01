/**
 * SBML Builder Tests
 *
 * Verify that SBML models are correctly generated for all kinetic models
 */

import {
  buildMichaelisMenten,
  buildCompetitiveInhibition,
  buildNonCompetitiveInhibition,
  buildProductInhibition,
  buildSBML
} from '../sbml-builder';

describe('SBML Builder', () => {
  describe('Michaelis-Menten', () => {
    it('should generate valid SBML', () => {
      const model = buildMichaelisMenten({
        km: 5.2,
        vmax: 12.8,
        s0: 10.0,
        e0: 1.0
      });

      expect(model.xml).toContain('<?xml version="1.0"');
      expect(model.xml).toContain('michaelis_menten');
      expect(model.species).toContain('S');
      expect(model.species).toContain('P');
      expect(model.species).toContain('E');
      expect(model.parameters).toContain('km');
      expect(model.parameters).toContain('vmax');
      expect(model.reactions).toContain('r1');
    });

    it('should use provided initial concentrations', () => {
      const model = buildMichaelisMenten({
        km: 5.2,
        vmax: 12.8,
        s0: 50.0,
        e0: 2.5
      });

      expect(model.xml).toContain('initialConcentration="50"');
      expect(model.xml).toContain('initialConcentration="2.5"');
    });

    it('should default enzyme concentration to 1.0', () => {
      const model = buildMichaelisMenten({
        km: 5.2,
        vmax: 12.8,
        s0: 10.0
      });

      expect(model.xml).toContain('initialConcentration="1"');
    });

    it('should include rate equation', () => {
      const model = buildMichaelisMenten({
        km: 5.2,
        vmax: 12.8,
        s0: 10.0
      });

      // Should contain Michaelis-Menten rate law: (vmax * S) / (km + S)
      expect(model.xml).toContain('<math');
      expect(model.xml).toContain('vmax');
      expect(model.xml).toContain('km');
      expect(model.xml).toContain('divide');
    });
  });

  describe('Competitive Inhibition', () => {
    it('should generate valid SBML', () => {
      const model = buildCompetitiveInhibition({
        km: 5.2,
        vmax: 12.8,
        ki: 3.0,
        s0: 10.0,
        i0: 2.0,
        e0: 1.0
      });

      expect(model.xml).toContain('competitive_inhibition');
      expect(model.species).toContain('I');
      expect(model.parameters).toContain('ki');
    });

    it('should include inhibitor in rate equation', () => {
      const model = buildCompetitiveInhibition({
        km: 5.2,
        vmax: 12.8,
        ki: 3.0,
        s0: 10.0,
        i0: 2.0
      });

      // Should contain (1 + [I] / Ki) term
      expect(model.xml).toContain('ki');
    });
  });

  describe('Non-Competitive Inhibition', () => {
    it('should generate valid SBML', () => {
      const model = buildNonCompetitiveInhibition({
        km: 5.2,
        vmax: 12.8,
        ki: 3.0,
        s0: 10.0,
        i0: 2.0,
        e0: 1.0
      });

      expect(model.xml).toContain('noncompetitive_inhibition');
      expect(model.species).toContain('I');
      expect(model.parameters).toContain('ki');
    });
  });

  describe('Product Inhibition', () => {
    it('should generate valid SBML', () => {
      const model = buildProductInhibition({
        km: 5.2,
        vmax: 12.8,
        kp: 1.5,
        s0: 10.0,
        e0: 1.0
      });

      expect(model.xml).toContain('product_inhibition');
      expect(model.parameters).toContain('kp');
    });
  });

  describe('buildSBML helper', () => {
    it('should route to correct builder', () => {
      const mm = buildSBML('michaelis_menten', {
        km: 5.2,
        vmax: 12.8,
        s0: 10.0
      });

      expect(mm.xml).toContain('michaelis_menten');
    });

    it('should throw on unknown model type', () => {
      expect(() => {
        buildSBML('unknown' as any, { km: 5 });
      }).toThrow('Unknown SBML model type');
    });
  });

  describe('SBML Validity', () => {
    it('all models should have closing XML tag', () => {
      const models = [
        buildMichaelisMenten({ km: 5.2, vmax: 12.8, s0: 10.0 }),
        buildCompetitiveInhibition({
          km: 5.2,
          vmax: 12.8,
          ki: 3.0,
          s0: 10.0,
          i0: 2.0
        }),
        buildNonCompetitiveInhibition({
          km: 5.2,
          vmax: 12.8,
          ki: 3.0,
          s0: 10.0,
          i0: 2.0
        }),
        buildProductInhibition({
          km: 5.2,
          vmax: 12.8,
          kp: 1.5,
          s0: 10.0
        })
      ];

      models.forEach((model) => {
        expect(model.xml).toMatch(/<\/sbml>$/);
        expect(model.xml).toContain('<listOfCompartments>');
        expect(model.xml).toContain('<listOfSpecies>');
        expect(model.xml).toContain('<listOfReactions>');
      });
    });

    it('should have matching parameter metadata', () => {
      const model = buildMichaelisMenten({
        km: 5.2,
        vmax: 12.8,
        s0: 10.0
      });

      // Parameters should have metaid for reference
      expect(model.xml).toMatch(/metaid="meta_km"/);
      expect(model.xml).toMatch(/metaid="meta_vmax"/);
    });
  });

  describe('Species Handling', () => {
    it('should set correct initial concentrations', () => {
      const model = buildMichaelisMenten({
        km: 5.2,
        vmax: 12.8,
        s0: 100.0,
        e0: 5.0
      });

      expect(model.xml).toContain('initialConcentration="100"');
      expect(model.xml).toContain('initialConcentration="5"');
      expect(model.xml).toContain('initialConcentration="0"'); // Product starts at 0
    });

    it('should mark species as non-boundary', () => {
      const model = buildMichaelisMenten({
        km: 5.2,
        vmax: 12.8,
        s0: 10.0
      });

      expect(model.xml).toMatch(/boundaryCondition="false"/g);
    });
  });
});
