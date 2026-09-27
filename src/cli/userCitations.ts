/**
 * `--cite km="Smith 2019, PMID 12345"` — let a value you supply carry the
 * source you got it from.
 *
 * WHY THIS EXISTS: SAURO WAS DESCRIBING A REAL FAILURE, AND CATERVA CAUSED IT
 * ---------------------------------------------------------------------------
 * Professor Herbert Sauro's argument for defaulting an unsourced parameter
 * was not only about convenience. The sharp part was a prediction about what
 * users do when a tool refuses:
 *
 *     a tool that refuses to produce a runnable model blocks step one, and
 *     the researcher works around it by hardcoding a number with no warning
 *     at all — a strictly worse outcome caused by the strict rule.
 *
 * Caterva was not just vulnerable to that. It **instructed** it. When a Km
 * could not be resolved, the error said:
 *
 *     Add km=<value> to your query and try again.
 *
 * The user then went and found a Km — from a paper, usually — typed it in,
 * and Caterva recorded `origin: user` with no citation field and no further
 * comment. A number with a real source in the world, stripped of that source
 * by the tool whose entire purpose is not losing sources.
 *
 * That is Sauro's predicted outcome arriving one step later than he
 * described it, through the door Caterva opened. ADR 0024 Decision 2 —
 * whether to default at all — is still open and still his to answer. This is
 * independent of it: whichever way that goes, a user who HAS a source should
 * be able to attach it.
 *
 * WHAT A USER CITATION IS NOT
 * ---------------------------
 * It is not verified. Caterva cannot check that "Smith 2019" says what the
 * user believes it says, and it does not try.
 *
 * So a user citation is a DIFFERENT KIND of thing from a resolved one, and
 * is carried as `origin: 'user_cited'` rather than folded into `resolved`.
 * Everything downstream — the CLI table, the annotated model, the
 * bibliography — says whose claim it is. Presenting an unverified citation
 * with the same authority as a BRENDA reference id would be the most
 * damaging thing this feature could do: it would let a number acquire
 * borrowed credibility by passing through a tool that promises provenance.
 *
 * Better than `user`, worse than `resolved`, and never silently either.
 */

export interface UserCitation {
  parameter: string;
  citation: string;
}

export interface ParsedCitations {
  citations: Map<string, string>;
  error?: string;
}

/**
 * Collect every occurrence of a repeatable flag from raw argv.
 *
 * `parseArgs` returns a flat `Record<string, string>`, so a second `--cite`
 * silently overwrites the first. Silently is the problem: a user citing
 * three parameters would have two citations vanish and be told nothing,
 * and the run would still succeed — producing a model that claims less
 * provenance than the user actually supplied.
 */
export function collectRepeated(argv: string[], flag: string): string[] {
  const token = `--${flag}`;
  const values: string[] = [];
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] !== token) continue;
    const next = argv[i + 1];
    if (next === undefined || next.startsWith('--')) {
      // Recorded as an empty value rather than skipped, so the parser below
      // can report it. Dropping it here would make `--cite` with no
      // argument look like no `--cite` at all.
      values.push('');
      continue;
    }
    values.push(next);
    i++;
  }
  return values;
}

/**
 * Parse `name=citation` pairs.
 *
 * `suppliedParameters` is the set of parameters the user actually gave a
 * value for. Citing a parameter you did not supply is refused rather than
 * ignored: it means either a typo or a belief that the citation is doing
 * something, and both deserve to be told.
 */
export function parseUserCitations(
  raw: string[],
  suppliedParameters: Iterable<string>,
): ParsedCitations {
  const citations = new Map<string, string>();
  const supplied = new Set([...suppliedParameters].map((name) => name.toLowerCase()));

  for (const entry of raw) {
    if (entry.trim().length === 0) {
      return {
        citations,
        error:
          '--cite needs a value, e.g. --cite km="Smith 2019, PMID 12345". ' +
          'It attaches a source to a value you supplied yourself.',
      };
    }

    const separator = entry.indexOf('=');
    if (separator <= 0) {
      return {
        citations,
        error:
          `--cite expects name=citation (got '${entry}'). ` +
          'Example: --cite km="Smith 2019, PMID 12345".',
      };
    }

    const parameter = entry.slice(0, separator).trim().toLowerCase();
    const citation = entry.slice(separator + 1).trim();

    if (citation.length === 0) {
      return {
        citations,
        error:
          `--cite ${parameter}= has no citation after the '='. ` +
          'An empty citation is worse than none: it would record that a ' +
          'source exists while saying nothing about it.',
      };
    }

    if (!supplied.has(parameter)) {
      const known = [...supplied].sort().join(', ') || '(none)';
      return {
        citations,
        error:
          `--cite ${parameter}=... but no value was supplied for ` +
          `'${parameter}'. A citation with nothing to attach to does ` +
          `nothing. Parameters you supplied: ${known}.`,
      };
    }

    if (citations.has(parameter)) {
      // Two citations for one value is not a merge — it is a question about
      // which paper the number came from, and only the user can answer it.
      return {
        citations,
        error:
          `--cite ${parameter} was given twice. A value comes from one ` +
          'source; if two papers report it, cite the one you took the ' +
          'number from.',
      };
    }

    citations.set(parameter, citation);
  }

  return { citations };
}

/**
 * The sentence shown beside a user citation, everywhere it appears.
 *
 * Centralised so the CLI, the exported model and the bibliography cannot
 * drift into describing it differently — the whole risk of this feature is
 * one surface presenting it with more confidence than another.
 */
export const USER_CITATION_CAVEAT =
  'cited by you; Caterva has not checked that this source reports this value';
