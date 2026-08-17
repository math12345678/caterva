import {
  USER_CITATION_CAVEAT,
  collectRepeated,
  parseUserCitations,
} from '../userCitations';

/**
 * `--cite` closes the failure Herbert Sauro predicted:
 *
 *   "a tool that refuses to produce a runnable model blocks step one, and
 *    the researcher works around it by hardcoding a number with no warning
 *    at all — a strictly worse outcome caused by the strict rule."
 *
 * Terrium was not merely vulnerable to that. Its refusal message said
 * "Add km=<value> to your query and try again", and then recorded the
 * result as origin=user with no citation — walking the user into exactly
 * the outcome he described, through a door the tool opened.
 *
 * The tests that matter here are the refusals, and the insistence that a
 * user citation never acquires the authority of a resolved one.
 */

describe('a repeatable flag must not silently lose values', () => {
  it('collects every occurrence', () => {
    // parseArgs returns a flat record, so a second --cite overwrites the
    // first. A user citing three parameters would have two vanish, be told
    // nothing, and get a model claiming less provenance than they gave.
    const argv = ['--cite', 'km=Smith 2019', '--cite', 'vmax=Jones 2020', '--json'];
    expect(collectRepeated(argv, 'cite')).toEqual(['km=Smith 2019', 'vmax=Jones 2020']);
  });

  it('records a flag with no value rather than skipping it', () => {
    // Skipping would make `--cite` with nothing after it look like no
    // --cite at all, and the user would never learn their citation was
    // dropped.
    expect(collectRepeated(['--cite', '--json'], 'cite')).toEqual(['']);
    expect(collectRepeated(['--json', '--cite'], 'cite')).toEqual(['']);
  });

  it('returns nothing when the flag is absent', () => {
    expect(collectRepeated(['--json', '--km', '5'], 'cite')).toEqual([]);
  });
});

describe('parsing', () => {
  it('attaches a citation to a supplied parameter', () => {
    const { citations, error } = parseUserCitations(
      ['km=Smith 2019, PMID 12345'],
      ['km'],
    );
    expect(error).toBeUndefined();
    expect(citations.get('km')).toBe('Smith 2019, PMID 12345');
  });

  it('is case-insensitive about the parameter name', () => {
    const { citations } = parseUserCitations(['KM=Smith 2019'], ['km']);
    expect(citations.get('km')).toBe('Smith 2019');
  });

  it('keeps equals signs inside the citation itself', () => {
    // DOIs and URLs contain '='. Splitting on the last one, or on all of
    // them, would truncate the source.
    const { citations } = parseUserCitations(
      ['km=https://doi.org/10.1/x?a=b&c=d'],
      ['km'],
    );
    expect(citations.get('km')).toBe('https://doi.org/10.1/x?a=b&c=d');
  });
});

describe('what it refuses', () => {
  it('refuses a citation for a parameter that was never supplied', () => {
    // Either a typo or a belief that the citation is doing something.
    // Both deserve to be told.
    const { error } = parseUserCitations(['ki=Smith 2019'], ['km', 'vmax']);
    expect(error).toContain("no value was supplied for 'ki'");
    expect(error).toContain('km, vmax');
  });

  it('refuses an empty citation', () => {
    const { error } = parseUserCitations(['km='], ['km']);
    expect(error).toContain('no citation after');
    // The reasoning, not just the rule.
    expect(error).toContain('worse than none');
  });

  it('refuses a bare --cite with no argument', () => {
    const { error } = parseUserCitations([''], ['km']);
    expect(error).toContain('--cite needs a value');
  });

  it('refuses a malformed pair with an example', () => {
    const { error } = parseUserCitations(['Smith 2019'], ['km']);
    expect(error).toContain('name=citation');
    expect(error).toContain('--cite km=');
  });

  it('refuses two citations for one value rather than merging them', () => {
    // Not a merge — a question about which paper the number came from,
    // and only the user can answer it.
    const { error } = parseUserCitations(
      ['km=Smith 2019', 'km=Jones 2020'],
      ['km'],
    );
    expect(error).toContain('given twice');
    expect(error).toContain('the one you took the number from');
  });

  it('refuses a leading equals sign', () => {
    const { error } = parseUserCitations(['=Smith 2019'], ['km']);
    expect(error).toContain('name=citation');
  });
});

describe('a user citation is never a verified one', () => {
  it('states plainly that Terrium has not checked it', () => {
    // The whole risk of this feature is a number acquiring borrowed
    // credibility by passing through a tool that promises provenance.
    expect(USER_CITATION_CAVEAT).toContain('cited by you');
    expect(USER_CITATION_CAVEAT).toContain('has not checked');
  });

  it('has one caveat string, so surfaces cannot describe it differently', () => {
    // Centralised deliberately: the risk is one surface presenting it with
    // more confidence than another.
    expect(typeof USER_CITATION_CAVEAT).toBe('string');
    expect(USER_CITATION_CAVEAT.length).toBeGreaterThan(30);
  });
});
