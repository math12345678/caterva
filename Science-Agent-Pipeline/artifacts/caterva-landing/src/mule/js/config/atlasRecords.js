/* ============================================================
   caterva — ATLAS inspection records

   One record per inspectable node. The schema is fixed, because
   the product's claim is that any object in the architecture can
   be interrogated the same way:

     role      what this component is responsible for
     receives  what arrives at it
     produces  what leaves it
     acts      what it verifies or transforms
     failure   what happens when it cannot proceed
     related   sibling components, by id
     badge     the honesty label, on every record

   `failure` is mandatory and is never "n/a". A component whose
   failure behaviour cannot be stated is a component nobody
   should trust.

   No real citation, DOI, PMID, author, journal, customer or
   benchmark appears anywhere in this file.
   ============================================================ */

export const BADGE = 'ILLUSTRATIVE / PLANNED V1 ARCHITECTURE';

export const SOURCE_BADGE = 'CONCEPTUAL SOURCE / NOT A LIVE INTEGRATION';

export const ATLAS_RECORDS = {
  /* --- 01 HUMAN INTAKE ------------------------------------ */
  question: {
    label: 'Scientific Question',
    role: 'Holds the question as written, in the words the person used, as the run\u2019s stated intent.',
    receives: 'One scientific question in plain language.',
    produces: 'Isolated quantities, the relation between them, and the untouched original sentence.',
    acts: 'Separates measurable quantities from the sentence without deciding yet what method they imply.',
    failure: 'Does not rewrite a question it cannot parse. It preserves the original wording and asks.',
    related: ['model-picker', 'decision-point', 'setup-files']
  },
  'setup-files': {
    label: 'Uploaded Setup Files',
    role: 'Accepts a user\u2019s own configuration, data or environment description as run input.',
    receives: 'Optional user files: parameter sets, data series, environment manifests.',
    produces: 'Registered user-supplied inputs, marked as user-defined rather than derived.',
    acts: 'Marks the provenance boundary — anything arriving here is attributed to the user, not to evidence.',
    failure: 'Does not infer missing structure from an unreadable file. It reports what it could not read.',
    related: ['question', 'parameter-builder']
  },
  'decision-point': {
    label: 'User Decision Point',
    role: 'The place the run stops and returns to the person when a choice is theirs to make.',
    receives: 'Clarification requests and unresolved options raised anywhere downstream.',
    produces: 'A stated decision, attributed to the user and carried into the record.',
    acts: 'Converts an ambiguity into an explicit, attributed choice instead of a silent default.',
    failure: 'This node is the failure behaviour. It exists so the system has somewhere to stop.',
    related: ['question', 'model-picker', 'critique']
  },

  /* --- 02 INTERPRETATION LAYER ---------------------------- */
  'model-picker': {
    label: 'Model Picker',
    role: 'Decides which scientific model a plain-language question actually implies, and says so out loud.',
    receives: 'Isolated quantities and the relation stated in the question.',
    produces: 'A named model, the candidates set aside, and the reason for the choice.',
    acts: 'Turns language into a stated method that every later parameter belongs to.',
    failure: 'Does not pick the most common model when the question is ambiguous. It requests clarification.',
    related: ['question', 'domain-class', 'literature-retrieval', 'equation-selector']
  },
  'domain-class': {
    label: 'Domain Classification',
    role: 'Places the question in a scientific field and regime so retrieval and checks know where to look.',
    receives: 'The question\u2019s quantities and the selected model.',
    produces: 'Field, sub-domain and operating regime labels.',
    acts: 'Narrows the space of relevant evidence before any retrieval is attempted.',
    failure: 'Does not force a domain. An unclassifiable question is escalated rather than approximated.',
    related: ['model-picker', 'constraint-recognition', 'literature-retrieval']
  },
  'constraint-recognition': {
    label: 'Constraint Recognition',
    role: 'Finds the limits implied by the question: bounds, conditions, and what must stay fixed.',
    receives: 'Question text, domain labels and the selected model.',
    produces: 'A constraint set, and a list of conditions the question leaves unspecified.',
    acts: 'Makes the unstated conditions of a question explicit before they become silent assumptions.',
    failure: 'Does not invent a bound. Unspecified conditions are passed on as open, not as defaults.',
    related: ['domain-class', 'scope-guard', 'assumption-register']
  },

  /* --- 03 EVIDENCE LAYER ---------------------------------- */
  'literature-retrieval': {
    label: 'Literature Retrieval',
    role: 'Assembles evidence objects and binds each one to the parameter or claim it is meant to support.',
    receives: 'The selected model, its required quantities, and domain labels.',
    produces: 'Evidence objects, each carrying its own scope and the claim it is attached to.',
    acts: 'Binds basis to claim, so no value travels downstream detached from what supports it.',
    failure: 'Does not return a plausible-looking source. It returns a gap, and the gap is carried forward.',
    related: ['src-pubmed', 'src-semantic', 'src-openalex', 'src-crossref', 'src-arxiv', 'parameter-builder', 'hallucination-check']
  },
  'src-pubmed': {
    label: 'PubMed',
    kind: 'source',
    role: 'Conceptual source region for biomedical and life-science literature.',
    receives: 'A scoped query derived from the model\u2019s required quantities.',
    produces: 'Candidate literature records for evidence assembly.',
    acts: 'Illustrates where biomedical basis would be drawn from in the planned v1 architecture.',
    failure: 'An empty result is reported as an evidence gap, never filled by substitution.',
    related: ['literature-retrieval', 'src-crossref']
  },
  'src-semantic': {
    label: 'Semantic Scholar',
    kind: 'source',
    role: 'Conceptual source region for citation-graph structure around a method or claim.',
    receives: 'Candidate records and the method identity.',
    produces: 'Citation relationships that indicate how established a method is.',
    acts: 'Illustrates how the standing of a method would be assessed, not just its existence.',
    failure: 'A sparse graph is disclosed as weak support rather than presented as consensus.',
    related: ['literature-retrieval', 'src-openalex']
  },
  'src-openalex': {
    label: 'OpenAlex',
    kind: 'source',
    role: 'Conceptual source region for breadth of coverage across a field.',
    receives: 'Domain labels and the assembled query scope.',
    produces: 'Coverage indications for the domain being configured.',
    acts: 'Illustrates how thin coverage in a domain would be detected before it becomes a claim.',
    failure: 'Thin coverage is surfaced as a scope warning rather than quietly accepted.',
    related: ['literature-retrieval', 'src-semantic']
  },
  'src-crossref': {
    label: 'CrossRef',
    kind: 'source',
    role: 'Conceptual source region for confirming that a cited record exists as described.',
    receives: 'Candidate references attached to evidence objects.',
    produces: 'Confirmation or non-confirmation of a reference\u2019s existence.',
    acts: 'Illustrates the check that separates a real reference from a fabricated one.',
    failure: 'An unconfirmed reference is marked unconfirmed. It is never shown as a citation.',
    related: ['literature-retrieval', 'hallucination-check']
  },
  'src-arxiv': {
    label: 'arXiv',
    kind: 'source',
    role: 'Conceptual source region for methodology and derivations, including pre-publication work.',
    receives: 'Method identity and the equation form under consideration.',
    produces: 'Methodological basis for the form of the model being configured.',
    acts: 'Illustrates where the justification for a method\u2019s form would come from.',
    failure: 'Pre-publication status is carried with the record rather than dropped.',
    related: ['literature-retrieval', 'equation-selector']
  },

  /* --- 04 CONFIGURATION LAYER ----------------------------- */
  'equation-selector': {
    label: 'Equation Selector',
    role: 'Fixes the specific equation form the run will use, given the named model.',
    receives: 'The selected model and its methodological basis.',
    produces: 'A single equation form, with the variants rejected and why.',
    acts: 'Turns a named method into an unambiguous, runnable mathematical form.',
    failure: 'Does not silently choose between competing forms. It surfaces the choice as a decision.',
    related: ['model-picker', 'parameter-builder', 'src-arxiv']
  },
  'parameter-builder': {
    label: 'Parameter Builder',
    role: 'Assembles the parameter set, attaching to every value the scope of the evidence behind it.',
    receives: 'The equation form, evidence objects, and any user-supplied values.',
    produces: 'A parameter schema where each value carries its basis, scope and origin.',
    acts: 'Refuses to let a number exist without a stated basis and a stated scope.',
    failure: 'Does not fill a missing parameter with a typical value. It marks it as required and unmet.',
    related: ['equation-selector', 'literature-retrieval', 'scope-guard', 'hallucination-check']
  },
  'scope-guard': {
    label: 'Scope Guard',
    role: 'Compares the run\u2019s conditions against the scope of the evidence supporting each parameter.',
    receives: 'The parameter schema with scopes, and the run\u2019s recognised constraints.',
    produces: 'Scope matches, and scope mismatches raised as warnings.',
    acts: 'Catches values used outside the conditions their basis actually establishes.',
    failure: 'Does not widen a scope to fit a run. It blocks the use and states the mismatch.',
    related: ['constraint-recognition', 'parameter-builder', 'assumption-register', 'critique']
  },
  'assumption-register': {
    label: 'Assumption Register',
    role: 'The standing list of everything the run assumed rather than established.',
    receives: 'Unspecified conditions, scope mismatches, and disclosures returned by Critique.',
    produces: 'A durable register of assumptions, carried into the final record.',
    acts: 'Keeps assumptions attached to the run itself, not only to the report about it.',
    failure: 'Does not discard an assumption once the run succeeds. Success does not retire a disclosure.',
    related: ['scope-guard', 'critique', 'notebook']
  },

  /* --- 05 EXECUTION LAYER --------------------------------- */
  'execution-router': {
    label: 'Execution Router',
    role: 'Chooses where a configured model can honestly be run.',
    receives: 'Method requirements, problem size, and the available environments.',
    produces: 'A selected runtime, or a statement that no available runtime is sufficient.',
    acts: 'Matches computational need to real capability, before anything is promised.',
    failure: 'Does not run heavy work in the browser to appear capable. It routes out, or prepares a package.',
    related: ['parameter-builder', 'rt-browser', 'rt-ode', 'rt-backend', 'rt-hpc']
  },
  'rt-browser': {
    label: 'Browser Runtime',
    role: 'Executes light analytical work directly in the visitor\u2019s browser.',
    receives: 'Small, closed-form or low-cost configured models.',
    produces: 'Immediate results, with no data leaving the machine.',
    acts: 'Handles work that genuinely fits in a browser, and only that.',
    failure: 'Declines work beyond its budget instead of degrading it, and hands back to the router.',
    related: ['execution-router', 'rt-ode']
  },
  'rt-ode': {
    label: 'Local ODE Runtime',
    role: 'Integrates ordinary differential equation systems for kinetics-style models.',
    receives: 'A configured system, its parameters and integration bounds.',
    produces: 'An illustrative result series with the solver settings that produced it.',
    acts: 'Produces numbers, and records the exact conditions under which they were produced.',
    failure: 'Reports non-convergence as non-convergence. It does not return the last usable step as a result.',
    related: ['execution-router', 'correctness']
  },
  'rt-backend': {
    label: 'Backend Runtime',
    role: 'Runs heavier numerical work on Caterva-side compute.',
    receives: 'Configured models exceeding browser capability.',
    produces: 'Results, timing and resource records for the run.',
    acts: 'Extends what can be run without leaving the system\u2019s own accountability.',
    failure: 'A timeout is reported as an incomplete run, not as a result.',
    related: ['execution-router', 'rt-hpc']
  },
  'rt-hpc': {
    label: 'User-Provided HPC / Cloud',
    role: 'The boundary of the system: compute the user owns and Caterva does not provide.',
    receives: 'Runs whose requirements exceed anything Caterva can offer.',
    produces: 'A complete setup package for the user\u2019s own environment.',
    acts: 'States the limit of the product honestly, and makes the work portable across it.',
    failure: 'This node is the failure behaviour. Caterva prepares the run rather than pretending to host it.',
    related: ['execution-router', 'setup-package']
  },

  /* --- 06 TRUST LAYER ------------------------------------- */
  /* Supplied verbatim in the brief. Kept word for word. */
  'hallucination-check': {
    label: 'Hallucination Check',
    role: 'Checks that proposed constants and scientific claims have a relevant evidence basis.',
    receives: 'Configuration claims, parameter values, retrieved evidence objects.',
    produces: 'Supported claims, scope warnings, unsupported-claim flags.',
    acts: 'Tests every claim against its stated basis, and reports the ones that have none.',
    failure: 'Does not silently invent a source. It marks unsupported claims for review.',
    related: ['parameter-builder', 'literature-retrieval', 'source-trail', 'critique']
  },
  correctness: {
    label: 'Correctness Verification',
    role: 'Checks that an execution behaves the way the chosen method requires.',
    receives: 'Execution output, the configured model, and the expected qualitative behaviour.',
    produces: 'A sanity verdict, with the specific behaviour that was checked.',
    acts: 'Distinguishes code that ran from science that holds.',
    failure: 'Withholds a failed execution from the final record rather than reporting it as a result.',
    related: ['rt-ode', 'critique', 'verification-record']
  },
  critique: {
    label: 'Critique',
    role: 'States the weaknesses of the run, including the ones nobody asked about.',
    receives: 'The configuration, its scope, the assumption register and the verification verdicts.',
    produces: 'Disclosures written into the record and returned to the assumption register.',
    acts: 'Converts an unstated weakness into a visible review point.',
    failure: 'Does not suppress a disclosure because the run otherwise succeeded.',
    related: ['scope-guard', 'assumption-register', 'correctness', 'polish']
  },
  polish: {
    label: 'Polish',
    role: 'Formats the finished run into a record that preserves its sources and its disclosures.',
    receives: 'All validated outputs, flags and disclosures.',
    produces: 'A source-preserving notebook record, ready to read and to re-run.',
    acts: 'Formats without editing: presentation may change, provenance may not.',
    failure: 'Does not tidy away a flag to make a record read more cleanly.',
    related: ['critique', 'notebook', 'verification-record']
  },

  /* --- 07 OUTPUT LAYER ------------------------------------ */
  notebook: {
    label: 'Interactive Notebook',
    role: 'The run as a document that can be read, checked and executed again.',
    receives: 'The formatted record, its parameters, code and disclosures.',
    produces: 'A re-runnable notebook carrying its own evidence trail.',
    acts: 'Makes the result inspectable and reproducible rather than merely presented.',
    failure: 'A withheld execution appears as withheld, with its reason, and not as a gap.',
    related: ['polish', 'source-trail', 'verification-record', 'assumption-register']
  },
  'verification-record': {
    label: 'Verification Record',
    role: 'States what was checked, by which component, and what the verdict was.',
    receives: 'Verdicts from every trust-layer gate the run passed through.',
    produces: 'An auditable list of checks performed and checks not performed.',
    acts: 'Separates what was verified from what was merely produced.',
    failure: 'A check that did not run is listed as not run, rather than omitted.',
    related: ['correctness', 'hallucination-check', 'notebook']
  },
  'source-trail': {
    label: 'Source Trail',
    role: 'Maps every claim in the record back to the basis it rests on.',
    receives: 'Claim-to-basis mappings from the hallucination check.',
    produces: 'A navigable trail from any stated value to its source and scope.',
    acts: 'Makes provenance traversable in both directions, claim to source and back.',
    failure: 'An unsupported claim appears in the trail as unsupported, with nothing standing in for a source.',
    related: ['hallucination-check', 'literature-retrieval', 'notebook']
  },
  'setup-package': {
    label: 'Setup Package',
    role: 'A complete, portable run for compute Caterva does not provide.',
    receives: 'The configured model and the environment requirements it could not meet locally.',
    produces: 'Code, parameters, environment manifest and the same disclosures as the record.',
    acts: 'Carries the run across the boundary of the product without losing its provenance.',
    failure: 'This node exists because of a failure upstream, and it names that failure in the package.',
    related: ['rt-hpc', 'execution-router', 'notebook']
  }
};

/** Records are keyed by node id; regions carry their own short brief. */
export const REGION_BRIEF = {
  intake: 'Where a person states what they want to know. Nothing is decided here.',
  interpretation: 'Language becomes a named method, with the alternatives stated.',
  evidence: 'Conceptual source regions and the assembly that binds basis to claim.',
  configuration: 'A runnable scope is assembled, and every value keeps its origin.',
  execution: 'The arithmetic happens somewhere real, and the location is recorded.',
  trust: 'Four gates. Nothing reaches the record without passing them.',
  output: 'The record: readable, re-runnable, and still carrying its sources.'
};
