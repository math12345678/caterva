# Recorded answers behind the studio's LDH parity tests

`caterva/tests/test_studio_compose.py` holds Caterva Studio's `compose` kind
to `caterva compose` for lactate dehydrogenase (EC 1.1.1.27, Homo sapiens):
the README's pyruvate Km, the quinoline sulfonamide of BRENDA ref 739793 in
a competitive and a noncompetitive model, and the README's gossypol example.
The BRENDA page those runs read is the committed one behind the Ki-mode
tests, `Tests/fixtures/ki_mode/brenda_1.1.1.27.html.gz` (see its README for
why it is not in `Tests/fixtures/recorded/`). An LDH search also asks six
other questions, recorded here so the tests never go live.

| service | host | what | status |
|---|---|---|---|
| NCBI Taxonomy | eutils.ncbi.nlm.nih.gov | esearch `Homo sapiens[Scientific Name]` | 200 |
| UniProt | rest.uniprot.org | `ec:1.1.1.27 AND organism_id:9606 AND reviewed:true`, accession only | 200 |
| PubChem | pubchem.ncbi.nlm.nih.gov | name to CID for `LDH`, `LDHA`, `LDHB`, `LDHC` (names in the rows' commentary) | 404 each, "No CID found" |

6 files, all fetched 2026-10-01 (UTC). Licences: NCBI and PubChem are US
Government works, public domain within the US; UniProt is CC BY 4.0
(cite The UniProt Consortium, Nucleic Acids Res. 53:D609 (2025),
doi:10.1093/nar/gkae1010).

**Format.** Exactly the format of `Tests/fixtures/recorded/http/` (its
README): one gzipped JSON file per request, named by the sha256 of the
request's key, written by `Tests/http_retry.py` under `CATERVA_HTTP_RECORD`
and read under `CATERVA_HTTP_RECORDED`. No request here carries a
credential (`http_retry` refuses to record one), and none was sent with
`NCBI_API_KEY` set.

**How they were made.** From the repository root, with the network
available and `NCBI_API_KEY`, `CORE_API_KEY` and `CATERVA_ENABLE_KEGG`
unset, `CATERVA_HTTP_RECORD` and `CATERVA_HTTP_RECORDED` both naming this
directory's `http/`, and `CATERVA_BRENDA_RECORDED` naming a directory that
holds the ki_mode page re-encoded as UTF-8 (the decoding the tests use),
`caterva compose` was run for the four requests the tests make:

    caterva compose "Michaelis Menten" --subject 1.1.1.27 --organism human --substrate pyruvate
    caterva compose "Michaelis-Menten with a competitive inhibitor" --subject 1.1.1.27 \
        --organism human --substrate pyruvate --inhibitor "<the quinoline of ref 739793>"
    caterva compose "Michaelis-Menten with a noncompetitive inhibitor" ... (the same)
    caterva compose "Michaelis-Menten with a competitive inhibitor" ... --inhibitor gossypol

Then the same four ran again with only `CATERVA_HTTP_RECORDED` set and every
proxy variable pointed at a closed port, and gave the same reports. The
tests go further: `caterva/tests/studio_kinetics_offline.py` makes httpx
refuse any request no recording answers.

**To refresh**: delete `http/`, run the four commands as above, and update
the date here.
