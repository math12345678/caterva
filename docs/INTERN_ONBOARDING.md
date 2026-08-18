# Working on Terrium

**This document moved to [`START_HERE.md`](../START_HERE.md) at the
repository root.**

It was the best onboarding document in the project, which is why it became
the single entry point rather than being deleted. Two things changed in the
move:

- It is at the root, where someone landing on the repository will see it
  without knowing to look in `docs/`.
- It is for **anyone** joining — interns and outside contributors both —
  rather than students specifically. There was no rule in it that applied to
  only one of those groups.

## Why this file is a stub rather than a copy

It stated *"roughly 1,291 tests"*, *"22 guards"* and *"docs/adr/ — 23
decision records"*. The real figures when this stub was written were 1,684,
35 and 56.

Nothing was wrong when it was typed. `scripts/check_documented_counts.py`
existed the whole time and had been catching exactly this class of drift —
in `README.md`, the only file it scanned. Three other documents drifted
beside it, unguarded, for months.

That is the same defect shape as
[ADR 0055](adr/0055-a-simulation-has-no-temperature-of-its-own.md): a guard
that worked correctly, on a scope narrower than the problem. Leaving two
copies of an onboarding document would have guaranteed a third round of it.

The guard now covers every present-tense contributor document. Historical
records — `EXPERT_FEEDBACK.md`, `ARCHIVE_TRIAGE.md`, `Business/build-stages/`
— are deliberately excluded, because they describe what was true on a date
and rewriting them would be falsifying a record.

Go to [`START_HERE.md`](../START_HERE.md).
