"""`caterva studio`: the desktop app's local server (skeleton; owner: core).

    caterva studio                       serve on 127.0.0.1, a free port, open the browser
    caterva studio --port 0 --no-browser --print-url
                                         what the macOS app runs; prints one line
                                         CATERVA_STUDIO_URL=<url> once serving
    caterva studio --self-test           start, request /api/health and / over a real
                                         socket, print the result, exit 0 or 1

The flags are fixed by docs/studio/CONTRACT.md, because the macOS shell, the
preview launch configurations and CI all pass them; the parser below is
therefore written now, before the server, and `main` refuses to run until
the core owner replaces it.

Exit codes follow the rest of Caterva: 0 served and stopped cleanly (or a
self-test passed), 1 a crash or a failed self-test, 2 a malformed command
line (a non-loopback --host, a port out of range), 3 refused and said why.
"""
from __future__ import annotations

import argparse
import re
import sys
from typing import Optional, Sequence

#: The only hosts the server will bind. Anything else is refused: the
#: server has no authentication beyond a token a page on the same machine
#: can read, so it must not be reachable from another one.
LOOPBACK_HOSTS = ("127.0.0.1", "::1", "localhost")

#: A development origin is another loopback server (Vite), named exactly as
#: the browser will send it in `Origin`: scheme, loopback host, port, no path.
DEV_ORIGIN = re.compile(r"^http://(?:127\.0\.0\.1|localhost):[0-9]{1,5}$")


def build_parser(prog: str = "caterva studio") -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog=prog,
        description=(
            "Serve Caterva Studio: a local page over the same engine the other "
            "commands run, with every number's origin beside it. Loopback only."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            f"  {prog}\n"
            f"  {prog} --port 0 --no-browser --print-url\n"
            f"  {prog} --self-test\n"
            "\nExit codes: 0 stopped cleanly or self-test passed, 2 malformed command line, "
            "3 refused and said why, 1 a crash or a failed self-test."
        ),
    )
    p.add_argument("--host", default="127.0.0.1",
                   help="loopback address to bind: 127.0.0.1 (default), ::1 or localhost")
    p.add_argument("--port", type=int, default=0,
                   help="port to bind; 0 (default) picks a free one")
    p.add_argument("--no-browser", action="store_true",
                   help="do not open the default browser")
    p.add_argument("--dev-origin", metavar="URL",
                   help="also accept requests from this origin (a Vite dev server); development only")
    p.add_argument("--data-dir", metavar="PATH",
                   help="where runs and settings are kept (default: the platform's application data folder)")
    p.add_argument("--print-url", action="store_true",
                   help="print CATERVA_STUDIO_URL=<url> on one line once serving")
    p.add_argument("--self-test", action="store_true",
                   help="start, request /api/health and / over a real socket, report, exit 0 or 1")
    return p


def main(argv: Optional[Sequence[str]] = None, prog: str = "caterva studio") -> int:
    parser = build_parser(prog)
    args = parser.parse_args(argv)
    if args.host not in LOOPBACK_HOSTS:
        parser.error(f"--host {args.host!r} is not a loopback address; the studio binds only "
                     f"{', '.join(LOOPBACK_HOSTS)}")
    if not 0 <= args.port <= 65535:
        parser.error(f"--port {args.port} is not a port number (0 picks a free one)")
    if args.dev_origin is not None and not DEV_ORIGIN.match(args.dev_origin):
        parser.error(f"--dev-origin {args.dev_origin!r} is not a loopback origin such as "
                     "http://127.0.0.1:18741 (scheme, host and port, nothing else)")
    print(
        f"{prog}: the server is not built yet. This is the skeleton the contract "
        "(docs/studio/CONTRACT.md) was committed with.",
        file=sys.stderr,
    )
    return 3


if __name__ == "__main__":
    sys.exit(main())
