"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
/**
 * Unit conversion, and the regression it exists to prevent.
 *
 * A hardcoded `vmax / 1000` with the comment "convert uM/min to mM/min"
 * has been introduced into this tree TWICE by different agents, both times
 * to make a failing test pass. It was a fabrication both times: the factor
 * applied unconditionally regardless of what units the parameters actually
 * declared, and nothing in the codebase established the units it asserted.
 *
 * These tests pin the property that makes such a constant unnecessary --
 * conversion is derived from the declared unit strings -- and the property
 * that makes it dangerous: an unknown unit must raise rather than pass
 * through. A wrong unit produces a number that is off by orders of
 * magnitude while looking entirely reasonable.
 */
const units_1 = require("../units");
describe('concentration conversion', () => {
    it.each([
        [1, 'M', 'mM', 1000],
        [1, 'mM', 'M', 0.001],
        [1000, 'uM', 'mM', 1],
        [1, 'mM', 'uM', 1000],
        [1, 'uM', 'nM', 1000],
        [5.2, 'mM', 'mM', 5.2]
    ])('%p %s -> %s = %p', (value, from, to, expected) => {
        expect((0, units_1.convertConcentration)(value, from, to)).toBeCloseTo(expected, 9);
    });
    it('treats both micro signs and ASCII u as the same unit', () => {
        // U+00B5 MICRO SIGN, U+03BC GREEK SMALL LETTER MU, and 'u'. These are
        // visually identical; different sources emit different ones, and this
        // tree's own fixtures use U+03BC. Treating them as distinct would make
        // a unit fail to parse for a reason invisible in a diff.
        const viaMicroSign = (0, units_1.concentrationFactor)('µM');
        const viaGreekMu = (0, units_1.concentrationFactor)('μM');
        const viaAscii = (0, units_1.concentrationFactor)('uM');
        expect(viaMicroSign).toBe(viaAscii);
        expect(viaGreekMu).toBe(viaAscii);
    });
    it('is case- and whitespace-insensitive', () => {
        expect((0, units_1.concentrationFactor)(' mM ')).toBe((0, units_1.concentrationFactor)('mm'));
    });
});
describe('time conversion', () => {
    it.each([
        ['s', 1],
        ['min', 60],
        ['h', 3600],
        ['hours', 3600]
    ])('%s -> %p seconds', (unit, expected) => {
        expect((0, units_1.timeFactor)(unit)).toBe(expected);
    });
});
describe('rate conversion', () => {
    it('reproduces the /1000 case ONLY when the units actually say so', () => {
        // The hardcoded constant happened to be right for exactly this pairing
        // and wrong for every other one.
        expect((0, units_1.convertRate)(1000, 'uM/min', 'mM/min')).toBeCloseTo(1, 9);
    });
    it('converts the time component too', () => {
        // 60 mM/min = 1 mM/s. A constant that only touches the concentration
        // half silently leaves the rate wrong by 60x.
        expect((0, units_1.convertRate)(60, 'mM/min', 'mM/s')).toBeCloseTo(1, 9);
    });
    it('converts both components at once', () => {
        // 1000 uM/min -> mM/s = 1 mM/min = 1/60 mM/s
        expect((0, units_1.convertRate)(1000, 'uM/min', 'mM/s')).toBeCloseTo(1 / 60, 9);
    });
    it('round-trips', () => {
        const there = (0, units_1.convertRate)(12.4, 'uM/min', 'M/h');
        expect((0, units_1.convertRate)(there, 'M/h', 'uM/min')).toBeCloseTo(12.4, 9);
    });
});
describe('refusing to guess', () => {
    it('throws on an unrecognised concentration unit', () => {
        expect(() => (0, units_1.concentrationFactor)('furlongs')).toThrow(units_1.UnitError);
    });
    it('throws on an unrecognised time unit', () => {
        expect(() => (0, units_1.timeFactor)('fortnight')).toThrow(units_1.UnitError);
    });
    it('rejects specific activity rather than treating it as a rate', () => {
        // 'umol/min/mg' is amount per time per mass of protein. Converting it
        // to a concentration rate needs [E] and the molecular weight. BRENDA
        // reports turnover in exactly this form, so silently reading it as
        // 'umol/min' would produce a physically meaningless number from real
        // data.
        expect(() => (0, units_1.parseRateUnit)('umol/min/mg')).toThrow(/specific activity/i);
    });
    it('rejects a rate that is not <concentration>/<time>', () => {
        expect(() => (0, units_1.parseRateUnit)('mM')).toThrow(units_1.UnitError);
    });
    it('throws rather than defaulting when Vmax has no declared unit', () => {
        expect(() => (0, units_1.vmaxInSubstrateUnitsPerSecond)(10, undefined, 'mM')).toThrow(units_1.UnitError);
    });
    it('throws rather than defaulting when the substrate has no unit', () => {
        expect(() => (0, units_1.vmaxInSubstrateUnitsPerSecond)(10, 'uM/min', undefined)).toThrow(units_1.UnitError);
    });
});
describe('vmaxInSubstrateUnitsPerSecond', () => {
    it('expresses Vmax in substrate units per second', () => {
        // 600 uM/min in mM units = 0.6 mM/min = 0.01 mM/s
        expect((0, units_1.vmaxInSubstrateUnitsPerSecond)(600, 'uM/min', 'mM')).toBeCloseTo(0.01, 9);
    });
    it('is not a constant factor -- it follows the declared units', () => {
        // The whole point. The same numeric Vmax converts differently
        // depending on what its unit says, which no hardcoded divisor can do.
        const asMicroPerMin = (0, units_1.vmaxInSubstrateUnitsPerSecond)(600, 'uM/min', 'mM');
        const asMilliPerSec = (0, units_1.vmaxInSubstrateUnitsPerSecond)(600, 'mM/s', 'mM');
        expect(asMicroPerMin).not.toBeCloseTo(asMilliPerSec, 6);
        expect(asMilliPerSec).toBe(600);
    });
});
