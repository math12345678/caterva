/**
 * The site's command line.
 *
 * Every command that reports a number computes it, here, now. `run mm`
 * evaluates the Michaelis-Menten rate law on two cited BRENDA constants.
 * `verify gillespie_ssa` runs fifty exact stochastic simulations and holds
 * their mean to the closed form. Nothing below prints a stored answer,
 * because a page arguing that claims must be checked should not itself be
 * a set of unchecked claims.
 *
 * Only Caterva's five live domains run (README.md, "five simulation
 * domains"; src/cli/domainCatalogue.ts). The domains archived on 2026-09-27
 * answer that they are archived and name the release that still runs them.
 */

import { LEDGER, PIPELINE } from './pipeline.ts';
import {
  simulateMichaelisMenten,
  simulateMMCompetitiveInhibition,
  DEFAULT_MM,
  DEFAULT_MM_COMPETITIVE,
  MM_TOLERANCE,
} from './simulate.ts';
import {
  checkAssociationMean,
  checkDecayMean,
  odeAssociation,
  ssaAssociation,
  ssaDecay,
  type EnsembleCheck,
} from './ssa.ts';
import {
  resolveAndSimulate,
  ApiUnavailableError,
  API_BASE_URL,
  type ParameterProvenanceEntry,
} from './api.ts';


export type LineKind =
  | 'out'
  | 'dim'
  | 'ok'
  | 'warn'
  | 'err'
  | 'cmd'
  | 'head'
  | 'rule';

export interface Line {
  kind: LineKind;
  text: string;
}

const o = (text = ''): Line => ({ kind: 'out', text });
const d = (text: string): Line => ({ kind: 'dim', text });
const ok = (text: string): Line => ({ kind: 'ok', text });
const warn = (text: string): Line => ({ kind: 'warn', text });
const err = (text: string): Line => ({ kind: 'err', text });
const head = (text: string): Line => ({ kind: 'head', text });
const rule = (): Line => ({ kind: 'rule', text: '' });

export interface Command {
  name: string;
  args?: string;
  help: string;
  run: (args: string[]) => Line[] | Promise<Line[]>;
}

/**
 * Render a resolved-and-simulated job's real provenance.
 *
 * IMPORTANT distinction, per the API's own test suite
 * ("model citations are not value citations", provenance.test.ts):
 * `provenance.modelCitations` documents the *model/methodology* this domain
 * generally draws on (e.g. "BRENDA is the database this system would
 * consult for enzyme kinetics") -- it is NOT a claim that any specific
 * number below was actually looked up there. That claim, if true, lives
 * per-parameter in `parameterProvenance[key].origin === "resolved"` with its
 * own `source`. Printing modelCitations under a "source:" label (as an
 * earlier version of this file did) conflates the two and makes an
 * unresolved default look literature-backed. Every parameter line below
 * must show its own real origin instead.
 */
function renderProvenance(
  domain: string,
  parameters: Record<string, unknown>,
  provenance: { reasoning: string; modelCitations: string[]; flags: string[] },
  parameterProvenance: Record<string, ParameterProvenanceEntry>,
): Line[] {
  const originTag: Record<ParameterProvenanceEntry['origin'], string> = {
    resolved: 'resolved',
    user: 'user-supplied',
    llm: 'llm-guessed',
    default: 'default',
  };
  const originLine = (fn: typeof ok, k: string, v: unknown, entry?: ParameterProvenanceEntry) => {
    const tag = entry ? originTag[entry.origin] : 'unlabeled';
    const text = `  ${k.padEnd(10)}${String(v).padEnd(10)}[${tag}]`;
    return fn(text);
  };

  const entries = Object.entries(parameters).map(([k, v]) => [
    k,
    v,
    parameterProvenance[k],
  ] as const);
  const resolvedCount = entries.filter(([, , e]) => e?.origin === 'resolved').length;
  // The header must say what actually happened, always as a ratio -- never
  // a bare "RESOLVED" that a single resolved parameter out of five can
  // trigger while the other four are silently defaults. That exact framing
  // was reported back as misleading (a user saw km resolve correctly and
  // read the unqualified "RESOLVED" header as a claim about all five
  // parameters). Most domains only have ONE resolvable field at all
  // (RESOLVABLE_FIELDS on the API side) -- e.g. mm only resolves km, never
  // vmax/s0/end/points, because those aren't things literature reports a
  // single true value for (s0/end/points are simulation choices; vmax
  // needs an enzyme concentration nothing in BRENDA records). A query that
  // resolves its one resolvable field is a full, correct success for that
  // domain, not a partial one -- so the header states the count plainly
  // and lets the per-parameter [default] notes (already printed below)
  // explain why the rest were never resolvable in the first place, rather
  // than a status word implying they should have been.
  const status = `${resolvedCount}/${entries.length} RESOLVED FROM LITERATURE`;

  const lines: Line[] = [head(`${status} · ${domain.toUpperCase()}`), rule()];
  for (const [k, v, entry] of entries) {
    const fn = entry?.origin === 'resolved' ? ok : entry?.origin === 'default' ? warn : o;
    lines.push(originLine(fn, k, v, entry));
    if (entry?.source) lines.push(d(`    source: ${entry.source}`));
    if (entry?.note) lines.push(d(`    ${entry.note}`));
  }
  lines.push(o(), d(`  ${provenance.reasoning}`));
  if (provenance.modelCitations.length > 0) {
    lines.push(d('  general reference for this model type (not a per-value citation):'));
    for (const c of provenance.modelCitations) lines.push(d(`    ${c}`));
  }
  if (provenance.flags.length > 0) {
    lines.push(o());
    for (const f of provenance.flags) lines.push(warn(`  flag: ${f}`));
  }
  return lines;
}

async function runLiteratureBacked(query: string, domainLabel: string): Promise<Line[]> {
  if (!API_BASE_URL) {
    return [
      err(`  no science-agent API configured (VITE_CATERVA_API_URL is unset)`),
      d(`  cannot claim a literature-backed ${domainLabel} result without one --`),
      d(`  see 'verify mm'`),
      d(`  for a pure math check of the integrator instead.`),
    ];
  }
  try {
    const job = await resolveAndSimulate(query);
    if (job.status === 'failed' || !job.result) {
      if (job.error?.error === 'MISSING_REQUIRED_INPUT') {
        return [
          err(`  cannot run: literature resolution was incomplete`),
          o(),
          d(`  ${job.error.message}`),
          o(),
          d(`  every parameter must either be resolved from literature or typed`),
          d(`  by you -- nothing runs on an unsourced default. add the values`),
          d(`  above to your query (e.g. 'run kinetics trypsin km=5 vmax=10') and`),
          d(`  try again.`),
        ];
      }
      return [
        err(`  pipeline failed: ${job.error?.message ?? 'unknown error'}`),
      ];
    }
    return renderProvenance(
      job.result.domain,
      job.result.parameters,
      job.result.provenance,
      job.result.parameterProvenance,
    );
  } catch (e) {
    const msg = e instanceof ApiUnavailableError ? e.message : String(e);
    return [err(`  could not reach the literature resolution API: ${msg}`)];
  }
}

// [id, description, type, literature]: the five live domains, with the ids
// and order of src/cli/domainCatalogue.ts. literature says what (if
// anything) THIS SHELL resolves from real databases: 'run mm <enzyme>' asks
// the API, whose RESOLVABLE_FIELDS for mm is Km alone (provenance.ts), and
// 'run mm_competitive_inhibition' never asks it. tests/terminal.test.mjs
// holds the column to both.
export const DOMAINS: Array<[string, string, string, string]> = [
  ['mm', 'Michaelis-Menten enzyme kinetics', 'continuous', 'Km from BRENDA'],
  ['mm_competitive_inhibition', 'Competitive inhibition kinetics', 'continuous', 'none: textbook constants'],
  ['gillespie_ssa', 'Exact stochastic decay, A -> B', 'stochastic', 'user-specified'],
  ['gillespie_ssa_bimolecular', 'Exact stochastic association, A + B -> C', 'stochastic', 'user-specified'],
  ['gillespie_ssa_replicates', 'Many SSA runs, to see the spread', 'stochastic', 'user-specified'],
];

/** Names a visitor may type for each live domain. */
export const ALIASES: Record<string, string> = {
  mm: 'mm',
  kinetics: 'mm',
  michaelis_menten: 'mm',
  mm_competitive_inhibition: 'mm_competitive_inhibition',
  competitive: 'mm_competitive_inhibition',
  inhibition: 'mm_competitive_inhibition',
  gillespie_ssa: 'gillespie_ssa',
  ssa: 'gillespie_ssa',
  decay: 'gillespie_ssa',
  gillespie_ssa_bimolecular: 'gillespie_ssa_bimolecular',
  bimolecular: 'gillespie_ssa_bimolecular',
  association: 'gillespie_ssa_bimolecular',
  gillespie_ssa_replicates: 'gillespie_ssa_replicates',
  replicates: 'gillespie_ssa_replicates',
};

/**
 * The domains archived on 2026-09-27, by every name the shell used to accept
 * for them. archive/legacy_domains/README.md lists each with v0.4.0 as the
 * last release that runs it; `git tag` holds v0.4.0.
 */
export const ARCHIVED_ON = '2026-09-27';
export const LAST_RELEASE = 'v0.4.0';
export const ARCHIVED: Array<[string[], string]> = [
  [['epidemiology', 'sir', 'seir'], 'SIR / SEIR epidemiology'],
  [['pcr'], 'PCR amplification'],
  [['monte_carlo'], 'Monte Carlo pi estimation'],
  [['popgen', 'wright_fisher', 'population_genetics'], 'Wright-Fisher population genetics'],
  [['md', 'molecular_dynamics', 'lj13', 'lennard_jones'], 'Lennard-Jones cluster molecular dynamics'],
];

function archivedAnswer(t: string): Line[] | null {
  const hit = ARCHIVED.find(([names]) => names.includes(t));
  if (!hit) return null;
  const [names, title] = hit;
  const lines = [
    warn(`  '${t}' (${title}) was archived on ${ARCHIVED_ON}.`),
    d('  Caterva no longer runs it, and neither does this shell.'),
    d(`  ${LAST_RELEASE} is the last release that does:  git checkout ${LAST_RELEASE}`),
    d('  see archive/legacy_domains/README.md in the repository.'),
  ];
  if (names.includes('md')) {
    lines.push(
      o(),
      d("  molecular dynamics continues as 'caterva md', which sets up GROMACS"),
      d('  runs of enzymes. it does not run in a browser. the moving lattice'),
      d('  behind this page is decoration, not a simulation.'),
    );
  }
  lines.push(o(), d("  live domains: try 'domains'"));
  return lines;
}

/**
 * Human hexokinase on D-glucose, the two cited rows of
 * caterva/evidence/showcase.py (KM_ROW, KCAT_ROW), read from the recorded
 * BRENDA page for EC 2.7.1.1 fetched 2026-09-28 (CC BY 4.0). Copied, not
 * fetched: this browser does not query BRENDA. tests/terminal.test.mjs fails
 * if showcase.py stops holding these values.
 */
export const HEXOKINASE = {
  ec: '2.7.1.1',
  organism: 'Homo sapiens',
  substrate: 'D-glucose',
  km: { value: 6.0, unit: 'mM', ref: '641068', conditions: '30°C, pH 7.5, wild-type' },
  kcat: { value: 40.1, unit: '1/s', ref: '739603', conditions: 'wild-type, pH 7.6, 25 °C' },
  /** Chosen, as in the showcase; nobody measured it. */
  s: 1,
};

/** Turnover per enzyme molecule, v/[E] = kcat·S/(Km + S), in 1/s. */
export function turnover(s: number, km = HEXOKINASE.km.value, kcat = HEXOKINASE.kcat.value): number {
  return (kcat * s) / (km + s);
}

function runHexokinase(): Line[] {
  const { km, kcat, s } = HEXOKINASE;
  const lines: Line[] = [
    head('MICHAELIS-MENTEN · HUMAN HEXOKINASE ON D-GLUCOSE'),
    rule(),
    ok(`  Km     ${km.value} ${km.unit}     BRENDA EC ${HEXOKINASE.ec}, ref ${km.ref} (${km.conditions})`),
    ok(`  kcat   ${kcat.value} ${kcat.unit}  BRENDA EC ${HEXOKINASE.ec}, ref ${kcat.ref} (${kcat.conditions})`),
    warn(`  S      ${s} mM      chosen, not measured`),
    o(),
    o(`  v/[E] = kcat·S / (Km + S) = ${turnover(s).toFixed(6)} 1/s at S = ${s} mM`),
    o(),
    o('  S (mM)    v/[E] (1/s)   v/Vmax'),
  ];
  for (const x of [km.value / 4, km.value / 2, km.value, 2 * km.value, 10 * km.value]) {
    const v = turnover(x);
    lines.push(o(`  ${x.toFixed(2).padEnd(10)}${v.toFixed(6).padEnd(14)}${(v / kcat.value).toFixed(6)}`));
  }
  lines.push(
    o(),
    d('  at S = Km the rate is exactly half of kcat, as the rate law requires.'),
    warn('  the two rows were measured at different temperatures and pH;'),
    warn('  BRENDA reports them as separate experiments.'),
    d('  Vmax = kcat·[E] needs an enzyme concentration, which nobody reported,'),
    d('  so this prints the rate per enzyme molecule.'),
    o(),
    d("  constants from caterva/evidence/showcase.py. for a live resolution of"),
    d("  another enzyme: 'run mm <enzyme>' (needs the literature API)."),
  );
  return lines;
}

function ensembleLines(label: string, c: EnsembleCheck): Line[] {
  const diff = Math.abs(c.mean - c.expected);
  return [
    o(`  ${label}`),
    o(`    expected  ${c.expected.toFixed(4)}`),
    o(`    measured  ${c.mean.toFixed(4)}   mean of ${c.runs} seeds`),
    o(`    |diff|    ${diff.toFixed(4)}   tolerance ${c.tolerance.toFixed(4)}`),
    (c.pass ? ok : err)(`    ${c.pass ? 'PASS' : 'FAIL'}${c.conserved ? '      conservation held after every event' : '      CONSERVATION BROKEN'}`),
  ];
}

const SAMPLE_TIMES = [0, 10, 20, 30, 40, 50];

export const COMMANDS: Command[] = [
  {
    name: 'help',
    help: 'list every command',
    run: () => [
      head('AVAILABLE COMMANDS'),
      rule(),
      ...COMMANDS.map((c) =>
        d(`  ${(c.name + (c.args ? ' ' + c.args : '')).padEnd(22)}${c.help}`),
      ),
      o(),
      d('  every number below is computed when you ask for it.'),
    ],
  },

  {
    name: 'domains',
    help: 'list the simulation domains',
    run: () => [
      head('DOMAINS'),
      rule(),
      o('  DOMAIN                     DESCRIPTION                               TYPE        LITERATURE'),
      o('  -------------------------  ----------------------------------------  ----------  ------------------------'),
      ...DOMAINS.map(([n, desc, kind, lit]) =>
        o(`  ${n.padEnd(27)}${desc.padEnd(42)}${kind.padEnd(12)}${lit}`),
      ),
      o(),
      d('  run <domain>     to simulate, in this browser'),
      d('  verify <domain>  to check against exact mathematics'),
      o(),
      d('  "user-specified": every parameter is typed by you, by design -- rate'),
      d('  constants and counts for a teaching system have no single "true"'),
      d('  value in any database.'),
      o(),
      d("  'run mm <enzyme>' resolves Km and nothing else; 'run mm' alone shows"),
      d("  hexokinase's two cited constants, Km and kcat. the competitive-"),
      d("  inhibition demo runs a textbook set: the API resolves Km and Ki for"),
      d('  that domain, and this shell does not call it.'),
      o(),
      d(`  archived ${ARCHIVED_ON}, runnable only in ${LAST_RELEASE}:`),
      d(`  ${ARCHIVED.map(([names]) => names[0]).join(', ')}`),
    ],
  },

  {
    name: 'run',
    args: '<domain>',
    help: 'run a simulation and report the result',
    run: (args) => {
      const t = (args[0] || '').toLowerCase();
      if (!t) return [err('usage: run <domain>    (try: run mm)')];
      const archived = archivedAnswer(t);
      if (archived) return archived;

      const id = ALIASES[t];
      if (id === 'mm') {
        const enzyme = args.slice(1).join(' ');
        if (!enzyme) return runHexokinase();
        return runLiteratureBacked(`simulate ${enzyme} kinetics`, 'kinetics');
      }

      if (id === 'mm_competitive_inhibition') {
        const t0 = performance.now();
        const p = DEFAULT_MM_COMPETITIVE;
        const r = simulateMMCompetitiveInhibition(p);
        const ms = Math.round(performance.now() - t0);
        const kmApp = p.km * (1 + p.i / p.ki);
        const lines: Line[] = [
          head('COMPETITIVE INHIBITION — MM WITH INHIBITOR'),
          rule(),
          d('  illustrative constants demo -- Km/Vmax/Ki/[I] below are a'),
          d("  textbook set, simulated client-side with RK4, not a literature"),
          d("  resolved enzyme. the API's competitive-inhibition domain accepts"),
          d('  these same parameters from you for a real resolved run.'),
          o(`  Km      ${p.km}   Vmax     ${p.vmax}   Ki      ${p.ki}`),
          o(`  S0      ${p.s0}   [I]      ${p.i}   points  ${p.points}`),
          o(`  Km_app  ${kmApp.toFixed(6)}   = Km·(1 + I/Ki)`),
          o(),
          o(`  t       S(t)`),
        ];
        for (let i = 0; i < r.trajectory.length; i += 10) {
          const pt = r.trajectory[i];
          lines.push(o(`  ${pt.t.toFixed(2)}    ${pt.S.toFixed(6)}`));
        }
        lines.push(o(), ok(`  ${ms}ms · client-side RK4`));
        return lines;
      }

      if (id === 'gillespie_ssa' || id === 'gillespie_ssa_bimolecular') {
        const seedArg = args[1] ?? '1';
        const seed = Number(seedArg);
        if (!/^\d+$/.test(seedArg) || !Number.isSafeInteger(seed)) {
          return [err(`  usage: run ${t} [seed]    (seed: a non-negative integer)`)];
        }
        const bi = id === 'gillespie_ssa_bimolecular';
        // The domain catalogue's own example parameters.
        const a0 = 100;
        const k = bi ? 0.01 : 0.1;
        const t0 = performance.now();
        const r = bi
          ? ssaAssociation(a0, a0, k, 50, seed, SAMPLE_TIMES)
          : ssaDecay(a0, k, 50, seed, SAMPLE_TIMES);
        const ms = Math.round(performance.now() - t0);
        const lines: Line[] = [
          head(bi ? 'GILLESPIE SSA · A + B -> C' : 'GILLESPIE SSA · A -> B'),
          rule(),
          d(bi
            ? `  a0 = b0 = ${a0}   k = ${k}   propensity k·a·b   seed ${seed}`
            : `  a0 = ${a0}   k = ${k}   propensity k·a   seed ${seed}`),
          o(),
          o(bi ? '  t      A this run   ODE a0/(1 + k·a0·t)' : '  t      A this run   mean a0·e^(-kt)'),
        ];
        SAMPLE_TIMES.forEach((ti, i) => {
          const ref = bi ? odeAssociation(ti, a0, a0, k) : a0 * Math.exp(-k * ti);
          lines.push(o(`  ${String(ti).padEnd(7)}${String(r.a[i]).padEnd(13)}${ref.toFixed(4)}`));
        });
        lines.push(
          o(),
          (r.conserved ? ok : err)(`  ${r.events} events · ${bi ? 'a + c = a0, b + c = b0' : 'a + b = a0'} ${r.conserved ? 'after every one' : 'BROKEN'}`),
          d(`  ${ms}ms · exact direct method · one path, so it wanders off the`),
          d(`  ${bi ? 'ODE' : 'mean'}: at counts this small the noise is the point.`),
          d(`  try 'run ${t} ${seed + 1}' for another path, 'verify ${t}' for the ensemble.`),
        );
        return lines;
      }

      if (id === 'gillespie_ssa_replicates') {
        const a0 = 100;
        const k = 0.1;
        const runs = 50;
        const t0 = performance.now();
        const paths = Array.from({ length: runs }, (_, seed) => ssaDecay(a0, k, 50, seed, SAMPLE_TIMES).a);
        const ms = Math.round(performance.now() - t0);
        const lines: Line[] = [
          head('GILLESPIE SSA · REPLICATES'),
          rule(),
          d(`  A -> B, a0 = ${a0}, k = ${k}, seeds 0..${runs - 1}`),
          d('  A(t) is exactly Binomial(a0, p), p = e^(-kt): mean a0·p, sd sqrt(a0·p·(1-p))'),
          o(),
          o('  t      mean      theory    sd        theory'),
        ];
        SAMPLE_TIMES.forEach((ti, i) => {
          const xs = paths.map((a) => a[i]);
          const mean = xs.reduce((s, x) => s + x, 0) / runs;
          const sd = Math.sqrt(xs.reduce((s, x) => s + (x - mean) ** 2, 0) / (runs - 1));
          const p = Math.exp(-k * ti);
          lines.push(o(
            `  ${String(ti).padEnd(7)}${mean.toFixed(3).padEnd(10)}${(a0 * p).toFixed(3).padEnd(10)}` +
              `${sd.toFixed(3).padEnd(10)}${Math.sqrt(a0 * p * (1 - p)).toFixed(3)}`,
          ));
        });
        lines.push(o(), d(`  ${ms}ms · sd is the sample sd over ${runs} runs, so it scatters too.`));
        return lines;
      }

      return [err(`unknown domain '${t}' — try: domains`)];
    },
  },

  {
    name: 'verify',
    args: '<domain>',
    help: 'check a domain against exact mathematics',
    run: (args) => {
      const t = (args[0] || '').toLowerCase();
      const archived = archivedAnswer(t);
      if (archived) return archived;
      const id = ALIASES[t];
      if (id === 'mm') {
        const r = simulateMichaelisMenten(DEFAULT_MM);
        const passes = r.finalResidual < MM_TOLERANCE;
        return [
          head('VERIFY · KINETICS'),
          rule(),
          o(`  target      Km·ln(S0/S) + (S0 - S) = Vmax·t     exact implicit solution`),
          o(`  measured    residual ${r.finalResidual.toExponential(3)}`),
          o(`  tolerance   ${MM_TOLERANCE}`),
          (passes ? ok : err)(`  ${passes ? 'PASS' : 'FAIL'}        margin ${(MM_TOLERANCE / r.finalResidual).toFixed(1)}x`),
          o(),
          d('  computed by RK4 integration of dS/dt = -Vmax·S / (Km + S), then'),
          d('  checked against the closed form the ODE has no free parameters left to fit.'),
          d(`  NOTE: Km=${DEFAULT_MM.km}, Vmax=${DEFAULT_MM.vmax} here are illustrative constants,`),
          d('  not a literature-resolved enzyme -- this checks the solver only.'),
          d("  for cited constants, try 'run mm'."),
        ];
      }
      if (id === 'mm_competitive_inhibition') {
        const p = DEFAULT_MM_COMPETITIVE;
        const r = simulateMMCompetitiveInhibition(p);
        const passes = r.finalResidual < MM_TOLERANCE;
        const kmApp = p.km * (1 + p.i / p.ki);
        return [
          head('VERIFY · COMPETITIVE INHIBITION'),
          rule(),
          o(`  target      Km_app·ln(S0/S) + (S0 - S) = Vmax·t     Km_app = Km·(1 + I/Ki)`),
          o(`  Km_app      ${kmApp.toFixed(6)}   (Km=${p.km}, I=${p.i}, Ki=${p.ki})`),
          o(`  measured    residual ${r.finalResidual.toExponential(3)}`),
          o(`  tolerance   ${MM_TOLERANCE}`),
          (passes ? ok : err)(`  ${passes ? 'PASS' : 'FAIL'}        margin ${(MM_TOLERANCE / r.finalResidual).toFixed(1)}x`),
          o(),
          d('  same apparent-Km closed form caterva/tests/test_mm_competitive_inhibition.py'),
          d('  checks against the Python engine; reduces exactly to plain MM at I=0.'),
          d(`  NOTE: these are illustrative constants, not a literature-resolved enzyme --`),
          d('  this checks the solver only, same caveat as verify mm.'),
        ];
      }
      if (id === 'gillespie_ssa' || id === 'gillespie_ssa_replicates') {
        return [
          head('VERIFY · GILLESPIE SSA'),
          rule(),
          d('  A(t) for A -> B is exactly Binomial(a0, e^(-kt)); the mean of N runs'),
          d('  must land within 3 standard errors, 3·sqrt(a0·p·(1-p)/N), of a0·e^(-kt).'),
          o(),
          ...ensembleLines('a0 4000, k 0.5, t 10', checkDecayMean()),
          o(),
          d('  parameters and rule of caterva/tests/test_gillespie_ssa_correctness.py'),
          d('  ::test_mean_a_tracks_exp_decay, re-run here on this browser\'s seeds.'),
          ...(id === 'gillespie_ssa_replicates'
            ? [d('  the replicates domain runs this system once per seed; this is its ensemble.')]
            : []),
          o(),
          warn('  try:  mutate gillespie_ssa     to break it deliberately'),
        ];
      }
      if (id === 'gillespie_ssa_bimolecular') {
        return [
          head('VERIFY · GILLESPIE SSA · A + B -> C'),
          rule(),
          d('  the stochastic mean tracks the ODE as counts grow; the mean of 40'),
          d('  runs must land within 3% of the closed-form A(t).'),
          o(),
          ...ensembleLines('a0 = b0 = 3000, k 2e-4, t 10', checkAssociationMean(3000, 3000, 2e-4)),
          o(),
          ...ensembleLines('a0 4000, b0 3000, k 1e-4, t 10', checkAssociationMean(4000, 3000, 1e-4)),
          o(),
          d('  parameters and rule of caterva/tests/'),
          d('  test_gillespie_ssa_bimolecular_correctness.py::TestOdeReference.'),
        ];
      }
      return [err('usage: verify <mm|mm_competitive_inhibition|gillespie_ssa|gillespie_ssa_bimolecular|gillespie_ssa_replicates>')];
    },
  },

  {
    name: 'mutate',
    args: '<domain>',
    help: 'inject a bug and watch the check catch it',
    run: (args) => {
      const t = (args[0] || '').toLowerCase();
      const archived = archivedAnswer(t);
      if (archived) return archived;
      if (ALIASES[t] !== 'gillespie_ssa') {
        return [err('usage: mutate gillespie_ssa')];
      }
      const c = checkDecayMean(4000, 0.5, 10, 50, { precedenceBug: true });
      return [
        head('MUTATION · A MISSING PAIR OF PARENTHESES'),
        rule(),
        d('  the waiting time to the next event is Exp(k·a). written without'),
        d('  parentheses, it divides by k and then multiplies by a:'),
        o(),
        err('  -   tau = -ln(u) / (k * a)'),
        ok('  +   tau = -ln(u) / k * a'),
        o(),
        ...ensembleLines('a0 4000, k 0.5, t 10', c),
        o(),
        d('  the bug makes every wait a²-times too long, so decay stalls.'),
        d('  this is the in-browser check, re-run on the mutated sampler; the'),
        d('  Python suite holds the engine to the same rule.'),
      ];
    },
  },

  {
    name: 'ledger',
    help: 'every verified claim and its source',
    run: () => [
      head('EVIDENCE LEDGER'),
      rule(),
      ...LEDGER.flatMap((r) => [
        o(`  ${r.claim}`),
        d(`    ${r.domain} · ${r.method}${r.reference !== '—' ? ' · ' + r.reference : ''}`),
      ]),
      o(),
      d(`  ${LEDGER.length} claims. the reference column is the product.`),
    ],
  },

  {
    name: 'pipeline',
    help: 'how a domain gets built and accepted',
    run: () => [
      head('BUILD PIPELINE'),
      rule(),
      ...PIPELINE.flatMap((s) => [
        s.conflict ? warn(`  ${s.label}`) : ok(`  ${s.label}`),
        d(`    ${s.detail}`),
        ...(s.agents ?? []).map((a) => d(`      ${a.name.padEnd(12)}${a.model}`)),
        ...(s.output ?? []).map((l) => d(`      ${l}`)),
      ]),
      o(),
      d('  an implementer report is a claim. it is reproduced before it counts.'),
    ],
  },

  {
    name: 'agents',
    help: 'the two independent implementers',
    run: () => [
      head('IMPLEMENTERS'),
      rule(),
      o('  opencode      nemotron-3'),
      o('  freebuff      deepseek-v4-pro'),
      o(),
      d('  both receive byte-identical prompts. neither sees the other.'),
      d('  disagreement is signal, not noise — it is the point of running two.'),
      o(),
      warn('  agreement is not evidence of correctness. both can share an error,'),
      warn('  and once did: a mutation blast radius overstated in a report that'),
      warn('  had already passed its own review. the reviewer reran it and found'),
      warn('  2 failing tests where 3 were claimed.'),
    ],
  },

  {
    name: 'audit',
    help: 'bugs found auditing our own work',
    run: () => [
      head('SELF-AUDIT'),
      rule(),
      ...[
        'duplicate error messages in three validators',
        'a dependency guard blind to package-level imports',
        'six CLI tests running from the wrong working directory',
        'a bare float equality comparison in a symmetry assertion',
        'a population-genetics test whose parameters were too small to',
        '  avoid fixation — it looked like a broken implementation; the',
        '  implementation was correct, the test was not',
        'an eigenvector sign bug that was invisible on the author machine',
        '  and deterministic on the pinned CI configuration, silently',
        '  producing NaN instead of raising',
      ].map((s) => o(`  · ${s}`)),
      o(),
      d('  found by auditing our own work. written down, not quietly fixed.'),
    ],
  },

  {
    name: 'cite',
    help: 'primary literature behind the numbers',
    run: () => [
      head('REFERENCES'),
      rule(),
      o('  Michaelis, L. & Menten, M. L. (1913)'),
      d('    Biochem. Z. 49, 333 — the rate law v = Vmax·S / (Km + S)'),
      o(),
      o('  Gillespie, D. T. (1977)'),
      d('    J. Phys. Chem. 81, 2340 — the exact stochastic simulation algorithm'),
      o(),
      o(`  BRENDA, EC ${HEXOKINASE.ec}, references ${HEXOKINASE.km.ref} and ${HEXOKINASE.kcat.ref} (CC BY 4.0)`),
      d(`    brenda-enzymes.org/literature.php?e=${HEXOKINASE.ec}&r=${HEXOKINASE.km.ref} — Km`),
      d(`    brenda-enzymes.org/literature.php?e=${HEXOKINASE.ec}&r=${HEXOKINASE.kcat.ref} — kcat`),
    ],
  },

  {
    name: 'whoami',
    help: 'what this thing is',
    run: () => [
      head('CATERVA'),
      rule(),
      o('  Enzyme kinetics and molecular dynamics for research groups and teaching labs.'),
      o(),
      d('  Ask a question in plain language. Caterva resolves the real'),
      d('  parameters from the literature, runs the simulation, and shows its'),
      d('  work: every number traceable to a citation that has been'),
      d('  independently checked.'),
      o(),
      d('  Built by two AI implementers working from identical specs, with'),
      d('  every claim reproduced by a third before it is accepted.'),
    ],
  },

  { name: 'clear', help: 'clear the screen', run: () => [] },
];

export async function execute(input: string): Promise<{ lines: Line[]; clear: boolean }> {
  const trimmed = input.trim();
  if (!trimmed) return { lines: [], clear: false };
  const [name, ...args] = trimmed.split(/\s+/);
  const cmd = COMMANDS.find((c) => c.name === name.toLowerCase());
  if (!cmd) {
    return {
      lines: [
        err(`command not found: ${name}`),
        d(`try 'help' — or one of: ${COMMANDS.slice(0, 6).map((c) => c.name).join(', ')}`),
      ],
      clear: false,
    };
  }
  if (cmd.name === 'clear') return { lines: [], clear: true };
  return { lines: await cmd.run(args), clear: false };
}

export const COMMAND_NAMES = COMMANDS.map((c) => c.name);
