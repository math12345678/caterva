# BRENDA pages behind the Ki-mode tests

Real pages, fetched from BRENDA and stored unmodified (gzipped with
`gzip -9 -n`). `caterva/tests/test_ki_mode.py` parses them with the
literature layer's `parse_brenda_ki_html` and checks that every Ki row it
uses is BRENDA's own, in the order BRENDA lists it, so the rows those tests
choose between are backed by a file and not only by a live run.

| file | source | fetched | sha256 of the uncompressed page |
|---|---|---|---|
| brenda_1.1.1.27.html.gz | https://www.brenda-enzymes.org/enzyme.php?ecno=1.1.1.27 | 2026-09-29 (2026-09-30 01:50 UTC) | d656c642e94db91902a1431545a7deeb0bb3bc04a4127372e05fc2250c476125 |
| brenda_1.4.3.4.html.gz | https://www.brenda-enzymes.org/enzyme.php?ecno=1.4.3.4 | 2026-09-29 (2026-09-30 01:50 UTC) | bcf5d145ef1dbec466f45deb384fc036da20b0c5e65aee3b9ebf34c001bda79e |

What the tests read from them:

- lactate dehydrogenase (1.1.1.27), Homo sapiens: the quinoline sulfonamide
  of ref 739793 (0.00059 mM competitive versus NADH, 0.00252 mM
  noncompetitive versus pyruvate) and gossypol, ref 711801 (LDH-B, LDH-A,
  LDH-C). The older trimmed fixture `Tests/fixtures/brenda_ldh_ki_fixture.html`
  records ref 739793's commentary in different words; BRENDA has since
  rewritten it, and these are the words it serves now.
- monoamine oxidase (1.4.3.4), Homo sapiens: benzylhydrazine and
  phenylhydrazine, ref 702238 (Binda et al. 2008, Biochemistry 47:5616,
  doi:10.1021/bi8002814), the rows that name an isoform and a mode.

These are deliberately NOT in `Tests/fixtures/recorded/`. That directory
replaces live fetches in the API server's tests (`CATERVA_BRENDA_RECORDED`
in `Science-Agent-Pipeline/artifacts/api-server/vitest.config.ts`), and two
things would follow from putting the LDH page there: the 27 API test
files that name LDH would read this recording wherever they reach BRENDA,
a change these files were not made for; and `fetch_brenda_html` decodes a
recording as strict UTF-8, which this LDH page is not. It carries six
single bytes that are not UTF-8, three Latin-1 degree signs (0xB0, the
first at byte 3,392,392) and three Latin-1 multiplication signs (0xD7). A
live fetch goes through `requests`, which replaces such bytes, and the test
decodes the same way.

BRENDA data are licensed CC BY 4.0; cite BRENDA (Chang et al. 2021, Nucleic
Acids Res. 49:D498, doi:10.1093/nar/gkaa1025) with any value taken from
them. To refresh: fetch the URLs again, gzip them here, and update the
hashes and dates; the tests say which rows changed.
