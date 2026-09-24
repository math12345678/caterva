# Packaged copies of two data files the engine reads at import

The originals are authoritative and stay where the guards, the TypeScript
side and the documentation point at them:

| packaged copy | original |
|---|---|
| `data-sources.json` | `docs/data-sources.json` (the attribution table `scripts/check_data_source_attribution.py` checks against NOTICE) |
| `identifiers_org_namespaces.json` | `Tests/fixtures/identifiers/identifiers_org_namespaces.json` (the dated capture `scripts/check_identifier_patterns_fresh.py` watches) |

`Terium/core/data_sources.py` and `Terium/core/miriam.py` read the original
when it exists (a checkout) and the packaged copy otherwise (an installed
wheel, the app folder). Before v0.3.0 the wheel carried neither file, so
`terium-compose --export sbml` and `--export antimony` crashed with a
`FileNotFoundError` from any installed copy (ADR 0177).

`Terium/tests/test_packaged_data.py` fails if a copy and its original ever
differ, so the two cannot drift apart unnoticed.
