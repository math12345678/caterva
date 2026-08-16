"""Every database Terrium calls at runtime must be recorded in NOTICE.

WHAT THIS COMES FROM
--------------------
`resolve_substrate_from_kegg()` has been calling `https://rest.kegg.jp`
from the server, on the live resolution path, since it was written. KEGG
appeared in neither `NOTICE` nor `Terium/core/data_sources.py`.

KEGG's own terms say it "is not a public database", that non-academic use
"requires a commercial license", and that even academic users providing a
service are asked to obtain a service-provider licence
(https://www.kegg.jp/kegg/legal.html).

`NOTICE` meanwhile records SABIO-RK as deliberately NOT integrated,
because its terms are non-commercial only. So the project had a considered
policy for exactly this situation, and a source with comparable terms got
in anyway — not by a decision that weighed them, but because nobody read
them.

`check_data_source_attribution.py` could not catch it. That guard checks
that everything the `SOURCES` table claims also appears in `NOTICE`, and
its own docstring is explicit that the direction is deliberate. A source
absent from the table is absent from its reach: it verifies the entries
that exist, not that an entry exists.

This is the missing direction. It starts from the network calls in the
code, not from a table someone remembered to update.
"""
from __future__ import annotations

import pathlib
import re
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]

#: Host substring -> the name that must appear in NOTICE near it.
#:
#: Keyed on hostnames because that is what a network call actually
#: contains. A list of "sources we use" maintained by hand is the thing
#: that was already wrong.
LIVE_HOSTS: dict[str, str] = {
    "rest.kegg.jp": "KEGG",
    "brenda-enzymes.org": "BRENDA",
    "eutils.ncbi.nlm.nih.gov": "NCBI",
    "pubchem.ncbi.nlm.nih.gov": "PubChem",
    "api.core.ac.uk": "CORE",
}

#: Hosts that are infrastructure rather than a licensed data source.
NOT_A_DATA_SOURCE: dict[str, str] = {
    "fonts.googleapis.com": (
        "A web font CDN, not a database. Its licensing is fine (OFL/Apache) "
        "and its problem is data protection -- see docs/DATA_PROTECTION.md."
    ),
    "fonts.gstatic.com": "Same as fonts.googleapis.com.",
    "cdnjs.cloudflare.com": "A script CDN, not a data source.",
    "schema.org": "A namespace URI, never fetched.",
    "www.w3.org": "A namespace URI, never fetched.",
    "www.sbml.org": "A namespace URI, never fetched.",
}


def _source_files() -> list[pathlib.Path]:
    listing = subprocess.run(
        ["git", "ls-files", "*.py", "*.ts"],
        cwd=ROOT, capture_output=True, text=True, check=False,
    ).stdout.split()
    return [
        ROOT / rel for rel in listing
        if "node_modules" not in rel and "/tests/" not in rel
        and not pathlib.Path(rel).name.startswith("test_")
    ]


def test_every_host_we_call_at_runtime_is_named_in_notice() -> None:
    """A database queried live is a database whose terms apply."""
    notice = (ROOT / "NOTICE").read_text(encoding="utf-8", errors="replace")
    files = _source_files()
    assert len(files) > 50, (
        f"only {len(files)} source files found; the listing is broken and "
        "this test would pass without examining anything"
    )

    called: set[str] = set()
    for path in files:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for host in LIVE_HOSTS:
            if host in text:
                called.add(host)

    assert called, (
        "no known data-source host was found in any source file. Either the "
        "hosts moved or the scan is broken; both need a person, not a pass."
    )

    # A source is "named in NOTICE" only if it has its own recorded
    # section, not merely a mention in passing. Deleting the KEGG section
    # while the word survived in the CORE paragraph next door passed this
    # check, which made the deletion of a whole licence record invisible.
    missing = [
        f"{LIVE_HOSTS[host]} ({host})"
        for host in sorted(called)
        if not re.search(
            rf"^{re.escape(LIVE_HOSTS[host])}\b.*$\n-+$",
            notice, re.M,
        )
    ]
    assert not missing, (
        "these databases are queried at runtime but are not named in NOTICE: "
        f"{missing}.\nA source called live is a source whose terms apply. "
        "Record it -- creator, licence, and whether use in a service is "
        "permitted -- the way BRENDA and SABIO-RK are recorded."
    )


def test_kegg_terms_are_recorded_as_unresolved_not_as_settled() -> None:
    """The specific finding, pinned so it cannot quietly become 'fine'.

    This test SHOULD start failing once the question is actually resolved
    -- a licence obtained from Pathway Solutions, or the dependency
    removed. Failing then is correct: it means someone must update NOTICE
    and docs/LICENSING.md to say which happened.
    """
    notice = (ROOT / "NOTICE").read_text(encoding="utf-8", errors="replace")
    assert "KEGG" in notice

    # Scoped to KEGG's own section. The first version of this test searched
    # the whole document, and a mutation that renamed the KEGG heading and
    # replaced "an open question" with "This is fine" passed all four tests
    # -- because the word "UNRESOLVED" still appeared, in the CORE section
    # further up. A keyword found somewhere in a 300-line file is not
    # evidence about the paragraph you meant.
    # Anchored on the HEADING, not on the first "KEGG" anywhere in the
    # file. The earlier version used `notice.index("KEGG")`, which finds a
    # mention in a neighbouring section and slices from there -- so
    # renaming the heading left the slice intact and the check passed.
    heading = "KEGG — queried live, and UNRESOLVED"
    assert heading in notice, (
        "the KEGG heading no longer says UNRESOLVED. A reader skimming "
        "NOTICE's section titles is the reader this flag is for. If the "
        "question was actually resolved, say how."
    )
    start = notice.index(heading)
    end = notice.index("SABIO-RK", start)
    section = notice[start:end]
    # Everything after the heading line. The heading already contains the
    # word "UNRESOLVED", so searching the whole section for it means the
    # heading vouches for the body -- and changing only the body's
    # sentence passed. Two independent statements, each independently
    # checkable.
    body = section.split("\n", 1)[1]

    assert "kegg.jp/kegg/legal" in section, (
        "NOTICE should cite KEGG's own terms page, not paraphrase it"
    )
    for phrase in ("not a public database", "commercial license"):
        assert phrase in section, (
            f"NOTICE no longer quotes KEGG's own words ({phrase!r}). A "
            "paraphrase of a licence is a summary of a licence."
        )
    assert re.search(r"unresolved|open question", body, re.I), (
        "the KEGG section no longer flags the licence question as open. If "
        "it was resolved, say how -- licence obtained from Pathway "
        "Solutions, or the dependency removed -- rather than deleting the "
        "flag."
    )


def test_the_kegg_call_site_still_degrades_rather_than_crashing() -> None:
    """The reason removal is cheap, verified rather than asserted.

    docs/LICENSING.md argues that dropping KEGG costs quality and not
    correctness, because the resolver already handles the lookup failing.
    That argument is only worth making if the fallback is real.
    """
    runner = (
        ROOT / "Science-Agent-Pipeline" / "artifacts" / "api-server" / "src"
        / "lib" / "science_agent_runner.py"
    )
    text = runner.read_text(encoding="utf-8", errors="replace")
    body = text[text.index("def resolve_substrate_from_kegg"):]
    body = body[: body.index("\ndef ", 1)]
    assert "except httpx.HTTPError" in body, (
        "the KEGG lookup no longer catches network failure, so removing "
        "KEGG is no longer the cheap change docs/LICENSING.md claims"
    )
    assert "return None" in body


def test_infrastructure_hosts_are_not_mistaken_for_data_sources() -> None:
    """Crying wolf about a font CDN would get this test switched off."""
    for host, reason in NOT_A_DATA_SOURCE.items():
        assert host not in LIVE_HOSTS, f"{host} is classified twice"
        assert len(reason) > 20, f"NOT_A_DATA_SOURCE[{host!r}] gives no reason"
