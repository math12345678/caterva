"""What this installation can do, decided by looking, so the page never offers what cannot run.

WHY THE PAGE ASKS FIRST
-----------------------
The same studio runs from a source checkout (the literature layer in
`Tests/` is there, `gmx` is on PATH), from the downloadable app (no
literature layer, a GUI app's short PATH), and on a laptop in a lecture
hall with no network. A page that offered a BRENDA search it could not run
would fail late, after the user had filled in a form, with an error that
reads like a defect. So the page reads `GET /api/capabilities` first and
draws every unavailable kind with its reason ("the literature layer is not
in this installation", "gmx was not found"), in the words below.

HOW EACH IS DECIDED, AND WHAT IS NEVER DONE UNASKED
---------------------------------------------------
- literature: the import the commands themselves make
  (`caterva.checkout.literature_module`), once per process, on first ask.
- network: never probed while the `offline` setting is on, and NOT probed
  until something asks (`?probe=network`), because
  probing contacts third-party hosts and a user who has not asked should
  not have their address sent to them. Then one HTTPS HEAD per host, to a
  path that host's own API serves for the literature layer (`PROBE_PATHS`:
  a BRENDA enzyme page, a UniProt search, an RCSB header, an NCBI einfo, a
  PubChem compound), with a 5 s timeout, all at once, so the answer takes at
  most about 5 s; any HTTP answer, even an error status, means the host is
  reachable. The hosts are the ones the literature layer reads: BRENDA,
  UniProt, the RCSB search and files, NCBI, PubChem, and KEGG only while
  its opt-in (`CATERVA_ENABLE_KEGG`) is set.
  REACHABILITY IS KEPT PER HOST: each host has its own last outcome, with
  the time, where it came from and why it failed (`host_status`). A BRENDA
  failure after a UniProt success does not overwrite UniProt's answer, and
  anything that must know whether UniProt can be asked (the enzyme finder's
  fallback) reads UniProt's own entry, not an aggregate. `reachable` is the
  aggregate and says only what was checked: True when every host that has
  an outcome answered, False when any of them did not, None when none has
  one; `reason` names the hosts that did not answer and, separately, those
  never checked.
  The studio also notes the outcome of REAL network use (`caterva.netuse`:
  a BRENDA, UniProt, NCBI, PubChem or RCSB request that was answered marks
  that host reachable, one that could not be made marks it unreachable,
  each with the time), so the status bar does not say "not checked" after a
  lookup has just worked. `source` says which of the two the newest outcome
  is from ("use" or "probe"); it is None, and `checked` False, only while
  nothing has happened yet. Noting use contacts nothing.
- gromacs: the settings' `gromacs_path`, else `$GMX`, else `gmx` on PATH,
  else the two places Homebrew puts it (a GUI app's PATH does not include
  them). The version is the `GROMACS version:` line of `gmx --version`
  (5 s timeout). Kept once found; looked for again on every request while
  it is not, so installing GROMACS does not need a restart.
- rates, ui, data_dir, kinds: read fresh on every request; each is a file
  test or a dictionary lookup.

Nothing here runs at startup: the server listens first and the page can
connect at once, whatever the literature import or `gmx` costs.
"""
from __future__ import annotations

import importlib.util
import os
import platform as _platform
import re
import shutil
import ssl
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, MutableMapping, Optional, Sequence, Tuple

from caterva import netuse
from caterva.studio.contract import RUN_KINDS, STUDIO_API_VERSION

#: The services the literature layer reads (CONTRACT.md 10).
NETWORK_HOSTS: Tuple[str, ...] = (
    "www.brenda-enzymes.org",
    "rest.uniprot.org",
    "search.rcsb.org",
    "files.rcsb.org",
    "eutils.ncbi.nlm.nih.gov",
    "pubchem.ncbi.nlm.nih.gov",
)
#: KEGG is read only when the person opted in (Tests/enzyme_lookup.py, KEGG_OPT_IN_ENV).
KEGG_HOST = "rest.kegg.jp"
KEGG_OPT_IN_ENV = "CATERVA_ENABLE_KEGG"
PROBE_TIMEOUT_S = 5.0

#: The path each host's API is asked at, for a check: one the literature layer reads,
#: with a fixed identifier that names a common enzyme, compound or structure. The
#: root of a host can answer while its API is down.
PROBE_PATHS: Mapping[str, str] = {
    "www.brenda-enzymes.org": "/enzyme.php?ecno=1.1.1.1",
    "rest.uniprot.org": "/uniprotkb/search?query=accession:P00338&fields=accession&size=1",
    "search.rcsb.org": "/rcsbsearch/v2/query",
    "files.rcsb.org": "/header/1LYZ.pdb",
    "eutils.ncbi.nlm.nih.gov": "/entrez/eutils/einfo.fcgi?retmode=json",
    "pubchem.ncbi.nlm.nih.gov": "/rest/pug/compound/cid/2244/cids/JSON",
    KEGG_HOST: "/get/ec:1.1.1.1",
}


def network_hosts(environ: Mapping[str, str] = os.environ) -> Tuple[str, ...]:
    """The hosts to check: the literature layer's, and KEGG only while its opt-in is set."""
    hosts = NETWORK_HOSTS
    if environ.get(KEGG_OPT_IN_ENV, "").strip().lower() in {"1", "true", "yes"}:
        hosts = hosts + (KEGG_HOST,)
    return hosts

#: Where Homebrew installs gmx on Apple silicon and on Intel Macs.
GMX_FALLBACKS: Tuple[str, ...] = ("/opt/homebrew/bin/gmx", "/usr/local/bin/gmx")
_GMX_VERSION = re.compile(r"^\s*GROMACS version:\s*(\S.*?)\s*$", re.M)

#: For a kind no adapter module registered yet: the command it will mirror
#: (CONTRACT.md 13), so the page can name what is missing.
UNBUILT_COMMANDS: Mapping[str, str] = {
    "compose": "caterva compose",
    "constants": "python3 scripts/cite.py",
    "sim": "caterva sim ssa",
    "bind": "caterva bind",
    "structure": "caterva structure",
    "prepare": "caterva prepare",
    "md.setup": "caterva md",
    "md.summarise": "caterva md --summarise",
    "analyze": "caterva analyze",
    "fep.status": "caterva fep --summarise",
    "complex.check": "caterva complex --check",
    "rates": "caterva rates",
}
NOT_BUILT_YET = "not built yet in this version of Caterva Studio"

#: Why a kind that may contact a database is refused, and why the network
#: is not probed, while the `offline` setting is on.
OFFLINE_REASON = ("offline mode is on (Settings): the studio contacts no network host, so kinds that may "
                  "need the network do not start")


def https_head(host: str, timeout: float) -> Optional[str]:
    """None when `host` answered an HTTPS HEAD at its API path (`PROBE_PATHS`), else why it did not."""
    from caterva import __version__

    request = urllib.request.Request(
        f"https://{host}{PROBE_PATHS.get(host, '/')}", method="HEAD",
        headers={"User-Agent": f"caterva-studio/{__version__} (reachability check)"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout):  # noqa: S310 - fixed https hosts
            return None
    except urllib.error.HTTPError:
        return None  # an error status is still an answer from the host
    except urllib.error.URLError as exc:
        return _describe_failure(exc.reason, timeout)
    except (TimeoutError, ssl.SSLError, OSError) as exc:
        return _describe_failure(exc, timeout)


def _describe_failure(reason: object, timeout: float) -> str:
    text = str(reason)
    if isinstance(reason, TimeoutError) or "timed out" in text:
        return f"no answer within {timeout:g} s"
    return text or type(reason).__name__


def parse_gmx_version(text: str) -> Optional[str]:
    match = _GMX_VERSION.search(text)
    return match.group(1) if match else None


class CapabilityProbe:
    """Builds `Capabilities` (contract.py) for one running server."""

    def __init__(
        self,
        *,
        registry: Any,
        workspace: Any,
        static_site: Any,
        dev_origin: Optional[str],
        settings: Callable[[], Mapping[str, Any]],
        environ: MutableMapping[str, str] = os.environ,
        which: Callable[[str], Optional[str]] = shutil.which,
        run: Callable[..., Any] = subprocess.run,
        head: Callable[[str, float], Optional[str]] = https_head,
        literature_import: Optional[Callable[[], Any]] = None,
        find_spec: Callable[[str], Any] = importlib.util.find_spec,
        clock: Optional[Callable[[], str]] = None,
        hosts: Optional[Sequence[str]] = None,
        is_executable: Callable[[str], bool] = lambda p: os.path.isfile(p) and os.access(p, os.X_OK),
    ) -> None:
        from caterva.studio.workspace import iso, utc_now

        self.registry = registry
        self.workspace = workspace
        self.static_site = static_site
        self.dev_origin = dev_origin
        self._settings = settings
        self._environ = environ
        self._which = which
        self._run = run
        self._head = head
        self._literature_import = literature_import or _import_literature
        self._find_spec = find_spec
        self._clock = clock or (lambda: iso(utc_now()))
        self._hosts = tuple(hosts) if hosts is not None else network_hosts(environ)
        self._is_executable = is_executable
        self._lock = threading.Lock()
        self._probe_lock = threading.Lock()
        self._literature: Optional[Dict[str, Any]] = None
        self._gromacs: Optional[Dict[str, Any]] = None
        #: host -> {reachable, checked_at, source, reason}: each host's own latest outcome.
        self._host_status: Dict[str, Dict[str, Any]] = {}
        self._network_reason: Optional[str] = None
        self._unsubscribe = netuse.subscribe(self.observe_network_use)
        #: $GMX as the server found it, before a setting or a Homebrew
        #: location was put there (apply_gromacs_to_environment).
        self._original_gmx = environ.get("GMX")

    # -- the whole answer ----------------------------------------------------

    def snapshot(self, *, probe_network: bool = False) -> Dict[str, Any]:
        from caterva import __version__

        if probe_network:
            self.probe_network()
        built, ui_reason = self.static_site.built()
        return {
            "version": __version__,
            "api_version": STUDIO_API_VERSION,
            "python": _platform.python_version(),
            "platform": sys.platform,
            "frozen": bool(getattr(sys, "frozen", False)),
            "literature": self.literature(),
            "network": self.network(),
            "gromacs": self.gromacs(),
            "rates": self.rates(),
            "ui": {"built": built, "static_dir": str(self.static_site.root), "reason": ui_reason},
            "data_dir": self.data_dir(),
            "kinds": self.kinds(),
            "dev_origin": self.dev_origin,
        }

    # -- each part -----------------------------------------------------------

    def literature(self) -> Dict[str, Any]:
        with self._lock:
            if self._literature is None:
                try:
                    self._literature_import()
                    self._literature = {"available": True, "reason": None}
                except ImportError as exc:  # LiteratureLayerUnavailable is one
                    self._literature = {"available": False, "reason": str(exc) or type(exc).__name__}
                except Exception as exc:  # noqa: BLE001 - reported, not raised: the page must still load
                    self._literature = {"available": False,
                                        "reason": f"the literature layer failed to load: {type(exc).__name__}: {exc}"}
            return dict(self._literature)

    def close(self) -> None:
        """Stop noting network use (the server is stopping)."""
        self._unsubscribe()

    def observe_network_use(self, host: str, reached: bool, reason: Optional[str]) -> None:
        """A real request was answered (`reached`) or could not be made.

        Called from whichever thread made the request (`caterva.netuse`).
        It updates THAT host's entry only: a BRENDA failure after a UniProt
        success leaves UniProt reachable. Nothing is contacted."""
        if self._settings().get("offline"):
            return
        stamp = self._clock()
        with self._lock:
            self._network_reason = None
            self._host_status[host] = {
                "reachable": reached, "checked_at": stamp, "source": "use",
                "reason": None if reached else (reason or "no reason given"),
            }

    def network(self) -> Dict[str, Any]:
        """The network capability as last learned, without probing."""
        with self._lock:
            return self._network_view()

    def _network_view(self) -> Dict[str, Any]:
        """The per-host outcomes and what they add up to. Caller holds the lock."""
        hosts_known = [h for h in self._hosts] + [h for h in self._host_status if h not in self._hosts]
        status = {
            h: dict(self._host_status.get(h) or {"reachable": None, "checked_at": None, "source": None,
                                                 "reason": None})
            for h in hosts_known
        }
        known = {h: s for h, s in status.items() if s["reachable"] is not None}
        if not known:
            return {
                "checked": False, "reachable": None, "hosts": {h: None for h in status},
                "host_status": status, "checked_at": None, "source": None,
                "reason": self._network_reason
                or "not checked: probing contacts third-party hosts, so it is done only when asked",
            }
        failed = [h for h, s in known.items() if s["reachable"] is False]
        newest = max(known.items(), key=lambda item: item[1]["checked_at"] or "")
        # Each failure in the words of where it was learned: a check says "not reachable from this
        # computer", a real request says which host "could not be reached".
        checked = [f"{h}: {known[h]['reason'] or 'no reason given'}" for h in failed if known[h]["source"] == "probe"]
        used = [f"{h} could not be reached: {known[h]['reason'] or 'no reason given'}"
                for h in failed if known[h]["source"] != "probe"]
        parts = ([("not reachable from this computer: " + "; ".join(checked))] if checked else []) + used
        return {
            "checked": True,
            "reachable": not failed,
            "hosts": {h: s["reachable"] for h, s in status.items()},
            "host_status": status,
            "checked_at": newest[1]["checked_at"],
            "source": newest[1]["source"],
            "reason": "; ".join(parts) if parts else None,
        }

    def probe_network(self) -> Dict[str, Any]:
        if self._settings().get("offline"):
            # Nothing is contacted; the last real probe, if any, is not shown
            # as current either.
            with self._lock:
                self._host_status = {}
                self._network_reason = OFFLINE_REASON
            return self.network()
        with self._probe_lock:
            results: Dict[str, Optional[str]] = {}
            threads = []
            for host in self._hosts:
                def check(h: str = host) -> None:
                    try:
                        results[h] = self._head(h, PROBE_TIMEOUT_S)
                    except Exception as exc:  # noqa: BLE001 - a probe that raised did not reach its host
                        results[h] = f"{type(exc).__name__}: {exc}"
                thread = threading.Thread(target=check, name=f"caterva-probe-{host}", daemon=True)
                thread.start()
                threads.append(thread)
            for thread in threads:
                thread.join(PROBE_TIMEOUT_S + 2.0)
            stamp = self._clock()
            with self._lock:
                self._network_reason = None
                for host in self._hosts:
                    if host not in results:
                        outcome: Optional[str] = f"no answer within {PROBE_TIMEOUT_S:g} s"
                    else:
                        outcome = results[host]
                    self._host_status[host] = {
                        "reachable": outcome is None, "checked_at": stamp, "source": "probe", "reason": outcome,
                    }
            return self.network()

    def gromacs_candidate(self) -> Tuple[Optional[str], str]:
        """(the gmx to try, where that choice came from)."""
        chosen = self._settings().get("gromacs_path")
        if chosen:
            return str(chosen), "the gromacs_path setting"
        gmx = self._original_gmx
        if gmx:
            found = gmx if os.path.isabs(gmx) else self._which(gmx)
            return found, f"$GMX ({gmx})"
        on_path = self._which("gmx")
        if on_path:
            return on_path, "gmx on PATH"
        for fallback in GMX_FALLBACKS:
            if self._is_executable(fallback):
                return fallback, f"{fallback} (not on this process's PATH)"
        return None, "gmx on PATH, $GMX, " + " and ".join(GMX_FALLBACKS)

    def gromacs(self) -> Dict[str, Any]:
        candidate, where = self.gromacs_candidate()
        with self._lock:
            cached = self._gromacs
            if cached and cached["found"] and cached["path"] == candidate:
                return dict(cached)
        result = self._probe_gromacs(candidate, where)
        with self._lock:
            self._gromacs = result
        return dict(result)

    def _probe_gromacs(self, candidate: Optional[str], where: str) -> Dict[str, Any]:
        if candidate is None:
            return {"found": False, "path": None, "version": None,
                    "reason": f"GROMACS was not found (looked for {where}); setting up a simulation still "
                              "works, running it needs GROMACS"}
        try:
            done = self._run([candidate, "--version"], capture_output=True, text=True, timeout=5,
                             stdin=subprocess.DEVNULL)
        except subprocess.TimeoutExpired:
            return {"found": False, "path": candidate, "version": None,
                    "reason": f"{candidate} (from {where}) did not answer `--version` within 5 s"}
        except OSError as exc:
            return {"found": False, "path": candidate, "version": None,
                    "reason": f"{candidate} (from {where}) could not be run: {exc.strerror or exc}"}
        version = parse_gmx_version(done.stdout or "") or parse_gmx_version(done.stderr or "")
        if done.returncode != 0 or version is None:
            return {"found": False, "path": candidate, "version": None,
                    "reason": f"{candidate} (from {where}) exited {done.returncode} without a "
                              "`GROMACS version:` line"}
        return {"found": True, "path": candidate, "version": version, "reason": None}

    def apply_gromacs_to_environment(self) -> Optional[str]:
        """Point $GMX at the gmx the settings name, or at a Homebrew gmx a
        GUI app's PATH does not reach, so the commands that honour $GMX
        (`caterva analyze --gromacs`) find the same program capabilities
        reports. Returns the value set, or None when $GMX is left as found."""
        chosen = self._settings().get("gromacs_path")
        if chosen:
            self._environ["GMX"] = str(chosen)
            return str(chosen)
        if self._original_gmx is not None:
            self._environ["GMX"] = self._original_gmx
            return None
        if self._which("gmx") is None:
            for fallback in GMX_FALLBACKS:
                if self._is_executable(fallback):
                    self._environ["GMX"] = fallback
                    return fallback
        self._environ.pop("GMX", None)
        return None

    def rates(self) -> Dict[str, Any]:
        try:
            module = self._find_spec("caterva.rates") is not None
        except (ImportError, ValueError):
            module = False
        registered = self.registry.get("rates") is not None
        if module and registered:
            return {"available": True, "reason": None}
        missing = []
        if not module:
            missing.append("the caterva.rates module is not in this installation")
        if not registered:
            missing.append("no adapter registered the rates kind")
        return {"available": False, "reason": "; ".join(missing)}

    def data_dir(self) -> Dict[str, Any]:
        reason = self.workspace.unwritable_reason()
        return {"path": str(self.workspace.root), "writable": reason is None,
                "runs": len(self.workspace.run_ids()), "reason": reason}

    def kinds(self) -> Dict[str, Dict[str, Any]]:
        out: Dict[str, Dict[str, Any]] = {}
        offline = bool(self._settings().get("offline"))
        for kind in RUN_KINDS:
            spec = self.registry.get(kind)
            if spec is None:
                command = UNBUILT_COMMANDS.get(kind, kind)
                out[kind] = {"available": False, "title": command, "command": command, "needs": [],
                             "reason": NOT_BUILT_YET}
                continue
            try:
                reason = spec.unavailable()
            except Exception as exc:  # noqa: BLE001 - an adapter's check that raised cannot vouch for the kind
                reason = f"could not tell whether it can run here: {type(exc).__name__}: {exc}"
            if reason is None and offline and "network" in spec.needs:
                reason = OFFLINE_REASON
            out[kind] = {"available": reason is None, "title": spec.title, "command": spec.command,
                         "needs": list(spec.needs), "reason": reason}
        return out


def _import_literature() -> Any:
    from caterva.checkout import literature_module

    return literature_module("fallback_logic")


__all__ = ["CapabilityProbe", "GMX_FALLBACKS", "KEGG_HOST", "KEGG_OPT_IN_ENV", "NETWORK_HOSTS", "NOT_BUILT_YET",
           "OFFLINE_REASON", "PROBE_PATHS", "PROBE_TIMEOUT_S", "UNBUILT_COMMANDS", "https_head", "network_hosts",
           "parse_gmx_version"]
