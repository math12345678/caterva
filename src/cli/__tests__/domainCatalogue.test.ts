import {
  DOMAIN_CATALOGUE,
  NOT_A_TEACHING_DOMAIN,
  reconcileCatalogue,
} from '../domainCatalogue';

/**
 * The catalogue must agree with the engine, not with itself.
 *
 * Terrium advertises fifteen teaching domains and, until `scientific
 * domains` existed, nothing could tell a student what they are: `help`
 * listed nine commands (all enzyme kinetics or generic), and the engine's
 * own subcommands lived behind a second CLI that `help` never mentions.
 * Epidemiology, PCR, Monte Carlo and molecular dynamics appeared in
 * neither.
 *
 * A capability nobody can find is not a capability — and a catalogue that
 * drifts from the engine reintroduces exactly that, one level up. These
 * tests are about the drift.
 */

/** What the engine reports today, plus the ingest path that is not a domain. */
const ENGINE_IDS = [
  'cell_cycle_oscillator',
  'gillespie_ssa',
  'gillespie_ssa_bimolecular',
  'gillespie_ssa_replicates',
  'lotka_volterra',
  'mm',
  'mm_competitive_inhibition',
  'molecular_dynamics',
  'monte_carlo_pi',
  'pcr',
  'repressilator',
  'sbml',
  'seir',
  'sir',
  'two_locus_wright_fisher',
  'wright_fisher',
];

describe('the catalogue against the engine', () => {
  it('describes every teaching domain the engine dispatches', () => {
    const report = reconcileCatalogue(ENGINE_IDS);
    // Named rather than counted: a failure should say WHICH domain a
    // student cannot find.
    expect(report.undescribed).toEqual([]);
  });

  it('promises no domain the engine does not have', () => {
    expect(reconcileCatalogue(ENGINE_IDS).phantom).toEqual([]);
  });

  /**
   * `sbml` is "run the model in this file" — a generic ingest path, not a
   * teaching domain. It is why the README says fifteen and DISPATCH holds
   * sixteen, and `check_documented_counts.py` declines to derive that
   * number for the same reason.
   */
  it('excludes the ingest path, so fifteen means fifteen', () => {
    const report = reconcileCatalogue(ENGINE_IDS);
    expect(NOT_A_TEACHING_DOMAIN.has('sbml')).toBe(true);
    expect(report.entries.map((e) => e.id)).not.toContain('sbml');
    expect(report.entries).toHaveLength(15);
  });

  /**
   * THE ONE THAT MATTERS WHEN SOMEBODY ADDS A DOMAIN. Without this, the new
   * domain runs, nothing describes it, and the catalogue silently keeps
   * printing the old list — which is the defect this command was written to
   * remove, arriving again by omission.
   */
  it('reports a new engine domain rather than quietly omitting it', () => {
    const report = reconcileCatalogue([...ENGINE_IDS, 'brand_new_domain']);
    expect(report.undescribed).toEqual(['brand_new_domain']);
  });

  /**
   * The opposite failure, and worse in kind: an entry whose example command
   * cannot run. A catalogue listing what the tool cannot do teaches a reader
   * to distrust the rest of it.
   */
  it('reports an entry the engine dropped', () => {
    const withoutPcr = ENGINE_IDS.filter((id) => id !== 'pcr');
    const report = reconcileCatalogue(withoutPcr);
    expect(report.phantom).toEqual(['pcr']);
    expect(report.entries.map((e) => e.id)).not.toContain('pcr');
  });
});

describe('what each entry has to carry to be useful', () => {
  it.each(DOMAIN_CATALOGUE.map((d) => [d.id, d] as const))(
    '%s is runnable and explained',
    (_id, entry) => {
      // A title a student would recognise, not the identifier.
      expect(entry.title.length).toBeGreaterThan(3);
      expect(entry.title).not.toBe(entry.id);
      // A sentence saying what question it answers.
      expect(entry.summary.length).toBeGreaterThan(15);
      // A command, not a description of one.
      expect(entry.example).toMatch(/^(simulate|python -m Terium\.cli)\b/);
    },
  );

  /**
   * Examples carry concrete numbers because a student copies the line and
   * runs it. A placeholder would make every entry fail on first use, and
   * they would reasonably conclude the tool is broken.
   */
  it.each(DOMAIN_CATALOGUE.map((d) => [d.id, d.example] as const))(
    '%s example has real values, not placeholders',
    (_id, example) => {
      expect(example).not.toMatch(/<[A-Z_]+>|VALUE|NAME\b/);
      expect(example).toMatch(/\d/);
    },
  );

  it('has no duplicate ids', () => {
    const ids = DOMAIN_CATALOGUE.map((d) => d.id);
    expect(new Set(ids).size).toBe(ids.length);
  });
});
