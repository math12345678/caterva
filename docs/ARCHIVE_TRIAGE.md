# Root document triage

The repository root held **81 markdown files**. Eighteen opened with a
hand-written banner admitting their own numbers were unverified, and nine
separately claimed to be the "complete" or "final" description of the
system.

Each was read and classified by content, not filename. A grandiose name is
not evidence of a bad document, and a modest one is not evidence of a good
one.

| class | count | goes to |
|---|---|---|
| KEEP | 14 | [`main`](https://github.com/math12345678/caterva) |
| WIRING | 3 | [`wiring-main`](https://github.com/Terrium-sim/wiring-main) |
| MISC | 6 | [`miscellaneous`](https://github.com/Terrium-sim/miscellaneous) |
| ARCHIVE | 58 | [`archive`](https://github.com/Terrium-sim/archive) |

Nothing is deleted. `archive` keeps the record of how the project got here,
including several documents whose mistakes are worth remembering.

## Full classification

| file | class | reason |
|---|---|---|
| `ADVANCED_FEATURES_SUMMARY.md` | ARCHIVE | Session report; own banner flags fabricated LOC and test figures |
| `API_DOCUMENTATION.md` | KEEP | Rewritten as an honest signpost to build-checked docs/API.md |
| `API_QUICK_REFERENCE.md` | KEEP | Accurate web-server endpoint cheat-sheet |
| `ARCHITECTURE_DECISIONS.md` | ARCHIVE | Invented ADR-0001..7 for another codebase; real set is docs/adr/ |
| `ARCHITECTURE_QUICK_REFERENCE.md` | ARCHIVE | Line numbers wrong at commit time; docs/ARCHITECTURE_RIGOR.md covers it |
| `BUILD_COMPLETE_SUMMARY.md` | ARCHIVE | "178 tests/84%/PRODUCTION READY" stale and false |
| `BUILD_STATUS_SUMMARY.md` | ARCHIVE | Duplicated by the fuller WIRING_VERIFICATION_REPORT |
| `BUILD_VERIFICATION_SUMMARY.md` | ARCHIVE | Stage-4 snapshot; counts stale per its own banner |
| `CHANGELOG.md` | KEEP | Honest date-grouped changelog |
| `CODE_OF_CONDUCT.md` | KEEP | Standard and current |
| `CODE_QUALITY_IMPROVEMENTS.md` | ARCHIVE | Superseded by _COMPREHENSIVE then _FINAL |
| `CODE_QUALITY_IMPROVEMENTS_COMPREHENSIVE.md` | ARCHIVE | Superseded by CODE_QUALITY_IMPROVEMENTS_FINAL |
| `CODE_QUALITY_IMPROVEMENTS_FINAL.md` | ARCHIVE | Re-summarised by COMPLETE_REFACTORING_SUMMARY |
| `COMPLETE_BUILD_REPORT.md` | ARCHIVE | LOC claims verified inflated (400+ vs 217, 12,000 vs 9,600) |
| `COMPLETE_BUILD_SESSION_SUMMARY.md` | ARCHIVE | Describes metrics.ts files that never existed |
| `COMPLETE_GUIDE.md` | ARCHIVE | One of nine near-identical guides; stale counts |
| `COMPLETE_REFACTORING_SUMMARY.md` | ARCHIVE | Historical narrative; no current instruction value |
| `COMPREHENSIVE_GUIDE.md` | KEEP | Fullest user manual; CLI commands independently verified |
| `COMPREHENSIVE_TEST_SUITE.md` | ARCHIVE | Blueprint whose import paths and coverage config do not exist |
| `CONTINUATION_FINAL_STATUS.md` | ARCHIVE | "819+ blocks across 49 files" fabricated |
| `CONTRIBUTING.md` | KEEP | Current and accurate |
| `DASHBOARD_INTEGRATION_GUIDE.md` | ARCHIVE | Targets deleted metrics.ts and wrong endpoint paths |
| `DATA_QUALITY_AND_REPRODUCIBILITY.md` | MISC | Aspirational framework; no implemented process behind it |
| `DELIVERABLES_SUMMARY.md` | ARCHIVE | Own banner says NOT production ready |
| `DELIVERY.md` | ARCHIVE | "65 tests" stale |
| `DEPLOYMENT_AND_OPS.md` | WIRING | Docker sections verified; K8s/CI-deploy aspirational |
| `DEVELOPER_EXPERIENCE_GUIDE.md` | MISC | Generic onboarding advice; overlaps CONTRIBUTING |
| `DOCUMENTATION_INDEX.md` | ARCHIVE | Index of a doc set now dispersed |
| `EVERYTHING_COMPLETE.md` | ARCHIVE | "197+ PASSING" untraceable; omits real /api/compare |
| `EXPORT_AND_ANALYSIS_GUIDE.md` | KEEP | Documents export routes that genuinely exist |
| `FEATURES_COMPLETE.md` | ARCHIVE | 197+/84% unverified; duplicated by API_QUICK_REFERENCE |
| `FEATURE_MODEL_COMPARISON.md` | KEEP | Independently verified accurate |
| `FEATURE_SWEEP_COMPLETE.md` | ARCHIVE | Jest transcript appears synthesized |
| `FINAL_DELIVERY_SUMMARY.md` | ARCHIVE | Own header concedes it fails the coverage gate |
| `FINAL_SESSION_REPORT.md` | ARCHIVE | Near-duplicate of EVERYTHING_COMPLETE |
| `FIXES_FROM_REAL_TESTING.md` | ARCHIVE | Its central "fix" was reverted in Stage 10 Part 24 |
| `FULL_SESSION_IMPROVEMENTS.md` | ARCHIVE | "51 test files" wrong (22) |
| `IMPLEMENTATION_COMPLETE.md` | ARCHIVE | "PRODUCTION READY" false; module list incomplete |
| `IMPROVEMENT_ROADMAP.md` | ARCHIVE | Phase 1-3 items already shipped |
| `LITERATURE_BACKED_INTEGRATION.md` | ARCHIVE | Code snippets do not match source |
| `LITERATURE_BACKED_SYSTEM.md` | ARCHIVE | Four irreconcilable test counts |
| `LITERATURE_BACKING_DATABASE.md` | MISC | Real bibliography, but totals do not reconcile |
| `LITERATURE_INTEGRATION_GUIDE.md` | MISC | Design spec for a schema that is not implemented |
| `LIVE_DASHBOARD_BUILD_SUMMARY.md` | ARCHIVE | Describes a metrics system that fabricated data |
| `NEXT_STEPS.md` | ARCHIVE | Expected counts contradicted by the README |
| `OPERATIONAL_EXCELLENCE_GUIDE.md` | ARCHIVE | Runbooks for a service that does not exist |
| `OVERNIGHT_LOG.md` | ARCHIVE | Append-only autonomous-cycle log; purely historical |
| `PERFORMANCE_BENCHMARKING_GUIDE.md` | ARCHIVE | Own banner: no benchmark ever ran; latencies invented |
| `PHASE_2_ENHANCEMENTS.md` | ARCHIVE | Phase report; re-documented in current guides |
| `PHASE_3_SUMMARY.md` | ARCHIVE | Superseded by WEB_INTERFACE |
| `PHASE_4_COMPLETE.md` | ARCHIVE | "179 tests" stale |
| `PHASE_4_IMPLEMENTATION.md` | ARCHIVE | Marked IN PROGRESS; superseded by PHASE_4_COMPLETE |
| `PHASE_4_REAL_DATA.md` | ARCHIVE | Pre-work plan; superseded by PHASE_4_COMPLETE |
| `PHASE_4_SETUP_GUIDE.md` | ARCHIVE | Setup for brenda-real.ts, deleted in Stage 10 Part 23 |
| `PHASE_5A_INTEGRATION_GUIDE.md` | KEEP | How-to for buildSBML/runCaterva, both of which exist |
| `PHASE_5A_SUMMARY.md` | ARCHIVE | Superseded by PHASE_5A_INTEGRATION_GUIDE |
| `PHASE_5A_CATERVA_ENGINE.md` | ARCHIVE | Same phase narrative; heavy overlap |
| `QUICK_START.md` | ARCHIVE | Contains invalid `npm build`; COMPREHENSIVE_GUIDE covers the CLI |
| `QUICK_START_DEPLOYMENT.md` | WIRING | Local/Docker steps verified against real docker-compose.yml |
| `QUICK_START_PHASE_4.md` | ARCHIVE | "179 tests" stale; references a throwaway script |
| `README.md` | KEEP | Accurate current entry point |
| `READY_TO_SHIP.md` | ARCHIVE | Corrected twice; superseded by START_HERE + docs/API.md |
| `REALITY_CHECK.md` | ARCHIVE | Describes a fabricated-literature state that Phase 4 removed |
| `REFACTORING_PROPOSAL.md` | ARCHIVE | Proposal already executed; REFACTOR_STATUS records the result |
| `REFACTOR_STATUS.md` | KEEP | Verified record of the engine package split and its guard |
| `RUN_TESTS.md` | WIRING | Test-invocation commands for the api-server workspace |
| `SCIENTIFIC_VALIDATION_FRAMEWORK.md` | MISC | Design doc; signatures differ from the shipped validator |
| `SECURITY.md` | KEEP | Real, honest disclosure policy |
| `SECURITY_AUDIT_CHECKLIST.md` | ARCHIVE | Marks controls IMPLEMENTED for a service that does not exist |
| `SESSION_CONTINUATION_SUMMARY.md` | ARCHIVE | Repeats the fabricated 819+/49 files figure |
| `SESSION_FINAL_DELIVERY.md` | ARCHIVE | "75+ test cases" inflated (real 44) |
| `SESSION_SUMMARY.md` | ARCHIVE | Lists a nonexistent literature endpoint |
| `START_HERE.md` | KEEP | Working quickstart; most accurate of the session batch |
| `TESTING_AND_ROADMAP.md` | MISC | Strategy plus roadmap; no false status claims |
| `TRULY_FINAL_SUMMARY.md` | ARCHIVE | "10 endpoints" wrong (18); three rival "final" docs exist |
| `VERIFIED_SYSTEM_STATUS.md` | ARCHIVE | Self-contradictory (18 vs 11 endpoints); fabricated counts |
| `WEB_INTERFACE.md` | KEEP | Repaired in Part 24; phantom endpoint removed |
| `WIRING_VERIFICATION_REPORT.md` | ARCHIVE | "ZERO STRUCTURAL ERRORS" disproved by Stage 10 Parts 23-24 |
| `findings.md` | ARCHIVE | Audit scratch file; never filled in |
| `progress.md` | ARCHIVE | Audit scratch log; abandoned |
| `task_plan.md` | ARCHIVE | Abandoned plan; five of six phases unchecked |

## The pattern worth naming

Eighteen of these were 'fixed' by adding a correction banner at the top
rather than by correcting the content. That does not work. A reader who has
been told a page is unreliable still reads its endpoint table, because the
table is specific and the disclaimer is vague — specificity reads as
authority.

The fix for a false claim is to make it true or remove it, and then to make
it mechanically checkable so it cannot rot again. That is why
`docs/API.md` carries no banner: `check_example_endpoints.py` fails the
build if it stops being true.
