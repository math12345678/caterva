# ADR 0177: A release is a workflow, not a command; the app folder conveys libSBML and says so.

**Status:** Accepted

**Date:** 2026-09-21

**Relates to:** ADR 0061 (GPL out of the default install; the conveyance
reasoning this applies), ADR 0143 (the first command a stranger runs; the
repository is still private and this does not change that), ADR 0058
(stdpopsim opt-in; the app folder does not collect it). Supersedes the
position recorded in NOTICE on 2026-09-19 that "whether to ship a desktop
bundle is the owner's decision": the owner decided, and this is the shape
of the decision.

## Context

Two tags existed before this ADR and neither was a release in the sense a
user would recognise.

- **v0.1.0 (2026-08-29)** was a tag and GitHub's automatic source archive.
  `pyproject.toml` said 0.1.0, but its packaging built an empty install
  (setuptools' flat-layout discovery saw `caterva/` beside `Tests/`,
  `Business/` and `node_modules/` and registered `dist-info` and no code).
- **v0.2.0 (2026-09-19)** fixed the packaging, built a wheel and an sdist,
  verified both from an empty directory, and pushed the tag. The Release
  page itself needed a GitHub token; the machine that did the work had one
  the keyring reported invalid, so the tag reached the remote and the
  artifacts stayed in a gitignored `dist/`. `docs/status/2026-09-19.md`
  records it as open problem 1: "the one step of the release this pass
  could not perform."

Separately, **PR #21 ("first DMG release")** on the branch
`claude/caterva-orientation-setup-c1310b` had frozen `scripts/report_lab.py`
with `PyInstaller --onefile`, which packs python-libsbml's shared object
inside the executable, and shipped this repository's NOTICE, unchanged,
saying "Nothing here bundles libSBML", inside the artifact that bundled it.
It was reviewed and not merged (`docs/EXPERT_FEEDBACK.md`, seventy-ninth
pass). NOTICE then stated the compliant shape, "libSBML as a separate,
replaceable shared object (a onedir freeze, not onefile) and a paragraph
here saying so," and left the choice to the owner.

The owner's ask on 2026-09-21: a release on GitHub, downloadable as an app,
made available. Three facts constrain how:

1. The machine doing the work cannot create a GitHub Release (invalid
   token), cannot reach PyPI (the sandbox's proxy denies it, so PyInstaller
   cannot be installed to test a freeze locally), and cannot run node.
2. Every guard that scans workflows is known exactly (`check_release_artifacts`
   and `check_ci_toolchain` read every root workflow; the rest read
   `tests.yml` only), as is every guard that scans `scripts/*.py`.
3. Making the repository public is blocked by owner decisions the docs
   record as not made: the confidential `.docx` blobs are still in git
   history (`docs/REMOVE_CONFIDENTIAL_FROM_HISTORY.md`, "Status: not done"),
   `Business/` with a cap table and named investors is in the tree and
   `split_repos.sh` would publish it, and three repository names are in
   use (`docs/status/2026-09-19.md`, problem 2).

## Decision

**A pushed `v*` tag becomes a GitHub Release by a workflow, `release.yml`,
using the token GitHub issues to the run.** No person's credential is on
the path. The workflow:

1. checks that the tag names the version in `caterva/__init__.py` and that
   `docs/releases/<tag>.md` exists;
2. builds the wheel and sdist with `scripts/build_release.py`, which
   refuses a wheel carrying tests or lacking LICENSE/NOTICE, and now
   normalises the sdist so both artifacts are byte-reproducible from the
   commit (measured: identical SHA256SUMS across two independent checkouts
   of v0.2.0);
3. rebuilds them in a second job and fails the release if the checksums
   differ;
4. installs the wheel into a fresh interpreter on Linux, macOS and Windows
   at Python 3.10 and 3.13 and, from an empty directory with `caterva`
   imported from `site-packages`, integrates a time course (the line
   `Integrated to t=` must appear and `no time course` must not, because
   the report turns a failed simulation into a note and still exits 0),
   exports SBML (libsbml, lxml and the two data files now packaged under
   `caterva/core/data/`, without which `--export sbml` crashed from every
   installed copy of 0.2.0), and builds a shape from an expansion library
   (reached only through `importlib`, invisible to static analysis);
5. freezes the INSTALLED wheel into a one-folder app per platform with
   `scripts/build_app.py`, which refuses the folder unless libSBML's
   extension is a separate file, every conveyed component's licence is
   inside, and the frozen binary passes the same three checks plus
   `--version` and `sim --help` from an empty directory;
6. only then creates the Release with the notes file, every artifact, and
   one `SHA256SUMS`.

A tag with a suffix (`v0.3.0-rc.1`) runs the same pipeline and publishes a
**pre-release**. That is how a version is cut: the candidate first, and the
plain tag on the same commit once the candidate's run is green. A first
freeze that fails then costs a candidate number, never a broken final tag.

**The app folder is ONEDIR, one executable, `caterva`.** `caterva/app.py`
dispatches `caterva compose ...` and `caterva sim ...` to the two existing
`main(argv)` functions unchanged, so the bundle's surface cannot drift from
the wheel's and the dispatch is tested from a checkout, where the freeze
itself cannot be. The folder conveys libSBML three times, not once:
python-libsbml's extension, and copies statically linked into
libroadrunner's `_roadrunner` and Antimony's `libantimony` by their
upstream projects (5.21.1, 5.20.4, 5.20.2 on the build machine; found by
scanning the binaries, which `build_app.py` now does on every build and
writes into README.txt). NOTICE says so in a section that distinguishes
the three artifacts and states how each LGPL obligation is met: notice
(README.txt, libSBML's own terms, and the LGPL text, which
`third_party_licenses/LGPL-2.1.txt` supplies because the python-libsbml
wheel refers to it without carrying it), and source: because only one of
the three copies is separately replaceable, and because the folder is
what puts even that copy on the recipient's machine, the project does not
rest on §6(b)'s "shared library mechanism"; the release workflow attaches
the corresponding source of every libSBML version the folders report and
of libroadrunner and Antimony to the release page beside the folders
(§4, §6(d)), and refuses to publish if a fetch fails. NOTICE names the two
questions that remain for counsel. The folder also carries
libRoadRunner's Apache-2.0 files, an MIT notice for Antimony (whose wheel
ships none), NumPy's and SciPy's BSD notices, CPython's licence, and
PyInstaller's COPYING.txt with the Bootloader Exception.

**PyInstaller is pinned in `requirements-release.txt`**, which only the
release workflow installs, with a `PERMISSION` entry recording its licence
and the exception, and the file is added to `check_pins_resolve.py`'s
list so the pin is resolved against PyPI like every other.

**Version 0.3.0**, a minor bump: what is added is a distribution channel
and an app folder, not a change to the science.

## What was not done, and why

- **No PyPI upload.** A separate, unmade decision; the name `caterva` has
  not been checked for availability. NOTICE says so.
- **No code signing or notarisation.** Needs an Apple Developer ID and a
  Windows certificate the repository does not hold; the folder's README.txt
  tells a user what the operating system will say and what to do. Getting
  the certificates is the owner's; wiring them into the workflow as secrets
  is a small follow-up once they exist.
- **No Intel-Mac folder.** The runner label for Intel macOS could not be
  verified from here; Intel Mac users install the wheel. Adding a matrix
  row is one line once the label is confirmed.
- **The repository stays private.** "Made available" to the public is
  blocked by the three owner decisions above, none of which a workflow can
  make. `docs/status/2026-09-21.md` lists them in order.
- **The freeze was not run on this machine.** PyPI is unreachable from the
  sandbox, so `scripts/build_app.py` was exercised only through its helper
  functions (licence discovery, platform tag, the installed-wheel refusal)
  and through `python -m caterva.app` end to end. The first real freeze is
  the workflow's first run; that is why the workflow verifies the folder
  by running it rather than trusting the build, and why v0.3.0 is
  published by the workflow rather than by hand.

## Consequences

- A tag is now a promise CI keeps or refuses: it cannot half-publish. If
  the app job fails on a platform, nothing is published and the tag can be
  re-run with `workflow_dispatch` after the fix, or the release built and
  verified without publishing (`publish: false`).
- NOTICE's sentence "this repository has exactly one CI workflow and it
  publishes nothing" is false and has been replaced with the dated history;
  ADR 0061's copy of it stays as written, being a record.
- `check_release_artifacts.py` now finds a publish marker and prints its
  reminder that a green guard "cannot verify the obligations are MET". The
  artifact-level verification that guard says it cannot do is what
  `scripts/build_app.py` does, on the artifact, before the archive exists.
- `scripts/check_dependency_licenses.py`'s description of python-libsbml
  and `docs/LICENSING.md` no longer say replacement is "a pip install
  away" unconditionally; they say it for the wheel and describe the file
  swap for the folder.
- Guard count unchanged (no new `check_*.py`). ADR count 174 → 175.
