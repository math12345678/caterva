---
name: A document says X, the code does Y
about: The most valuable thing you can report. No fix needed — just the mismatch.
title: "docs-vs-code: "
labels: docs-vs-code
---

**Where the claim is**
File and line, e.g. `README.md:112`

**What it claims**
Quote it.

**What the code actually does**
File and line, plus what you ran to find out.

**How you checked**
The command, and its output. If you ran nothing, say so — a suspicion is
still worth reporting, just label it as one.

---

*Why this template exists: a sweep of this repository once found a 725-line
API reference describing endpoints that had never existed, and eighteen
documents whose own first line admitted their numbers were unverified.
Documentation rots faster than code, and nobody notices because nothing
fails. You noticing is the whole mechanism.*
