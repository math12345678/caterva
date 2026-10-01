"""The adapter registry: one entry per run kind, each a thin wrapper over a CLI command.

WHY ADAPTERS GO THROUGH THE CLI'S OWN PARSER
--------------------------------------------
Every `caterva <command>` already decides what a well-formed question is:
which flags combine, what a default is, when a value is out of range
(`--robustness 0`, `--stochastic-seed` without `--stochastic`, a PDB id of
five characters). A studio that re-stated those rules in its own validation
would hold a second copy of them, and the two would drift the first time
someone added a flag. So an adapter's first job is `argv(request)`: the JSON
request turned into the exact argv the CLI would receive. `parse_cli` then
runs that command's own `build_parser()` over it, and argparse's refusal
becomes HTTP 400 with argparse's message. The argv is also recorded on the
run (`RunRecord.cli`), so every result in History carries the command that
reproduces it in a terminal.

WHY THE MODULE LIST IS FIXED HERE
---------------------------------
Five owners build adapters in parallel. If each added its module to a list
in this file, every merge would conflict on that list. So the list is
written once, now, with every module the contract names, and each module
already exists with a `register(registry)` that registers nothing until its
owner fills it in (docs/studio/CONTRACT.md, "Ownership map"). A module that
registers nothing leaves its kind reported as unavailable, "not built yet",
rather than missing.

WHAT AN ADAPTER MAY NOT DO
--------------------------
Compute. It calls library functions and serialises their return values
with `caterva.studio.contract`. A number the library did not produce, a
rounding the library did not apply, or a sentence summarising one the
library wrote, is a defect here whatever it looks like on the page.
"""
from __future__ import annotations

import argparse
import importlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Protocol, Sequence, Tuple

from caterva.studio.contract import NEEDS, RUN_KINDS, Malformed
from caterva.studio.routes import ROUTES

#: Every adapter module, in the order capabilities lists their kinds. Owned
#: by the contract; see the module docstring for why nobody appends to it.
ADAPTER_MODULES: Tuple[str, ...] = (
    "compose", "constants", "sim", "bind",
    "structure", "prepare", "md", "analyze", "fep",
    "rates",
)


class Cancelled(Exception):
    """Raised by `Progress.check_cancelled` when the run was cancelled."""


class Progress(Protocol):
    """What an adapter reports while it runs. Each call becomes an SSE event
    (docs/studio/CONTRACT.md, "Jobs and events")."""

    def stage(self, key: str, label: str, fraction: Optional[float] = None) -> None: ...

    def log(self, line: str) -> None: ...

    def check_cancelled(self) -> None: ...


@dataclass(frozen=True)
class Artifact:
    """A file a run produced, stored beside its record and served back by
    name only (never by a path from the request)."""

    name: str
    content: bytes
    content_type: str
    description: str


@dataclass(frozen=True)
class RunContext:
    run_id: str
    #: <data dir>/runs/<run id>. An adapter writes here only through
    #: `AdapterOutcome.artifacts`, except `md.setup`, whose default output
    #: directory is <run dir>/md-setup because GROMACS runs from it.
    run_dir: Path
    data_dir: Path
    progress: Progress


@dataclass(frozen=True)
class AdapterOutcome:
    #: 0 produced, 3 refused and said why, 4 a negative finding: the code
    #: the CLI exits with for the same request (contract.EXIT_MEANING).
    exit_code: int
    #: The kind's Result shape (contract.KIND_SHAPES), already JSON-ready.
    #: None only for a refusal that produced nothing (compose's
    #: UnrecognisedShape, a structure search the RCSB refused); a refusal
    #: that still produced a report (compose with a refused section, md
    #: setup without measured conditions) carries its result.
    result: Optional[Mapping[str, Any]]
    #: One line for History, taken from the result or the refusal.
    summary: str
    #: For exit 3: what the CLI prints to stderr, verbatim. Required then.
    refusal: Optional[str] = None
    artifacts: Tuple[Artifact, ...] = ()


@dataclass(frozen=True)
class AdapterSpec:
    kind: str
    #: What the kind is called on the page ("Compose a model").
    title: str
    #: The `caterva <command>` it mirrors.
    command: str
    #: Which of contract.NEEDS a run MAY need, depending on its request.
    needs: Tuple[str, ...]
    #: request -> argv after "caterva <command>". Raises contract.Malformed.
    argv: Callable[[Mapping[str, Any]], List[str]]
    #: (request, context) -> outcome. Raises contract.Malformed for a
    #: question the parser accepted and the library then called malformed,
    #: Cancelled when cancelled; anything else is a crash (status failed).
    run: Callable[[Mapping[str, Any], RunContext], AdapterOutcome]
    #: None when the kind can run here, else the reason it cannot.
    unavailable: Callable[[], Optional[str]] = field(default=lambda: None)
    #: request -> the run's title in History ("Michaelis Menten, EC 2.7.1.1,
    #: Homo sapiens"). None: the core titles it with the CLI command line.
    describe: Optional[Callable[[Mapping[str, Any]], str]] = None
    #: The argv prefix that reproduces a run from the repository root:
    #: ("caterva", command) for every kind but `constants`, which is
    #: ("python3", "scripts/cite.py") because cite is a script, not a command.
    cli_prefix: Tuple[str, ...] = ()
    #: True for kinds that drive the simulation engine (roadrunner,
    #: antimony, libsbml). None of them documents calls from two threads at
    #: once as supported, so the job runner holds one process-wide
    #: engine lock around every serial run: they run one at a time, in
    #: submission order, while network-bound kinds run beside them.
    serial: bool = False
    #: request -> which of `needs` this request has (compose without a
    #: subject searches nothing). None: every request has all of `needs`.
    #: Called only on a request `argv` accepted. Offline mode refuses a run
    #: by these, so a question that needs no network is not refused for one
    #: that would.
    needs_for: Optional[Callable[[Mapping[str, Any]], Tuple[str, ...]]] = None
    #: (request, data dir) -> None, raising contract.Malformed: the user-path
    #: rules of contract section 15 that need the data dir, which `argv`
    #: cannot see (an md.setup `out` inside the workspace). Called by the
    #: server right after `argv`, so a breach is a 400 and never a run.
    check_paths: Optional[Callable[[Mapping[str, Any], Path], None]] = None


def request_needs(spec: AdapterSpec, request: Mapping[str, Any]) -> Tuple[str, ...]:
    """What this request needs: `spec.needs_for(request)`, never more than
    `spec.needs`, or all of `spec.needs` when the kind cannot tell."""
    if spec.needs_for is None:
        return tuple(spec.needs)
    return tuple(n for n in spec.needs_for(request) if n in spec.needs)


@dataclass(frozen=True)
class EndpointRequest:
    """What an adapter-owned route's handler receives (routes.Route.owner)."""

    #: The path's placeholders, already matched against their patterns.
    params: Mapping[str, str]
    #: Query parameters, each single-valued; a repeated key is malformed.
    query: Mapping[str, str]
    #: The parsed JSON body, or None for a method without one.
    body: Any
    data_dir: Path


#: An adapter-owned route's handler: the JSON-ready response, or raises
#: contract.Malformed (400), contract.NotFound (404), contract.Unavailable
#: (503). Anything else is a crash (500).
EndpointHandler = Callable[[EndpointRequest], Mapping[str, Any]]


class Registry:
    """Kind -> AdapterSpec. Registering a kind twice is a programming error."""

    def __init__(self) -> None:
        self._specs: Dict[str, AdapterSpec] = {}
        self._endpoints: Dict[str, EndpointHandler] = {}

    def register(self, spec: AdapterSpec) -> None:
        if spec.kind not in RUN_KINDS:
            raise ValueError(f"{spec.kind!r} is not a contract RunKind; amend contract.RunKind first")
        if spec.kind in self._specs:
            raise ValueError(f"{spec.kind!r} is registered twice")
        unknown = [n for n in spec.needs if n not in NEEDS]
        if unknown:
            raise ValueError(f"{spec.kind!r} needs {unknown}, which are not contract.NEEDS")
        self._specs[spec.kind] = spec

    def add_endpoint(self, handler: str, fn: EndpointHandler, *, owner: str) -> None:
        """Supply the handler of a route this adapter module owns.

        `owner` is the registering module's name in ADAPTER_MODULES; a
        route owned by core or by another module is refused, so two owners
        cannot answer one path."""
        routes = [r for r in ROUTES if r.handler == handler]
        if not routes:
            raise ValueError(f"{handler!r} is not a handler in routes.ROUTES; amend the contract first")
        if routes[0].owner != owner:
            raise ValueError(f"{handler!r} belongs to {routes[0].owner!r}, not {owner!r}")
        if handler in self._endpoints:
            raise ValueError(f"{handler!r} is registered twice")
        self._endpoints[handler] = fn

    def endpoint(self, handler: str) -> Optional[EndpointHandler]:
        return self._endpoints.get(handler)

    def get(self, kind: str) -> Optional[AdapterSpec]:
        return self._specs.get(kind)

    def kinds(self) -> List[str]:
        return [k for k in RUN_KINDS if k in self._specs]

    def missing(self) -> List[str]:
        """Contract kinds no module registered: reported as not built yet."""
        return [k for k in RUN_KINDS if k not in self._specs]


def load_registry(modules: Sequence[str] = ADAPTER_MODULES) -> Registry:
    """Import every adapter module and let each register its kinds.

    Adapter modules import nothing heavy at module level (the engine, the
    literature layer, numpy) so that /api/health and /api/capabilities
    answer in milliseconds; the heavy imports happen inside `run`.
    """
    registry = Registry()
    for name in modules:
        module = importlib.import_module(f"{__name__}.{name}")
        module.register(registry)
    return registry


def cli_parser(build_parser: Callable[..., argparse.ArgumentParser], prog: str) -> argparse.ArgumentParser:
    """A command's own parser whose `error` raises contract.Malformed.

    argparse reports a malformed question by printing usage to stderr and
    exiting 2. Neither can happen inside the server: stderr is shared by
    every thread, and exiting would stop it. So `error` is replaced on this
    one instance, and the message is argparse's own. Pass the same parser
    to any check the CLI makes with `parser.error` after parsing
    (compose's `_check_combination`), so those refusals arrive the same way.
    """
    parser = build_parser(prog)

    def refuse(message: str) -> None:
        raise Malformed(f"{prog}: error: {message}")

    def no_exit(status: int = 0, message: Optional[str] = None) -> None:
        # --help or --version reached the parser: help text is not a run.
        raise Malformed(message.strip() if message else f"{prog}: the request asked for help text, which is not a run")

    # Subcommand parsers (`caterva sim ssa`) report their own errors, so
    # each is patched the same way.
    pending = [parser]
    while pending:
        current = pending.pop()
        current.error = refuse  # type: ignore[method-assign]
        current.exit = no_exit  # type: ignore[method-assign]
        for action in current._actions:
            if isinstance(action, argparse._SubParsersAction):
                pending.extend(action.choices.values())
    return parser


def parse_cli(build_parser: Callable[..., argparse.ArgumentParser], argv: Sequence[str],
              prog: str) -> argparse.Namespace:
    """Parse `argv` with a command's own parser, or raise contract.Malformed
    carrying argparse's message (what the CLI prints before exit 2)."""
    return cli_parser(build_parser, prog).parse_args(list(argv))


__all__ = [
    "ADAPTER_MODULES", "AdapterOutcome", "AdapterSpec", "Artifact", "Cancelled",
    "EndpointHandler", "EndpointRequest", "Progress", "Registry", "RunContext",
    "cli_parser", "load_registry", "parse_cli", "request_needs",
]
