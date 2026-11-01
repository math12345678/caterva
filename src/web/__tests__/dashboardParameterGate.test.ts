import { readFileSync } from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';

/**
 * The dashboard's refusal, tested against the shipped page.
 *
 * WHY THIS FILE EXISTS
 * --------------------
 * ADR 0044 removed `km value="5.2"` from the simulation form — the exact
 * number ADR 0024 names as the forbidden default — and noted that the guard
 * clause behind it, `if (!km || !vmax || !s0)`, had been **unreachable in
 * practice**: the form was never empty, so the refusal never fired.
 *
 * That ADR closed by admitting nothing proved the refusal works. The
 * dashboard had no test harness at all, which is why an inline guard could
 * sit dead for the life of the page without anyone noticing.
 *
 * WHY A VM AND NOT JSDOM
 * ----------------------
 * jsdom is not installed and cannot be installed in this environment. More
 * to the point, `server.ts` serves **only** `dashboard.html` and 404s
 * everything else, so extracting the script into a file the test could
 * `require` would break the page in production. Two bad options; this is the
 * third.
 *
 * The script is read out of the real HTML and evaluated against a stub DOM.
 * That means the test exercises the code that actually ships, rather than a
 * copy of it — which matters, because a copy is the defect this project has
 * hit five times now.
 *
 * WHAT IT CANNOT DO
 * -----------------
 * It does not render. Layout, CSS and event wiring are untested, and a
 * button whose `onclick` was misspelled would pass everything here. This
 * covers the parameter gate specifically, because that gate is the project's
 * central rule at the surface a student uses.
 */

const DASHBOARD = path.join(__dirname, '..', 'dashboard.html');

interface Harness {
  runSimulation: () => Promise<void>;
  resolveKm: () => Promise<void>;
  alerts: string[];
  fetches: string[];
  /** Queue a canned response for the next fetch. */
  reply: (status: number, body: unknown) => void;
  /** The rendered provenance panel, as HTML. */
  panelHtml: () => string;
  /** The simulation's run-conditions panel, as HTML (ADR 0062). */
  conditionsHtml: () => string;
  /** Whether the run-conditions card is shown at all. */
  conditionsVisible: () => boolean;
  /** The renderer itself, so the three states can be driven directly. */
  renderRunConditions: (rc: unknown, warnings?: unknown) => void;
  setInputs: (values: Record<string, string>) => void;
}

/** Build a stub DOM, evaluate the page's inline script in it, return the
 * handles a test needs. */
function loadDashboard(initial: Record<string, string>): Harness {
  const html = readFileSync(DASHBOARD, 'utf8');
  const scripts = [...html.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g)].map(
    (m) => m[1],
  );
  const source = scripts.reduce((a, b) => (a.length >= b.length ? a : b), '');
  if (source.trim().length === 0) {
    // A harness that silently tests nothing is the failure mode this whole
    // file is about. Fail loudly instead.
    throw new Error('No inline script found in dashboard.html');
  }

  const values: Record<string, string> = { ...initial };
  const alerts: string[] = [];
  const fetches: string[] = [];
  const responses: unknown[] = [];

  const makeElement = (id: string) => ({
    get value() {
      return values[id] ?? '';
    },
    set value(v: string) {
      values[id] = v;
    },
    textContent: '',
    innerHTML: '',
    disabled: false,
    style: {},
    getContext: () => ({}),
    querySelector: () => null,
    querySelectorAll: () => [] as unknown[],
    insertBefore: () => undefined,
    appendChild: () => undefined,
    addEventListener: () => undefined,
  });

  const elements = new Map<string, ReturnType<typeof makeElement>>();
  const document = {
    getElementById: (id: string) => {
      if (!elements.has(id)) elements.set(id, makeElement(id));
      return elements.get(id);
    },
    querySelector: () => makeElement('button'),
    querySelectorAll: () => [] as unknown[],
    createElement: () => makeElement('created'),
    addEventListener: () => undefined,
  };

  const sandbox: Record<string, unknown> = {
    document,
    alert: (message: string) => alerts.push(String(message)),
    console,
    setTimeout,
    clearTimeout,
    Promise,
    JSON,
    Math,
    Date,
    parseFloat,
    parseInt,
    isNaN,
    String,
    Number,
    Array,
    Object,
    URLSearchParams,
    URL,
    // Chart.js is loaded from a CDN and is absent here. A constructor stub
    // is enough: nothing under test reads back from a chart.
    Chart: function Chart() {
      return { destroy: () => undefined, update: () => undefined };
    },
    fetch: async (url: string) => {
      fetches.push(String(url));
      const canned = responses.shift();
      if (canned) return canned;
      return {
        ok: true,
        status: 200,
        json: async () => ({ jobId: 'test-job', status: 'complete' }),
      };
    },
    // The page registers `initCharts` on window load. A stub that records
    // listeners rather than running them keeps chart setup out of the way
    // without pretending the event never existed.
    window: {
      addEventListener: () => undefined,
      location: { href: '' },
    },
    location: { href: '' },
    addEventListener: () => undefined,
  };
  sandbox['globalThis'] = sandbox;

  vm.createContext(sandbox);
  vm.runInContext(source, sandbox, { timeout: 5000 });

  return {
    runSimulation: sandbox['runSimulation'] as () => Promise<void>,
    resolveKm: sandbox['resolveKm'] as () => Promise<void>,
    alerts,
    fetches,
    reply: (status, body) =>
      responses.push({ ok: status >= 200 && status < 300, status, json: async () => body }),
    panelHtml: () => String(elements.get('kmProvenance')?.innerHTML ?? ''),
    // ADR 0062: the simulation's own conditions panel, which is a different
    // element from the resolve panel above. Reading the wrong one would make
    // every assertion below pass against an empty string.
    conditionsHtml: () => String(elements.get('runConditions')?.innerHTML ?? ''),
    conditionsVisible: () =>
      (elements.get('runConditionsCard')?.style as { display?: string })
        ?.display === 'block',
    renderRunConditions: sandbox['renderRunConditions'] as (
      rc: unknown,
      warnings?: unknown,
    ) => void,
    setInputs: (v) => Object.assign(values, v),
  };
}

const COMPLETE = { km: '2.5', vmax: '12.8', s0: '10', model: 'mm' };

describe('the dashboard refuses rather than defaulting (ADR 0044)', () => {
  it('is loadable at all — the harness is not vacuously passing', () => {
    const h = loadDashboard(COMPLETE);
    expect(typeof h.runSimulation).toBe('function');
  });

  it.each(['km', 'vmax', 's0'])(
    'refuses to run when %s is empty, and does not call the API',
    async (field) => {
      const h = loadDashboard({ ...COMPLETE, [field]: '' });
      await h.runSimulation();

      expect(h.alerts.length).toBeGreaterThan(0);
      // The load-bearing half. A warning that still submits is not a
      // refusal — the simulation would run on a missing parameter and the
      // student would see a result with a caveat above it.
      expect(h.fetches.filter((u) => u.includes('/api/simulate'))).toHaveLength(0);
    },
  );

  it('names which parameter is missing', async () => {
    const h = loadDashboard({ ...COMPLETE, km: '' });
    await h.runSimulation();
    expect(h.alerts.join(' ')).toContain('Km');
  });

  it('names ALL the missing parameters, not just the first', async () => {
    // A message naming one of three sends the student round the loop twice
    // more. The original `if (!km || !vmax || !s0)` short-circuited.
    //
    // Asserted against the "Cannot simulate: ..." CLAUSE, not the whole
    // message. The first version checked `message.toContain('Vmax')` and
    // passed under a mutation that short-circuited after Km — because the
    // explanatory prose below says "Km and Vmax are measurements", so the
    // word was present regardless of what the gate found. The test was
    // reading the sentence that never changes.
    const h = loadDashboard({ ...COMPLETE, km: '', vmax: '' });
    await h.runSimulation();

    const clause = /Cannot simulate:\s*([^.\n]*)/.exec(h.alerts.join('\n'));
    expect(clause).not.toBeNull();
    const named = clause![1];
    expect(named).toContain('Km');
    expect(named).toContain('Vmax');
  });

  it('says a measurement will not be invented for you', async () => {
    // The reason matters more than the refusal. Without it the student
    // reads "required field" and types a plausible number, which is exactly
    // the outcome ADR 0044 exists to prevent.
    const h = loadDashboard({ ...COMPLETE, km: '' });
    await h.runSimulation();
    const message = h.alerts.join(' ');
    expect(message).toMatch(/measurement/i);
    expect(message).toMatch(/scientific resolve/);
  });

  it('runs when every parameter is supplied', async () => {
    // The counterpart. Without this, a gate that refused everything would
    // pass every test above.
    const h = loadDashboard(COMPLETE);
    await h.runSimulation();

    expect(h.alerts).toHaveLength(0);
    expect(h.fetches.some((u) => u.includes('/api/simulate'))).toBe(true);
  });
});

describe('the shipped form carries no measured defaults', () => {
  // Overlaps check_no_unsourced_ui_numbers.py deliberately. That guard runs
  // in CI over the file; this runs in the suite a developer runs locally,
  // and the two failing together is cheaper than either failing alone.
  it.each(['km', 'vmax'])('input #%s ships with no value attribute', (id) => {
    const html = readFileSync(DASHBOARD, 'utf8');
    const input = new RegExp(`<input[^>]*id="${id}"[^>]*>`).exec(html);
    expect(input).not.toBeNull();
    expect(input![0]).not.toMatch(/value="/);
  });

  it('tells the student which parameters are measured and which they choose', () => {
    // The distinction ADR 0012/0013 rest on. It lived only in code and prose
    // until ADR 0044 put it on the page; this keeps it there.
    const html = readFileSync(DASHBOARD, 'utf8');
    expect(html).toMatch(/measured-tag/);
    expect(html).toMatch(/chosen-tag/);
  });
});

const RESOLVED = {
  found: true,
  quantity: 'km',
  value: 2.5,
  unit: 'mM',
  organism: 'Homo sapiens',
  source: 'brenda_exact',
  citation: { source: 'BRENDA', reference_id: '649716' },
  crossSpecies: false,
  assayConditions: { ph: 7.4, temperatureC: 25 },
  logs: [],
};

const FORM = { enzyme: 'lactate dehydrogenase', substrate: 'lactate', organism: 'Homo sapiens' };

describe('resolving a Km in the page shows where it came from (ADR 0049)', () => {
  it('fills the field from the response', async () => {
    const h = loadDashboard({ ...COMPLETE, ...FORM, km: '' });
    h.reply(200, RESOLVED);
    await h.resolveKm();
    expect(h.fetches.some((u) => u.includes('/api/resolve'))).toBe(true);
  });

  it('shows the citation, not just the number', async () => {
    // The number alone is what the student would have typed anyway. The
    // citation is the entire difference between a resolved value and a guess.
    const h = loadDashboard({ ...COMPLETE, ...FORM, km: '' });
    h.reply(200, RESOLVED);
    await h.resolveKm();
    expect(h.panelHtml()).toContain('649716');
    expect(h.panelHtml()).toContain('BRENDA');
  });

  it('shows the assay conditions', async () => {
    const h = loadDashboard({ ...COMPLETE, ...FORM, km: '' });
    h.reply(200, RESOLVED);
    await h.resolveKm();
    expect(h.panelHtml()).toContain('7.4');
    expect(h.panelHtml()).toContain('25');
  });

  it('says "not reported" rather than leaving a blank', async () => {
    // A blank invites the reader to assume. STRENDA makes pH and temperature
    // mandatory precisely because a Km without them cannot be compared.
    const h = loadDashboard({ ...COMPLETE, ...FORM, km: '' });
    h.reply(200, { ...RESOLVED, assayConditions: { ph: null, temperatureC: null } });
    await h.resolveKm();
    expect(h.panelHtml()).toMatch(/not reported/);
  });

  it('warns when the value came from another organism', async () => {
    const h = loadDashboard({ ...COMPLETE, ...FORM, km: '' });
    h.reply(200, { ...RESOLVED, crossSpecies: true, organism: 'Sus scrofa' });
    await h.resolveKm();
    expect(h.panelHtml()).toMatch(/cross-species/i);
    expect(h.panelHtml()).toContain('Sus scrofa');
  });

  it('warns when the value came from a protein variant', async () => {
    const h = loadDashboard({ ...COMPLETE, ...FORM, km: '' });
    h.reply(200, {
      ...RESOLVED,
      variant: { status: 'variant', kind: 'mutant', evidence: 'Y337A', reason: 'r' },
    });
    await h.resolveKm();
    expect(h.panelHtml()).toContain('Y337A');
    expect(h.panelHtml()).toMatch(/sequence variant/i);
  });

  it('says so when the source did not state wild-type or variant', async () => {
    // `unstated` is the majority of BRENDA and it is NOT wild-type. Silence
    // here would let a reader infer the enzyme as found (ADR 0029).
    const h = loadDashboard({ ...COMPLETE, ...FORM, km: '' });
    h.reply(200, { ...RESOLVED, variant: { status: 'unstated', reason: 'r' } });
    await h.resolveKm();
    expect(h.panelHtml()).toMatch(/does not say whether/i);
  });

  it('distinguishes "could not look" from "nothing found"', async () => {
    // Three outcomes, not two — the reason the CLI has three exit codes. A
    // client that conflates them teaches its user to read an absence of
    // evidence as evidence of absence.
    const unavailable = loadDashboard({ ...COMPLETE, ...FORM, km: '' });
    unavailable.reply(503, { error: 'RESOLVER_UNAVAILABLE', message: 'no interpreter' });
    await unavailable.resolveKm();

    const notFound = loadDashboard({ ...COMPLETE, ...FORM, km: '' });
    notFound.reply(200, { found: false });
    await notFound.resolveKm();

    expect(unavailable.panelHtml()).toMatch(/could not run/i);
    expect(unavailable.panelHtml()).toMatch(/not the same as/i);
    expect(notFound.panelHtml()).toMatch(/No Km found/i);
    expect(notFound.panelHtml()).not.toMatch(/could not run/i);
  });

  it('leaves the field empty when nothing was found', async () => {
    const h = loadDashboard({ ...COMPLETE, ...FORM, km: '' });
    h.reply(200, { found: false });
    await h.resolveKm();
    // Filling it with anything would be the defaulting ADR 0044 removed.
    expect(h.panelHtml()).toMatch(/left empty on purpose/i);
  });

  it.each(['enzyme', 'substrate', 'organism'])(
    'refuses to look up anything when %s is missing',
    async (field) => {
      // Each field on its own, not all three at once. The first version
      // blanked enzyme AND substrate, so it never isolated a missing
      // organism — and a mutation restoring `|| 'Homo sapiens'` passed.
      //
      // That default is the substitution Jeske's objection is about, and it
      // would have been reintroduced by the very feature built to honour
      // her: the page would quietly look up a human Km for a student who
      // never said human.
      const h = loadDashboard({ ...COMPLETE, ...FORM, [field]: '', km: '' });
      await h.resolveKm();

      expect(h.alerts.length).toBeGreaterThan(0);
      expect(h.fetches.filter((u) => u.includes('/api/resolve'))).toHaveLength(0);
    },
  );

  it('names the organism as required, and says why', async () => {
    const h = loadDashboard({ ...COMPLETE, ...FORM, organism: '', km: '' });
    await h.resolveKm();
    const message = h.alerts.join(' ');
    expect(message).toContain('organism');
    expect(message).toMatch(/species-specific/i);
  });

  it('sends the organism the student typed, not a substitute', async () => {
    const h = loadDashboard({
      ...COMPLETE, ...FORM, organism: 'Oryctolagus cuniculus', km: '',
    });
    h.reply(200, RESOLVED);
    await h.resolveKm();

    // URLSearchParams encodes a space as `+`, which decodeURIComponent
    // leaves alone — so the query has to be normalised before matching. The
    // first version asserted on the decoded string and failed while the code
    // was correct: a false RED, which is the less dangerous direction but
    // still a test that was wrong about its subject.
    const call = h.fetches.find((u) => u.includes('/api/resolve')) ?? '';
    const query = decodeURIComponent(call).replace(/\+/g, ' ');
    expect(query).toContain('Oryctolagus cuniculus');
    expect(query).not.toContain('Homo sapiens');
  });
});

/**
 * ADR 0062 — the conditions a run is at, shown to the student.
 *
 * ADR 0055 made the pipeline compute `runConditions` and closed by naming
 * what it had not done: nothing rendered it. That is the same gap as
 * ADR 0027 and ADR 0040, and it is the fourth time in this project a value
 * has been computed correctly and shown to nobody.
 *
 * These tests drive `renderRunConditions` directly rather than through a
 * whole simulation, because the thing under test is the DISPLAY of three
 * states and a full run only ever produces one of them per fixture.
 */
describe('the run-conditions panel (ADR 0062)', () => {
  const agreed = (v: number, silent: string[] = []) => ({
    status: 'agreed',
    value: v,
    reported: [{ parameter: 'km', value: v }],
    silent,
  });

  it('shows the temperature when every parameter agrees', () => {
    const h = loadDashboard(COMPLETE);
    h.renderRunConditions({ temperatureC: agreed(25), ph: agreed(7) });

    expect(h.conditionsHtml()).toContain('25');
    expect(h.conditionsVisible()).toBe(true);
  });

  it('names both values on a conflict and shows no single temperature', () => {
    const h = loadDashboard(COMPLETE);
    h.renderRunConditions({
      temperatureC: {
        status: 'conflicting',
        reported: [
          { parameter: 'km', value: 25 },
          { parameter: 'vmax', value: 37 },
        ],
        silent: [],
      },
      ph: agreed(7),
    });

    const html = h.conditionsHtml();
    expect(html).toContain('km at 25');
    expect(html).toContain('vmax at 37');
    // 31 is the mean. Rendering it would state an assay temperature that no
    // assay used -- the exact fabrication ADR 0055 exists to prevent.
    expect(html).not.toContain('31');
  });

  it('renders conflicting and not_reported DIFFERENTLY', () => {
    // The whole point. Both end with no usable number; one is a gap in
    // BRENDA's record and the other is a defect in the model being built.
    // A display that collapsed them would undo ADR 0055 at the last step.
    const conflict = loadDashboard(COMPLETE);
    conflict.renderRunConditions({
      temperatureC: {
        status: 'conflicting',
        reported: [
          { parameter: 'km', value: 25 },
          { parameter: 'vmax', value: 37 },
        ],
        silent: [],
      },
      ph: agreed(7),
    });

    const silent = loadDashboard(COMPLETE);
    silent.renderRunConditions({
      temperatureC: { status: 'not_reported', reported: [], silent: ['km', 'vmax'] },
      ph: agreed(7),
    });

    expect(conflict.conditionsHtml()).not.toEqual(silent.conditionsHtml());
    expect(conflict.conditionsHtml()).toContain('conflict');
    expect(silent.conditionsHtml()).toContain('not reported');
    expect(silent.conditionsHtml()).not.toContain('conflict');
  });

  it('does not style a silent record as a warning', () => {
    // "The papers did not say" is the common case and nothing is wrong.
    // Styling it as an alert would train the reader to skim past the ones
    // that are.
    const h = loadDashboard(COMPLETE);
    h.renderRunConditions({
      temperatureC: { status: 'not_reported', reported: [], silent: ['km'] },
      ph: { status: 'not_reported', reported: [], silent: ['km'] },
    });

    expect(h.conditionsHtml()).not.toContain('alert-info');
  });

  it('says which parameters stayed silent when one value carried the verdict', () => {
    const h = loadDashboard(COMPLETE);
    h.renderRunConditions({
      temperatureC: agreed(30, ['vmax', 's0']),
      ph: agreed(7),
    });

    expect(h.conditionsHtml()).toContain('vmax, s0');
  });

  it('hides the card entirely when there are no run conditions', () => {
    // A failed run has no resolved parameters to derive conditions from.
    // An empty panel would imply we looked and found nothing.
    const h = loadDashboard(COMPLETE);
    h.renderRunConditions(undefined);

    expect(h.conditionsVisible()).toBe(false);
  });

  it('renders the pipeline warnings it is given', () => {
    const h = loadDashboard(COMPLETE);
    h.renderRunConditions(
      { temperatureC: agreed(25), ph: agreed(7) },
      ['Assay temperature conflict: km at 25 C, vmax at 37 C.'],
    );

    expect(h.conditionsHtml()).toContain('Assay temperature conflict');
  });

  it('states that the simulation has no temperature of its own', () => {
    // The counter-intuitive fact the whole feature rests on. A student who
    // does not read this will assume the number is a setting they chose.
    const h = loadDashboard(COMPLETE);
    h.renderRunConditions({ temperatureC: agreed(25), ph: agreed(7) });

    expect(h.conditionsHtml()).toContain('no temperature of');
  });
});

/**
 * The call site, not the function.
 *
 * Every test in the block above drives `renderRunConditions` directly. A
 * mutation that deleted the CALL from `runSimulation` passed all eight of
 * them, because none of them ran a simulation.
 *
 * That is the same defect ADR 0055 records — its own tests covered
 * `deriveRunConditions` thoroughly while a mutation restoring
 * `temperature: 37` at nine call sites passed — repeated by the feature
 * built to finish that ADR. Third time in this project, and the second time
 * I have written the warning and then made the mistake it describes.
 */
describe('a completed simulation actually populates the panel (ADR 0062)', () => {
  it('renders the conditions the run returned', async () => {
    const h = loadDashboard(COMPLETE);

    h.reply(200, { jobId: 'job-1', status: 'queued' });
    h.reply(200, {
      status: 'complete',
      duration: 12,
      result: {
        validated: true,
        validationConfidence: 0.9,
        results: { trajectory: [{ time: 0, value: 10 }], finalValue: 4.2 },
        runConditions: {
          temperatureC: {
            status: 'agreed',
            value: 25,
            reported: [{ parameter: 'km', value: 25 }],
            silent: [],
          },
          ph: { status: 'not_reported', reported: [], silent: ['km'] },
        },
        metadata: { warnings: [] },
      },
    });

    await h.runSimulation();

    expect(h.conditionsVisible()).toBe(true);
    expect(h.conditionsHtml()).toContain('25');
    expect(h.conditionsHtml()).toContain('not reported');
  });

  it('leaves the panel hidden when the run returned no conditions', async () => {
    // A run that failed before resolving parameters has none to report, and
    // an empty panel would imply we looked.
    const h = loadDashboard(COMPLETE);

    h.reply(200, { jobId: 'job-2', status: 'queued' });
    h.reply(200, {
      status: 'complete',
      duration: 8,
      result: {
        validated: false,
        validationConfidence: 0,
        results: { trajectory: [], finalValue: 0 },
        metadata: { warnings: [] },
      },
    });

    await h.runSimulation();

    expect(h.conditionsVisible()).toBe(false);
  });
});
