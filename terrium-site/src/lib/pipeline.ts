/**
 * Terrium's build architecture, as data.
 *
 * Every field below describes something that actually happened while building
 * the population-genetics domain. The divergence in stage 03 is real: an
 * implementer's report claimed three tests would fail under the 2N->N
 * mutation, an independent rerun found two, and the permanent record in the
 * test file was corrected. That correction is in the git history.
 *
 * Nothing here is illustrative or representative. If a number appears on the
 * page it came from a run.
 */

export type StageState = 'idle' | 'active' | 'done' | 'conflict';

export interface PipelineStage {
  id: string;
  label: string;
  detail: string;
  /** Sub-rows, e.g. the two implementers working in parallel. */
  agents?: { name: string; model: string }[];
  /** Rendered when the stage is reached; the payload of what happened. */
  output?: string[];
  /** Conflict stages resolve to amber rather than mint. */
  conflict?: boolean;
  /** Milliseconds this stage occupies in the animated walkthrough. */
  duration: number;
}

export const PIPELINE: PipelineStage[] = [
  {
    id: 'spec',
    label: 'SPEC',
    detail: 'stage_02 · wright_fisher',
    output: [
      'governing model      binomial sampling, 2N copies',
      'verification target  H(t) = H0 (1 - 1/2N)^t',
      'pre-specified bug    2N -> N',
    ],
    duration: 2200,
  },
  {
    id: 'implement',
    label: 'IMPLEMENT',
    detail: 'identical prompt, two agents, no contact',
    agents: [
      { name: 'opencode', model: 'nemotron-3' },
      { name: 'freebuff', model: 'deepseek-v4-pro' },
    ],
    output: [
      'both returned an implementation',
      'both reported their own mutation tests',
    ],
    duration: 2600,
  },
  {
    id: 'diverge',
    label: 'DIVERGENCE',
    detail: 'reports disagree',
    conflict: true,
    output: [
      'report      "3 tests fail under 2N -> N"',
      'rerun       2 tests fail',
      'cause       fixation target runs different parameters',
      '            and is structurally untouched',
    ],
    duration: 3400,
  },
  {
    id: 'reproduce',
    label: 'REPRODUCE',
    detail: 'reviewer reruns independently',
    output: [
      'a report is a claim, not evidence',
      'every mutation reproduced before it is trusted',
    ],
    duration: 2400,
  },
  {
    id: 'record',
    label: 'RECORD',
    detail: 'permanent record corrected',
    output: [
      'test docstring updated: 3 -> 2',
      'correction dated and attributed',
    ],
    duration: 2200,
  },
  {
    id: 'verified',
    label: 'VERIFIED',
    detail: 'domain accepted',
    output: ['checked against exact mathematics, not against itself'],
    duration: 3000,
  },
];

export interface LedgerRow {
  domain: string;
  claim: string;
  method: string;
  reference: string;
}

/**
 * The verification ledger. The `reference` column is the product — it is the
 * difference between "our simulation says" and "this matches a result
 * published in 1962 that we did not produce."
 */
export const LEDGER: LedgerRow[] = [
  {
    domain: 'kinetics',
    claim: 'Km·ln(S₀/S) + (S₀−S) = Vmax·t',
    method: 'exact closed form',
    reference: 'implicit Michaelis-Menten solution',
  },
  {
    domain: 'epidemiology',
    claim: 'peak at S = N/R₀',
    method: 'closed form + independent solver',
    reference: 'scipy solve_ivp, shares no code',
  },
  {
    domain: 'pcr',
    claim: 'N(c) = n₀(1+E)^c',
    method: 'exact recurrence',
    reference: '—',
  },
  {
    domain: 'monte_carlo',
    claim: 'error ∝ 1/√N',
    method: 'CLT convergence rate',
    reference: '—',
  },
  {
    domain: 'popgen',
    claim: 'Hₜ = H₀(1 − 1/2N)^t',
    method: 'exact closed form',
    reference: '—',
  },
  {
    domain: 'popgen',
    claim: 'P(fixation) = p₀',
    method: 'exact closed form',
    reference: 'Kimura (1962)',
  },
  {
    domain: 'molecular_dynamics',
    claim: 'E(LJ13) = −44.326801 ε',
    method: 'published global minimum',
    reference: 'Hoare & Pal, Adv. Phys. 20, 161 (1971)',
  },
  {
    domain: 'molecular_dynamics',
    claim: '|ΔE|/E ∝ Δt²',
    method: 'symplectic order check',
    reference: 'Swope et al., J. Chem. Phys. 76, 637 (1982)',
  },
];
