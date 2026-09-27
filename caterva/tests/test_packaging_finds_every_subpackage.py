"""pyproject's package list must find every subpackage of caterva.

Found 2026-09-27: the rename turned `include = ["Terium", "Terium.*"]` into
`["caterva", "Caterva.*"]`. The pattern matched nothing, the wheel carried
5 modules instead of 85, and every command crashed on install -- while every
test here passed, because the repository puts the source tree on sys.path.

Standard library only (no tomllib, which 3.10 lacks, and no setuptools,
which is not a declared dependency): the patterns are read with a regex and
matched the way setuptools matches them, with fnmatch.
"""
from __future__ import annotations

import fnmatch
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = (ROOT / "pyproject.toml").read_text(encoding="utf-8")


def _patterns(key: str) -> list[str]:
    section = PYPROJECT.split("[tool.setuptools.packages.find]", 1)[1].split("\n[", 1)[0]
    match = re.search(rf"^{key}\s*=\s*\[([^\]]*)\]", section, re.M)
    assert match, f"no `{key}` under [tool.setuptools.packages.find]"
    return re.findall(r'"([^"]+)"', match.group(1))


def _shipped(package: str) -> bool:
    included = any(fnmatch.fnmatchcase(package, p) for p in _patterns("include"))
    excluded = any(fnmatch.fnmatchcase(package, p) for p in _patterns("exclude"))
    return included and not excluded


def test_every_package_directory_is_included() -> None:
    on_disk = sorted(
        ".".join(p.parent.relative_to(ROOT).parts)
        for p in (ROOT / "caterva").rglob("__init__.py")
        if "tests" not in p.parts
    )
    assert len(on_disk) > 5, f"found only {on_disk}: the test itself is broken"
    missing = [p for p in on_disk if not _shipped(p)]
    assert missing == [], f"not shipped in the wheel: {missing}"


def test_package_data_is_keyed_by_the_real_package_name() -> None:
    for table in ("package-data", "exclude-package-data"):
        body = PYPROJECT.split(f"[tool.setuptools.{table}]", 1)[1].split("\n[", 1)[0]
        keys = re.findall(r"^([A-Za-z_][\w.]*)\s*=", body, re.M)
        assert keys and all(k == "caterva" or k.startswith("caterva.") for k in keys), (table, keys)
