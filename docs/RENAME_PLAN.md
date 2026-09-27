# Rename plan

**Status: done, 2026-09-27.** The project, repository, command and Python
package are now **Caterva** (the repository is `math12345678/caterva`; the
old `terrium` command is kept as an alias). This document is kept as the
record of why. Its tables below were written against the old names and have
been passed through the same rename, so they read oddly: the two spellings
they count were "Terrium" (the product) and "Terium" (the package).

**Not legal advice.** The trademark judgement belongs to a lawyer. This
document is the engineering cost and the sequencing.

## Why this is on the table

Caterva sits in the same field as **Tellurium**, an established
systems-biology environment from the Sauro lab at the University of
Washington. Caterva runs *on* that lab's libRoadRunner and generates their
Antimony. The names differ by two letters.

That is not hypothetical harm. It has already happened once: Matthias König
(HU Berlin) read a cold outreach email as a false claim of credit for
Tellurium's work. The README now says so in plain terms, near the top.

The licensing question is settled and favourable — see `docs/LICENSING.md`.
The naming question is not, and it is the larger of the two.

## Evidence the name was independently coined

This was missing from the first version of this document, which is a
material omission: it framed the collision as though the name had been
derived from Tellurium. `Docw/caterva_spec.docx` — an internal brand spec
dated July 2026, written before the outreach that caused the incident —
says otherwise:

> **Name: Caterva.** Coined in the register of real element names
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

README.md says "The project was called Terrium until 2026-09-27, too close to Tellurium's name; it has been Caterva since." That remains the
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
| `caterva` / `CATERVA` | 767 | the **Python package you import** — `caterva/`, `python -m caterva.cli` |
| `Caterva` / `caterva` / `CATERVA` | 1,470 | the **product**, the repo, the site, the docs |

One 'r' in the code, two in the name. `pyproject.toml` declares
`name = "caterva"`, so you `pip install caterva` and then `import caterva`.

**An earlier draft of this section claimed this was a live bug — that a
reader following the documentation would type `import Caterva` and get an
ImportError. That was wrong, and checking it is what showed so.** No
document anywhere tells a user to `import Caterva`. All 17 occurrences of
`python -m caterva.cli` are correct, the one documented `import caterva` is
correct, and `examples/python_integration.py` really does export the
`CatervaClient` that `QUICK_START_DEPLOYMENT.md` promises.

So the split is a cosmetic inconsistency, not a defect: install under one
spelling, import under another. Worth resolving, but it is **not** urgent,
and that changes the sequencing advice below.

Specifically: renaming `caterva/` to `Caterva/` now would be doing the same
767-occurrence change twice if a different name is chosen later, and a
directory move is the single most disruptive edit available in a repository
where other work is in flight — at the time of writing, 27 files under
`caterva/` carry uncommitted changes and 12 of those are new files that do
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
| Python package directory | `caterva/` | 30 files import from it; `pyproject.toml` already declares `name = "caterva"`, so the *distribution* name is already the two-r spelling and only the *import* name changes |
| CLI module path | `python -m caterva.cli` | 17 documented invocations |
| npm package names | `caterva-scientific-backend`, `caterva-site` | not published; renaming is free today |
| Front-end workspace | `Science-Agent-Pipeline/artifacts/caterva-landing/` | directory rename plus workspace references |
| `CITATION.cff` | `title`, `repository-code` | citation metadata; cheap now, expensive after anyone cites it |

### Tier 3 — external, and the reason to decide soon (~a day, plus lead time)

| what | note |
|---|---|
| GitHub org and repo URLs | Published at `math12345678/caterva` (owner-confirmed 2026-08-16); `origin` is `math12345678/caterva`. Both true — see below |
| PyPI / npm names | Not published. Nothing to migrate **today** |
| Domain, landing site | `caterva-site/`, `landing/` |
| Binary artefacts | `caterva_pitch_deck.pptx`, five `.docx` files under `Docw/` — hand edits, not scriptable |
| Anyone already emailed | The outreach that caused the incident |

## The URL disagreement — resolved 2026-08-16

**`https://github.com/math12345678/caterva` is the published location**,
confirmed by the owner. `git remote get-url origin` says
`https://github.com/math12345678/caterva.git`, which is where this working
copy pushes; both are true at once, which is normal for a repository that
moved.

Every self-reference now says `math12345678/caterva`, and
`Tests/test_clone_instructions_agree.py` keeps them there — including the
five `contact_links` on `.github/ISSUE_TEMPLATE/config.yml`, which are what
a newcomer reaches before cloning anything.

### How this was nearly settled the wrong way

The URL was stated three ways: `math12345678/caterva` here and in most places,
`math12345678/caterva` in `README.md`, `math12345678/caterva` in `origin`.
The first repair made README, START_HERE and CONTRIBUTING agree — on
`caterva`, chosen because it was what README happened to say, **without
counting how often each appeared**.

The count was 3 against 126. The 126 included every link on the GitHub New
Issue page and the clone command in `docs/REPO_MAP.md`. So the repair
reduced a three-way disagreement in three files and left the repository
more inconsistent than it found it, while reporting the problem as fixed.

Two lessons, both cheap and both skipped:

- **Count before normalising.** One `grep -c` across the tree would have
  shown which spelling was load-bearing. Internal agreement among the files
  you happen to be reading is not agreement.
- **A surface is not always a document.** `.github/ISSUE_TEMPLATE/config.yml`
  is YAML, so an audit looking at markdown never saw the most
  contributor-facing links in the project.

The sandbox has no GitHub network access, so `git ls-remote` fails for
every URL including the real origin — the test is uninformative rather than
negative, and *which* URL is right was never checkable from here. What was
checkable, and was not checked, is which one the repository already
believed.

## The recommendation on sequencing

1. **Decide whether to rename before publishing anything.** Nothing is on
   PyPI or npm and nothing has a DOI. Every cost in Tier 3 is currently
   zero and starts accruing the moment the first person installs, cites, or
   links to it.
2. **Fold the caterva/Caterva split into whichever rename happens.** It is
   cosmetic, not a defect — see the correction above — so it does not
   justify a directory move on its own, and doing it separately means
   paying the same 767-occurrence cost twice.
3. **Ask a trademark attorney before committing either way.** The specific
   facts to put in front of them:
   - Two-letter difference from an established mark in the same field.
   - Same target users (systems biology, teaching labs).
   - Caterva is built on the other project's libraries, which strengthens
     the association rather than weakening it.
   - One documented instance of an expert in the field actually being
     confused about credit.
   - Caterva is pre-launch, so a change now costs days rather than years.
   - **`Docw/caterva_spec.docx`, July 2026** — contemporaneous evidence the
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
