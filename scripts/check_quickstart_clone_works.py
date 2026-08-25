#!/usr/bin/env python3
"""The first command a stranger runs actually works.

WHY THIS EXISTS
---------------
START_HERE.md opens with "You are in the right place whether you are an
intern joining the team or a stranger who found this on GitHub", and the
first command it gives is:

    git clone https://github.com/Terrium-sim/main.git

That repository is not readable anonymously. A stranger following the only
document they are asked to read gets a username prompt and stops, on line
one, having seen nothing. Behind that prompt sit 2,220 tests, 67 guards and
140 architecture decisions, none of which they will ever reach.

Every other guard in this directory protects a claim made *inside* the
product. This one protects the only claim that has to be true before any of
those matter: that the thing can be obtained.

HOW IT AVOIDS BEING THE BUG IT CHECKS FOR
-----------------------------------------
A network probe that reports "unreachable" cannot tell the difference
between "this repository is private" and "this machine has no network",
and reporting the first when it means the second would be the shape this
repository has now recorded seven times: a matcher narrower than the thing
it measures says "it is not there" when it means "I could not see".

So this guard probes **known-public controls first** -- repositories that
must be cloneable if anonymous GitHub access works at all. If a control
fails, the answer is NOT "the documented URL is broken". It is "this check
could not run", and the exit code is 3.

That is the same three-state discipline the rest of the project uses:
reachable / unreachable / could-not-check, never collapsing the third into
either of the first two.

WHAT IT CHECKS
--------------
Every `git clone <url>` in a contributor-facing document resolves for a user
with no credentials, tested exactly the way a stranger's shell would do it
(`git ls-remote`, `GIT_TERMINAL_PROMPT=0`, no interactive prompt possible).

WHAT IT DOES NOT CHECK
----------------------
That the clone then builds, or that the branch named exists in a usable
state. It answers one question -- "can a stranger get this at all" -- and
says so rather than implying it vouched for the quickstart.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

REPO_ROOT = Path(__file__).resolve().parent.parent

#: Documents a newcomer is actually pointed at. Not every markdown file:
#: a clone URL inside a historical record in Business/build-stages/ is a
#: description of what was true then, and rewriting those is forbidden.
PUBLISHED_DOCS = ("README.md", "START_HERE.md", "CONTRIBUTING.md")
PUBLISHED_DIRS = ("docs/readmes",)

CLONE = re.compile(r"git\s+clone\s+(?:--\S+\s+)*(https://github\.com/[^\s`'\")]+)")

#: The authenticated form: `gh repo clone Terrium-sim/main`.
#:
#: ADR 0143 wired this guard deliberately red, on the premise that the fix
#: "is not a code change and is not mine to make: the repository becomes
#: readable, or the quickstart points somewhere that is. On that day this
#: goes green with no edit."
#:
#: The owner has now decided the repositories stay private. That settles the
#: premise the other way, and a guard that CANNOT go green is not a signal --
#: it is a red light people learn to walk past, which is the thing ADR 0143
#: argued against when it refused to baseline itself.
#:
#: So the guard now knows there are two audiences, and asks the right
#: question of each rather than one question of both:
#:
#:   `git clone https://...`  promises anonymous access -> probed, as before.
#:   `gh repo clone owner/x`  requires credentials       -> must SAY so.
#:
#: The second is not a way out. Swapping the command silently would trade a
#: reader who hits a credential prompt for a reader who hits a credential
#: prompt with no warning, so a document using this form must carry the
#: access notice AND the decision behind it -- the sibling guard's rule, that
#: the cheapest way to pass should also be the correct one.
GH_CLONE = re.compile(r"gh\s+repo\s+clone\s+([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)")

#: Both required, in the same document. A bare marker is a guard you satisfy
#: by typing the marker.
ACCESS_SENTINEL = "**Private repository.**"
ACCESS_ADR_LINK = "0179-the-guard-that-could-not-go-green.md"

#: Must be cloneable by anyone. If these fail, the network is the problem.
#: Two, from different orgs, so one repository being renamed does not turn
#: this guard into a permanent "could not check".
CONTROLS = (
    "https://github.com/sys-bio/tellurium.git",
    "https://github.com/pnpm/pnpm.git",
)

#: Must NOT be cloneable. Proves the probe can return a negative at all --
#: without this, a probe that said CLONEABLE unconditionally would pass
#: every control and vouch for everything.
NEGATIVE_CONTROL = "https://github.com/sys-bio/this-repository-does-not-exist-9f3a.git"

TIMEOUT_S = 40


class Reference(NamedTuple):
    document: str
    url: str


def reachable_anonymously(url: str) -> bool | None:
    """True / False / None, where None means the probe itself failed.

    `GIT_TERMINAL_PROMPT=0` is what makes this honest: without it git blocks
    on a username prompt, and a guard that hangs is a guard that gets removed.

    IT WAS NOT ANONYMOUS
    --------------------
    Blocking the prompt is not the same as having no credentials. A developer
    machine with `gh auth login` has

        credential.https://github.com.helper = !gh auth git-credential

    and the helper answers without any prompt to block. Measured here:
    `git ls-remote https://github.com/Terrium-sim/main.git` returned 0, so
    this function reported that a **private** repository "resolves for a user
    with no credentials" -- the guard vouching for the exact promise it was
    written to protect, on the machine of the one person who could not
    discover the mistake by running it.

    CI has no credentials, so CI got the right answer and the disagreement
    was invisible: the check was correct precisely where nobody was looking
    at it. Found by sabotage -- putting an anonymous URL back into a document
    and expecting red, which is why the sabotage step exists.

    `-c credential.helper=` empties the helper list, and the per-host entry
    is cleared separately because a URL-scoped helper is not removed by
    resetting the generic one. Verified in both directions: the private
    repository now reports unreachable, and the public controls still report
    reachable, so the override is not simply breaking every request.

    Clearing config rather than the environment on purpose --
    `GIT_CONFIG_GLOBAL=/dev/null` was tried first and the repository still
    came back reachable, because the helper is not only reached through the
    global file.
    """
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_ASKPASS="", GCM_INTERACTIVE="never")
    try:
        done = subprocess.run(
            ["git",
             "-c", "credential.helper=",
             "-c", "credential.https://github.com.helper=",
             "ls-remote", url, "HEAD"],
            env=env,
            capture_output=True,
            timeout=TIMEOUT_S,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return None
    except FileNotFoundError:
        return None
    return done.returncode == 0


def _newcomer_docs() -> list[Path]:
    """The documents in scope, shared by both collectors.

    One list, not two: a second copy would drift, and this project's
    most-repeated defect is one fact stored twice with nothing comparing them.
    """
    paths = [REPO_ROOT / name for name in PUBLISHED_DOCS]
    for directory in PUBLISHED_DIRS:
        paths.extend(sorted((REPO_ROOT / directory).glob("*.md")))
    return [p for p in paths if p.is_file()]


def documented_clone_urls() -> list[Reference]:
    refs: list[Reference] = []
    seen: set[tuple[str, str]] = set()
    for path in _newcomer_docs():
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        rel = str(path.relative_to(REPO_ROOT))
        for match in CLONE.finditer(text):
            url = match.group(1)
            if not url.endswith(".git"):
                url = url.rstrip("/") + ".git"
            if (rel, url) not in seen:
                seen.add((rel, url))
                refs.append(Reference(rel, url))
    return refs


class AuthReference(NamedTuple):
    document: str
    repo: str
    has_sentinel: bool
    has_adr_link: bool

    @property
    def is_honest(self) -> bool:
        return self.has_sentinel and self.has_adr_link


def documented_authenticated_clones() -> list[AuthReference]:
    """`gh repo clone` references, and whether their document admits why.

    Reachability is deliberately NOT probed. Answering it needs credentials,
    and CI has none -- so a probe here would report "unreachable" for a
    repository that is merely unreachable BY THIS RUNNER, which is the
    narrower-matcher failure this guard's docstring exists to avoid. What can
    be checked without credentials is whether the document warns the reader,
    and that is what is checked. Stated rather than implied.
    """
    refs: list[AuthReference] = []
    seen: set[tuple[str, str]] = set()
    for path in _newcomer_docs():
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        rel = str(path.relative_to(REPO_ROOT))
        for match in GH_CLONE.finditer(text):
            repo = match.group(1)
            if (rel, repo) in seen:
                continue
            seen.add((rel, repo))
            refs.append(AuthReference(
                rel, repo,
                ACCESS_SENTINEL in text,
                ACCESS_ADR_LINK in text,
            ))
    return refs


def _selftest() -> int:
    """Prove the probe can say both yes and no.

    A probe that always answered one way would pass either the positive or
    the negative control and quietly vouch for everything else.
    """
    failures = 0

    for url in CONTROLS:
        got = reachable_anonymously(url)
        if got is True:
            print(f"  [ok] positive control cloneable: {url}")
        elif got is None:
            print(f"  [could not check] probe failed on {url} — network?")
            failures += 1
        else:
            print(f"  [SELFTEST FAILED] positive control NOT cloneable: {url}")
            failures += 1

    got = reachable_anonymously(NEGATIVE_CONTROL)
    if got is False:
        print("  [ok] negative control correctly reported unreachable")
    elif got is None:
        print("  [could not check] probe failed on the negative control")
        failures += 1
    else:
        print("  [SELFTEST FAILED] a repository that does not exist read as cloneable")
        failures += 1

    # The extractor, on text rather than on the tree, so a clean tree cannot
    # make this look like it passed by matching nothing.
    sample = "run `git clone https://github.com/o/r.git` then\n git clone https://github.com/a/b\n"
    found = {m.group(1) for m in CLONE.finditer(sample)}
    if len(found) == 2:
        print("  [ok] extractor found both clone URLs, with and without .git")
    else:
        print(f"  [SELFTEST FAILED] extractor found {len(found)} of 2 URLs: {found}")
        failures += 1

    if failures:
        print(f"\nSELFTEST FAILED: {failures} case(s).")
        return 1
    print("\nSelftest passed: the probe can return both answers.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    if args.selftest:
        return _selftest()

    # Controls FIRST. Everything below is only meaningful if these pass.
    for url in CONTROLS:
        if reachable_anonymously(url) is not True:
            print("Could not check: a known-public repository was unreachable.")
            print(f"  control: {url}")
            print()
            print("  This is 'could not check', NOT 'the documented URL is fine'")
            print("  and NOT 'the documented URL is broken'. Exiting 3.")
            return 3

    refs = documented_clone_urls()
    auth_refs = documented_authenticated_clones()

    if not refs and not auth_refs:
        print("No clone command found in any newcomer-facing document.")
        print("  Nothing checked — that is a finding of its own if the")
        print("  quickstart is supposed to have one. Exiting 3.")
        return 3

    # An authenticated command whose document does not admit it needs
    # credentials is WORSE than the anonymous one it replaced: the reader
    # still hits a prompt, and now nothing warned them. Checked first so
    # switching commands can never be the cheap way past this guard.
    silent = [r for r in auth_refs if not r.is_honest]
    if silent:
        print(f"\n`gh repo clone` with no access notice ({len(silent)}):\n")
        for ref in silent:
            missing = []
            if not ref.has_sentinel:
                missing.append(f'the sentinel {ACCESS_SENTINEL}')
            if not ref.has_adr_link:
                missing.append(f"a link to {ACCESS_ADR_LINK}")
            print(f"  {ref.document}")
            print(f"      gh repo clone {ref.repo}")
            print(f"      -> missing {' and '.join(missing)}.")
            print("         The reader still meets a credential prompt; now")
            print("         nothing told them to expect one.\n")
        print("  Both are required so the marker has to carry its reasoning.")
        return 1

    if auth_refs:
        print(f"Authenticated clone commands: {len(auth_refs)}, "
              f"all carrying the access notice.")
        print("  NOT checked: whether the repository is reachable. That needs")
        print("  credentials, which CI does not have — and a probe without")
        print("  them would report 'unreachable' when it meant 'I could not")
        print("  see', the failure this guard's controls exist to prevent.")
        print()

    if not refs:
        print("No anonymous `git clone` command remains to probe.")
        return 0

    broken = [r for r in refs if reachable_anonymously(r.url) is not True]

    print(f"Anonymous clone commands checked: {len(refs)} (controls passed)")
    if not broken:
        print("  every one resolves for a user with no credentials.")
        print()
        print("  NOT checked: whether the clone then builds. See the docstring.")
        return 0

    print(f"\nClone commands a stranger cannot run ({len(broken)}):\n")
    for ref in broken:
        print(f"  {ref.document}")
        print(f"      git clone {ref.url}")
        print("      -> prompts for a username and stops. Anyone without push")
        print("         access to this repository sees nothing at all.\n")
    print("  Fix: publish the repository, or point the quickstart at the")
    print("  location that is actually public. A quickstart whose first")
    print("  command fails is worse than no quickstart, because it is")
    print("  believed until it is run.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
