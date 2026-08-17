# Rename plan

**Status:** planning only. Nothing has been renamed. This exists so that
renaming is a decision you can make cheaply and on evidence, rather than a
project you have to start in order to find out what it costs.

**Not legal advice.** The trademark judgement belongs to a lawyer. This
document is the engineering cost and the sequencing.

## Why this is on the table

Terrium sits in the same field as **Tellurium**, an established
systems-biology environment from the Sauro lab at the University of
Washington. Terrium runs *on* that lab's libRoadRunner and generates their
Antimony. The names differ by two letters.

That is not hypothetical harm. It has already happened once: Matthias König
(HU Berlin) read a cold outreach email as a false claim of credit for
Tellurium's work. The README now says so in plain terms, near the top.

The licensing question is settled and favourable — see `docs/LICENSING.md`.
The naming question is not, and it is the larger of the two.

## Evidence the name was independently coined

This was missing from the first version of this document, which is a
material omission: it framed the collision as though the name had been
derived from Tellurium. `Docw/terrium_spec.docx` — an internal brand spec
dated July 2026, written before the outreach that caused the incident —
says otherwise:

> **Name: Terrium.** Coined in the register of real element names
> (Terbium, Tritium, Yttrium) — sounds like it belongs on the periodic
> table, signals hard science without being literal or overused.

Tellurium is not mentioned. The same document records that the project was
**"Formerly Quanticle"**, so a rename has already happened once here and is
evidently not unthinkable.

**Why this matters, and what it does not do.** Contemporaneous evidence of
independent derivation goes to *intent*: it is the difference between
coining a name that turned out to collide and adopting one that traded on
another project's reputation. That distinction matters a great deal to how
a dispute is framed and to whether anything is treated as willful.

It does **not** resolve likelihood of confusion, which is about the effect
in the marketplace rather than the state of mind of the person who chose
the name. König's reaction is evidence about the effect, and it is
independent of how carefully the name was derived. Both facts are true at
once: coined independently, and colliding anyway.

README.md says "The similar name is a mistake of mine." That remains the
right thing to say publicly — it addresses the collision, which is real.
This section addresses the derivation, which is different, and belongs in
front of an attorney alongside it.

**Give both to the lawyer.** The spec is dated, internal, and predates the
incident, which is exactly the kind of document that is worth much more
before a dispute than after one.

## What the name actually costs to change

452 tracked files contain it, 2,651 occurrences. But raw counts overstate
the difficulty, because most of it is prose that a careful search-and-replace
handles. The real cost sits in a small number of places.

### Finding: there are already two spellings

| spelling | occurrences | what it is |
|---|---|---|
| `Terium` / `TERIUM` | 767 | the **Python package you import** — `Terium/`, `python -m Terium.cli` |
| `Terrium` / `terrium` / `TERRIUM` | 1,470 | the **product**, the repo, the site, the docs |

One 'r' in the code, two in the name. `pyproject.toml` declares
`name = "terrium"`, so you `pip install terrium` and then `import Terium`.

**An earlier draft of this section claimed this was a live bug — that a
reader following the documentation would type `import Terrium` and get an
ImportError. That was wrong, and checking it is what showed so.** No
document anywhere tells a user to `import Terrium`. All 17 occurrences of
`python -m Terium.cli` are correct, the one documented `import Terium` is
correct, and `examples/python_integration.py` really does export the
`TerriumClient` that `QUICK_START_DEPLOYMENT.md` promises.

So the split is a cosmetic inconsistency, not a defect: install under one
spelling, import under another. Worth resolving, but it is **not** urgent,
and that changes the sequencing advice below.

Specifically: renaming `Terium/` to `Terrium/` now would be doing the same
767-occurrence change twice if a different name is chosen later, and a
directory move is the single most disruptive edit available in a repository
where other work is in flight — at the time of writing, 27 files under
`Terium/` carry uncommitted changes and 12 of those are new files that do
not exist in any commit. **Fold the spelling fix into the real rename.**

### Tier 1 — mechanical, low risk (~1 hour)

Prose in 452 files. Search-and-replace, then `make pr`. The guards make
this safer than it sounds: `check_documented_counts.py`,
`check_doc_paths_resolve.py`, `check_doc_links.py` and
`check_commands_runnable.py` between them fail on a broken path, a broken
link, a stale count or an unrunnable command.

### Tier 2 — identifiers, medium risk (~half a day)

| what | where | note |
|---|---|---|
| Python package directory | `Terium/` | 30 files import from it; `pyproject.toml` already declares `name = "terrium"`, so the *distribution* name is already the two-r spelling and only the *import* name changes |
| CLI module path | `python -m Terium.cli` | 17 documented invocations |
| npm package names | `terrium-scientific-backend`, `terrium-site` | not published; renaming is free today |
| Front-end workspace | `Science-Agent-Pipeline/artifacts/terrium-landing/` | directory rename plus workspace references |
| `CITATION.cff` | `title`, `repository-code` | citation metadata; cheap now, expensive after anyone cites it |

### Tier 3 — external, and the reason to decide soon (~a day, plus lead time)

| what | note |
|---|---|
| GitHub org and repo URLs | Docs point at `Terrium-sim/*`; `origin` is `math12345678/terrium`. **These already disagree** — see below |
| PyPI / npm names | Not published. Nothing to migrate **today** |
| Domain, landing site | `terrium-site/`, `landing/` |
| Binary artefacts | `terrium_pitch_deck.pptx`, five `.docx` files under `Docw/` — hand edits, not scriptable |
| Anyone already emailed | The outreach that caused the incident |

## The pre-existing URL disagreement

`README.md`'s quick start says:

```bash
git clone https://github.com/Terrium-sim/terrium.git
```

`git remote get-url origin` says `https://github.com/math12345678/terrium.git`.

`docs/PUBLISHING.md` describes splitting into six `Terrium-sim/*`
repositories, and `docs/ARCHIVE_TRIAGE.md` links to four of them.

I could not verify which is correct — this sandbox has no GitHub network
access, so `git ls-remote` fails for every URL including the real origin,
which makes the test uninformative rather than negative. **Someone with
network access needs to confirm what exists.** If the org is being created
anyway, that is the cheapest possible moment to pick the final name.

## The recommendation on sequencing

1. **Decide whether to rename before publishing anything.** Nothing is on
   PyPI or npm and nothing has a DOI. Every cost in Tier 3 is currently
   zero and starts accruing the moment the first person installs, cites, or
   links to it.
2. **Fold the Terium/Terrium split into whichever rename happens.** It is
   cosmetic, not a defect — see the correction above — so it does not
   justify a directory move on its own, and doing it separately means
   paying the same 767-occurrence cost twice.
3. **Ask a trademark attorney before committing either way.** The specific
   facts to put in front of them:
   - Two-letter difference from an established mark in the same field.
   - Same target users (systems biology, teaching labs).
   - Terrium is built on the other project's libraries, which strengthens
     the association rather than weakening it.
   - One documented instance of an expert in the field actually being
     confused about credit.
   - Terrium is pre-launch, so a change now costs days rather than years.
   - **`Docw/terrium_spec.docx`, July 2026** — contemporaneous evidence the
     name was coined from Terbium/Tritium/Yttrium, with no reference to
     Tellurium. Take the file, not a summary of it.

## If the name is kept

The disclaimer should be load-bearing rather than decorative. Today it
appears near the top of `README.md` and in `NOTICE`. It should also reach:

- `CITATION.cff` (`abstract`)
- `pyproject.toml` description and the npm `description` fields
- the landing page footer
- the API's own metadata response, so it travels with the software rather
  than only with the repository

and be covered by a guard, so it cannot quietly disappear the way the
BRENDA attribution did before 2026-08-13.
