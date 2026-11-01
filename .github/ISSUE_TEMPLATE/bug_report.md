---
name: Bug report
about: Something is broken -- a crash, wrong output, or a flag that should have fired but didn't
title: ''
labels: bug
assignees: ''
---

## What happened?

<!-- What you did, and what happened instead of what you expected. -->

## Is this a "wrong answer" bug or a "crashed" bug?

If Caterva produced a *number* that's wrong (not just a crash), this is the
most important category of bug this project has -- please include:

- The exact parameters you used
- What Caterva returned
- What the correct answer actually is, and how you know (a citation, a
  hand calculation, an independent tool) -- this is exactly the kind of
  claim the test suite is built to prevent, so a concrete repro here likely
  becomes a permanent regression test.

## Steps to reproduce

```python
# minimal code that triggers it
```

## Environment

- Did this happen with `make setup` or the Docker sandbox?
- Python version (`python --version`)
- Output of `python scripts/check_env.py` if it's not obviously unrelated
