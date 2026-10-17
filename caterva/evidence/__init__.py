"""Claims over pinned evidence (ADR 0179).

A number in a model is traced to a derivation: the rule that produced it,
the inputs it was produced from, byte spans in a pinned page that hold what
the rule read, and the settings it ran with. The modules:

    canonical    one byte string per value, floats refused; digests
    claims       Snapshot, Row, Certificate, Derivation, Refusal, Claim; identities
    bundle       the exchange format a standard-library checker reads
    store        SQLite index + blobs, reverse index, export of one claim's closure
    rows         rows as the literature layer's parser reads them; certificates
    references   BRENDA's literature page for a reference id
    capture      pin every page the resolver reads, and the reference pages
    showcase     the hexokinase bundle, offline, for tests and the ADR

Nothing here is imported by `caterva compose` unless `--claims` is given, and
the checker in `caterva/check/` imports nothing from here.
"""
