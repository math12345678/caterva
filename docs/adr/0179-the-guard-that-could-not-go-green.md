# ADR 0179: The guard that could not go green

**Status:** Accepted, implemented

**Date:** 2026-08-24

**Context:** `scripts/check_quickstart_clone_works.py`,
`scripts/check_availability_notice_matches_reality.py`, `README.md`,
`START_HERE.md`, the seventeen `docs/readmes/*.md`

**Supersedes the premise of:** [ADR 0143](0143-the-first-command-a-stranger-runs.md)

## Context

ADR 0143 found that nineteen newcomer-facing documents open with

```bash
git clone https://github.com/Terrium-sim/main.git
```

against a repository that is not readable anonymously, and wired a guard
that fails on it. It shipped **deliberately red**, and said why:

> The fix is not a code change and is not mine to make: the repository
> becomes readable, or the quickstart points somewhere that is. On that day
> this goes green with no edit.

That was the right call on the day. It rested on a premise — that
publication was coming — and the premise has now been settled the other
way. **The owner has decided the repositories stay private.**

That changes what the red light means. ADR 0143 refused to baseline itself
because "recording the problem instead of fixing it" is what a list that
only grows amounts to. A guard that *cannot* go green is the same failure
wearing the opposite costume: it is not a signal any more, it is a red light
people learn to walk past, and it teaches a build's own maintainers that red
is the normal colour.

The guard was also asking the wrong question. It has one model of the reader
— an anonymous stranger — and the decision has created a different one.

## Decision

**The guard learns that there are two audiences, and asks each the question
that applies to it.**

| command in a document | promises | checked by |
|---|---|---|
| `git clone https://github.com/...` | anonymous access | probed, exactly as before |
| `gh repo clone owner/repo` | credentials required | the document must **say so** |

The nineteen documents now use the authenticated form, because that is the
command that actually works for the only people who can run it.

**Switching the command is not a way past the guard**, which was the obvious
risk in making this change. A `gh repo clone` whose document does not admit
it needs credentials is *worse* than the anonymous command it replaced: the
reader still meets a credential prompt, and now nothing warned them. So a
document using that form must carry both

- the sentinel `**Private repository.**`, and
- a link to this record,

and the guard fails, red, naming the file, if either is missing. Requiring
both is the sibling guard's rule — a bare marker is a guard you satisfy by
typing the marker, whereas a marker that has to carry its reasoning makes
the cheapest way to pass also the correct one.

**Reachability of the private repositories is deliberately not probed.**
Answering it needs credentials and CI has none, so a probe would report
"unreachable" for a repository that is merely unreachable *by this runner* —
the narrower-matcher failure this guard's own controls exist to prevent, and
which this repository has now recorded nine times. The guard prints what it
did not check rather than letting a green tick imply it.

## Verification

- Selftest passes: positive controls cloneable, negative control not, the
  extractor finds both URL forms.
- With the documents converted, the guard reports 19 authenticated commands
  all carrying the notice, no anonymous command left to probe, and exits 0.
- Sabotage, which is the part that matters: deleting the sentinel from one
  document turns it red and names that document; deleting the ADR link does
  the same. Neither was silently tolerated.
- `check_availability_notice_matches_reality.py` still passes, and still
  fails in the other direction — publish the repositories and it demands the
  notice be deleted, so the notice cannot outlive the thing it describes.

## Consequences

- The build has no permanently-red step, so red means something again.
- The quickstart tells the truth to the people who can actually run it.

**What this does not check.**

- **Not that the repository is reachable.** Named above; it is the honest
  limit of a check with no credentials, not an oversight.
- **Not that the prose around the sentinel is accurate.** The guard reads a
  marker and a link, not a paragraph — the same limit its sibling states.
- **The `**Not public yet.**` sentinel still says "yet".** ADR 0143's notice
  was written expecting publication, and the word now understates a
  decision. It is left alone because that string is the contract between two
  guards, and changing it is a coordinated edit that should be its own
  change rather than a side effect of this one.
- **Nobody has run `gh repo clone` from a clean machine.** The command is
  correct by construction and by `gh` documentation; it has not been
  executed here against an empty credential store.
