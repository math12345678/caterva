/**
 * Literature grounding for a model the CALLER wrote.
 *
 * WHY THIS EXISTS
 *
 * Tellurium is innovative because there is no catalogue: you write your
 * model, it compiles, it runs. Caterva shipped fifteen hardcoded domains,
 * and measured against realistic questions only three of them could
 * resolve anything from literature at all. "Write twelve more resolvers"
 * is the wrong answer, because a lab's actual model is never one of the
 * fifteen -- it is theirs.
 *
 * `POST /api/simulate/model` already runs any Antimony or SBML document.
 * But it stamped every parameter `origin: "user"` with `modelCitations:
 * []`, so the moment a real lab used the one endpoint built for them,
 * Caterva's entire reason to exist switched off and they had plain
 * Tellurium with extra steps.
 *
 * This module is the missing half: your model, with the constants in it
 * traced to the literature.
 *
 * THE RULE THAT SHAPES EVERY DECISION BELOW
 *
 * Caterva must never guess which enzyme a parameter called `Km` belongs
 * to. `Km_1`, `KmA`, `Km_hex` are names, not facts, and a Km resolved
 * against the wrong enzyme is the worst failure this system has: a real
 * citation attached to a number that does not belong to it, which is more
 * convincing than no citation at all.
 *
 * So the caller declares it, in a comment:
 *
 *     // caterva: km enzyme="hexokinase" substrate="glucose" unit="mM"
 *     Km_hex = 0.15;
 *
 * That is a claim the caller makes and can be held to, not an inference
 * this code made. Everything here parses declarations; nothing here
 * infers one.
 *
 * TWO MODES, AND WHY BOTH
 *
 *   check   (default) -- your value stands. Caterva resolves what the
 *                        literature says and reports both, with the
 *                        citation and assay conditions. Your model is
 *                        never modified.
 *
 *   resolve            -- you left the constant to Caterva. It is filled
 *                        from literature with a citation, or the run
 *                        REFUSES. There is no fallback value, because a
 *                        fallback is the fabrication this project exists
 *                        to prevent.
 *
 * `check` is the one a lab will use on a model they already trust, and it
 * is non-invasive by construction. `resolve` is the one that makes the
 * literature layer worth having: write the structure, let Caterva source
 * the numbers, and get a run that either cites every constant or does not
 * happen.
 */

/** What the caller says a parameter is. Matches `resolveKineticValue`. */
export type AnnotatedQuantity = "km" | "ki" | "kcat";

export type AnnotationMode = "check" | "resolve";

export interface ModelAnnotation {
  /** The model parameter this annotation is attached to. */
  parameter: string;
  quantity: AnnotatedQuantity;
  mode: AnnotationMode;
  /**
   * The value written in the model. Absent in `resolve` mode when the
   * caller left a placeholder rather than a number.
   */
  value?: number;
  enzymeName?: string;
  ecNumber?: string;
  substrate?: string;
  organism?: string;
  /**
   * The unit the caller's value is in.
   *
   * Load-bearing, not documentation. BRENDA normalises Km and Ki to mM
   * (Tests/brenda_client.py, `unit: str = "mM"`). A model written in uM
   * whose Km is compared against a literature mM value disagrees by 1000x
   * for a reason that has nothing to do with the science. Antimony's own
   * unit support is optional and usually absent, so the source cannot be
   * relied on to say. Without a unit here, the value is reported
   * side-by-side and explicitly NOT compared -- see `auditAnnotations`.
   */
  unit?: string;
  /** 1-based line in the caller's source, for pointing at the mistake. */
  line: number;
}

/**
 * A problem with the annotation itself.
 *
 * Returned rather than thrown, and never silently skipped. A typo in
 * `enzmye="hexokinase"` that quietly resolved nothing would leave the
 * caller believing a parameter was literature-checked when it was
 * ignored -- the silent-failure shape this project treats as worse than
 * an error.
 */
export interface AnnotationProblem {
  line: number;
  message: string;
  /** The offending source line, trimmed, so the message can point at it. */
  source: string;
}

export interface ParsedAnnotations {
  annotations: ModelAnnotation[];
  problems: AnnotationProblem[];
}

/** `// caterva: ...` or `# caterva: ...`, case-insensitive on the tag. */
const DIRECTIVE_RE = /(?:\/\/|#)\s*caterva\s*:\s*(.+)$/i;

/**
 * The same directive inside SBML: an XML comment, or free text in a
 * `<notes>` element.
 *
 * SBML is the format labs actually exchange -- COPASI, CellDesigner and
 * BioModels all speak it -- so Antimony-only grounding would have meant
 * most labs could not use this at all.
 *
 * WHY NOT SBO TERMS, WHICH WOULD NEED NO NEW SYNTAX
 *
 * SBML already has a standard way to say "this parameter is a Michaelis
 * constant": an `sboTerm` attribute. Reading those would be the elegant
 * answer, and it is deliberately not what this does.
 *
 * libsbml 5.21.1 (the version this engine runs) exposes `SBO.intToString`,
 * which only formats an integer as "SBO:0000027" -- there is no label
 * lookup, and `SBO.isKineticConstant(27)` returns false while
 * `isKineticConstant(25)` returns true, which is not enough to establish
 * what either term MEANS. Identifying parameters from remembered ontology
 * numbers, with no way to check them here, would attach real citations to
 * misidentified constants: the precise failure this module exists to
 * refuse, committed by the code meant to prevent it.
 *
 * So SBML uses the same explicit declaration Antimony does. When an SBO
 * label source can be verified rather than recalled, reading sboTerm
 * becomes a strict addition to this, not a replacement for it.
 */
const XML_DIRECTIVE_RE = /caterva\s*:\s*([^<>]+?)\s*(?:-->|<\/|$)/i;

/**
 * An Antimony scalar assignment: `Km_hex = 0.15;`
 *
 * Only a literal number. An assignment to an expression is not a constant
 * this module can compare against a measured value, and treating one as
 * though it were would report a citation for something the model computes.
 */
const ASSIGNMENT_RE =
  /^\s*([A-Za-z_]\w*)\s*=\s*(-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)\s*;?/;

/**
 * A parameter with no value yet -- `resolve` mode's placeholder.
 *
 * Antimony needs the symbol to exist, so the caller writes the assignment
 * and leaves Caterva to supply the number.
 */
const PLACEHOLDER_RE = /^\s*([A-Za-z_]\w*)\s*=\s*\?\s*;?/;

const KNOWN_QUANTITIES = new Set<string>(["km", "ki", "kcat"]);

/** key="value" pairs. Double or single quotes; values may contain spaces. */
const FIELD_RE = /(\w+)\s*=\s*(?:"([^"]*)"|'([^']*)')/g;

const KNOWN_FIELDS = new Set([
  // SBML only: names the parameter this declaration is about. XML has no
  // "the line below" to bind to, so the binding is stated rather than
  // positional -- which is the same reason the enzyme is stated.
  "parameter",
  "enzyme",
  "ec",
  "substrate",
  "organism",
  "unit",
]);

/**
 * Read `caterva:` declarations out of an Antimony source.
 *
 * Antimony only. SBML is XML and carries no comments in the same sense;
 * its annotation story is `<annotation>` RDF, which is a different and
 * much larger job. Declaring that limit is the point of saying it here --
 * `auditAnnotations`' caller reports it to SBML callers rather than
 * returning an empty audit that reads as "nothing to check".
 */
export type ModelFormat = "antimony" | "sbml";

export function parseModelAnnotations(
  source: string,
  format: ModelFormat = "antimony",
): ParsedAnnotations {
  return format === "sbml"
    ? parseSbmlAnnotations(source)
    : parseAntimonyAnnotations(source);
}

/**
 * Validate the body of a directive -- everything after `caterva:`.
 *
 * Shared by both formats deliberately. An SBML caller and an Antimony
 * caller must be held to exactly the same standard, or the weaker one
 * becomes the way to get an unidentified parameter resolved.
 */
function parseDirectiveBody(
  body: string,
): { fields: Record<string, string>; quantity: AnnotatedQuantity; mode: AnnotationMode } | { error: string } {
  // The quantity is the first bare word: "km", "kcat", "ki".
  const quantityMatch = /^([A-Za-z_]+)/.exec(body);
  const quantity = quantityMatch?.[1]?.toLowerCase();
  if (!quantity || !KNOWN_QUANTITIES.has(quantity)) {
    return {
      error:
        `'${quantity ?? body}' is not a quantity Caterva can resolve. ` +
        `Use one of: ${[...KNOWN_QUANTITIES].join(", ")}.`,
    };
  }

  // Unknown keys are reported rather than ignored: a mistyped
  // `enzmye="..."` would otherwise leave the annotation silently
  // unidentifiable while looking correct in the source.
  const fields: Record<string, string> = {};
  let unknownField: string | undefined;
  for (const m of body.matchAll(FIELD_RE)) {
    const key = m[1]!.toLowerCase();
    if (!KNOWN_FIELDS.has(key)) {
      unknownField ??= m[1]!;
      continue;
    }
    fields[key] = (m[2] ?? m[3] ?? "").trim();
  }
  if (unknownField !== undefined) {
    return {
      error:
        `'${unknownField}' is not a field Caterva understands. ` +
        `Use: ${[...KNOWN_FIELDS].join(", ")}. To have Caterva supply ` +
        "the value from literature, add the bare word 'resolve'.",
    };
  }

  // Identity is mandatory. This is the whole reason the declaration
  // exists: without an enzyme or an EC number there is nothing to look
  // up, and picking one from the parameter's NAME is exactly the guess
  // this module refuses to make.
  if (!fields["enzyme"] && !fields["ec"]) {
    return {
      error:
        'an enzyme must be named: add enzyme="..." or ec="1.1.1.27". ' +
        "Caterva will not infer which enzyme a parameter belongs to from " +
        "its name.",
    };
  }

  return {
    fields,
    quantity: quantity as AnnotatedQuantity,
    mode: /\bresolve\b/i.test(body) ? "resolve" : "check",
  };
}

function parseAntimonyAnnotations(source: string): ParsedAnnotations {
  const annotations: ModelAnnotation[] = [];
  const problems: AnnotationProblem[] = [];
  const lines = source.split(/\r?\n/);

  for (let i = 0; i < lines.length; i++) {
    const raw = lines[i]!;
    const directive = DIRECTIVE_RE.exec(raw);
    if (!directive) continue;

    const line = i + 1;
    const body = directive[1]!.trim();
    const fail = (message: string): void => {
      problems.push({ line, message, source: raw.trim() });
    };

    const parsed = parseDirectiveBody(body);
    if ("error" in parsed) {
      fail(parsed.error);
      continue;
    }
    const { fields, quantity, mode } = parsed;

    // Bind to a parameter: the assignment on THIS line if the directive
    // trails one, otherwise the next assignment below it.
    const beforeComment = raw.slice(0, directive.index);
    let bound = ASSIGNMENT_RE.exec(beforeComment);
    let placeholder = bound ? null : PLACEHOLDER_RE.exec(beforeComment);
    let boundLine = line;

    if (!bound && !placeholder) {
      for (let j = i + 1; j < lines.length; j++) {
        const next = lines[j]!;
        if (next.trim() === "" || DIRECTIVE_RE.test(next)) continue;
        bound = ASSIGNMENT_RE.exec(next);
        placeholder = bound ? null : PLACEHOLDER_RE.exec(next);
        boundLine = j + 1;
        break;
      }
    }

    if (!bound && !placeholder) {
      fail(
        "this annotation is not attached to a parameter. Put it on the " +
          "same line as an assignment, or on the line directly above one.",
      );
      continue;
    }

    const parameter = (bound?.[1] ?? placeholder?.[1])!;

    if (placeholder && mode === "check") {
      fail(
        `${parameter} has no value to check ('= ?'). Either give it a ` +
          "value, or add 'resolve' to the annotation to have Caterva " +
          "supply one from literature.",
      );
      continue;
    }

    const value = bound ? Number.parseFloat(bound[2]!) : undefined;
    if (bound && !Number.isFinite(value)) {
      fail(`could not read a number from '${bound[2]}'.`);
      continue;
    }

    annotations.push({
      parameter,
      quantity: quantity as AnnotatedQuantity,
      mode,
      ...(value !== undefined ? { value } : {}),
      ...(fields["enzyme"] ? { enzymeName: fields["enzyme"] } : {}),
      ...(fields["ec"] ? { ecNumber: fields["ec"] } : {}),
      ...(fields["substrate"] ? { substrate: fields["substrate"] } : {}),
      ...(fields["organism"] ? { organism: fields["organism"] } : {}),
      ...(fields["unit"] ? { unit: fields["unit"] } : {}),
      line: boundLine,
    });
  }

  return dedupeByParameter(annotations, problems);
}

/**
 * Collapse duplicate declarations about one parameter.
 *
 * Shared by both formats: an SBML caller must not be able to get two
 * conflicting claims resolved where an Antimony caller cannot.
 */
function dedupeByParameter(
  annotations: ModelAnnotation[],
  problems: AnnotationProblem[],
): ParsedAnnotations {
  // A parameter declared twice is ambiguous about which claim holds, and
  // resolving it twice would attach two different citations to one
  // symbol.
  //
  // BOTH are dropped, not just the second. Keeping the first would be
  // choosing between two claims by source order -- the same
  // whichever-came-first non-decision that let domain classification pick
  // the wrong model for years. The problem below stops the run either
  // way, so dropping both costs nothing and states the right thing.
  const byParameter = new Map<string, ModelAnnotation[]>();
  for (const annotation of annotations) {
    const group = byParameter.get(annotation.parameter);
    if (group) group.push(annotation);
    else byParameter.set(annotation.parameter, [annotation]);
  }

  const unique: ModelAnnotation[] = [];
  for (const [parameter, group] of byParameter) {
    if (group.length === 1) {
      unique.push(group[0]!);
      continue;
    }
    problems.push({
      line: group[1]!.line,
      message:
        `${parameter} is annotated ${group.length} times (lines ` +
        `${group.map((a) => a.line).join(", ")}). Caterva will not choose ` +
        "between two claims about the same parameter.",
      source: parameter,
    });
  }

  return { annotations: unique, problems };
}


/** `<parameter id="Km_hex" value="0.15"/>`, in any attribute order. */
function findSbmlParameter(
  lines: string[],
  id: string,
): { line: number; value?: number; hasValueAttr: boolean } | undefined {
  const idPattern = new RegExp(`<parameter\\b[^>]*\\bid\\s*=\\s*"${id.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}"`);
  for (let i = 0; i < lines.length; i++) {
    const raw = lines[i]!;
    if (!idPattern.test(raw)) continue;
    const valueMatch = /\bvalue\s*=\s*"([^"]*)"/.exec(raw);
    if (!valueMatch) return { line: i + 1, hasValueAttr: false };
    const parsed = Number.parseFloat(valueMatch[1]!);
    return Number.isFinite(parsed)
      ? { line: i + 1, value: parsed, hasValueAttr: true }
      : { line: i + 1, hasValueAttr: true };
  }
  return undefined;
}

function parseSbmlAnnotations(source: string): ParsedAnnotations {
  const annotations: ModelAnnotation[] = [];
  const problems: AnnotationProblem[] = [];
  const lines = source.split(/\r?\n/);

  for (let i = 0; i < lines.length; i++) {
    const raw = lines[i]!;
    const directive = XML_DIRECTIVE_RE.exec(raw);
    if (!directive) continue;

    const line = i + 1;
    const fail = (message: string): void => {
      problems.push({ line, message, source: raw.trim() });
    };

    const parsed = parseDirectiveBody(directive[1]!.trim());
    if ("error" in parsed) {
      fail(parsed.error);
      continue;
    }
    const { fields, quantity, mode } = parsed;

    const name = fields["parameter"];
    if (!name) {
      fail(
        'an SBML declaration must say which parameter it is about: add ' +
          'parameter="Km_hex". XML has no line below to bind to.',
      );
      continue;
    }

    const target = findSbmlParameter(lines, name);
    if (!target) {
      // A typo here would otherwise silently check nothing at all.
      fail(`no <parameter id="${name}"> exists in this document.`);
      continue;
    }

    if (!target.hasValueAttr && mode === "check") {
      fail(
        `<parameter id="${name}"> has no value to check. Either give it a ` +
          "value, or add 'resolve' to the declaration to have Caterva " +
          "supply one from literature.",
      );
      continue;
    }

    annotations.push({
      parameter: name,
      quantity,
      mode,
      ...(target.value !== undefined ? { value: target.value } : {}),
      ...(fields["enzyme"] ? { enzymeName: fields["enzyme"] } : {}),
      ...(fields["ec"] ? { ecNumber: fields["ec"] } : {}),
      ...(fields["substrate"] ? { substrate: fields["substrate"] } : {}),
      ...(fields["organism"] ? { organism: fields["organism"] } : {}),
      ...(fields["unit"] ? { unit: fields["unit"] } : {}),
      line: target.line,
    });
  }

  return dedupeByParameter(annotations, problems);
}
