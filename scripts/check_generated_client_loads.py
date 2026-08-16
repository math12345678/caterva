#!/usr/bin/env python3
"""Guard: generated zod syntax must match the zod that is actually installed.

WHY THIS EXISTS
---------------
`pnpm --filter @workspace/api-spec run codegen` -- the documented command --
produced a contract that **threw on import**, and every other check in the
repository passed.

The mechanism, because it is the interesting part:

  * orval's `override.zod.version` defaults to `"auto"`, which inspects the
    installed zod.
  * zod 3.25 ships a `zod/v4` SUBPATH. Detection saw v4 capability and
    emitted v4 syntax -- `zod.iso.datetime(...)`.
  * The generated import is plain `"zod"`, where `iso` is `undefined`.

So the generated file was syntactically valid TypeScript that type-checked
cleanly and would crash the moment anything parsed a request.

**`tsc --noEmit` cannot see this.** `zod.iso` is present in zod 3.25's TYPE
declarations even though it is absent from the default export at RUNTIME.
That gap between the declared and the actual surface is the whole defect,
and it is why a type-checker was never going to catch it.

The only reason nobody hit it is that the committed files predated the zod
bump and nobody had regenerated. ADR 0027 recorded the difference as
formatting-level drift, which understated it; ADR 0030 corrects that.

WHAT THIS CHECKS
----------------
Three things, cheaply and without a build:

  1. The zod major pinned in orval.config.ts matches the installed zod major.
  2. The generated schema contains no v4-only syntax while zod is v3.
  3. The runtime surface agrees -- `zod.iso` is actually undefined on v3.

(3) is the one that makes the other two more than bookkeeping. It asks the
installed package what it can do rather than trusting its version string.

RUNTIME PARSING IS COVERED ELSEWHERE, ON PURPOSE
------------------------------------------------
`schemas.test.ts` and `physiologicalReferenceRoute.test.ts` import
`RunSimulationBody` and parse with it, so a contract that fails to load
fails those. This guard deliberately does NOT duplicate that: it catches the
configuration drift that would cause it, at a point where the message can
name the cause instead of showing a TypeError.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PIPELINE = REPO_ROOT / "Science-Agent-Pipeline"
ORVAL_CONFIG = PIPELINE / "lib" / "api-spec" / "orval.config.ts"
GENERATED_ZOD = PIPELINE / "lib" / "api-zod" / "src" / "generated" / "api.ts"

#: Syntax orval emits only when it believes zod 4 is available. Each entry is
#: (pattern, what it needs). Extend when a new v4-only form is adopted.
V4_ONLY = [
    (re.compile(r"\bzod\.iso\."), "zod.iso.* (v4)"),
    (re.compile(r"\bz\.iso\."), "z.iso.* (v4)"),
]

_VERSION_IN_CONFIG = re.compile(r"\bversion:\s*(\d+)")


def installed_zod() -> tuple[str, bool] | None:
    """`(version, has_iso)` for the zod the workspace resolves, or None."""
    probe = (
        "const p=require('zod/package.json');"
        "const z=require('zod');"
        "console.log(JSON.stringify({version:p.version,hasIso:typeof z.iso!=='undefined'}))"
    )
    for cwd in (PIPELINE / "lib" / "api-zod", PIPELINE):
        try:
            result = subprocess.run(
                ["node", "-e", probe],
                capture_output=True, text=True, cwd=str(cwd), timeout=60,
            )
        except (subprocess.TimeoutExpired, OSError):
            continue
        if result.returncode == 0 and result.stdout.strip():
            try:
                data = json.loads(result.stdout.strip().splitlines()[-1])
                return data["version"], bool(data["hasIso"])
            except (ValueError, KeyError, IndexError):
                continue
    return None


def main() -> int:
    problems: list[str] = []

    if not ORVAL_CONFIG.exists():
        print(f"FAIL: {ORVAL_CONFIG.relative_to(REPO_ROOT)} is missing.")
        return 1
    if not GENERATED_ZOD.exists():
        print(f"FAIL: {GENERATED_ZOD.relative_to(REPO_ROOT)} is missing.")
        return 1

    config = ORVAL_CONFIG.read_text()
    generated = GENERATED_ZOD.read_text()

    # 1. The pin must exist. `auto` is what caused this.
    match = _VERSION_IN_CONFIG.search(config)
    if match is None:
        problems.append(
            "orval.config.ts pins no zod `version:`, so it defaults to "
            '"auto" -- which is what emitted v4 syntax against a v3 runtime. '
            "Pin it explicitly."
        )
        pinned = None
    else:
        pinned = int(match.group(1))

    # 2. The runtime surface, asked rather than assumed.
    zod = installed_zod()
    if zod is None:
        problems.append(
            "Could not determine the installed zod. Run `pnpm install` in "
            "Science-Agent-Pipeline. Reported as a failure rather than a "
            "skip: a guard that quietly does nothing when its subject is "
            "missing is the false-green shape this repository keeps finding."
        )
        version, has_iso = "unknown", None
    else:
        version, has_iso = zod
        major = int(version.split(".")[0])
        if pinned is not None and pinned != major:
            problems.append(
                f"orval.config.ts pins zod version {pinned}, but the "
                f"installed zod is {version} (major {major}). The generator "
                "will emit syntax the runtime does not have."
            )

    # 3. The generated file must not use v4-only forms on a v3 runtime.
    if has_iso is False:
        for pattern, label in V4_ONLY:
            hits = pattern.findall(generated)
            if hits:
                problems.append(
                    f"{GENERATED_ZOD.relative_to(REPO_ROOT)} uses {label} "
                    f"{len(hits)} time(s), but the installed zod {version} "
                    "has no `iso` on its default export. This contract "
                    "throws on import. Regenerate with `version: 3` pinned."
                )

    if problems:
        print("Generated zod contract does not match the installed zod:\n")
        for p in problems:
            print(f"  - {p}\n")
        print(
            "Verify by hand before changing anything:\n"
            '    node -e "const z=require(\'zod\'); console.log(typeof z.iso)"\n'
            "  undefined -> the workspace is on zod 3.x; pin `version: 3`.\n"
            "  object    -> the workspace is on zod 4.x; pin `version: 4`.\n"
            "\nSee ADR 0030."
        )
        return 1

    iso_note = "no `iso` on the default export" if has_iso is False else "`iso` present"
    print(
        f"OK: orval pins zod {pinned}, installed zod is {version} "
        f"({iso_note}), and the generated contract uses no syntax that "
        "runtime lacks."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
