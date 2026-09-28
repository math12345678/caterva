# Changelog

> **⚠️ CORRECTION (2026-08-12):** the `## Unreleased` section's counts are stale — the repo has moved well past the state they describe:
> - **"11 guard scripts"**: running `python3 scripts/verify_build.py --quick` today shows the Guard Wiring Guard reporting **"all 22 guards run in at least one harness"** — 22 guards now exist, not 11.
> - **"Engine test suite: 715 -> 883 tests"**: `python3 -m pytest --collect-only` in `caterva/` now collects **1,014** tests.
> - **"Literature test suite: 182 -> 214 tests"**: `Tests/` now collects **277** tests.
> - **"TypeScript test suite: 111 -> 224 tests (16 files)"**: `Science-Agent-Pipeline/artifacts/api-server` now has **433** test cases across **32** `*.test.ts` files (`npx vitest list`).
> This is ordinary changelog staleness (the Unreleased section wasn't updated as later work landed, and later work was logged in `OVERNIGHT_LOG.md` instead — see that file's own correction banner for the same underlying drift), not fabrication.

This file follows [Semantic Versioning](https://semver.org/) from 0.1.0
onward and [Keep a Changelog](https://keepachangelog.com/) in shape.
Entries before 0.1.0 are grouped by date, because that is how the work was
done: there was no release to version.

## [Unreleased: site]

### Fixed
- The website called BRENDA ref 739793's Ki "oxamate". It is not: the
  ref measures a quinoline sulfonamide against His-tagged human LDH-A, and
  its 0.00059 mM is competitive against NADH, not pyruvate. The hero and
  the example gallery now use the same paper's pyruvate row (0.00252 mM,
  noncompetitive, pH 7.5, 37 C) and draw noncompetitive inhibition (Vmax
  falls, Km holds). The two example queries naming oxamate are gone: BRENDA
  has no oxamate Ki for human LDH, so the resolver could not answer them.
  The 2026 entry below that says "oxamate" is kept as it was written.

## [0.3.1] - 2026-09-22

Nobody could tell what to type. The release worked and explained nothing,
which is a product nobody adopts.

### Added
- **`docs/USING_CATERVA.md`**, the user's guide: the one rule that explains
  most refusals (it recognises a *shape*, never a *subject*), what to type
  in the first three minutes, how to read a report section by section, and
  a recipe for each question a lab actually asks -- which step matters
  (`--screen`), what to measure next (`--design`), does the conclusion
  survive not knowing the constants (`--robustness`), is it physically
  possible in and out (`--scale`, `--predictions`). Every command in it was
  executed before it was written down.
- **`caterva/tests/test_using_caterva_guide.py`** pins the guide to the
  code: every flag it names must exist in the parser, every shape must be
  recognised by the grammar, every export format must be offered, every
  `sim` subcommand must exist, and the stated mechanism count must equal
  the grammar's. Verified by mutation: a renamed flag, a misspelt shape, a
  withdrawn export format and a stale count each fail it.

### Changed
- **`caterva` with no arguments is now the first lesson**, not a six-line
  usage: three commands worth typing in order, the shape-versus-subject
  rule, the flags that answer real questions, and the exit codes. The
  mechanism count in it is read from the grammar, so the message cannot
  claim a number the builder does not have.
- **The app folder's `README.txt`** carries the same quick start, because
  somebody who downloads a folder has no repository to read.
- README, `START_HERE.md`, the docs index and the v0.3.0 release notes
  point at the guide.

## [Unreleased]

Caterva narrows to enzymes: kinetics, structure and dynamics.

### Added
- **`caterva structure`**: an enzyme's PDB entries, grouped by UniProt
  protein (an EC number in one organism is often several proteins, and the
  command refuses to pick between them), ranked by the ligand asked for,
  method and resolution, with ligands, cofactors, metals and
  crystallisation additives kept apart, and each entry cited by its paper
  or, when unpublished, by its own DOI. `--chimerax` writes a script.
- **`caterva md`**: a GROMACS setup (mdp files, `run.sh`,
  `PROVENANCE.md`) in which every setting is measured, chosen or cited;
  with `--subject/--organism/--substrate` the temperature and pH come from
  the assay behind a cited kinetic constant. Run end to end with GROMACS
  2021 on LDHA (held 310.2 K for a measured 37 C); a CI job runs every
  stage on lysozyme.
- `caterva/methods.py`: the eleven method citations those outputs rest on,
  each DOI checked against Crossref.
- **`caterva prepare`**: a structure-preparation audit. Reads a PDB entry's
  mmCIF records and reports sequence differences from UniProt (whatever
  the depositors call them: 1L63's C54T/C97A are labelled 'conflict'),
  chain breaks, truncated side chains, alternate conformations,
  non-standard residues, the biological assembly and model quality, each
  ranked by distance to the catalytic residues. Those come from a cited
  M-CSA snapshot carried onto each chain by alignment, with the reference,
  its identity and the rejected candidates named. On 1I10 it finds LDH-A's
  catalytic Arg105 truncated in chain D and unmodelled in chain G, and
  recommends chains A or C. No new dependencies.
- **`caterva md` runs three replicas by default** from one minimised system,
  differing only in velocity seeds (all recorded), and **`caterva md
  --summarise DIR`** reports each replica's block-averaged error
  (Flyvbjerg & Petersen 1989), its effective sample count, and whether the
  replicas agree: consistent, replicas disagree, unconverged, or one sample.
  Exit 4 unless consistent.
- **`caterva analyze`**: in every replica, the distance between the
  functional groups of each pair of catalytic residues (M-CSA, mapped by
  `caterva prepare`) against the crystal, and the active-site pocket's RMSF
  against the rest of the protein; each called held/moved or rigid/mobile
  only when the replicas agree. Measured by `gmx distance` and `gmx rmsf`,
  with the commands written to analyze.sh.
- `docs/design/MD_ROADMAP.md`: what the dynamics side will add
  (structure-preparation audit, replicas by default, enzyme-specific
  analysis, ligand provenance, simulation beside measured Ki), and why each
  is better than running the engines by hand.

### Removed (archived)
- SIR/SEIR epidemiology, PCR, Monte Carlo π, population genetics
  (Wright-Fisher, two-locus), the Lennard-Jones cluster MD and the three ODE
  oscillators moved to `archive/legacy_domains/` with their tests. The
  engine, the API runner, the root CLI and the website no longer offer
  them. A query for one is refused with a message naming the archive,
  never answered with an enzyme simulation; v0.4.0 still runs them.
- `caterva sim` keeps only `ssa`.

### Changed
- The website's hero widget and example gallery show human LDH-A with and
  without oxamate, from recorded BRENDA constants (Km 0.03 mM, ref 286469;
  Ki 0.00059 mM, ref 739793), in place of an SIR outbreak with drifting
  parameters.

### Fixed
- The TypeScript record store resolved its directory through
  `os.homedir()`, and the jest suites' temporary `HOME` did not reach it, so
  test runs wrote thousands of records into the real `~/.terrium/records`.
  It now reads `HOME` first, and still loads records left in the old
  location.

## [0.4.0] - 2026-09-27

**Terrium is now Caterva.** Notes: `docs/releases/v0.4.0.md`.

### Changed
- **The name, everywhere.** Product, repository (`math12345678/caterva`),
  command (`caterva`), Python package (`caterva`, was `Terium`), download
  filenames, environment variables (`TERRIUM_*` to `CATERVA_*`) and the
  website. New logo: a C of eleven dots with a serif wordmark, in ink
  (`#1D201A`) on paper (`#F2EFE5`); see `docs/brand/`. The
  `terrium` command is kept as an alias. Entries below this one were passed
  through the same rename, so older command names read as `caterva`.
- **The engine command is `caterva-sim`** (was `terium`); `caterva sim` is
  the same thing.

### Removed
- **`Business/`, the pitch deck and seven confidential documents, from the
  repository and its whole history**, before it went public.

### Fixed
- The README quick start `cd main` after cloning `caterva`.
- The website credited a nonexistent "Terium" project at a nonexistent
  address; links pointed at domains that never existed.
- A tracked `.coverage` database, already listed in `.gitignore`.

## [0.3.4] - 2026-09-24

The first clean-checkout run of 0.3.3 read like a demo: a sourced model's
verdict said no search had run, and plain Michaelis-Menten was refused.

### Fixed
- **The bare `caterva` screen said sourced constants were "not wired
  yet"**, false since 0.3.3; it now shows the command. `compose --help`
  leads with a `--subject` example, and every help example is tested.
- **Naming the inhibited step did nothing** despite the note promising
  it. `feedback_inhibition` now wires the end product to the named step.
  `caterva/tests/test_feedback_inhibition_named_step.py`.
- The guide said twelve scenario presets; there are thirteen (now tested).
- **`"3 step phosphorylation cascade"` crashed** (any description
  starting with a digit gave an invalid model name).
- **The Hill-function trigger matched "uphill" and "downhill".**
- **The verdict read only one kind of provenance.** A model sourced by the
  literature search was graded STRUCTURAL with "none has been run", above
  a table of BRENDA citations. It now reads the search's results; a fully
  sourced model is GROUNDED. The behaviour caveat's count was wrong for
  the same reason. `caterva/tests/test_verdict_after_search.py`, which fails
  without the fix.
- **A withheld constant named an option that does not exist.** It now says
  to re-run with `--organism` set to an organism that has a measurement.

### Added
- **Every shape builds from its own `--shapes` description** (21 of 36 did
  not), and every example in the usage message and the guide builds.
  `caterva/tests/test_every_shape_builds_from_its_own_words.py`.
- **`--organism` reads common names and lower case** (`human`, `yeast`,
  `homo sapiens`) and says how it read them; `make cite` does the same.
  `caterva/compose/organisms.py`.
- **A misspelt substrate lists what BRENDA holds**; an unknown or
  incomplete EC number says so and exits 3; the verdict's remedy is the
  reason the search could not run.
- With no `--organism`, the report names the organism the search chose.

- **Plain Michaelis-Menten**, the `michaelis_menten` rule, at priority 45
  so every enzyme shape with more structure still wins.
  `caterva/tests/test_grammar_michaelis_menten.py`. The composer now builds
  12 of the twenty coverage questions, not 11.
- **"Try it on your own enzyme"** in `docs/OWNER_CHECKLIST.md`, with four
  enzymes run unscripted.

## [0.3.3] - 2026-09-22

The product's central claim -- every number traces to its source -- was
true of the code and unreachable from anything a person types.

### Fixed
- **A refused literature search exited 0.** This CLI's contract, in its own
  `--help`, is "0 produced everything asked for ... 3 something refused and
  said why (the report is still printed)". `--subject "lactate
  dehydrogenase"` asks for a search, the resolver refuses because that name
  is six different enzymes, and the report said so in prose while the
  process exited 0 — a script could not tell the search never ran. A search
  that could not be RUN (ambiguous name, missing `--substrate`, no
  literature layer, a crash) is now a refusal and exits 3; a search that
  ran and found nothing is an answer and exits 0, the answer being in the
  provenance table.

### Added
- **`caterva` is the command everywhere.** The wheel installs it beside
  `caterva` and `caterva-compose`, and `make setup` now installs the package
  itself, so in a checkout `caterva compose ...` works from any directory
  instead of `./.venv/bin/python -m caterva.app compose ...` from the root.
- **`make doctor` detects the macOS + iCloud failure** that makes it
  vanish. Python 3.13 skips `.pth` files carrying the macOS `hidden` flag,
  and iCloud Drive sets that flag on files inside `.venv` when the checkout
  is under `~/Desktop` or `~/Documents`. Measured on the owner's machine:
  `caterva --version` worked right after install and minutes later failed
  with `No module named 'caterva'` from the same interpreter. Nothing in that
  error points at iCloud, so the doctor names it and gives the fix.
- **`docs/OWNER_CHECKLIST.md`**: the owner's remaining steps, copy and
  paste, each with what you should see and what to do if you don't.
- **A placeholder now says what the search actually met.** The resolver
  distinguishes four outcomes and the report printed one invented sentence,
  "searched the km table and found nothing", for all of them -- which is
  not a summary but FALSE for two: the value may exist in other organisms
  and not have been substituted (ADR 0024: offered, never substituted), or
  papers may have been found with no number extractable from their free
  text. Measured live on EC 3.1.1.7 in *Homo sapiens*: kcat is "available
  in: Cimex lectularius, Drosophila melanogaster, Macroptilium
  atropurpureum, Mus musculus" and Ki is "candidate papers were found but a
  number was not extracted". Both had been reported as nothing found,
  sending a reader to stop looking for a number that is in the database.
  The summary sentence underneath no longer says "looked for and not
  found", which contradicted the table it sat under. `<input>`, the
  blackboard's label for a constraint the caller raised, is translated to
  "your own request" at the edge rather than leaking into a page a
  researcher is reading.
- **A composed model reports the conditions its values were measured
  under, and whether they can be mixed.** pH, temperature and buffer decide
  whether two constants belong in one model; `Measurement` has carried
  them since it was written and the CSV printed them, while the report a
  person actually reads did not. It now lists them per constant, names any
  source that stated none ("a fact about the paper, not a gap in the
  search"), and compares the ones that can be compared against
  `model_compatibility`'s own thresholds (1 pH unit, 10 °C), saying
  plainly when a model would describe an experiment nobody ran. With one
  constant it makes no comparison claim, because a reassurance about
  nothing reads like a check that passed.
- **A composed model reports what the evidence did not settle.** Where the
  resolver ranked more than one row equal, the report names the spread
  instead of presenting the pick as the answer: for EC 1.1.1.27 and
  pyruvate, *"2 sources report 2 values (BRENDA ref 286442, 286469),
  spanning 0.03 to 0.398 mM (13.3-fold). The model carries 0.03 — the
  resolver's pick, not a verdict"*. The rows were being dropped at the
  `Measurement` boundary, so a 13-fold disagreement arrived downstream as
  one confident cited number, which looks more settled than a placeholder
  rather than less. It distinguishes several papers disagreeing from one
  paper reporting several rows, because sending a reader to one paper to
  adjudicate itself is not advice. The lab-report path has printed this
  since it was written; this is the composed model catching up.
- **`compose` searches the literature.**
  `caterva compose "..." --subject 1.1.1.27 --organism "Homo sapiens"
  --substrate pyruvate` returns a model whose constants are BRENDA's, each
  with its reference, and every section below -- stability, the influence
  ranking, the time course, the verdict -- runs on those numbers. The
  exports carry them too, so an SBML file and the report beside it cannot
  disagree. A partial result stays partial: constants the search did not
  find keep the motif library's placeholder and are listed as
  *searched and not found*, which is a different fact from *not looked
  for*. Four pieces (ADR 0178): `caterva/checkout.py` makes the literature
  layer importable outside pytest; `ComposedModel` carries `organism` and
  `substrate` and fills the `ec_number`, `substrate` and `organism` fields
  BRENDA requires; `with_measured()` substitutes through
  `export.provenance_of`, the one place that decides an origin; and the
  CLI runs the search before the analyses, turning every failure into a
  note on the report rather than an error instead of it.
- **`scripts/cite.py` and `make cite`: real constants with real
  citations**, in one command.
  `make cite EC=1.1.1.27 SUBSTRATE=pyruvate ORGANISM="Homo sapiens"`
  returns `km = 0.03 mM` from `BRENDA ref 286469`, the papers that
  disagree and by how much, the conditions the value was measured under,
  and `--` for anything nothing measured. `--fixture` keeps the offline
  route. It re-implements none of the resolution, ranking or rendering:
  it builds `report_lab.py`'s payload and hands it over. Verified live on
  three enzymes (ADR 0178).
- **ADR 0178**, recording why it was unreachable: `compose --subject`
  never called `compose_and_parameterise`; that function failed every
  scout with `ModuleNotFoundError: fallback_logic` **while reporting
  `converged=True`**; with the path repaired it failed again because
  `parameter_requests()` never filled the `ec_number`, `substrate` and
  `organism` fields BRENDA requires; and the working entry point read a
  six-key JSON payload on stdin. The ADR lists the four things that would
  let `compose` search, and the guide says plainly that it does not.

### Fixed
- **Every BRENDA citation was being degraded to a bare enzyme-page URL.**
  `citation_text` looked for an attribute called `reference`; `Citation`
  declares `reference_id`. The attribute never existed, so every citation
  fell through to `url` and two measurements from two different papers
  produced the identical string. The same model's two constants now cite
  `BRENDA ref 286469` and `BRENDA ref 739793` -- different papers, as they
  always were. BRENDA has no working per-reference deep link, so the
  reference id was the only thing identifying which row a number came
  from, and it was the one field being dropped.
- **The verdict recommended a ranking it had just called worthless.** On a
  saturated model -- a three-step cascade at the library's placeholder
  values sits at 99.99% phosphorylated, so every sensitivity falls below
  the threshold -- the provenance section said "No constant here clears
  |S| = 0.01" while the one line labelled "Do this next" said "start with
  the top of its influence ranking". The remedy was a fixed string that
  never read the ranking. It now reads it, and says so when nothing is
  singled out. This is the defect `_settling_ranking` was written for
  (a ranking zeroed by a conservation law) in its other form.

## [0.3.0] - 2026-09-21

The first release that reaches GitHub's Releases page, and the first that
is downloadable as an app. v0.2.0 built and verified a wheel; the Release
itself needed a token the machine did not have, so the tag sat on the
remote with nothing attached. From this version a pushed tag is published
by a workflow with the run's own token, after it has rebuilt, reinstalled
and run everything it is about to attach (ADR 0177).

### Added
- **A release workflow.** `.github/workflows/release.yml`: on a `v*` tag
  (or by hand for an existing tag), builds the wheel and sdist, rebuilds
  them independently and fails if the checksums differ, installs the wheel
  into a fresh interpreter on Linux, macOS and Windows at Python 3.10 and
  3.13 and runs `caterva-compose` to a `VERDICT:` from an empty directory,
  freezes the app folders, and only then creates the Release with the
  notes, every artifact and one `SHA256SUMS`.
- **A downloadable app folder per platform** (`caterva-<version>-<os>-
  <arch>.tar.gz` / `.zip`, Linux x86_64, macOS arm64, Windows x86_64):
  one executable, `caterva`, with `caterva compose "..."` and
  `caterva sim ...`. No Python, no install. Built from the released wheel
  by `scripts/build_app.py`, which refuses the folder unless python-
  libsbml's extension is a separate replaceable file, every conveyed
  component's licence is inside, and the frozen binary runs from an empty
  directory. libSBML is in the folder three times (python-libsbml's copy
  and the copies libroadrunner and Antimony compile in); the script finds
  and lists them, and the release page carries the corresponding source
  of every version, and of the two libraries, beside the folders.
- **`caterva`, a single entry point.** `caterva/app.py` dispatches to the
  two existing commands unchanged (`python -m caterva.app` from the wheel;
  the executable in the folder). 83 modules in the wheel, up from 82.
- **`third_party_licenses/LGPL-2.1.txt`.** The LGPL text python-libsbml's
  wheel refers to but does not carry; the app folder ships it.
- **`requirements-release.txt`** pins PyInstaller for the release workflow
  only, with its licence (GPL-2.0-or-later WITH Bootloader-exception)
  recorded in the dependency-licence guard.

### Changed
- **Both artifacts are byte-reproducible from the commit.** The sdist is
  normalised after the build (sorted members, epoch mtimes, gzip mtime 0);
  0.2.0's notes said the wheel was and the sdist was not. Measured:
  identical `SHA256SUMS` from two independent checkouts of the tag.
- **NOTICE now states the licence position artifact by artifact.** The
  wheel and sdist name libSBML and do not convey it; the app folder does,
  and the section says how each LGPL-2.1 obligation is met (notice, and a
  separate replaceable file). The sentence "this repository has exactly
  one CI workflow and it publishes nothing" was true from 2026-08-15 to
  2026-09-19 and is replaced with that history. `docs/LICENSING.md` and the
  dependency-licence guard no longer say replacement is "a pip install
  away" without qualification.
- `SECURITY.md` names which versions receive fixes; it said there were no
  released builds.

### Fixed
- **`caterva-compose --export sbml` and `--export antimony` crashed from
  every installed copy of 0.2.0** with `FileNotFoundError`: two files the
  engine reads at import, `docs/data-sources.json` and
  `Tests/fixtures/identifiers/identifiers_org_namespaces.json`, were
  resolved relative to the checkout and shipped in neither the wheel nor
  the sdist. Copies now live in `caterva/core/data/`; the loaders read the
  checkout's original when it exists and the packaged copy otherwise, and
  `caterva/tests/test_packaged_data.py` fails if a copy and its original
  ever differ. Proved from an installed wheel in an empty directory. The
  0.2.0 notes' "Known limits" did not record this; it was found by reading
  every `Path(__file__)` in the package for the app folder.
- `CHANGELOG.md` carried a duplicated, truncated block (a second correction
  banner and a stale `[0.1.0] - 2026-09-19` section) introduced by the
  0.2.0 commit's edit anchoring on the wrong `## Unreleased`. Removed.

### Known limits, stated
- **Not on PyPI.** A separate decision; the name has not been checked.
- **Not signed.** The macOS and Windows folders carry no code signature;
  each folder's `README.txt` says what the operating system asks on first
  run. Signing needs certificates the repository does not hold.
- **No Intel-Mac folder.** Intel Mac users install the wheel.
- **The repository is still private**, so the Release is visible to
  collaborators. Going public is blocked by owner decisions listed in
  `docs/status/2026-09-21.md`, not by anything in this release.
- **The freeze could not be run where this was written** (no PyPI in the
  sandbox). The workflow's first run is the first real freeze; it verifies
  the folder by running it, and publishes nothing if that fails.

## [0.2.0] - 2026-09-19

The first release with built artifacts. A source distribution, a
pure-Python wheel, and two installed commands. 0.1.0 (below) was a tag and
a source archive; this is the version you can `pip install`. Everything
under the `Unreleased` heading further down was already in the tree; this
entry records what makes 0.2.0 an installable release rather than a
checkout.

### Added
- **Installable package.** `pip install caterva-0.2.0-py3-none-any.whl`
  installs `caterva` (engine, composer, agents; 82 modules) with pinned
  dependencies. Verified by installing the wheel into an empty directory
  and building a model from there with nothing of the repository on the
  path.
- **Two commands.** `caterva` (the simulation engine: `wf`, `kimura`, `ne`,
  `sweep`, `scenarios`, `ld`, `ssa`) and `caterva-compose` (the model
  builder and its analyses). Before this the composer was reachable only
  as `python -m caterva.compose` from a checkout.
- **A version.** `caterva.__version__` is the single source; `pyproject.toml`
  reads it, and `CITATION.cff` and `package.json` are kept equal to it.
  `caterva-compose` and the package metadata cannot disagree.
- **`scripts/build_release.py`.** Builds the sdist, then the wheel from
  the extracted sdist, checks the wheel against what the release notes
  claim (no tests, no conftest, LICENSE and NOTICE inside, every module
  under `caterva/`), and writes `SHA256SUMS`. With `SOURCE_DATE_EPOCH`
  pinned to the tagged commit the wheel is byte-reproducible; the sdist is
  content-identical but not byte-identical (setuptools writes fresh
  mtimes into `PKG-INFO`), and the script says so rather than hiding it.
- **A conveyance section in NOTICE** stating what the artifacts do and do
  not distribute: Caterva's own code only; python-libsbml (LGPL-2.1) is
  named as a dependency and not bundled, so its conveyance obligations do
  not attach. (This is also why there is no frozen desktop bundle in this
  release: PR #21's onefile DMG froze libSBML in, and that changes the
  obligations. See NOTICE.)

### Fixed
- **Packaging built nothing.** Setuptools' flat-layout discovery saw
  `caterva/` beside `Tests/`, `Business/`, `node_modules/` and a dozen more,
  and an editable install registered `dist-info` and no code: `import
  Caterva` failed from any directory but the repository root. Packages are
  now named explicitly. The sdist also swept the whole `Tests/` tree in
  through a case-folded `tests/` glob; a `MANIFEST.in` prunes it.
- **A wheel built straight from the tree carried `caterva/conftest.py`.**
  `MANIFEST.in` governs the sdist and `exclude-package-data` governs data
  files; neither excludes a module from a wheel built directly. Building
  the wheel from the sdist does, which is what the build script enforces.
- **ADR 0176's mutation table had no set file.** Seven mutations across
  four files, run through `scripts/mutate.py`, all caught.
- Everything under `Unreleased` below, which this release ships.

### Known limits, stated
- **Literature search needs the source checkout.** `caterva.agents` reaches
  into `Tests/` (the BRENDA resolvers) lazily; those modules are not part
  of the package. From the wheel, `caterva-compose ... --subject <enzyme>`
  builds the model and the verdict page says, correctly, that no search
  was run. Running the search means cloning the repository.
- **The api-server and landing site are not in this release.** They are
  TypeScript, deploy separately, and their test suite could not be run in
  the environment this release was built in (port binding is sandboxed).
  They are unversioned until they can be verified.
- **0.2.0, not 1.0.0.** The public API has not been frozen and the
  composer's library is eleven mechanisms. The number says "usable,
  changing," which is true.

## [0.1.0] - 2026-08-29

Tagged and released as a source archive only, deliberately: the licence
position rested on distributing nothing that contains libSBML, and a
source archive contains none. `pyproject.toml` said 0.1.0 but its
packaging built an empty install (see 0.2.0, Fixed), so this version was
never `pip install`-able. The record of the release and its measured
figures is in `docs/EXPERT_FEEDBACK.md` ("Seventy-ninth pass").

## Unreleased

### Added
- **ADR 0012**: kcat is resolved from literature but is not a simulation parameter.
- **ADR 0013**: Enzyme concentration bridges kcat to Vmax (Vmax = kcat * [E]0).
- **ADR 0014**: Python 3.10-3.12 support window documented with the correct
  constraint (libroadrunner + numpy, not libSBML).
- **ADR 0015**: A constitution rule that nothing executes is not enforced —
  adding caterva to requirements.txt passed every guard.
- **ADR 0016**: Cached results lose per-parameter provenance — schema column,
  persistence, cache read, and serialisation guard all implemented.
- 11 guard scripts with automated wiring check (`check_guard_wiring.py`).
- Documented-counts guard (`check_documented_counts.py`) that fails if README
  test/domain counts don't match the repository.
- Python support claim guard (`check_python_support_claim.py`) across all
  files that state the version window.
- Constitution Rules 7+8 guard (`check_forbidden_packages.py`) — forbids the
  tellurium umbrella package and verifies every ADR is indexed.
- **Eleventh simulation domain**: Michaelis-Menten with competitive
  inhibition (`v = Vmax·S / (Km·(1+I/Ki) + S)`), verified against the
  apparent-Km closed form `Km_app = Km·(1 + I/Ki)` and against plain MM
  exactly at I=0. Reachable end-to-end (engine, API dispatch, TS schema).
- **Python 3.13 support** (ADR 0014 follow-through): `numpy` and
  `libroadrunner` bumped to publish cp310-cp313 wheels, verified against
  PyPI with `--online`, not assumed from the pin bump alone.

### Changed
- Engine test suite: 715 -> 883 tests (Gillespie SSA, SSA bimolecular,
  SSA replicates, two-locus WF, competitive-inhibition MM).
- Literature test suite: 182 -> 214 tests.
- TypeScript test suite: 111 -> 224 tests (16 files).
- README Layout section now lists all six top-level directories.
- README domain count: ten -> eleven, kept consistent across both
  places it's stated (guarded by `check_documented_counts.py`).

### Fixed
- ADR 0016: parameter provenance now survives cache hits (was silently
  returning {} on every cached result).
- ADR 0014: the documented reason for the Python version constraint corrected
  in README, CONTRIBUTING, and requirements.txt.
- Rule 8: ADR indexing verified automatically; two unindexed ADRs found and
  fixed during guard development.
- README.md Layout and scripts/README.md stale counts corrected.
- Two real environment bugs: `pipeline.ts`'s and `scienceAgent.ts`'s health
  check / literature bridge both hardcoded `spawn("python3", ...)` instead
  of resolving the actual configured interpreter — silently wrong on any
  machine where the venv Python isn't literally named `python3` on PATH.
- A false capability claim: `RESOLVABLE_FIELDS` said the new domain's `ki`
  is resolved from BRENDA; nothing populates it, so it always silently fell
  back to a default. Narrowed the claim rather than fake a lookup path —
  same precedent as ADR 0012 excluding kcat.
- The parameter-provenance fix and the competitive-inhibition domain were
  both originally built on a branch that turned out to be 92 commits behind
  main; ported the real diffs onto current main by hand after the naive
  cherry-pick failed outright.

## 2026-07-25

### Added
- PCR amplification as a third live simulation domain: exact closed-form
  exponential growth, optional discrete-logistic plateau mode, validation
  with an `ok`/`flagged` distinction consistent with the rest of the engine.
  32 new tests, mutation-verified.
- Sandbox: `Dockerfile` + `.devcontainer/devcontainer.json` for a one-command
  reproducible environment.
- `Business/` scaffolding: incorporation checklist, cap table placeholder,
  fundraising tracker, roadmap.

## 2026-07-23

### Added
- Caterva simulation engine (`caterva_engine.py`): Michaelis-Menten
  enzyme kinetics and SIR/SEIR epidemiology, built on antimony/roadrunner
  rather than the full `tellurium` umbrella package.
- 258-test simulation-engine suite, verified against exact closed-form
  solutions, an independent solver (scipy), and property-based tests
  (Hypothesis) -- not just internal self-consistency.
- `requirements.txt` / `requirements-dev.txt`, `Makefile`, GitHub Actions CI,
  `scripts/check_env.py`, `README.md`.
- Investor pitch deck (`caterva_pitch_deck.pptx`).
- `tests/test_dependencies_declared.py`: automated guard that fails CI if
  any import isn't declared in `requirements*.txt`.

### Fixed
- `KM_PLAUSIBLE_MAX_MM` mismatch between the literature layer
  (`Tests/brenda_client.py`) and the simulation engine (1e4 vs 1e3) -- a
  real bug that would have let a Km value flagged as implausible upstream
  arrive as "confirmed" downstream. Pinned equal, with a regression test.
- CI dependency install failures: `libroadrunner==2.9.0` had no Python 3.10
  wheels (reverted to `2.7.0`), and `httpx`/`pydantic` were imported by
  `brenda_client.py` but never declared as dependencies.
- A broken git submodule reference: `Science-Agent-Pipeline` had been
  committed as a gitlink with no `.gitmodules`, which made GitHub Actions'
  checkout step fail outright. Untracked it; it's an independent repo.

## 2026-07-21 to 2026-07-22

### Added
- Initial BRENDA/KEGG/PubMed literature-scraping layer (`Tests/`), 124 tests.
- Verified project specification and planning documents (`Docw/`).
