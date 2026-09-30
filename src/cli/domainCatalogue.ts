/**
 * What Caterva can simulate, and the command that runs each one.
 *
 * THE PROBLEM THIS EXISTS FOR
 * ---------------------------
 * Caterva advertises fifteen teaching domains. Nothing told a student what
 * they are.
 *
 *   - `scientificCLI.ts help` lists nine commands. All of them are enzyme
 *     kinetics (`resolve`, `literature`, `corpus`) or generic (`simulate`,
 *     `sweep`, `validate`).
 *   - `python -m caterva.cli --help` lists seven subcommands, all population
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
 * The domain NAMES come from `caterva_runner.py --list-domains`, which emits
 * `DISPATCH` — the table the engine actually dispatches on. A hand-written
 * list is a second source of truth that goes stale the first time somebody
 * adds a domain, and `caterva_runner.py` already carries a comment about two
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
 * teaching domain, which is why the catalogue holds five domains against
 * DISPATCH's six. `check_documented_counts.py` makes the same
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
      // --inhibitor since 2026-09-30: the Ki is looked up under the inhibitor
      // BRENDA files it under, and without one the run refuses. Gossypol has
      // three human Ki rows on BRENDA's LDH page (ref 711801, one per
      // isoform); none states a mode, and the run prints that it does not.
      'simulate mm --resolve --model competitive --enzyme "lactate dehydrogenase" \\\n      --substrate pyruvate --organism "Homo sapiens" --inhibitor gossypol \\\n      --s0 10mM --i0 1mM --enzyme-conc 0.001mM',
    literatureBacked: true,
  },
  {
    id: 'gillespie_ssa',
    title: 'Gillespie SSA — decay',
    summary: 'Exact stochastic A → B, where small numbers make noise matter.',
    example: 'python -m caterva.cli ssa --a0 100 --k 0.1 --end 50 --seed 1',
    literatureBacked: false,
  },
  {
    id: 'gillespie_ssa_bimolecular',
    title: 'Gillespie SSA — association',
    summary: 'Exact stochastic A + B → C.',
    example: 'python -m caterva.cli ssa --bimolecular --a0 100 --b0 100 --k 0.01 --end 50 --seed 1',
    literatureBacked: false,
  },
  {
    id: 'gillespie_ssa_replicates',
    title: 'Gillespie SSA — replicates',
    summary: 'Many runs of the same system, to see the spread rather than one path.',
    example: 'python -m caterva.cli ssa --a0 100 --k 0.1 --end 50 --seed 1 --out runs.csv',
    literatureBacked: false,
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
