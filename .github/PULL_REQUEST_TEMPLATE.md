## What does this change?

<!-- One or two sentences. If this is a new simulation domain or touches
tellurium_engine.py or Tests/brenda_client.py, say which domain/module. -->

## Why?

<!-- What problem does this solve, or what gap does it close? Link an issue
if one exists. -->

## How was this verified?

<!-- Required for anything touching tellurium_engine.py or brenda_client.py.
See CONTRIBUTING.md's "standard this codebase holds itself to" section. -->

- [ ] New/updated tests added, and they fail without this change (checked,
      not assumed)
- [ ] For new numerical claims: verified against an exact closed-form
      solution, an independent solver, or a property-based test -- not just
      "the output looked reasonable"
- [ ] `make test` passes locally (not just "CI will catch it")
- [ ] If a new dependency was added: it's in `requirements.txt` or
      `requirements-dev.txt` (otherwise `test_dependencies_declared.py`
      will fail this PR)
- [ ] If this changes `KM_PLAUSIBLE_MIN_MM`/`KM_PLAUSIBLE_MAX_MM`: both
      `tellurium_engine.py` and `Tests/brenda_client.py` were updated
      together (see ADR 0003)

## Anything you're unsure about?

<!-- Genuinely fine to leave open questions here -- better than silently
picking an answer and hoping it's right. -->
