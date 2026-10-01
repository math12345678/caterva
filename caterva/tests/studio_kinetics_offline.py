"""Run the kinetics commands and their studio adapters offline, on committed real answers.

Shared by caterva/tests/test_studio_{compose,constants,sim,bind}.py, which
hold Caterva Studio's kinetics adapters to the commands they mirror. A
parity test is only worth something when the two sides read the same
database answers, and only repeatable when those answers do not change
under it, so every literature lookup here is answered from a file in the
repository:

- hexokinase (EC 2.7.1.1): the recordings the API server's tests use,
  Tests/fixtures/recorded/ (README there): the BRENDA page and the 15
  NCBI, UniProt and PubChem answers one human hexokinase Km lookup makes.
- lactate dehydrogenase (EC 1.1.1.27): the BRENDA page behind the Ki-mode
  tests, Tests/fixtures/ki_mode/brenda_1.1.1.27.html.gz, decoded as a live
  fetch decodes it (that page is not strict UTF-8, which is why it is not
  in Tests/fixtures/recorded/), and the six other answers an LDH search
  asks for, recorded into caterva/tests/fixtures/studio_kinetics/http/
  (README there).

A request with no recording is refused rather than sent: a test that went
live would pass or fail with the database's mood and could not be called a
parity test on recorded inputs. The refusal surfaces as the search's own
"could not run" note, which the tests' value assertions then catch.

The recorded-answer variables are set here, in caterva/tests/, and never
by anything under caterva/studio/ (Tests/test_recorded_env_is_test_only.py).
"""
from __future__ import annotations

import contextlib
import gzip
import io
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Iterator, List, Optional, Sequence, Tuple

REPO = Path(__file__).resolve().parents[2]
RECORDED = REPO / "Tests" / "fixtures" / "recorded"
RECORDED_HTTP = RECORDED / "http"
KI_MODE_PAGES = REPO / "Tests" / "fixtures" / "ki_mode"
LDH_HTTP = Path(__file__).resolve().parent / "fixtures" / "studio_kinetics" / "http"
LDH_KI_PAGE = REPO / "Tests" / "fixtures" / "brenda_ldh_ki_fixture.html"

#: Port 9 (discard) on loopback: nothing listens there, so a request
#: through this proxy fails at once instead of reaching a database.
CLOSED_PROXY = "http://127.0.0.1:9"
PROXY_VARIABLES = ("HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY", "https_proxy", "http_proxy", "all_proxy")

#: The inhibitor of BRENDA ref 739793, as BRENDA names it.
QUINOLINE = "3-[7-(2,4-dimethoxypyrimidin-5-yl)-3-sulfamoylquinolin-4-yl]aminobenzoic acid"


class Recorder:
    """A Progress that keeps every call, and can cancel at a chosen stage."""

    def __init__(self, cancel_at: Optional[str] = None) -> None:
        self.calls: List[Tuple[str, Any, Any, Any]] = []
        self.cancel_at = cancel_at
        self._cancel = False

    def stage(self, key: str, label: str, fraction: Optional[float] = None) -> None:
        self.calls.append(("stage", key, label, fraction))
        if self.cancel_at is not None and key == self.cancel_at:
            self._cancel = True

    def log(self, line: str) -> None:
        self.calls.append(("log", line, None, None))

    def check_cancelled(self) -> None:
        from caterva.studio.adapters import Cancelled

        if self._cancel:
            raise Cancelled()

    def stages(self) -> List[str]:
        return [c[1] for c in self.calls if c[0] == "stage"]

    def logs(self) -> List[str]:
        return [c[1] for c in self.calls if c[0] == "log"]


def context(tmp: Path, progress: Optional[Recorder] = None) -> Any:
    from caterva.studio.adapters import RunContext

    return RunContext(run_id="20261001-000000-test-00000000", run_dir=tmp, data_dir=tmp,
                      progress=progress or Recorder())


def run_cli(main: Callable[..., int], argv: Sequence[str]) -> Tuple[int, str, str]:
    """(exit code, stdout, stderr) of a command's `main(argv)`."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(list(argv))
    return code, out.getvalue(), err.getvalue()


def _http_retry_modules() -> List[Any]:
    """Every loaded copy of the literature layer's http_retry: it can be
    imported both flat and as `Tests.http_retry`, each with its own memo."""
    from caterva.checkout import literature_module

    literature_module("http_retry")
    return [sys.modules[n] for n in ("http_retry", "Tests.http_retry") if n in sys.modules]


@contextlib.contextmanager
def _patched(env: dict, remove: Optional[Path] = None) -> Iterator[None]:
    """Recorded answers on, and httpx refusing to send anything else."""
    import httpx

    modules = _http_retry_modules()
    # A subprocess the command starts (scripts/cite.py runs report_lab as
    # one) does not inherit the patch below; a proxy that is a closed port
    # refuses its live requests instead.
    env = dict(env, **{name: CLOSED_PROXY for name in PROXY_VARIABLES}, NO_PROXY="", no_proxy="")
    saved_env = {k: os.environ.get(k) for k in env}
    saved_get = httpx.get

    def refuse_live(url: Any, *args: Any, **kwargs: Any) -> Any:
        raise ConnectionError(f"no recording answers {url}; this test does not go live")

    try:
        os.environ.update(env)
        httpx.get = refuse_live
        for module in modules:
            module.clear_memo()
        yield
    finally:
        httpx.get = saved_get
        for module in modules:
            module.clear_memo()
        for key, value in saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        if remove is not None:
            shutil.rmtree(remove, ignore_errors=True)


def _page_directory(name: str, text: str) -> Path:
    """A directory holding `text` as brenda_<ec>.html.gz, the form
    fetch_brenda_html reads a recorded page in."""
    directory = Path(tempfile.mkdtemp(prefix="caterva-brenda-"))
    (directory / name).write_bytes(gzip.compress(text.encode("utf-8"), mtime=0))
    return directory


def hexokinase_offline() -> Any:
    """Answers for EC 2.7.1.1 from Tests/fixtures/recorded/."""
    return _patched({"CATERVA_BRENDA_RECORDED": str(RECORDED),
                     "CATERVA_HTTP_RECORDED": str(RECORDED_HTTP)})


def ldh_offline() -> Any:
    """Answers for EC 1.1.1.27: the committed page of Tests/fixtures/ki_mode/,
    decoded as `requests` decodes the live page (errors replaced, as
    caterva/tests/test_ki_mode.py reads it) and served the way a recorded
    page is served, and the other answers from LDH_HTTP."""
    text = gzip.decompress((KI_MODE_PAGES / "brenda_1.1.1.27.html.gz").read_bytes()).decode(
        "utf-8", errors="replace")
    pages = _page_directory("brenda_1.1.1.27.html.gz", text)
    return _patched({"CATERVA_BRENDA_RECORDED": str(pages), "CATERVA_HTTP_RECORDED": str(LDH_HTTP)}, pages)


def ldh_ki_page_offline() -> Any:
    """BRENDA's LDH Ki page as `caterva bind --html` reads it (test_bind.py's
    page), served to the fetch the studio's bind makes."""
    pages = _page_directory("brenda_1.1.1.27.html.gz", LDH_KI_PAGE.read_text(encoding="utf-8"))
    return _patched({"CATERVA_BRENDA_RECORDED": str(pages)}, pages)
