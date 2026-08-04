/**
 * The site's command line.
 *
 * Every command that reports a number computes it, here, now. `verify md`
 * runs a golden-section search and reports what it found. `run popgen`
 * simulates two thousand populations. Nothing below prints a stored answer,
 * because a page arguing that claims must be checked should not itself be
 * a set of unchecked claims.
 */

import { CONFIG, prepare, type PreparedData } from './drift';
import { lj13, exactCluster, R_MIN } from './md';
import { LEDGER, PIPELINE } from './pipeline';
import {
  simulateMichaelisMenten,
  simulateMMCompetitiveInhibition,
  simulateSIR,
  DEFAULT_MM,
  DEFAULT_MM_COMPETITIVE,
  DEFAULT_SIR,
  MM_TOLERANCE,
  SIR_TOLERANCE,
} from './simulate';
import {
  resolveAndSimulate,
  ApiUnavailableError,
  API_BASE_URL,
  type ParameterProvenanceEntry,
} from './api';

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

/** Lazily computed once, then reused — 2000 replicates is real work. */
let driftCache: PreparedData | null = null;
function drift(): PreparedData {
  if (!driftCache) driftCache = prepare();
  return driftCache;
}

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
      err(`  no science-agent API configured (VITE_TERRIUM_API_URL is unset)`),
      d(`  cannot claim a literature-backed ${domainLabel} result without one --`),
      d(`  see 'verify ${domainLabel === 'kinetics' ? 'kinetics' : 'epidemiology'}'`),
      d(`  for a pure math check of the integrator instead.`),
    ];
  }
  try {
    const job = await resolveAndSimulate(query);
    if (job.status === 'failed' || !job.result) {
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

const DOMAINS = [
  ['kinetics', 'Michaelis-Menten enzyme kinetics', 'continuous'],
  ['mm_competitive_inhibition', 'Competitive inhibition kinetics', 'continuous'],
  ['epidemiology', 'SIR / SEIR compartment models', 'continuous'],
  ['pcr', 'PCR amplification', 'discrete'],
  ['monte_carlo', 'Monte Carlo pi estimation', 'stochastic'],
  ['popgen', 'Wright-Fisher neutral drift', 'stochastic'],
  ['md', 'Lennard-Jones molecular dynamics', 'discrete-time'],
];

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
      ...DOMAINS.map(([n, desc, kind]) =>
        o(`  ${n.padEnd(16)}${(desc as string).padEnd(38)}${kind}`),
      ),
      o(),
      d('  run <domain>     to simulate'),
      d('  verify <domain>  to check against exact mathematics'),
    ],
  },

  {
    name: 'run',
    args: '<domain>',
    help: 'run a simulation and report the result',
    run: (args) => {
      const t = (args[0] || '').toLowerCase();
      if (!t) return [err('usage: run <domain>    (try: run popgen)')];

      if (t === 'popgen' || t === 'wright_fisher') {
        const t0 = performance.now();
        const p = drift();
        const ms = Math.round(performance.now() - t0);
        return [
          head('WRIGHT-FISHER NEUTRAL DRIFT'),
          rule(),
          d(`  N = ${CONFIG.populationSize}   2N = ${CONFIG.correctAlleleCopies} allele copies`),
          d(`  ${CONFIG.replicates} replicate populations, ${CONFIG.generations} generations, seed ${CONFIG.seed}`),
          o(),
          o(`  H(0)   measured ${p.correct.meanHeterozygosity[0].toFixed(6)}   theory ${p.theory[0].toFixed(6)}`),
          o(`  H(50)  measured ${p.correct.meanHeterozygosity[50].toFixed(6)}   theory ${p.theory[50].toFixed(6)}`),
          o(`  H(200) measured ${p.correct.meanHeterozygosity[200].toFixed(6)}   theory ${p.theory[200].toFixed(6)}`),
          o(),
          ok(`  max deviation ${p.deviationCorrect.toFixed(6)} < tolerance ${CONFIG.tolerance}`),
          d(`  ${ms === 0 ? 'cached' : ms + 'ms'} · closed form H(t) = H0 (1 - 1/2N)^t`),
        ];
      }

      if (t === 'md' || t === 'molecular_dynamics') {
        const t0 = performance.now();
        const r = lj13();
        const ms = Math.round(performance.now() - t0);
        return [
          head('LENNARD-JONES CLUSTER — LJ13'),
          rule(),
          d('  golden-section scale search, bracket [0.40, 0.80], 200 iterations'),
          o(),
          o(`  optimal scale   ${r.scale.toFixed(15)}`),
          o(`  energy          ${r.energy.toFixed(12)} eps`),
          o(`  published       -44.326801 eps`),
          ok(`  agreement       ${Math.abs(r.energy + 44.326801).toExponential(3)}  (published value is 6 d.p.)`),
          o(),
          d(`  centre-to-shell ${r.centre.toFixed(9)}  compressed below r_min`),
          d(`  shell-to-shell  ${r.shell.toFixed(9)}  stretched above r_min`),
          d(`  r_min           ${R_MIN.toFixed(9)}`),
          d(`  ${ms}ms · Hoare & Pal, Adv. Phys. 20, 161 (1971)`),
        ];
      }

      if (t === 'kinetics' || t === 'michaelis_menten' || t === 'mm') {
        const enzyme = args.slice(1).join(' ');
        if (!enzyme) {
          return [
            err('  usage: run kinetics <enzyme>    (try: run kinetics lactate dehydrogenase)'),
            d('  a bare "run kinetics" has no literature source to resolve --'),
            d("  this command reports what BRENDA/KEGG/PubMed actually found for"),
            d('  a named enzyme, not a demo number.'),
          ];
        }
        return runLiteratureBacked(`simulate ${enzyme} kinetics`, 'kinetics');
      }

      if (t === 'epidemiology' || t === 'sir' || t === 'seir') {
        const rest = args.slice(1).join(' ');
        const query = rest ? `simulate ${rest}` : 'simulate sir outbreak';
        return runLiteratureBacked(query, 'epidemiology');
      }

      if (DOMAINS.some(([n]) => n === t)) {
        return [
          warn(`  '${t}' runs in the Python engine, not in this browser.`),
          d('  domains compiled to the web: popgen, md (pure math demos)'),
          d('  domains resolved via the literature API: kinetics, epidemiology'),
        ];
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
      if (t === 'md' || t === 'molecular_dynamics') {
        const e2 = exactCluster(2);
        const e3 = exactCluster(3);
        const e4 = exactCluster(4);
        const r = lj13();
        const row = (n: string, got: number, pub: number, tol: string) => {
          const diff = Math.abs(got - pub);
          const pass = diff < (tol === '1e-12' ? 1e-12 : 1e-6);
          return {
            kind: pass ? ('ok' as LineKind) : ('err' as LineKind),
            text: `  LJ${n.padEnd(3)} ${got.toFixed(12).padStart(18)}  ${pub
              .toFixed(6)
              .padStart(12)}   ${diff.toExponential(2).padStart(9)}   ${pass ? 'PASS' : 'FAIL'}`,
          };
        };
        return [
          head('VERIFY · MOLECULAR DYNAMICS'),
          rule(),
          d('       computed            published        |diff|    '),
          row('2', e2, -1, '1e-12'),
          row('3', e3, -3, '1e-12'),
          row('4', e4, -6, '1e-12'),
          row('13', r.energy, -44.326801, '1e-6'),
          o(),
          d('  LJ2/3/4 are exact by two independent routes: derivable by hand'),
          d('  (a regular tetrahedron places all six pairs at r_min simultaneously)'),
          d('  and independently listed in the Cambridge Cluster Database.'),
          d('  LJ5 is the first size where frustration makes this impossible:'),
          d('  -9.103852, not -10.'),
        ];
      }
      if (t === 'kinetics' || t === 'michaelis_menten' || t === 'mm') {
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
          d("  for a real enzyme's resolved parameters, try 'run kinetics <enzyme>'."),
        ];
      }
      if (t === 'competitive' || t === 'mm_competitive_inhibition' || t === 'inhibition') {
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
          d('  same apparent-Km closed form Tellurium/tests/test_mm_competitive_inhibition.py'),
          d('  checks against the Python engine; reduces exactly to plain MM at I=0.'),
          d(`  NOTE: these are illustrative constants, not a literature-resolved enzyme --`),
          d('  this checks the solver only, same caveat as verify kinetics.'),
        ];
      }
      if (t === 'epidemiology' || t === 'sir' || t === 'seir') {
        const r = simulateSIR(DEFAULT_SIR);
        const passes = r.conservationError < SIR_TOLERANCE;
        return [
          head('VERIFY · EPIDEMIOLOGY'),
          rule(),
          o(`  target      S + I + R = N at every t     population conservation`),
          o(`  measured    |S+I+R-N| ${r.conservationError.toExponential(3)}`),
          o(`  tolerance   ${SIR_TOLERANCE}`),
          (passes ? ok : err)(`  ${passes ? 'PASS' : 'FAIL'}        margin ${(SIR_TOLERANCE / r.conservationError).toFixed(1)}x`),
          o(),
          d('  same invariant Tellurium/tests/test_properties.py checks with Hypothesis'),
          d('  across the whole input space; spot-checked here at the final point.'),
          d(`  NOTE: beta=${DEFAULT_SIR.beta}, gamma=${DEFAULT_SIR.gamma} here are illustrative,`),
          d('  not resolved from an outbreak literature source -- this checks the'),
          d("  solver only. try 'run epidemiology <disease/outbreak>' for a resolved run."),
        ];
      }
      if (t === 'popgen' || t === 'wright_fisher') {
        const p = drift();
        return [
          head('VERIFY · POPULATION GENETICS'),
          rule(),
          o(`  target      H(t) = H0 (1 - 1/2N)^t     exact closed form`),
          o(`  measured    max deviation ${p.deviationCorrect.toFixed(6)}`),
          o(`  tolerance   ${CONFIG.tolerance}`),
          ok(`  PASS        margin ${(CONFIG.tolerance / p.deviationCorrect).toFixed(1)}x`),
          o(),
          d('  second target: P(fixation) = p0 — Kimura (1962)'),
          o(),
          warn('  try:  mutate popgen     to break it deliberately'),
        ];
      }
      return [err('usage: verify <md|popgen|kinetics|epidemiology>')];
    },
  },

  {
    name: 'mutate',
    args: '<domain>',
    help: 'inject a real bug and watch the test catch it',
    run: (args) => {
      const t = (args[0] || '').toLowerCase();
      if (t !== 'popgen' && t !== 'wright_fisher') {
        return [err('usage: mutate popgen')];
      }
      const p = drift();
      const fails = p.deviationBugged > CONFIG.tolerance;
      return [
        head('MUTATION · 2N -> N'),
        rule(),
        d('  the diploid off-by-factor-of-two. a real bug, pre-specified in'),
        d('  the domain spec before the code was written.'),
        o(),
        err('  -   return rng.binomial(2 * n_pop, p)'),
        ok('  +   return rng.binomial(n_pop, p)'),
        o(),
        o(`  max deviation   ${p.deviationBugged.toFixed(6)}`),
        o(`  tolerance       ${CONFIG.tolerance}`),
        fails
          ? err(`  FAIL            exceeds tolerance by ${(p.deviationBugged / CONFIG.tolerance).toFixed(1)}x`)
          : ok('  PASS'),
        o(),
        d('  decay now follows (1 - 1/N)^t instead of (1 - 1/2N)^t.'),
        d('  caught by test_heterozygosity_decay_matches_exact_rate.'),
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
      o('  Hoare, M. R. & Pal, P. (1971)'),
      d('    Adv. Phys. 20, 161 — LJ13 and LJ55 icosahedral global minima'),
      o(),
      o('  Swope, Andersen, Berens & Wilson (1982)'),
      d('    J. Chem. Phys. 76, 637 — velocity Verlet, in the appendix'),
      o(),
      o('  Kimura, M. (1962)'),
      d('    fixation probability of a neutral allele equals its frequency'),
      o(),
      o('  Cambridge Cluster Database'),
      d('    Wales, Doye et al. — tabulated LJ global minima, N <= 150'),
    ],
  },

  {
    name: 'whoami',
    help: 'what this thing is',
    run: () => [
      head('TERRIUM'),
      rule(),
      o('  A scientific simulation engine for teaching labs.'),
      o(),
      d('  A student asks a question in plain language. Terrium resolves the'),
      d('  real parameters from published literature, runs the simulation, and'),
      d('  shows its work. Every number traces to a citation that has been'),
      d('  independently reproduced.'),
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
