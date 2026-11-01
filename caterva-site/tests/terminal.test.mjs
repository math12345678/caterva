// The shell offers only live domains, and its numbers are the cited ones.
// Run with `npm test` (node --test; Node >= 23.6 strips the imported .ts).
// Plain JS outside src/: the site has no @types/node, so tsc could not check
// node:test imports, and the Vite build never sees this file.

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import {
  ALIASES,
  ARCHIVED,
  DOMAINS,
  HEXOKINASE,
  LAST_RELEASE,
  execute,
  turnover,
} from '../src/lib/terminal.ts';
import { checkAssociationMean, checkDecayMean } from '../src/lib/ssa.ts';

const REPO = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const read = (rel) => readFileSync(join(REPO, rel), 'utf8');
const text = async (cmd) => (await execute(cmd)).lines.map((l) => l.text).join('\n');

test('the domain table is the catalogue of live domains', () => {
  const catalogue = read('src/cli/domainCatalogue.ts');
  const body = catalogue.slice(catalogue.indexOf('export const DOMAIN_CATALOGUE'));
  const ids = [...body.matchAll(/^ {4}id: '([a-z_]+)'/gm)].map((m) => m[1]);
  assert.ok(ids.length > 0, 'found no ids in domainCatalogue.ts; the parse is broken');
  assert.deepEqual(DOMAINS.map(([id]) => id), ids);
});

test('every live domain runs and verifies', async () => {
  for (const [id] of DOMAINS) {
    for (const verb of ['run', 'verify']) {
      const out = await text(`${verb} ${id}`);
      assert.doesNotMatch(out, /unknown domain|usage:|archived/, `${verb} ${id}`);
      assert.doesNotMatch(out, /FAIL/, `${verb} ${id}`);
    }
  }
  // A seed is a whole number or nothing: '2x' must not quietly run seed 2.
  for (const seed of ['2x', '-1', '1.5']) {
    assert.match(await text(`run gillespie_ssa ${seed}`), /usage:/, `seed ${seed}`);
  }
});

test('every archived name answers archived, with the release that runs it', async () => {
  const tag = execFileSync('git', ['-C', REPO, 'tag', '-l', LAST_RELEASE], { encoding: 'utf8' }).trim();
  assert.equal(tag, LAST_RELEASE, `git has no ${LAST_RELEASE} tag`);
  assert.match(read('archive/legacy_domains/README.md'), new RegExp(`\\| ${LAST_RELEASE} \\|`));
  for (const [names] of ARCHIVED) {
    for (const name of names) {
      for (const verb of ['run', 'verify', 'mutate']) {
        const out = await text(`${verb} ${name}`);
        assert.match(out, /archived on 2026-09-27/, `${verb} ${name}`);
        assert.match(out, new RegExp(`git checkout ${LAST_RELEASE}`), `${verb} ${name}`);
        assert.doesNotMatch(out, /PASS/, `${verb} ${name} must not report a result`);
      }
    }
  }
});

test('every domain name the v0.4.0 shell accepted is live or answers archived', async () => {
  // Read from the release itself, so a name dropped from ARCHIVED (and so
  // answered "unknown domain") is still caught.
  const old = execFileSync('git', ['-C', REPO, 'show', `${LAST_RELEASE}:caterva-site/src/lib/terminal.ts`], {
    encoding: 'utf8',
  });
  const names = new Set([
    ...[...old.matchAll(/t === '([a-z_0-9]+)'/g)].map((m) => m[1]),
    ...[...old.matchAll(/^ {2}\['([a-z_]+)'/gm)].map((m) => m[1]),
  ]);
  assert.ok(names.has('popgen') && names.has('md'), 'the v0.4.0 parse found no domain names');
  for (const name of names) {
    if (name in ALIASES) continue;
    assert.match(await text(`run ${name}`), /archived on 2026-09-27/, `run ${name}`);
  }
});

test('the literature column claims only what the shell resolves', async () => {
  // 'run mm <enzyme>' asks the API, which resolves RESOLVABLE_FIELDS.mm and
  // nothing else; the column once said "Km, kcat" over a Km-only lookup.
  const prov = read('Science-Agent-Pipeline/artifacts/api-server/src/lib/provenance.ts');
  const body = prov.slice(prov.indexOf('export const RESOLVABLE_FIELDS'));
  const m = body.match(/^\s*mm: (\[[^\]]*\])/m);
  assert.ok(m, 'provenance.ts has no RESOLVABLE_FIELDS.mm; the parse is broken');
  const lit = Object.fromEntries(DOMAINS.map(([id, , , l]) => [id, l]));
  const named = (s) => [...s.matchAll(/\b(Km|kcat|Ki|Vmax)\b/gi)].map((x) => x[1].toLowerCase());
  assert.deepEqual(named(lit.mm), JSON.parse(m[1]));
  // The competitive-inhibition command runs textbook constants and never
  // calls the API, so its column may name no constant and no database.
  assert.match(await text('run mm_competitive_inhibition'), /not a literature/);
  assert.deepEqual(named(lit.mm_competitive_inhibition), []);
  assert.doesNotMatch(lit.mm_competitive_inhibition, /BRENDA/);
});

test('the hexokinase constants are the showcase rows', () => {
  const showcase = read('caterva/evidence/showcase.py');
  const row = (name) => {
    const m = showcase.match(new RegExp(`^${name} = \\("\\w+", ([\\d.]+), "([^"]+)", "(\\d+)"\\)`, 'm'));
    assert.ok(m, `showcase.py has no ${name}`);
    return { value: Number(m[1]), conditions: m[2], ref: m[3] };
  };
  const { value: kmV, conditions: kmC, ref: kmR } = row('KM_ROW');
  const { value: kcV, conditions: kcC, ref: kcR } = row('KCAT_ROW');
  assert.deepEqual(
    [HEXOKINASE.km.value, HEXOKINASE.km.conditions, HEXOKINASE.km.ref],
    [kmV, kmC, kmR],
  );
  assert.deepEqual(
    [HEXOKINASE.kcat.value, HEXOKINASE.kcat.conditions, HEXOKINASE.kcat.ref],
    [kcV, kcC, kcR],
  );
  assert.equal(turnover(HEXOKINASE.km.value), HEXOKINASE.kcat.value / 2);
});

test('the SSA checks pass on the sampler and fail on the mutated one', () => {
  assert.ok(checkDecayMean().pass);
  assert.ok(checkAssociationMean(3000, 3000, 2e-4).pass);
  assert.ok(checkAssociationMean(4000, 3000, 1e-4).pass);
  const mutated = checkDecayMean(4000, 0.5, 10, 50, { precedenceBug: true });
  assert.equal(mutated.pass, false);
});

test('the decay check rejects a sampler whose mean is 5 standard errors off', () => {
  // The precedence bug moves the mean by orders of magnitude, so it fails
  // under any tolerance: a 30-SE rule passed every test above. Here the
  // sampler runs at the rate k' whose exact mean, a0·e^(-k'·end), is
  // expected ± 5·SE, with SE = sqrt(a0·p·(1-p)/runs) (0.73 at these
  // parameters). Seeds 0..49 land 4.44 and 4.52 SE off: outside the 3-SE
  // rule, and inside any rule of 4.6 SE or looser.
  const [a0, k, end, runs] = [4000, 0.5, 10, 50];
  const p = Math.exp(-k * end);
  const expected = a0 * p;
  const se = Math.sqrt((a0 * p * (1 - p)) / runs);
  for (const off of [-5, 5]) {
    const biased = -Math.log((expected + off * se) / a0) / end;
    const r = checkDecayMean(a0, k, end, runs, { rateScale: biased / k });
    assert.ok(Math.abs(r.mean - expected) > 4 * se, `the ${off}-SE sampler is not that far off`);
    assert.equal(r.pass, false, `a mean ${((r.mean - expected) / se).toFixed(2)} SE off passed`);
  }
});
