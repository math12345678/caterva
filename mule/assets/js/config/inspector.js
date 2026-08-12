/* ============================================================
   terrium — inspection content

   Every inspectable node resolves to a record with the same
   schema, because the promise of the product is that any object
   in the architecture can be interrogated the same way:

     category   what kind of thing this is
     purpose    one sentence, what it is for
     inputs     what arrives
     outputs    what leaves
     event      what it did in this illustrated run
     status     supported / user / review
     trail      its position in the chain of custody
     path       the nodes lit in the architecture behind the panel
     note       the honest limit of what is being shown

   All source metadata is explicitly illustrative. No real
   citation, DOI, PMID, author or journal appears anywhere.
   ============================================================ */

const DEMO_NOTE =
  'Illustrative demonstration of Terrium\u2019s evidence-trail interface. Not a research-ready parameter recommendation.';

/* The ordered spine of the run. Used to derive each record's position in the
   chain of custody, so the trail statement can never drift out of step with
   the architecture it describes. */
export const CHAIN = [
  'question-chamber', 'model-picker', 'literature-retrieval',
  'configuration-agent', 'configuration-assembly', 'compute-router',
  'simulation-core', 'verification-vault', 'verified-record'
];

export const INSPECTOR = {
  /* --- chamber ------------------------------------------- */
  'question-chamber': {
    eyebrow: 'INTAKE / TIER 01',
    title: 'Question Chamber',
    category: 'Intake structure',
    purpose: 'Accepts a scientific question in plain language and holds it as the run\u2019s stated intent.',
    status: 'user',
    inputs: 'One question, written as a person would ask it',
    outputs: 'Isolated quantities and the relation between them',
    event: 'Accepted run 0007. Two quantities and one relation lifted from the sentence.',
    trail: 'Origin of the chain of custody. Everything downstream is answerable to this sentence.',
    path: ['question-chamber', 'model-picker'],
    note: 'A typed question routes into the same illustrative architecture as the demonstration question.'
  },

  /* --- interpretation array ------------------------------ */
  'model-picker': {
    eyebrow: 'AGENT / 01',
    title: 'Model Picker',
    category: 'Interpretation agent',
    purpose: 'Decides which simulation model a plain-language question actually implies.',
    status: 'supported',
    inputs: 'Isolated concepts from the question chamber',
    outputs: 'Saturation kinetics \u2014 illustrative',
    event: 'Classified as saturation kinetics. Mass-action and Hill were considered and set aside.',
    trail: 'Second link. Names the method every later parameter belongs to.',
    path: ['question-chamber', 'model-picker', 'configuration-agent'],
    note: 'The choice is stated out loud so a reviewer can disagree with it.'
  },
  'literature-retrieval': {
    eyebrow: 'AGENT / 02',
    title: 'Literature Retrieval',
    category: 'Interpretation agent',
    purpose: 'Finds source records and attaches them to the parameters they support.',
    status: 'supported',
    inputs: 'Selected model and its required quantities',
    outputs: 'Three illustrative evidence objects, each carrying its own scope',
    event: 'Emitted three demo records, routed to Km, Vmax and solver tolerance.',
    trail: 'Third link. Supplies the basis that the hallucination check later traces back to.',
    path: ['literature-retrieval', 'ev-method', 'ev-scope', 'ev-ode'],
    note: 'Evidence objects here are placeholders. No real citation or identifier is shown.'
  },
  'configuration-agent': {
    eyebrow: 'AGENT / 03',
    title: 'Configuration',
    category: 'Interpretation agent',
    purpose: 'Turns a chosen model into an explicit parameter schema with a declared basis for each value.',
    status: 'supported',
    inputs: 'Model, evidence objects, user-stated conditions',
    outputs: 'Six parameters, each labelled by where its value came from',
    event: 'Built six parameters. Three from evidence, two user-defined, one marked for review.',
    trail: 'Fourth link. Converts the method into something executable and inspectable.',
    path: ['configuration-agent', 'configuration-assembly'],
    note: 'Nothing is filled in silently. A value without support is labelled, not hidden.'
  },
  'compute-router': {
    eyebrow: 'AGENT / 04',
    title: 'Compute Router',
    category: 'Interpretation agent',
    purpose: 'Decides where a method can honestly run.',
    status: 'supported',
    inputs: 'Method, parameter schema, available runtimes',
    outputs: 'Local ODE runtime \u2014 illustrated',
    event: 'Selected the local solver. Heavier methods were routed away from the browser.',
    trail: 'Fifth link. Sets the runtime the core executes in.',
    path: ['compute-router', 'simulation-core'],
    note: 'Molecular dynamics is not claimed as browser-executable. Run where the method permits.'
  },

  /* --- evidence objects ---------------------------------- */
  'ev-method': {
    eyebrow: 'EVIDENCE OBJECT / 01',
    title: 'Demo source \u2014 kinetics method',
    category: 'Illustrative literature record',
    purpose: 'Carries a method basis for the kinetic constants, together with the conditions it holds under.',
    status: 'supported',
    inputs: 'Retrieved by Literature Retrieval',
    outputs: 'Source basis for Km and Vmax',
    event: 'Docked beside the left berth column. Two parameters now trace to it.',
    trail: 'Basis for two of the six parameters. Traced by sentinel 01.',
    scope: 'Illustrative enzyme / stated conditions',
    path: ['literature-retrieval', 'ev-method', 'p-km', 'p-vmax', 's-hallucination'],
    note: 'Placeholder record used to demonstrate source attachment. Not a real publication.'
  },
  'ev-scope': {
    eyebrow: 'EVIDENCE OBJECT / 02',
    title: 'Demo scope \u2014 enzyme conditions',
    category: 'Illustrative scope record',
    purpose: 'States the boundary a value is valid inside, so a mismatch can be detected instead of assumed away.',
    status: 'supported',
    inputs: 'Retrieved by Literature Retrieval',
    outputs: 'Condition boundary for Vmax',
    event: 'Docked below the method record. Its boundary is what flagged the temperature assumption.',
    trail: 'The object that makes critique possible. Scope travels with the value.',
    scope: 'Bounded set / not generalised',
    path: ['literature-retrieval', 'ev-scope', 'p-vmax', 's-critique', 'p-temp'],
    note: 'Conditions outside this set are not covered by it. That limit is the point.'
  },
  'ev-ode': {
    eyebrow: 'EVIDENCE OBJECT / 03',
    title: 'Method record \u2014 ODE solution',
    category: 'Illustrative method record',
    purpose: 'Describes how the illustrated system is solved numerically.',
    status: 'supported',
    inputs: 'Retrieved by Literature Retrieval',
    outputs: 'Basis for solver tolerance',
    event: 'Docked on the right of the assembly core, tied to the tolerance berth.',
    trail: 'Supports the numerical method rather than the biology.',
    /* Not "browser numerical integration": this run routed away from the
       browser, and Terrium's ODE path is libroadrunner. See architecture.js. */
    scope: 'Local ODE runtime / numerical integration',
    path: ['literature-retrieval', 'ev-ode', 'p-tol', 'compute-router'],
    note: 'Describes how the system is solved, not what the result means.'
  },

  /* --- assembly ------------------------------------------ */
  'configuration-assembly': {
    eyebrow: 'STRUCTURE / TIER 03',
    title: 'Configuration Assembly',
    category: 'Structural holder',
    purpose: 'Holds every parameter in a declared position with a declared basis.',
    status: 'supported',
    inputs: 'Parameter schema and docked evidence objects',
    outputs: 'An executable configuration with its provenance still attached',
    event: 'Six parameters docked. Three tied to evidence, two user-defined, one disclosed.',
    trail: 'Where provenance becomes structure. The core executes only what is docked here.',
    path: ['configuration-agent', 'configuration-assembly', 'simulation-core'],
    note: 'Select any berth to read the basis behind a single parameter.'
  },

  /* --- vault + sentinels --------------------------------- */
  'verification-vault': {
    eyebrow: 'TRUST LAYER / TIER 04',
    title: 'The Verification Vault',
    category: 'Verification enclosure',
    purpose: 'Surrounds execution with four checks that fail in four different ways.',
    status: 'supported',
    inputs: 'Executed output, configuration, evidence objects',
    outputs: 'A traced, checked, critiqued and composed record',
    event: 'All four sentinels resolved. One assumption carried out as a disclosure.',
    trail: 'Generation is one step. Verification surrounds it.',
    path: ['verification-vault', 's-hallucination', 's-correctness', 's-critique', 's-polish'],
    note: 'Verification reduces silent error. It does not certify correctness.'
  },
  's-hallucination': {
    eyebrow: 'SENTINEL / 01',
    title: 'Hallucination Check',
    category: 'Verification sentinel',
    purpose: 'Traces every constant back to the object that supports it.',
    status: 'supported',
    inputs: 'Six parameters, three evidence objects',
    outputs: 'A claim-to-basis link for each traceable value',
    event: 'Three of six parameters resolved to a source basis. Three did not.',
    trail: 'Checks the link between assembly and evidence. Unresolved values stay visible.',
    path: ['s-hallucination', 'ev-method', 'ev-scope', 'ev-ode', 'p-km', 'p-vmax', 'p-tol'],
    note: 'Tracing a value does not prove it is appropriate for your system.'
  },
  's-correctness': {
    eyebrow: 'SENTINEL / 02',
    title: 'Correctness Verification',
    category: 'Verification sentinel',
    purpose: 'Checks whether an executed result behaves the way the method says it should.',
    status: 'supported',
    inputs: 'Illustrative output curve, expected-behaviour envelope',
    outputs: 'A behaviour verdict against the envelope',
    event: 'Saturating response checked against the expected region. Within envelope.',
    trail: 'Checks execution, not intent. The structure locks only once this resolves.',
    path: ['s-correctness', 'simulation-core'],
    note: 'Code that runs is not necessarily science that holds. This does not confirm the model choice.'
  },
  's-critique': {
    eyebrow: 'SENTINEL / 03',
    title: 'Critique',
    category: 'Verification sentinel',
    purpose: 'Finds scope mismatches and assumptions that need a human decision.',
    status: 'review',
    inputs: 'Configuration, evidence scope boundaries',
    outputs: 'A disclosed assumption, carried forward rather than resolved',
    event: 'Temperature assumption detected. 37 \u00B0C is not established by the sample source scope.',
    trail: 'Compares configuration against the limits its own evidence declared.',
    path: ['s-critique', 'ev-scope', 'p-temp', 'verified-record'],
    note: 'An amber disclosure is the architecture working, not failing.'
  },
  's-polish': {
    eyebrow: 'SENTINEL / 04',
    title: 'Polish',
    category: 'Verification sentinel',
    purpose: 'Composes the final record without letting presentation hide anything.',
    status: 'supported',
    inputs: 'Verified output, sources, open disclosures',
    outputs: 'An archival record with citations and scope intact',
    event: 'Run composed. Disclosure and source links survived formatting.',
    trail: 'Last check before release. Presentation is treated as its own failure mode.',
    path: ['s-polish', 'verified-record'],
    note: 'Polish may never remove or soften a critique flag.'
  },

  /* --- core + record ------------------------------------- */
  'simulation-core': {
    eyebrow: 'EXECUTION / TIER 05',
    title: 'Simulation Core',
    category: 'Execution chamber',
    purpose: 'Runs the configured method in the runtime the router selected.',
    status: 'user',
    inputs: 'Docked configuration, local ODE runtime',
    outputs: 'Illustrative kinetics output',
    event: 'Velocity rises with substrate concentration and approaches a plateau.',
    trail: 'The generation step. One step among nine, and the only one that produces a number.',
    path: ['configuration-assembly', 'compute-router', 'simulation-core', 's-correctness'],
    note: 'A design demonstration of shape and behaviour. Not an experimental result.'
  },
  'verified-record': {
    eyebrow: 'ARTIFACT / TIER 06',
    title: 'Verified run 0007',
    category: 'Released record',
    purpose: 'Carries the whole run as something a reviewer can take apart.',
    status: 'supported',
    inputs: 'Everything above it',
    outputs: 'Six parameters, three evidence objects, four verification operations, one disclosure',
    event: 'Released and inspectable. The temperature assumption is stated on the record itself.',
    trail: 'Question \u2192 model \u2192 evidence \u2192 configuration \u2192 execution \u2192 verification \u2192 record.',
    path: CHAIN,
    note: 'An inspectable scientific trail, not a black-box answer.'
  }
};

/** Parameter records. Same schema, so a value is interrogated like a structure. */
export const PARAM_INSPECTOR = {
  'p-km': {
    eyebrow: 'PARAMETER / Km',
    title: '0.42 mM',
    category: 'Michaelis constant',
    purpose: 'Sets the substrate concentration at which velocity reaches half of its maximum.',
    status: 'supported',
    inputs: 'Demo source / kinetics method',
    outputs: 'Docked to the assembly, left column',
    event: 'Traced to its evidence object by sentinel 01.',
    trail: 'Value \u2192 demo source \u2014 kinetics method.',
    scope: 'Illustrative enzyme / stated conditions',
    path: ['p-km', 'ev-method', 's-hallucination'],
    note: DEMO_NOTE
  },
  'p-vmax': {
    eyebrow: 'PARAMETER / Vmax',
    title: '1.00 relative',
    category: 'Maximum velocity',
    purpose: 'Sets the plateau the reaction approaches at saturating substrate.',
    status: 'supported',
    inputs: 'Demo source / kinetics method, bounded by demo scope',
    outputs: 'Docked to the assembly, left column',
    event: 'Traced to two evidence objects: one for the value, one for its boundary.',
    trail: 'Value \u2192 kinetics method, bounded by \u2192 enzyme conditions.',
    scope: 'Normalised for illustration',
    path: ['p-vmax', 'ev-method', 'ev-scope', 's-hallucination'],
    note: DEMO_NOTE
  },
  'p-s': {
    eyebrow: 'PARAMETER / [S]',
    title: '0 \u2192 5.0 mM',
    category: 'Substrate range',
    purpose: 'Sets the sweep the illustrated run is evaluated across.',
    status: 'user',
    inputs: 'Declared by the person running the simulation',
    outputs: 'Docked to the assembly, left column',
    event: 'Carried into execution as a stated condition, not an inferred one.',
    trail: 'No source basis, and none claimed. User-defined values are labelled as such.',
    scope: 'Sweep range for this run',
    path: ['p-s', 'simulation-core', 's-correctness'],
    note: DEMO_NOTE
  },
  'p-temp': {
    eyebrow: 'PARAMETER / Temperature',
    title: '37 \u00B0C',
    category: 'Environmental condition',
    purpose: 'Sets the thermal condition the kinetics are assumed to hold at.',
    status: 'review',
    inputs: 'None. Not established by the sample source scope.',
    outputs: 'Docked to the assembly, and disclosed on the released record',
    event: 'Raised by Critique. Carried out of the vault as an open assumption.',
    trail: 'The one link in the chain that does not close. Confirm or replace it before treating the run as meaningful.',
    scope: 'Outside the declared scope of every attached source',
    path: ['p-temp', 's-critique', 'ev-scope', 'verified-record'],
    note: 'This disclosure is what the architecture exists to produce. Science should not depend on invisible assumptions.'
  },
  'p-time': {
    eyebrow: 'PARAMETER / Reaction time',
    title: '120 s',
    category: 'Observation window',
    purpose: 'Sets how long the illustrated reaction is observed for.',
    status: 'user',
    inputs: 'Declared by the person running the simulation',
    outputs: 'Docked to the assembly, right column',
    event: 'Carried into execution as a stated condition.',
    trail: 'No source basis, and none claimed.',
    scope: 'Illustrative observation window',
    path: ['p-time', 'simulation-core', 's-correctness'],
    note: DEMO_NOTE
  },
  'p-tol': {
    eyebrow: 'PARAMETER / Solver tolerance',
    title: '1e\u22126',
    category: 'Numerical setting',
    purpose: 'Sets how tightly the numerical integration must converge.',
    status: 'supported',
    inputs: 'Method record / ODE solution',
    outputs: 'Applied by the compute router at execution',
    event: 'Traced to its method record by sentinel 01.',
    trail: 'Value \u2192 method record \u2014 ODE solution.',
    /* Not "browser numerical integration": this run routed away from the
       browser, and Terrium's ODE path is libroadrunner. See architecture.js. */
    scope: 'Local ODE runtime / numerical integration',
    path: ['p-tol', 'ev-ode', 'compute-router', 's-hallucination'],
    note: DEMO_NOTE
  }
};

export function getInspectorRecord(id) {
  return INSPECTOR[id] || PARAM_INSPECTOR[id] || null;
}
