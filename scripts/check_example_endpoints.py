"""Guard that documented API examples call endpoints that exist.

WHAT THIS CAUGHT ON ITS FIRST RUN

`examples/python_integration.py` is the client example
`QUICK_START_DEPLOYMENT.md` points readers at. Ten of the eleven endpoints
it called did not exist:

    /api/health           -> the route is /api/healthz
    /api/jobs/<id>        -> the route is /api/simulate/<jobId>
    /api/export/jobs/csv  -> the route is /api/simulate/<jobId>/export
    /api/jobs/query, /api/batch, /api/batches/<id>, /api/sweep,
    /api/sweeps/<id>, /api/compare/jobs, /api/stats
                          -> no such routes, at all

Only `POST /api/simulate` was real. Someone following the quick start would
have got a 404 on essentially every call, and concluded the product was
broken rather than the documentation.

Nothing could have noticed. The example is Python, so `tsc` never sees it;
it makes no network calls at import time, so no test exercises it; and the
orphan guard's complaint -- "imported by nothing" -- is the wrong diagnosis,
because an example is *meant* to be read rather than imported. It was
simultaneously unreachable and wrong, and the two conditions hid each other.

WHAT IT CHECKS

Every `{base_url}/api/...` path in `EXAMPLE_FILES` and in every markdown
document at the repository root, resolved against the routes actually
registered by BOTH HTTP servers, with `:param` segments and `{placeholder}`,
`${placeholder}` and `<placeholder>` spellings treated as wildcards.

WHAT IT DELIBERATELY DOES NOT COUNT AS A CLAIM

Prose is not code. A document writes `/api/...` for at least five reasons
that are not "you may call this address", and the first attempt to widen
this guard to the root documents reported all of them as defects:

    /api/jobs/*                     a family, not an address
    location /api/ {                nginx, routing a prefix
    if (pathname === '/api/custom') a tutorial on ADDING an endpoint
    - Add `/api/jobs/:id/export`    a roadmap item, proposed not shipped
    lists non-existent /api/x       a banner WARNING the route is fake

The last one is the sharpest: flagging a correction banner punishes the
document for telling the truth, and the obvious way to make the build green
is to delete the warning. Each of the five is classified and excluded below,
with the concrete line it was found on quoted in the comment. `--verbose`
prints every exclusion, because a guard that quietly stops looking is the
failure this whole file exists to record.

This is a text-level check, not a live one: it needs no server, so it runs
in the fast path alongside the other static guards. It cannot tell whether
the request BODY is right -- only that the address exists. That is the
larger half of the defect it found, and worth saying plainly rather than
implying more coverage than there is.

Classification runs only on a mention the route table FAILS to resolve. A
mention that names a real route is always counted as checked, whatever else
the line around it says -- so a loose rule can cost a missed defect on an
absent endpoint, but can never quietly narrow coverage of a present one.

Run directly: python scripts/check_example_endpoints.py [--verbose]
"""

from __future__ import annotations

import pathlib
import re
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

API_SERVER = REPO_ROOT / "Science-Agent-Pipeline" / "artifacts" / "api-server"
ROUTES_DIR = API_SERVER / "src" / "routes"
APP_FILE = API_SERVER / "src" / "app.ts"

#: Files whose documented endpoints must exist. Add to this rather than
#: writing a new guard: an example is a promise, and every promise in the
#: repository should be checkable.
EXAMPLE_FILES = [
    REPO_ROOT / "examples" / "python_integration.py",
    REPO_ROOT / "examples" / "nodejs_integration.js",
]

#: Markdown that documents the HTTP API, and must therefore describe the
#: API that exists.
#:
#: A sweep of the repository root found **two** documents asserting an
#: endpoint that exists on neither server (`/api/literature/search`, in
#: `READY_TO_SHIP.md` and `WEB_INTERFACE.md`). Both are fixed; PubMed search
#: is not a route, it happens inside `POST /api/simulate`.
#:
#: An EARLIER version of this comment said "242 of 294 mentions wrong — 82%".
#: That figure was produced by this guard when it parsed only the Express
#: routers and could not see `src/web/server.ts` at all, and it is wrong by
#: more than an order of magnitude. The true rate was 19 of 282, of which
#: two were real. It is corrected here rather than deleted because the
#: number was acted on: two client examples were rewritten against the wrong
#: service on the strength of it. See STAGE_10_PART_24.
#:
#: Eighteen root documents open with a hand-written "CORRECTION" banner
#: admitting some claim of theirs is unverified. That is the wrong repair:
#: a reader who has been told the document is unreliable still reads the
#: endpoint table, and a disclaimer does not make a wrong URL right. The
#: fix for a false claim is to make it true or remove it, and then to make
#: it checkable so it cannot rot again — which is what this guard is for.
#:
#: Narrative records (Business/build-stages/**) are deliberately excluded:
#: they describe what was true on a date, and rewriting history to satisfy a
#: guard would destroy the thing that makes them worth keeping. Everything
#: at the repository ROOT is in scope, because a root document is what a
#: reader opens first and therefore what they act on.
#:
#: Discovered by glob rather than by list. Part 24 left "the other 22 root
#: documents are tracked but unchecked" as the open item, and a list is
#: exactly the mechanism by which the 23rd arrives unchecked: nobody
#: remembers to add it. The cost of globbing is that prose has to be
#: understood (see CLASSIFICATION below); the cost of listing is silent
#: shrinkage of what is covered, which is the failure this project keeps
#: finding.
ROOT_DOC_GLOB = "*.md"

#: Extra documents outside the root that must also be true.
EXTRA_DOC_FILES = [REPO_ROOT / "docs" / "API.md"]

#: Documents that must name at least one endpoint.
#:
#: `docs/API.md` is the reference: if it stops naming any endpoint, the
#: reference has been gutted and that is a failure. `API_DOCUMENTATION.md`
#: is now a signpost pointing at it, and legitimately names none — but if
#: fabricated endpoints reappear there, they must still be caught. So the
#: two questions are separated: "does this file describe the API" and "is
#: what it describes true". Most root documents answer "no" to the first
#: and that is fine; only the reference is held to it.
MUST_DOCUMENT_ENDPOINTS = {REPO_ROOT / "docs" / "API.md"}

#: `router.get("/simulate/:jobId", ...)` across several formatting styles,
#: including the multi-line form Prettier produces:
#:     router.get(
#:       "/simulate/:jobId",
ROUTE_RE = re.compile(
    r"""(?:router|app)\.(get|post|put|patch|delete)\(\s*['"`]([^'"`]+)['"`]""",
    re.MULTILINE,
)

#: THIS PROJECT SERVES TWO HTTP APIS, and the first version of this guard
#: knew about only one.
#:
#: `Science-Agent-Pipeline/artifacts/api-server/` is Express and matched
#: ROUTE_RE. `src/web/server.ts` is a raw `http.createServer` that
#: dispatches on `pathname === '/api/...'` and `pathname.match(/^\/api\/...`,
#: so ROUTE_RE never saw a single one of its routes.
#:
#: The consequence was not a missed check but a WRONG one: measured against
#: half the route table, this guard reported 242 of 294 endpoint mentions
#: across the documentation as nonexistent. Many of them were real. A
#: checker whose source of truth is incomplete does not fail quietly — it
#: produces confident false accusations, and I acted on several before
#: noticing.
#:
#: Recorded rather than tidied away, because the shape recurs: it is the
#: same defect as `check_typescript_compiles` deciding membership by walking
#: up to a tsconfig that matched everything (Part 14), and as a citation
#: guard parsing zero entries and printing OK (Part 20). The lesson is that
#: a guard must be able to say how much of the world it looked at.
WEB_SERVER = REPO_ROOT / "src" / "web" / "server.ts"

#: `pathname === '/api/stats'`
PATHNAME_EQ_RE = re.compile(r"""pathname\s*===\s*['"`]([^'"`]+)['"`]""")

#: `pathname.match(/^\/api\/jobs\/[a-z0-9_]+$/i)` -- the parameterised
#: routes. The regex body is converted to a route pattern by replacing each
#: character-class or wildcard segment with `:param`.
PATHNAME_MATCH_RE = re.compile(r"""pathname\.match\(\s*/\^(.+?)/[gimsuy]*\s*\)""")

#: Where the router is mounted: `app.use("/api", router)`.
MOUNT_RE = re.compile(r"""app\.use\(\s*['"`](/[^'"`]*)['"`]\s*,\s*router""")

#: Any `/api/...` path in a string or template literal, in any language.
#:
#: The first version matched only Python's `f"{self.base_url}/api/..."`.
#: `examples/nodejs_integration.js` writes `axios.get('/api/health')` and
#: `` `/api/jobs/${jobId}` ``, so it matched NOTHING — and the guard would
#: have reported "no API calls" rather than the eleven wrong endpoints it
#: actually contained. A checker that only understands one of the two
#: example files it is pointed at is a checker with a blind spot the size of
#: the thing it missed.
#:
#: Anchoring on `/api/` rather than on how the base URL is spelled keeps it
#: language-agnostic; `${...}` and `{...}` placeholders are normalised to a
#: wildcard below.
CALL_RE = re.compile(r"""['"`]?(/api/[A-Za-z0-9_/:${}.-]*)""")


def _mount_prefix() -> str:
    if not APP_FILE.is_file():
        raise FileNotFoundError(
            f"{APP_FILE} does not exist, so the route table could not be "
            "read. Refusing to report success: with no routes parsed, every "
            "example endpoint would look wrong, or (worse) the check would "
            "pass vacuously."
        )
    match = MOUNT_RE.search(APP_FILE.read_text(encoding="utf-8"))
    return match.group(1).rstrip("/") if match else ""


def registered_routes() -> set[str]:
    """Every path the Express app serves, mount prefix included."""
    prefix = _mount_prefix()
    routes: set[str] = set()

    sources = [APP_FILE]
    if ROUTES_DIR.is_dir():
        sources += sorted(ROUTES_DIR.glob("*.ts"))

    for path in sources:
        if not path.is_file() or ".test." in path.name:
            continue
        for match in ROUTE_RE.finditer(path.read_text(encoding="utf-8")):
            route = match.group(2)
            if not route.startswith("/"):
                continue
            full = route if path == APP_FILE else f"{prefix}{route}"
            routes.add(full.rstrip("/") or "/")

    routes |= _web_server_routes()
    return routes


def _web_server_routes() -> set[str]:
    """Routes served by the raw-http server in `src/web/server.ts`."""
    if not WEB_SERVER.is_file():
        # Not a silent skip: this file is half the route table, and
        # pretending it is empty is what produced the false accusations
        # documented above.
        raise FileNotFoundError(
            f"{WEB_SERVER} does not exist, so half the API's routes could "
            "not be read. Refusing to check documentation against a route "
            "table known to be incomplete."
        )

    text = WEB_SERVER.read_text(encoding="utf-8")
    routes = {match.group(1).rstrip("/") or "/" for match in PATHNAME_EQ_RE.finditer(text)}

    for match in PATHNAME_MATCH_RE.finditer(text):
        # `\/api\/jobs\/[a-z0-9_]+$` -> `/api/jobs/:param`
        raw = match.group(1).replace("\\/", "/")
        anchored = raw.endswith("$")
        body = raw.rstrip("$")

        segments = [s for s in body.split("/") if s]

        # A segment may be OPTIONAL-SUFFIXED rather than a wildcard:
        # `sweeps?` serves both /sweep and /sweeps; `batch(?:es)?` serves both
        # /batch and /batches. Those spellings exist because the reads are
        # plural and the exports were singular, so a user who had just called
        # /api/sweeps/:id would guess /api/export/sweeps/:id/csv and 404.
        #
        # Recorded as SEPARATE routes, one per spelling. The first version of
        # this parser copied the regex text through verbatim and produced a
        # route literally named `/api/export/batch(?:es)?/:param/csv`, which
        # matched no document -- so adding the alias made the guard report the
        # correctly-documented singular form as nonexistent. A route table
        # that cannot express the routes being served is the same
        # half-a-route-table failure as STAGE_10_PART_24.
        variants: list[list[str]] = [[]]
        for segment in segments:
            options = _segment_spellings(segment)
            variants = [prefix + [option] for prefix in variants for option in options]

        for cleaned in variants:
            # An UNANCHORED pattern ending in `/` is a prefix match:
            # `/^\/api\/batches\//` accepts `/api/batches/<anything>`.
            # Without this the route was recorded as `/api/batches`, which is
            # not a path the server serves -- so a document correctly citing
            # `/api/batches/<id>` would have been reported as wrong.
            tail = cleaned + ([":param"] if (not anchored and body.endswith("/")) else [])
            if tail:
                routes.add("/" + "/".join(tail))

    return routes


#: `sweeps?` -> sweep, sweeps.  `batch(?:es)?` -> batch, batches.
_OPTIONAL_GROUP = re.compile(r"^([A-Za-z0-9_-]+)\(\?:([A-Za-z0-9_-]+)\)\?$")
_OPTIONAL_CHAR = re.compile(r"^([A-Za-z0-9_-]+)([A-Za-z0-9_-])\?$")


def _segment_spellings(segment: str) -> list[str]:
    """Every literal spelling one regex path segment accepts."""
    match = _OPTIONAL_GROUP.match(segment)
    if match:
        return [match.group(1), match.group(1) + match.group(2)]

    match = _OPTIONAL_CHAR.match(segment)
    if match:
        return [match.group(1), match.group(1) + match.group(2)]

    # Anything else containing regex metacharacters is a value the caller
    # supplies, not a spelling of a fixed segment.
    if re.search(r"[\[\].*+()?]", segment):
        return [":param"]

    return [segment]


def _to_pattern(route: str) -> re.Pattern[str]:
    """Turn `/api/simulate/:jobId` into a matcher for a concrete path."""
    parts = [
        r"[^/]+" if segment.startswith(":") else re.escape(segment)
        for segment in route.strip("/").split("/")
    ]
    return re.compile("^/" + "/".join(parts) + "$")


def _is_prose(line: str, state: dict) -> bool:
    """Whether this line is a comment or docstring rather than code.

    Needed because the guard's own fix notes list the endpoints that USED to
    be wrong. Flagging a comment that documents a past defect would make the
    only honest way to record the history a build failure — which is a good
    way to teach people to delete the history.

    Tracks Python `\"\"\"` docstrings and JS `/* */` blocks, and skips `#`,
    `//` and `*` line comments. Deliberately simple: it only has to be right
    about the two example files, and being wrong in the safe direction
    (treating code as prose) costs a missed check, not a false alarm.
    """
    stripped = line.strip()

    if state.get("in_block"):
        if state["in_block"] in stripped:
            state["in_block"] = None
        return True

    for opener, closer in (('"""', '"""'), ("'''", "'''"), ("/*", "*/")):
        if stripped.startswith(opener):
            # A docstring opened and closed on one line is wholly prose.
            if stripped.count(opener) < 2 and closer not in stripped[len(opener):]:
                state["in_block"] = closer
            return True

    return stripped.startswith(("#", "//", "*"))


def example_calls(path: pathlib.Path) -> list[tuple[int, str]]:
    """(line number, endpoint) for each API call in an example file."""
    calls: list[tuple[int, str]] = []
    state: dict = {"in_block": None}
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if _is_prose(line, state):
            continue
        for match in CALL_RE.finditer(line):
            endpoint = match.group(1).rstrip("/") or "/"
            # `{job_id}` (Python) and `${jobId}` (JS template literal) are
            # both values the caller supplies -- the same role `:jobId`
            # plays on the server side.
            endpoint = re.sub(r"\$?\{[^}]*\}", ":param", endpoint)
            calls.append((number, endpoint))
    return calls


# ---------------------------------------------------------------------------
# CLASSIFICATION: which markdown mentions of `/api/...` are actually claims
# ---------------------------------------------------------------------------
#
# Everything below exists to answer one question per mention: is this
# document telling a reader they may call this address? Only then is a
# missing route a defect. Every rule here was written against a line that
# really appears in this repository, and the line is quoted, so that a
# future reader can tell a rule that earned its place from a rule that was
# added to make the build green.

#: ```typescript / ~~~bash — the start or end of a fenced block.
FENCE_RE = re.compile(r"^\s*(?:```|~~~)")

#: A line that DEFINES a route rather than calls one.
#:
#:     if (pathname === '/api/custom' && req.method === 'POST') {
#:
#: `COMPLETE_GUIDE.md` and `WEB_INTERFACE.md` both have a section titled
#: "Add a New API Endpoint" whose sample code invents `/api/custom` on the
#: spot. Reporting that as a nonexistent endpoint is backwards: the whole
#: point of the passage is that it does not exist yet and here is how you
#: would add it. Only endpoints the block itself defines are excused, and
#: only inside that block — a `curl` in the same document is still checked.
ROUTE_DEFINITION_RE = re.compile(
    r"""pathname\s*===|pathname\.match\s*\("""
    r"""|(?:router|app|server)\.(?:get|post|put|patch|delete|all|use)\s*\("""
    r"""|^\s*case\s+['"`]|^\s*location\s+/"""
)

#: Words that turn a mention into a WARNING about the endpoint.
#:
#:     **Note:** `/api/literature/search` does NOT exist (...)
#:     - ⚠️ WEB_INTERFACE.md (lists non-existent /api/literature/search)
#:     > A `GET /api/literature/search` endpoint was listed here and has been
#:     > removed: it does not exist on either server.
#:
#: These are the repository's own corrections for the two real defects Part
#: 24 found. A guard that fails the build because a document says an
#: endpoint is fake teaches exactly one lesson: delete the correction. The
#: negation has to be searched across the whole paragraph because the
#: sentence wraps — "has been" ends one line and "removed" begins the next.
NEGATION_RE = re.compile(
    r"""does\s+not\s+exist|does\s*n['’]t\s+exist|do\s+not\s+exist"""
    r"""|never\s+existed|no\s+longer\s+exists?|non-?existent"""
    r"""|no\s+such\s+(?:route|endpoint|path)|phantom|fabricated"""
    r"""|exists?\s+on\s+neither|not\s+on\s+either"""
    r"""|been\s+removed|was\s+removed|not\s+implemented""",
    re.IGNORECASE,
)

#: The paragraph window for NEGATION_RE. A correction banner is a handful of
#: wrapped lines; an endpoint TABLE can be forty. Without the cap, one
#: "…does not exist" footnote sitting inside a long unbroken table would
#: excuse every row above it — which is how a rule meant to prevent false
#: positives starts causing false negatives instead. Beyond the cap the
#: negation must be on the mention's own line.
NEGATION_PARAGRAPH_MAX_LINES = 10

#: A line PROPOSING an endpoint rather than documenting one.
#:
#:     - Add `/api/jobs/:jobId/export?format=csv|json|bibtex|pdf`
#:
#: from `IMPROVEMENT_ROADMAP.md`, under "**Implementation:**". Nothing about
#: that line claims the route exists today; it claims the opposite. The verb
#: list is deliberately short and imperative — `support`/`provide` were left
#: out because they read as nouns as often as verbs ("- Support for /api/x"
#: is a claim, not a plan).
PROPOSAL_RE = re.compile(
    r"""^\s*[-*+]\s*\[\s\]"""
    r"""|^\s*(?:[-*+]|\d+\.)\s*(?:\*\*)?"""
    r"""(?:add|create|implement|build|expose|introduce)\b"""
    r"""|\bTODO\b|\bFIXME\b|\bwould\s+add\b|\bnot\s+yet\s+implemented\b""",
    re.IGNORECASE,
)

#: `## Next Steps`, `## Roadmap`, `### Future Work` — a section whose whole
#: subject is what does not exist yet. Only LIST ITEMS inside such a section
#: are excused, and only when they are not shaped like an invocation: a
#: `curl` or `fetch` under a Roadmap heading is still a runnable instruction
#: a reader will paste, and still gets checked.
FORWARD_LOOKING_HEADING_RE = re.compile(
    r"next\s+steps|roadmap|future|planned|proposed|backlog|wish\s*list"
    r"|not\s+implemented|ideas?\b",
    re.IGNORECASE,
)
LIST_ITEM_RE = re.compile(r"^\s*(?:[-*+]|\d+\.)\s")
INVOCATION_RE = re.compile(r"curl|fetch\(|axios|requests\.|http://|https://|\$\s")
HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.*)")

#: `/api/...` as it appears in PROSE, which has a looser alphabet than code:
#: `*` (wildcard or markdown bold), `<jobId>` (angle placeholder), and a
#: trailing `/` (a prefix) all occur.
#:
#: `*` is the delicate one. `**POST /api/simulate**` is bold markup around a
#: real claim, while `/api/jobs/*` is a family of routes; treating every `*`
#: as a wildcard would have silently excused the first, which is a false
#: NEGATIVE in a guard whose whole purpose is catching that claim. So the
#: wildcard test is `/` immediately before the `*`, not `*` anywhere.
DOC_MENTION_RE = re.compile(r"(/api/[A-Za-z0-9_/:$.*<>{}-]*)")


def _normalise_mention(raw: str) -> tuple[str, bool]:
    """`(endpoint, names_a_family)` for one raw `/api/...` match.

    A family is a prefix rather than an address: `/api/jobs/*` in a summary
    table, `location /api/ {` in the nginx config in `DEPLOYMENT_AND_OPS.md`,
    `http://localhost:3000/api/*` in a "what is running" list. None of them
    can be looked up in a route table, and none of them is wrong.
    """
    core = raw.rstrip("*").rstrip(".,;:!?)]'\"`")
    family = core.endswith("/")

    # `{job_id}` (Python), `${jobId}` (JS template literal) and `<jobId>`
    # (prose) are all the value the caller supplies -- the same role `:jobId`
    # plays on the server. Prose is the one that matters here: without it
    # `curl http://localhost:3000/api/jobs/<jobId>` in WEB_INTERFACE.md
    # truncates at the `<` to `/api/jobs`, which is not a route, and a
    # correct instruction gets reported as a 404.
    endpoint = re.sub(r"\$?\{[^}]*\}|<[^>]*>", ":param", core)
    endpoint = endpoint.rstrip("/") or "/"
    return endpoint, family or endpoint == "/api"


def _paragraph_map(lines: list[str]) -> dict[int, tuple[str, int]]:
    """Line index -> (joined text of its paragraph, paragraph line count).

    A lone `>` is a blank line inside a blockquote, and separates paragraphs
    the same way a truly empty line does.
    """
    result: dict[int, tuple[str, int]] = {}
    index = 0
    while index < len(lines):
        if lines[index].strip() in ("", ">"):
            index += 1
            continue
        end = index
        while end < len(lines) and lines[end].strip() not in ("", ">"):
            end += 1
        blob = " ".join(lines[index:end])
        for inner in range(index, end):
            result[inner] = (blob, end - index)
        index = end
    return result


def _fence_definition_map(lines: list[str]) -> dict[int, set[str]]:
    """Line index -> endpoints DEFINED by the fenced code block it sits in.

    Two passes over each block, because the comment naming the endpoint
    precedes the code defining it:

        // GET /api/custom
        if (pathname === '/api/custom' && req.method === 'GET') {

    Both lines are excused, and only for `/api/custom`. An unterminated
    fence is treated as no fence at all -- the safe direction is to CHECK,
    since a missed exclusion is a visible false alarm while a missed check
    is invisible.
    """
    result: dict[int, set[str]] = {}
    start: int | None = None

    for index, line in enumerate(lines):
        if not FENCE_RE.match(line):
            continue
        if start is None:
            start = index
            continue

        body = range(start + 1, index)
        defined: set[str] = set()
        for inner in body:
            if not ROUTE_DEFINITION_RE.search(lines[inner]):
                continue
            for match in DOC_MENTION_RE.finditer(lines[inner]):
                defined.add(_normalise_mention(match.group(1))[0])
        for inner in body:
            result[inner] = defined
        start = None

    return result


def doc_mentions(path: pathlib.Path) -> list[tuple[int, str, str | None]]:
    """(line, endpoint, exclusion reason or None) for a markdown document."""
    lines = path.read_text(encoding="utf-8").splitlines()
    paragraphs = _paragraph_map(lines)
    definitions = _fence_definition_map(lines)

    mentions: list[tuple[int, str, str | None]] = []
    heading = ""

    for index, line in enumerate(lines):
        found = HEADING_RE.match(line)
        if found:
            heading = found.group(1)

        blob, height = paragraphs.get(index, (line, 1))

        # AN ENDPOINT MUST NOT EXCUSE ITSELF. The keyword rules below read
        # the surrounding prose, and the path is not prose -- so the path is
        # blanked out first. Found by mutation test: a fabricated endpoint
        # named `/api/zzzfabricated/status` was waved through, because the
        # word "fabricated" is one of the words that marks a line as a
        # warning ABOUT a fake endpoint. Any route called `/api/add-job`,
        # `/api/nonexistent-check` or `/api/removed-items` would have had
        # the same free pass.
        scrubbed_line = DOC_MENTION_RE.sub(" ", line)
        scrubbed_blob = DOC_MENTION_RE.sub(" ", blob)

        for match in DOC_MENTION_RE.finditer(line):
            endpoint, family = _normalise_mention(match.group(1))
            mentions.append(
                (index + 1, endpoint, _exclusion(
                    endpoint=endpoint,
                    family=family,
                    line=line,
                    scrubbed_line=scrubbed_line,
                    paragraph=(scrubbed_blob, height),
                    heading=heading,
                    defined_here=definitions.get(index, set()),
                ))
            )

    return mentions


def _exclusion(
    *,
    endpoint: str,
    family: bool,
    line: str,
    scrubbed_line: str,
    paragraph: tuple[str, int],
    heading: str,
    defined_here: set[str],
) -> str | None:
    """Why this mention is not a claim that the endpoint exists, or None.

    `scrubbed_line` and `paragraph` have every `/api/...` token blanked out;
    see the note in `doc_mentions` for why the keyword rules must not be
    allowed to read the endpoint's own name.
    """
    if family:
        return "names a family/prefix, not an address"

    if endpoint in defined_here:
        return "sample code that DEFINES this endpoint"

    blob, height = paragraph
    if NEGATION_RE.search(scrubbed_line) or (
        height <= NEGATION_PARAGRAPH_MAX_LINES and NEGATION_RE.search(blob)
    ):
        return "a warning that this endpoint does NOT exist"

    if PROPOSAL_RE.search(scrubbed_line):
        return "proposed, not documented as shipped"

    if (
        FORWARD_LOOKING_HEADING_RE.search(heading)
        and LIST_ITEM_RE.match(line)
        and not INVOCATION_RE.search(line)
    ):
        return f"list item under a forward-looking heading ({heading!r})"

    return None


def documentation_files() -> list[pathlib.Path]:
    """Every markdown document held to the route table.

    Refuses to return nothing, for the same reason `registered_routes`
    refuses: a checker that read zero files prints the same "OK" as one that
    read fifty, and the difference is invisible from the outside.
    """
    root_docs = sorted(REPO_ROOT.glob(ROOT_DOC_GLOB))
    docs = root_docs + [path for path in EXTRA_DOC_FILES if path not in set(root_docs)]
    if not docs:
        raise FileNotFoundError(
            f"no {ROOT_DOC_GLOB} documents found at {REPO_ROOT}. Refusing to "
            "report success on an empty document set."
        )
    return docs


def check(verbose: bool = False) -> list[str]:
    """Returns a list of violation strings, empty when every example is true."""
    routes = registered_routes()
    if not routes:
        return [
            "parsed ZERO routes from the api-server. Refusing to report "
            "success: with no route table there is nothing to check against, "
            "and every example would be reported wrong. A guard that cannot "
            "distinguish 'all correct' from 'nothing read' is worse than no "
            "guard, because it is trusted."
        ]

    patterns = [(route, _to_pattern(route)) for route in sorted(routes)]
    violations: list[str] = []
    checked = 0
    excluded: list[str] = []

    def verdict(relative: pathlib.Path, line: int, endpoint: str) -> None:
        nonlocal checked
        checked += 1
        if any(pattern.match(endpoint) for _route, pattern in patterns):
            return
        near = [r for r in sorted(routes) if r.split("/")[:3] == endpoint.split("/")[:3]]
        hint = f" Closest registered: {', '.join(near[:3])}." if near else ""
        violations.append(
            f"{relative}:{line} documents {endpoint}, which the API does "
            f"not serve.{hint} A reader following this example gets a 404 "
            "and concludes the product is broken."
        )

    for path in EXAMPLE_FILES:
        if not path.is_file():
            violations.append(
                f"{path.relative_to(REPO_ROOT)} is listed in EXAMPLE_FILES "
                "but does not exist. Remove it from the list or restore the "
                "file; a missing example silently shrinks what is checked."
            )
            continue

        calls = example_calls(path)
        if not calls:
            violations.append(
                f"{path.relative_to(REPO_ROOT)} yielded no API calls. "
                "Either it stopped describing the API or CALL_RE stopped "
                "matching it; both are worth knowing, and neither is a pass."
            )
            continue

        for line, endpoint in calls:
            verdict(path.relative_to(REPO_ROOT), line, endpoint)

    documents = documentation_files()
    for path in documents:
        if not path.is_file():
            violations.append(
                f"{path.relative_to(REPO_ROOT)} is listed in EXTRA_DOC_FILES "
                "but does not exist. Remove it from the list or restore the "
                "file; a missing document silently shrinks what is checked."
            )
            continue

        relative = path.relative_to(REPO_ROOT)
        mentions = doc_mentions(path)

        if not mentions and path in MUST_DOCUMENT_ENDPOINTS:
            violations.append(
                f"{relative} yielded no API mentions. Either it stopped "
                "describing the API or DOC_MENTION_RE stopped matching it; "
                "both are worth knowing, and neither is a pass."
            )
            continue

        # ORDER MATTERS: resolve against the route table FIRST, and consult
        # the classifier only for mentions that do not resolve.
        #
        # The first version classified first, and excused 52 mentions --
        # most of them naming routes that DO exist, e.g. `/api/jobs/history`
        # on a line beginning "- Add". Excusing a correct mention costs
        # nothing today and coverage tomorrow: the day someone edits that
        # line into a wrong endpoint, the exclusion is already in place and
        # the guard stays green. This way an exclusion can only ever apply
        # to an endpoint that is genuinely absent, which is the only case
        # where the question "is this a claim?" is even being asked.
        for line, endpoint, reason in mentions:
            if any(pattern.match(endpoint) for _route, pattern in patterns):
                checked += 1
                continue
            if reason is not None:
                excluded.append(f"{relative}:{line} {endpoint} — {reason}")
                continue
            verdict(relative, line, endpoint)

    if verbose:
        print(
            f"Mentions of a NONEXISTENT path not treated as claims "
            f"({len(excluded)}):"
        )
        for entry in excluded:
            print(f"  {entry}")
        print()

    if not violations:
        # State how much of the world was looked at. The Part 24 rule: a
        # guard must be able to say what it read, because "OK" on 68
        # endpoints and "OK" on 0 print identically otherwise.
        print(
            f"OK: {checked} endpoint claim(s) across {len(EXAMPLE_FILES)} "
            f"example file(s) and {len(documents)} doc(s) all exist among the "
            f"{len(routes)} routes the API registers. {len(excluded)} further "
            "mention(s) name no route but are wildcards, config, tutorials, "
            "proposals or corrections rather than claims (--verbose to list "
            "them)."
        )
    return violations


def main() -> int:
    verbose = "--verbose" in sys.argv[1:]
    violations = check(verbose=verbose)
    if not violations:
        return 0

    print(f"Example endpoints that do not exist ({len(violations)}):\n")
    for violation in violations:
        print(f"  {violation}")
    print(
        "\nAn example nobody checks is documentation that rots. Fix the "
        "example, or the route."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
