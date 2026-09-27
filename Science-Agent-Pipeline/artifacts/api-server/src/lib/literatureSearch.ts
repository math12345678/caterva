/**
 * What the literature said, branch by branch, when a model's constants
 * were looked up rather than supplied.
 *
 * `POST /simulate/network` takes a network whose values the caller already
 * has, and reports provenance per quantity. `POST /simulate/parameterize`
 * takes a network whose values it does NOT, and goes and looks them up:
 * resolving every constant concurrently, judging whether the resolved set
 * composes, re-searching under whatever that judgement requires, and
 * exploring each candidate organism when the literature offers more than
 * one.
 *
 * THE LOSING BRANCHES ARE THE RESULT
 *
 * "No Ki has been measured in human, though one exists in rabbit" is a
 * result the report would be wrong to hide. A branch that does not
 * converge is information a reader acts on -- a measurement to make, an
 * organism to reconsider -- so every branch is carried, not just the
 * winner. This mirrors `modelGrounding`, which reports the literature's
 * value beside the caller's rather than folding the fold-difference into
 * a sentence: the numbers are for a reader, not a prompt.
 *
 * WHAT THIS DELIBERATELY DOES NOT DO
 *
 * It does not judge the science. `coherent` is the engine's compatibility
 * verdict over one organism's resolved set; `converged` is whether the
 * rounds stopped. Both are reported as the engine computed them, neither
 * is second-guessed here.
 */
import type { CatervaResult } from "./catervaRunner";

/** One resolved value, as the engine serialised it. */
export interface LiteratureSource {
  value?: number;
  unit?: string | null;
  organism?: string | null;
  ph?: number | null;
  temperature_c?: number | null;
  buffer?: string | null;
  citation?: string | null;
  /** True when the value came from a different organism than requested. */
  cross_species?: boolean;
  explicitly_unreported?: string[];
}

/** One constraint the resolution rounds imposed, e.g. "same organism". */
export interface LiteratureConstraint {
  kind: string;
  subject: string | null;
  requirement: string;
  reason: string | null;
  raised_by: string;
}

/** A compatibility finding: a fact about the resolved set, not a verdict. */
export interface LiteratureFinding {
  kind: string;
  severity: string;
  quantities: string[];
  detail: string;
}

/**
 * What `run_parameterize` actually sends, before reshaping.
 *
 * The engine serialises `not_simulated_because` in snake_case; the public
 * report uses camelCase. Keeping the raw shape as its own type means the
 * mapper below renames honestly instead of `ParameterizePayload` pretending
 * the engine already spoke camelCase (a field the type names
 * `notSimulatedBecause` would then carry a key that is actually
 * `not_simulated_because` at runtime -- a lie that would survive to the
 * reader of `literatureSearch`).
 */
export interface RawLiteratureBuild {
  converged: boolean;
  rounds: number;
  constraints: LiteratureConstraint[];
  /** quantity -> resolved source, or null when the quantity was refused. */
  resolved: Record<string, LiteratureSource | null>;
  /** quantity -> reason, for quantities the literature did not supply. */
  missing: Record<string, string>;
  findings: LiteratureFinding[];
  unassessable: string[];
  coherent: boolean;
  simulated: boolean;
  not_simulated_because: string | null;
  summary: string;
}

export interface RawLiteratureBranch {
  organism: string | null;
  complete: boolean;
  build: RawLiteratureBuild;
}

/** The end state of one organism's resolution rounds. */
export interface LiteratureBuild {
  converged: boolean;
  rounds: number;
  constraints: LiteratureConstraint[];
  /** quantity -> resolved source, or null when the quantity was refused. */
  resolved: Record<string, LiteratureSource | null>;
  /** quantity -> reason, for quantities the literature did not supply. */
  missing: Record<string, string>;
  findings: LiteratureFinding[];
  unassessable: string[];
  coherent: boolean;
  simulated: boolean;
  /** Why this branch did not reach a simulation, when it did not. */
  notSimulatedBecause: string | null;
  summary: string;
}

/** One candidate organism explored, winner or not. */
export interface LiteratureBranch {
  organism: string | null;
  complete: boolean;
  build: LiteratureBuild;
}

/** Whether the chosen model actually ran, and what came of it. */
export interface LiteratureSimulation {
  ran: boolean;
  because: string;
  trajectory?: Record<string, number>[];
  values?: Record<string, number>;
  initials?: Record<string, number>;
  quantitySources?: Record<
    string,
    { origin: string | null; citation: string | null; note: string | null }
  >;
}

/**
 * The full literature search behind a `parameterize` run.
 *
 * `chosenOrganism` names the winner when there was one; `undecidedOrganisms`
 * names the candidates the request did not separate; `branches` carries
 * every organism explored, the losing ones included, because they are the
 * useful part.
 */
export interface LiteratureSearchReport {
  chosenOrganism: string | null;
  undecidedOrganisms: string[];
  branches: LiteratureBranch[];
  /** The winning branch's build, present when a model was chosen. */
  model: LiteratureBuild | null;
  summary: string;
  simulation: LiteratureSimulation;
}

/**
 * The structure `compose` built, carried when a query was answered with a
 * mechanism rather than a simulation.
 *
 * `structureOnly` is true when no enzyme was named, which means nothing was
 * searched for: the output is the shape plus the list of constants it needs.
 */
export interface CompositionReport {
  rule: string;
  reading: string;
  structureOnly: boolean;
  network: {
    name: string;
    species: { id: string; initial: number }[];
    parameters: { id: string; value: number }[];
    reactions: {
      id: string;
      reactants: Record<string, number>;
      products: Record<string, number>;
      rateLaw: string;
    }[];
  };
  conservationLaws: string[];
  notes: string[];
  toResolve: {
    id: string;
    motif: string;
    parameter: string;
    unit: string | null;
    table: string | null;
    description: string;
  }[];
  yourChoice: string[];
  unitFindings: { where: string; detail: string; severity: string }[];
  summary: string;
}

/**
 * The composition `compose` refused, with the two refusals kept apart.
 */
export interface CompositionRefusal {
  kind: "named_pathway" | "unrecognised_shape";
  reason: string;
  shapes: string[];
}

/**
 * What `runCaterva("parameterize", ...)` returns, over and above the common
 * `CatervaResult` fields. The engine's serialised search sits on the payload
 * alongside `parameters`/`trajectory`; the extra keys are what this module
 * exists to name. The build fields are still snake_case here -- that is what
 * the engine sent -- and become camelCase in `toLiteratureSearchReport`.
 */
export interface ParameterizePayload extends CatervaResult {
  chosen_organism: string | null;
  undecided_organisms: string[];
  branches: RawLiteratureBranch[];
  model: RawLiteratureBuild | null;
  summary: string;
  simulation: LiteratureSimulation;
}

function fromRawBuild(build: RawLiteratureBuild): LiteratureBuild {
  return {
    converged: build.converged,
    rounds: build.rounds,
    constraints: build.constraints,
    resolved: build.resolved,
    missing: build.missing,
    findings: build.findings,
    unassessable: build.unassessable,
    coherent: build.coherent,
    simulated: build.simulated,
    notSimulatedBecause: build.not_simulated_because,
    summary: build.summary,
  };
}

/** Reshape the engine's snake_case search payload into the report. */
export function toLiteratureSearchReport(
  payload: ParameterizePayload,
): LiteratureSearchReport {
  return {
    chosenOrganism: payload.chosen_organism,
    undecidedOrganisms: payload.undecided_organisms,
    branches: payload.branches.map((branch) => ({
      organism: branch.organism,
      complete: branch.complete,
      build: fromRawBuild(branch.build),
    })),
    model: payload.model ? fromRawBuild(payload.model) : null,
    summary: payload.summary,
    simulation: payload.simulation,
  };
}

/**
 * Build a `CompositionReport` from the engine's `compose` payload.
 *
 * The engine hands back the network it built (species, parameters,
 * reactions with rate laws), the quantities the literature could supply
 * (if a subject were named), and everything its dimensional checks found.
 * Shape-guarded rather than cast, on the same principle as the parameter
 * provenance guard in `simulate.ts`: the engine's report is JSON, and a
 * cast here would launder an unexpected shape into a typed field. A
 * built report MUST carry its mechanism fields; missing any of them means
 * the two enforcers have drifted, and that is thrown, not papered over.
 */
export function toCompositionReport(
  engineResult: Partial<{
    rule: string;
    reading: string;
    structureOnly: boolean;
    network: CompositionReport["network"];
    conservationLaws: string[];
    notes: string[];
    toResolve: CompositionReport["toResolve"];
    yourChoice: string[];
    unitFindings: CompositionReport["unitFindings"];
    summary: string;
  }>,
): CompositionReport {
  const required: (keyof CompositionReport)[] = [
    "rule",
    "reading",
    "structureOnly",
    "network",
    "conservationLaws",
    "notes",
    "toResolve",
    "yourChoice",
    "unitFindings",
    "summary",
  ];

  for (const key of required) {
    if (engineResult[key] === undefined) {
      throw new Error(
        `compose reported built without "${key}"; the two enforcers ` +
          `have drifted (engine payload vs CompositionReport).`,
      );
    }
  }

  return {
    rule: engineResult.rule as string,
    reading: engineResult.reading as string,
    structureOnly: engineResult.structureOnly as boolean,
    network: engineResult.network as CompositionReport["network"],
    conservationLaws: engineResult.conservationLaws as string[],
    notes: engineResult.notes as string[],
    toResolve: engineResult.toResolve as CompositionReport["toResolve"],
    yourChoice: engineResult.yourChoice as string[],
    unitFindings: engineResult.unitFindings as CompositionReport["unitFindings"],
    summary: engineResult.summary as string,
  };
}