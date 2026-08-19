/**
 * What Terrium can simulate, and the command that runs each one.
 *
 * THE PROBLEM THIS EXISTS FOR
 * ---------------------------
 * Terrium advertises fifteen teaching domains. Nothing told a student what
 * they are.
 *
 *   - `scientificCLI.ts help` lists nine commands. All of them are enzyme
 *     kinetics (`resolve`, `literature`, `corpus`) or generic (`simulate`,
 *     `sweep`, `validate`).
 *   - `python -m Terium.cli --help` lists seven subcommands, all population
 *     genetics and Gillespie.
 *   - Neither mentions the other exists.
 *   - Neither names epidemiology, PCR, Monte Carlo or molecular dynamics —
 *     domains the engine runs, verified against closed-form solutions, with
 *     over a thousand tests behind them.
 *
 * A capability nobody can find is not a capability. ADR 0090 says that about
 * exported functions; it is worse for a product surface, because the person
 * who cannot find it is the person the product is for.
 *
 * WHY THE LIST IS NOT WRITTEN HERE
 * --------------------------------
 * The domain NAMES come from `terium_runner.py --list-domains`, which emits
 * `DISPATCH` — the table the engine actually dispatches on. A hand-written
 * list is a second source of truth that goes stale the first time somebody
 * adds a domain, and `terium_runner.py` already carries a comment about two
 * tables "kept equal by hand (they have diverged before)".
 *
 * What IS written here is the part that cannot be derived: a sentence saying
 * what the domain is for, and an example. A description is a judgement, and
 * generating one from an identifier would produce "Mm" and "Sir".
 *
 * So the two halves are checked against each other. A domain in `DISPATCH`
 * with no entry below is a domain a student cannot discover, and
 * `describeDomains` reports it rather than omitting it — the alternative
 * being a catalogue that silently shrinks as the engine grows.
 */

export interface DomainEntry {
  /** Key in the engine's DISPATCH table. */
  id: string;
  /** What a student would call it. */
  title: string;
  /** One line: what question it answers. */
  summary: string;
  /** A command that runs, copy-pasteable. */
  example: string;
  /** Whether the parameters can be resolved from literature. */
  literatureBacked: boolean;
}

/**
 * `sbml` is deliberately absent, and that is the one judgement call in this
 * file. It is a generic ingest path — "run the model in this file" — not a
 * teaching domain, which is why the README's own count is fifteen against
 * DISPATCH's sixteen. `check_documented_counts.py` makes the same
 * distinction and refuses to derive the number for the same reason.
 */
export const NOT_A_TEACHING_DOMAIN = new Set(['sbml']);

export const DOMAIN_CATALOGUE: DomainEntry[] = [
  {
    id: 'mm',
    title: 'Michaelis–Menten enzyme kinetics',
    summary: 'How fast an enzyme turns substrate into product.',
    example:
      'simulate "michaelis menten of lactate dehydrogenase on pyruvate in Homo sapiens" \\\n      --resolve --s0 10mM --enzyme-conc 0.001mM',
    literatureBacked: true,
  },
  {
    id: 'mm_competitive_inhibition',
    title: 'Competitive inhibition',
    summary: 'The same, with an inhibitor competing for the active site.',
    example:
      'simulate mm --resolve --model competitive --enzyme "lactate dehydrogenase" \\\n      --substrate pyruvate --organism "Homo sapiens" --s0 10mM --i0 1mM --enzyme-conc 0.001mM',
    literatureBacked: true,
  },
  {
    id: 'sir',
    title: 'SIR epidemic',
    summary: 'How an infection spreads through a population and burns out.',
    example: 'simulate sir --beta 0.3 --gamma 0.1 --i0 0.01 --end 160',
    literatureBacked: true,
  },
  {
    id: 'seir',
    title: 'SEIR epidemic',
    summary: 'SIR with an exposed-but-not-yet-infectious stage.',
    example: 'simulate seir --beta 0.3 --sigma 0.2 --gamma 0.1 --i0 0.01 --end 160',
    literatureBacked: true,
  },
  {
    id: 'pcr',
    title: 'PCR amplification',
    summary: 'How much DNA you have after N cycles, with efficiency below 1.',
    example: 'simulate pcr --cycles 30 --efficiency 0.9 --initial 1000',
    literatureBacked: false,
  },
  {
    id: 'monte_carlo_pi',
    title: 'Monte Carlo estimation of pi',
    summary: 'Why random sampling converges, and how slowly (1/sqrt(N)).',
    example: 'simulate monte_carlo_pi --samples 100000 --seed 1',
    literatureBacked: false,
  },
  {
    id: 'wright_fisher',
    title: 'Wright–Fisher drift',
    summary: 'How allele frequencies wander in a finite population.',
    example: 'python -m Terium.cli wf --population-size 100 --starting-frequency 0.5 --generations 200 --seed 1',
    literatureBacked: false,
  },
  {
    id: 'two_locus_wright_fisher',
    title: 'Two-locus Wright–Fisher',
    summary: 'Linkage disequilibrium, and how recombination decays it.',
    example: 'python -m Terium.cli ld --population-size 500 --recombination-rate 0.01 --generations 200 --seed 1',
    literatureBacked: false,
  },
  {
    id: 'gillespie_ssa',
    title: 'Gillespie SSA — decay',
    summary: 'Exact stochastic A → B, where small numbers make noise matter.',
    example: 'python -m Terium.cli ssa --a0 100 --k 0.1 --end 50 --seed 1',
    literatureBacked: false,
  },
  {
    id: 'gillespie_ssa_bimolecular',
    title: 'Gillespie SSA — association',
    summary: 'Exact stochastic A + B → C.',
    example: 'python -m Terium.cli ssa --bimolecular --a0 100 --b0 100 --k 0.01 --end 50 --seed 1',
    literatureBacked: false,
  },
  {
    id: 'gillespie_ssa_replicates',
    title: 'Gillespie SSA — replicates',
    summary: 'Many runs of the same system, to see the spread rather than one path.',
    example: 'python -m Terium.cli ssa --a0 100 --k 0.1 --end 50 --seed 1 --out runs.csv',
    literatureBacked: false,
  },
  {
    id: 'molecular_dynamics',
    title: 'Molecular dynamics (Lennard-Jones)',
    summary: 'Atoms attracting and repelling, with energy conserved.',
    example: 'simulate molecular_dynamics --atoms 13 --steps 1000 --dt 0.001',
    literatureBacked: false,
  },
  {
    id: 'lotka_volterra',
    title: 'Lotka–Volterra',
    summary: 'Predator and prey populations cycling against each other.',
    example: 'simulate lotka_volterra --alpha 1.1 --beta 0.4 --delta 0.1 --gamma 0.4 --end 100',
    literatureBacked: false,
  },
  {
    id: 'repressilator',
    title: 'Repressilator',
    summary: 'Three genes repressing each other in a ring, producing oscillation.',
    example: 'simulate repressilator --end 500',
    literatureBacked: true,
  },
  {
    id: 'cell_cycle_oscillator',
    title: 'Cell-cycle oscillator',
    summary: 'The biochemical clock that drives division.',
    example: 'simulate cell_cycle_oscillator --end 200',
    literatureBacked: true,
  },
];

export interface CatalogueReport {
  entries: DomainEntry[];
  /** In DISPATCH, described nowhere — a domain nobody can discover. */
  undescribed: string[];
  /** Described here, absent from DISPATCH — an entry promising a domain that does not run. */
  phantom: string[];
}

/**
 * Reconcile the written catalogue against what the engine really dispatches.
 *
 * BOTH DIRECTIONS MATTER, AND THEY FAIL DIFFERENTLY.
 *
 * `undescribed` is a domain the engine runs and no student can find — the
 * defect this file exists to remove, arriving again the next time somebody
 * adds a domain and does not come back here.
 *
 * `phantom` is worse in kind: an entry advertising a domain that is not
 * there, so the example command cannot run. A catalogue that lists something
 * the tool cannot do teaches a reader to distrust the rest of it.
 *
 * Reported rather than filtered. Silently dropping either would make this a
 * catalogue that agrees with itself and not with the engine.
 */
export function reconcileCatalogue(dispatchIds: string[]): CatalogueReport {
  const teaching = dispatchIds.filter((id) => !NOT_A_TEACHING_DOMAIN.has(id));
  const described = new Set(DOMAIN_CATALOGUE.map((d) => d.id));
  const available = new Set(teaching);

  return {
    entries: DOMAIN_CATALOGUE.filter((d) => available.has(d.id)),
    undescribed: teaching.filter((id) => !described.has(id)).sort(),
    phantom: DOMAIN_CATALOGUE.map((d) => d.id)
      .filter((id) => !available.has(id))
      .sort(),
  };
}
