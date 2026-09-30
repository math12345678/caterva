"""Caterva Studio: a local window onto the engine the command line runs.

WHY A SERVER AT ALL
-------------------
Every capability here already exists as a `caterva <command>`, and each one
prints a report a person has to read in a terminal: the verdict, the table
of where each number came from, the refusal and its reason. A research
group or a teaching lab mostly does not live in a terminal, and a report
that scrolls away cannot be reopened, compared or exported. The studio is
a browser page (inside a native macOS window, or any local browser) over a
small HTTP server that calls THE SAME library functions the CLI calls and
hands their results over as JSON, so the page can draw them.

WHAT IT REFUSES TO BE
---------------------
A second implementation. No adapter here derives a number, rounds one
differently, or supplies one the engine did not produce: each adapter turns
a JSON request into the argv the CLI would parse, parses it with that
command's own parser, calls the library, and serialises what came back
with its provenance attached (`contract.py`). A parity test per adapter
proves the JSON equals what the CLI computes for the same input.

A network service. It binds loopback only, checks every request's Host
header against the bound address (DNS rebinding), refuses any Origin but
its own and an explicit development origin, and requires a per-launch
session token on every `/api/` request. The rules are in
docs/studio/CONTRACT.md, section "Security".

A new dependency. The server is the standard library's `http.server`; the
app is frozen with PyInstaller and pyproject pins every dependency, so
nothing is added to either for this.

Layout (ownership is in docs/studio/CONTRACT.md, "Ownership map"):

    contract.py        request/response shapes and the provenance helpers
    routes.py          the API route table, as data
    adapters/          one module per CLI command family, each with
                       register(registry)
    __main__.py        `caterva studio`
"""
