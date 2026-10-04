# Changelog

> **⚠️ CORRECTION (2026-08-12):** the `## Unreleased` section's counts are stale — the repo has moved well past the state they describe:
> - **"11 guard scripts"**: running `python3 scripts/verify_build.py --quick` today shows the Guard Wiring Guard reporting **"all 22 guards run in at least one harness"** — 22 guards now exist, not 11.
> - **"Engine test suite: 715 -> 883 tests"**: `python3 -m pytest --collect-only` in `caterva/` now collects **1,014** tests.
> - **"Literature test suite: 182 -> 214 tests"**: `Tests/` now collects **277** tests.
> - **"TypeScript test suite: 111 -> 224 tests (16 files)"**: `Science-Agent-Pipeline/artifacts/api-server` now has **433** test cases across **32** `*.test.ts` files (`npx vitest list`).
> This is ordinary changelog staleness (the Unreleased section wasn't updated as later work landed, and later work was logged in `OVERNIGHT_LOG.md` instead — see that file's own correction banner for the same underlying drift), not fabrication.

This file follows [Semantic Versioning](https://semver.org/) from 0.1.0
onward and [Keep a Changelog](https://keepachangelog.com/) in shape.
Entries before 0.1.0 are grouped by date, because that is how the work was
done: there was no release to version.

## [0.5.0] - 2026-10-03

Caterva Studio, the enzyme finder, and a Mac app, on top of the tools listed
below them.


### Fixed
- The packaged app and Caterva Studio's network status: the standard library's HTTPS found no certificate authorities in a frozen app (its OpenSSL looks for a file on the machine that built it), so the studio's reachability check and the RCSB download in `caterva complex` failed with a certificate error while the literature lookups beside them worked, and the status bar reported the network as down on a network that was up. The app now points OpenSSL at the certificate bundle it ships (`caterva/tls.py`) when no certificate setting of the user's own exists, and the status line explains a certificate failure in plain words. The status bar also checks the network once when the app opens, so it no longer opens on "network not checked".
### Added
- **Caterva Studio**, `caterva studio`: a local window onto the commands. A server on this computer (127.0.0.1 only, a fresh session key every launch, no outside origin accepted) calls the library functions the commands call, keeps every run in a workspace folder, and serves a page that marks each number as a cited measurement, a fit, a computation, a value you chose, or a placeholder with its reason. Screens: Home (one written line starts a model), Compose, Constants (every BRENDA row the resolver read, with its reference, organism, conditions and the row's own words), Stochastic (`caterva sim ssa`), Binding (`caterva bind`), Structures (with a 3D view of the chosen entry), Prepare, Dynamics (`caterva md`, and `--summarise` for finished replicas), Analyze, History (search, reopen, export as a zip, delete with an undo), Settings and About. A parity test per adapter holds the studio's numbers equal to the command's for the same inputs. There is no Rates screen yet: `caterva rates` works in the terminal, and its Studio screen is reserved and hidden. The server's contract is `docs/studio/CONTRACT.md` and the guide `docs/studio/USING_STUDIO.md`. Run it from a checkout with `make studio`, or install the DMG. The wheel and the plain app folder carry no built page: `caterva studio` there serves a page saying so (the page comes with the DMG, or from `make studio-page` in a checkout). `caterva studio --self-test` starts the server on a free port, requests `/api/health` and `/` over a real socket and exits 0 or 1. Two servers on one data folder share `settings.json` last-writer-wins, and a server started in the background stops about a second after the shell that started it exits; both are written down in `docs/studio/README.md`.
- **`caterva enzyme NAME`**: which enzyme a name, EC number or partial EC number means. It prints every enzyme that matches with why it matched, its reaction and class, the organism's proteins, and the exact `caterva compose ... --subject EC` line to use. Exit 0 when it resolved or listed candidates, 3 when nothing matched (with did-you-mean spellings), 2 for a malformed command. It reads the IUBMB nomenclature as ExPASy ENZYME distributes it (SIB Swiss Institute of Bioinformatics, CC BY 4.0, release 02-Sep-2026), reduced to a packaged index (`caterva/enzymes/data/`, built by `scripts/build_enzyme_index.py`) and credited in NOTICE. A phrase inside a longer name, or words spread over one, is a fragment: it is listed and ranked, never resolved to on its own ("angiotensin converting enzyme" is ACE, EC 3.4.15.1, not the start of "angiotensin-converting enzyme 2").
- **One name policy.** `caterva compose --subject`, `caterva structure`, `scripts/cite.py`, the report and catalog scripts and the API server's runner all resolve an enzyme name through the same function: the nomenclature first, UniProt's protein-name search only for a name the nomenclature does not hold. So `--subject "hexokinase"` is resolved **offline**; a name that means more than one enzyme is refused with each candidate named ("EC 1.1.1.27 L-lactate dehydrogenase (human: LDHA, LDHB, ...)") and the flag to re-run with. compose says what a name was read as, replaces a transferred EC number and says so, and refuses a deleted one. `caterva structure` takes a name as well as an EC number.
- **The isozyme notice.** When one EC number is several proteins in the organism asked about (EC 2.7.1.1 is five in human), the constants came from a search, and no `--isoform` was given, the verdict carries a concern naming the isozymes and a qualifier under "What this supports", and the report a "Which isozyme" paragraph beside the constants. GROUNDED is not lowered and no constant changes; the notice stays quiet with `--isoform`, with one protein, with no organism and with an organism the index does not know.
- **Caterva.app and its DMG** (`scripts/build_studio_app.py`, `.github/workflows/studio-dmg.yml`, called by `release.yml`): the studio in its own native window for **Apple silicon Macs on macOS 14 or later**, in a disk image attached to the GitHub Release beside the wheel and the folders. **It is not signed with an Apple Developer ID and not notarised** (the project holds none; the bundle carries an ad-hoc signature, which Apple silicon requires). The DMG's README says how to open it: System Settings, Privacy & Security, Open Anyway, then `xattr -dr com.apple.quarantine /Applications/Caterva.app` if macOS keeps refusing. On a macOS older than 14 the app says so and quits (the wheels it carries, NumPy 2.2.6, SciPy 1.15.3 and libRoadRunner 2.8.0, are built for macOS 14). The shell is Swift (AppKit and WKWebView, compiled with `swiftc`, no Xcode project); `Caterva --smoke` starts the bundled server on a temporary data folder, fetches the page and stops it, and the copy inside the mounted DMG is smoke-tested again. Intel Macs are not built.
- **The literature search ships in every artifact.** The resolvers that read BRENDA (`fallback_logic` and the modules it imports, with `scripts/cite.py` and `scripts/report_lab.py` for Studio's Constants screen) were only in `Tests/`, so an installed wheel could not search and the app folder said so. `scripts/vendor_literature.py` now copies exactly the import closure (found with `ast`) into `caterva/_literature/`, git-ignored and written by `scripts/build_release.py` before the sdist; `caterva.checkout.literature_module` looks in a checkout's `Tests/` first and in that directory second. No fixture or recorded answer is shipped. `caterva compose --subject 2.7.1.1 --organism human --substrate glucose` therefore works from the wheel, the app folder and the app (it reads BRENDA, NCBI, UniProt and PubChem live and needs a network connection). The release build refuses a wheel without it, and `scripts/build_app.py` runs that very command from the frozen folder, offline, against the recorded BRENDA page and database answers in the repository, before the folder is archived.
- **Third-party notices for the page.** The Studio page bundles React, d3, Radix, markdown-it, lucide, recharts and others (88 packages in this build) and three typefaces. The page's build now writes `licenses/THIRD-PARTY-NOTICES.txt` beside it, from the build's own module graph, with each package's licence text, and fails if a bundled package has no licence text or one outside MIT, BSD, ISC, Apache-2.0, 0BSD, OFL-1.1 or the Unlicense. Three packages (`wouter`, `react-remove-scroll-bar`, `victory-vendor`) ship no licence file; their notices are written by the build from the standard text and say so. NOTICE no longer says Caterva bundles none of its dependencies: it lists what the app and the page do carry and where the texts are, and Help, Licences in the app opens them.
- **Studio, hardened and reworked.** The session key now travels in the address's URL fragment and is in no page the server sends; `gromacs_path` is validated and never run by a GET; names from a request or a folder reach no shell script; runs have caps, cancel and limits; the macOS shell is hardened. The page carries 22 design and accessibility fixes (plain wording where the engine speaks in flags, refusals laid out the same way, chart patterns and mark shapes beside colour, a command palette dialog, plurals). The network status is per host: one host failing no longer marks the others unreachable, and the finder's constants and compose screens show the engine's tie reason and isozyme notice with numbers in plain decimals.
- `caterva rates FILE` fits a laboratory's own initial rates: v at several [S], optionally at several [I] and in groups. The CSV names each column's unit, and a unit that cannot be read is refused by column; an amount per volume such as umol/L/min is refused as the molar unit it is. The error bar comes from exactly one source and is never invented: a sigma column, the pooled replicates (`--error-model constant|proportional`, degrees of freedom stated, one sigma across groups, which the report says) or the residuals (OLS, as R's `nls`, with no goodness-of-fit chi-square printed for it). Fitting is weighted least squares in log space with multi-start. Every constant gets a profile-likelihood interval, reported one-sided when the data bound it on one side only, and flagged when it is more than four decades wide. A constant the data do not determine is never printed as a number, in the tables or in the literature comparison: rates far below Km report the Vmax/Km they do determine (for the Hill law, Vmax/K0.5^n is named), and far above Km they report Vmax. The report also says whether the substrate range brackets Km (Assay Guidance Manual, 0.2 to 5 Km). With an inhibitor, competitive, uncompetitive and noncompetitive are tested against mixed. The boundary restrictions use the 50:50 chi-square mixture (Self & Liang 1987). Competitive against uncompetitive is described, not tested. The verdict names the measurement that would decide. Also: lack of fit against pure error; shared-constant tests between groups; and the fitted Km and Ki held against the resolver's BRENDA row (inhibitor name, mode, substrate, isoform), with no ratio to an undetermined constant. Outputs: report, `--json`, `--export csv|curves|methods`, `--show-linearizations` (apparent constants at [I] > 0). On the Puromycin data (Treloar 1974; Bates & Watts 1988; examples/rates/puromycin.csv) it reproduces R 4.6.0's `nls`, `confint` and `anova`. 110 tests.
- `caterva analyze` reports each catalytic residue's solvent-accessible area, which tells whether the active site opens or closes to solvent.
  - **Method.** The surface is the whole protein, with a 0.14 nm probe and Bondi's radii exactly as GROMACS's vdwradii.dat lists them, hydrogens included. Caterva's own route uses Shrake & Rupley's method with 2,000 points per atom. The GROMACS route runs `gmx sasa -surface Protein -nopbc -ndots 2000`, which uses Eisenhaber's double cubic lattice and rounds the request up to 2,252 points per atom. The section names whichever method produced its numbers.
  - **What each residue gets.**
    - its area in em.gro;
    - per replica, the mean ± SD over frames and the range the middle 95% of frames fall in;
    - a share of the largest area its residue type can have (Tien et al. 2013, Table 1: DSSP's heavy-atom scale, so a guide);
    - a verdict: buried below 20%, exposed at 40% or above, both stated choices.
  - **When there is no share or verdict.** A replica whose mean crosses a threshold while its frames still reach the starting state is reported as such and does not count as replicas disagreeing. A residue without a peptide bond on both sides in em.gro (a chain end, or beside a break) gets no share and no verdict.
  - **Two chains.** When more than one chain is simulated with the same numbering, this section says why it is not measured, and the rest of the report is written as before.
  - **CI.** The smoke run compares the two routes' areas to 0.03·√area nm² (at least 0.0075) plus the table's rounding. That bound was chosen over 11,514 measured residue areas, of which the largest difference was 0.0205 nm² and none came nearer than 0.71 of the bound. The smoke run also compares the verdicts.
  - **Exit code.** Exit 0 now says only that every distance and angle is consistent. The verdict tables, this one included, do not set it.
- `caterva analyze` now runs a principal component analysis on the catalytic residues' heavy atoms: backbone and side chain, no hydrogens, 47 atoms on lysozyme. Each frame is superposed on the same atoms of `em.gro` by unweighted least squares. The analysis runs per replica and again with every replica's frames pooled (caterva/analyze/pca.py).
  - **What the report gives:** the three largest eigenvalues (nm²), the total, and the share in PC1 and in PC1-10. The pooled analysis adds the share of the motion that comes from the replicas sitting in different places.
  - **Do the replicas move the same way?** The RMSIP of each pair's first ten modes (Amadei, Ceruso & Di Nola 1999) is printed beside its exact chance level for random subspaces of the 3N-6 directions the fit leaves: RMSIP² = 10/135 = 0.074 ± 0.010 on lysozyme. Verdicts: same motions, partly shared, or no more alike than chance.
  - **Is a replica's largest motion only diffusion?** The cosine content of PC1 and PC2 (Hess 2000, 2002) measures how closely each projection matches the shape random diffusion gives: a one-way drift for PC1, one excursion out and back for PC2. At 0.5 or more, a stated choice, the replica is called diffusion-like, not converged. Beside the values the report prints what time-uncorrelated frames give: a mean of 0.05 at 21 frames, and at most 0.0007 chance of being called diffusion-like on either mode.
  - **No motion:** a replica whose total fluctuation is below 1e-8 nm² is called no motion, and its cosine contents and RMSIP are not reported.
  - **Exit code:** a diffusion-like replica, or a pair of replicas at chance, makes the exit code 4.
  - **Minimum length:** fewer than 21 frames per replica is refused rather than reported.
  - **GROMACS route:** runs `gmx covar` (fit and analysis group the same, no -ref), `gmx anaeig -proj/-over` and `gmx analyze -cc`, and converts gmx's (n+1)/n cosine normalisation.
  - **Checked against GROMACS 2026.1** on a committed lysozyme replica (tests) and on local smoke runs: eigenvalues to 1.3e-5 relative, projections to 5e-6 nm, cosine content to 1.1e-5, RMSIP² to the 0.001 gmx prints.
  - **CI:** `make md-smoke` now keeps 21 frames per replica and compares the two routes' principal-motion tables on every run. At the smoke run's 0.4 ps, the cosine content falls on either side of the threshold and says nothing about the enzyme.
- CI runs the root TypeScript package's tests, which it never had: the
  `scientific` CLI and the literature resolver, 72 files and 944 tests, in
  a new root-typescript job with a type-check and a step that fails if jest
  ran fewer files than are on disk. All 944 passed on the first run. Four
  files written in this cycle for vitest could not load under the package's
  runner (jest); they were converted without changing an assertion.
  `make test-ts` runs the same steps locally.
- `scientific simulate --resolve --model competitive|noncompetitive|product`
  looks its Ki up under `--inhibitor` for the model's mode, with `--substrate`
  as the model's substrate, and refuses without an inhibitor; until now it
  asked BRENDA for a Ki "of" the substrate. It takes `--isoform`, and
  `--allow-cross-species` (listed in its help since 2026-08-18) now reaches
  its lookups, which it never did. `product` asks for a noncompetitive Ki:
  this CLI's product model integrates the noncompetitive rate law with P for
  I, which a test pins. A successful run reports the Ki's inhibitor, mode and
  source row through `--json` and the exports. Custom-model `ki` annotations
  take `inhibitor=` and `inhibition=`, and one naming no inhibitor is not
  looked up. The TypeScript CLI also dropped the runner's `referenceId`
  ("Citation BRENDA", "BRENDA ref ?"); it now prints the reference. The
  README's inhibition example, which could not run, is replaced by one that
  does (Ki 0.00252 mM, BRENDA 739793).
- The isoform reader reads the names BRENDA writes with a space ("isoform
  MAO B", "hexokinase 2"), reads a request the way it reads a row, and no
  longer reads plurals or strain codes as isoforms; every Ki, Km and kcat
  row on the committed BRENDA pages was audited. `caterva compose` now asks
  the resolver for its isoform and mode, so both rank before the evidence
  frontier and carry the same row (T. cruzi hexokinase and ADP: 1.5 mM on
  both); the README examples are unchanged.
- The API and `scientific resolve` say when a row is evidence against the
  model's mechanism, as compose does, from the same Python function: for
  BRENDA 739793 a competitive pyruvate model is told that, measured against
  pyruvate, the inhibitor is noncompetitive (0.00252 mM).
- The API and `scientific resolve` choose a Ki row by the model's
  inhibition mode, with `caterva compose`'s ranking, which now lives in one
  place (caterva/compose/ki_mode.py). The resolver narrows the pool before a
  row is chosen (`inhibition_mode=`, `model_substrate=`), and refuses a Ki
  held only for other mechanisms as `mode_withheld`, naming the modes. The
  API sends "competitive" for mm_competitive_inhibition with the model's
  substrate; the CLI takes `--mode` and `--model-substrate`. BRENDA 739793:
  noncompetitive gives 0.00252 mM, uncompetitive is refused naming both
  rows. One known difference, pinned by a test: for T. cruzi hexokinase and
  ADP the resolver, ranking before its evidence frontier, gives 1.5 mM
  ("competitive to ATP") where compose, ranking only the frontier, carries
  1.3 mM.
- `caterva analyze` says which face of each angle's vertex its partners are
  on: the elevation of the vertex's arm to its own Cα out of the plane of
  the angle, signed like the dihedral a-v-b-Cα (the dihedral itself has no
  value when the Cα lines up, which happens in lysozyme). A frame counts on
  a face only outside a 7.5-degree dead band. Equal to `gmx gangle -g1
  plane -g2 vector` to 0.001 degree on 24 angles x 21 frames, as stored and
  across the periodic box; the smoke job compares the routes, tolerating one
  frame on the band edge, which gangle's 0.001-degree output can put on the
  other side.
- `caterva compose` takes a Ki from a row whose stated inhibition mode fits
  the model (caterva/compose/ki_mode.py). BRENDA 739793 gives human LDH two
  Ki for one quinoline sulfonamide: 0.00059 mM "competitive versus NADH" and
  0.00252 mM "noncompetitive versus pyruvate". A noncompetitive model carried
  the first while its own report called it the wrong mechanism; it now
  carries the second. A row of the model's mode wins (mixed counts for
  noncompetitive; versus the model's substrate first), then a row stating
  none, and a constant held only for other modes is refused naming them;
  `--any-mode` keeps the resolver's pick. With `--isoform`, the isoform is
  chosen first. Kitz-Wilson rows (irreversible inactivation) rank last and
  are named as such. `caterva bind` now reads "mixed inhibitor versus X".
  Rows are checked against unmodified BRENDA pages in Tests/fixtures/ki_mode/.
- `caterva analyze` measures the angle at each catalytic group between two
  partners in contact with it in the crystal, on both routes (`gmx gangle`
  on the GROMACS route; equal to it to 0.001 degree on 21 real frames, also
  across the periodic box). Each angle is fixed by three distances the
  report already has, and the report says so: it adds the triangle's shape
  at one group and a verdict, not new information, and it cannot tell which
  face a partner is on.
- `caterva analyze` counts water at each catalytic residue: water oxygens
  within 0.35 nm of its functional atoms per frame, per replica, beside
  em.gro's count (`gmx select` on the GROMACS route; equal per frame on real
  frames with water, also across the box). `make md-smoke` compares both
  new tables across the routes.
- The API tests no longer call NCBI, UniProt or PubChem: `retry_get`
  replays real recorded responses when `CATERVA_HTTP_RECORDED` is set (the
  API test config sets it beside `CATERVA_BRENDA_RECORDED`). Requests that
  may carry a credential are never recorded or replayed (headers are an
  allowlist). `scripts/record_http_fixtures.py` records the 13 runner
  payloads the tests send and proves each replays with the network refused;
  42 recordings, 15,672 bytes. A test fails if anything outside test
  configuration sets either variable.
- The API's row-scope flags know the isoform the query named.
- `caterva bind`: cited Ki values become ΔG°bind targets at their own
  assay temperatures, filtered by inhibition mode (`--state free|ternary`)
  and isoform (`--isoform`), and a computed free energy is judged against
  the band at 2σ (exit 0 agrees, 4 disagrees). See docs/USING_CATERVA.md.
- Caterva's own free-energy estimators: MBAR, BAR, equilibration
  detection, statistical-inefficiency subsampling, overlap and
  forward/reverse convergence, validated on harmonic oscillators with
  exact answers and calibrated error bars; `caterva fep --summarise` uses
  them on the raw dhdl files. The FEP setup now writes energies at every
  state (`calc-lambda-neighbors = -1`) so MBAR can use them.
- Each constant is looked up under the compound it belongs to. 29 library
  constants name their own port (an inhibitor's Ki, a product's Km, a
  phosphatase's Km, ATP, a second substrate); `compose` takes
  `--inhibitor`, `--product` and `--compound PORT=NAME`; an unnamed
  compound means no search and a reason naming the flag, never a lookup
  under the substrate's name or under no name at all. Mixed inhibition's
  Kic and Kiu are refused. The report says what each value's own row
  measured (isoform, mode, what it competed with). The README's headline
  example, which promised a Ki the live system did not return, now shows
  live output.
- All four `compose --export` formats carry what each value's own source
  row measured (isoform, inhibition mode, what it was measured against)
  and the spread of the other rows the resolver ranked. Both had reached
  the report only: the exports handed a lab gossypol's LDH-B Ki with no
  word that it is one isoform's constant with no stated mode, and dropped
  the 13-fold spread in human LDH's pyruvate Km although the record
  carried it. The CSV gains seven columns; each per-value sentence gains
  `SOURCE ROW:` and `VALUES DISAGREE:` clauses. One reader
  (`compose/row_scope.py`) serves the report and the exports.
  The preparation is among them: a Ki measured on a His-tagged construct
  (human LDH's quinoline sulfonamide, BRENDA 739793) is named as one in the
  report and every export, as the API already did.
- The API looks a Ki up under the inhibitor the query names ("... by
  oxamate"), not under the substrate taken from the enzyme's own name, and
  reports the row's isoform and mode; the CLI's `resolve` prints the same.
- The landing page's export samples are generated from a real run by
  `scripts/refresh_export_samples.py`. The panel had shown a command that
  does not exist, a JSON format the CLI does not write, and a CSV
  trajectory where the real CSV is the parameter audit trail.
- Isoforms reach the API and the TypeScript CLI too. The resolver takes an
  `isoform` and keeps the rows measuring it before choosing; a row naming
  the isozyme asked for is no longer withheld as a "variant"; and a
  constant only measured on other isoforms is refused as
  `isoform_withheld`, naming them. The API reads the isoform from the
  query ("human LDH-A inhibited by gossypol"); `scientific resolve` takes
  `--isoform`. The CLI also stopped printing "BRENDA and PubMed were
  searched and returned nothing" when rows were found and withheld
  (another isoform, a variant, another organism): it now says what was
  withheld and the flag that reaches it.
- `caterva analyze` reports the chi1 rotamer of each catalytic residue:
  per replica, the fraction of frames in the well it started in (+60, 180
  or -60), and kept, flipped, partial or replicas disagree. The angles
  equal `gmx angle`'s to 0.001 degree on real lysozyme frames; the
  `--gromacs` route measures them with `gmx angle` and CI compares the two.
- `caterva compose --isoform NAME`: each constant comes from a row that
  measured that isoform. For human LDH and gossypol, `--isoform LDH-A`
  gives LDH-A's Ki (0.0019 mM) where the resolver's pick was LDH-B's
  (0.0014 mM); a row naming no isoform is used only when none names the one
  asked for, and the report says its isoform is unknown; a constant held
  only for other isoforms is refused. The spread line says why the carried
  value was carried.
- `caterva analyze --gromacs` put the RMSF of lysozyme's residues 66-74
  about 10% above the native route, a gap recorded as unexplained. It was
  the GROMACS route's: `gmx rmsf` fits to the `-s` coordinates as stored,
  and the tpr stores them wrapped, with those residues a box length from
  their neighbours. The generated script now makes the reference and the
  trajectory whole first; the routes agree to 0.0001 nm on every residue,
  and the MD smoke job now fails if their mean RMSF differ.
- The effector parser no longer sends role words ("activator LY-2121260"),
  changes to the protein ("with removed helix alpha13") or two compounds
  joined by "or" to PubChem as one name; and identical HTTP requests are
  answered once per process, which stopped NCBI's rate limit firing on a
  single lookup.
- The MD smoke test read the hydrogen-bond table as distances and failed
  CI with a 0.697 nm "disagreement"; it now reads only the geometry section.
- `caterva prepare --ph`: a protonation-risk audit of the active site from
  measured pKa spreads in folded proteins (Grimsley et al. 2009, values
  read from the PubMed abstract): which residues' charge is settled at the
  assay pH, which is uncertain, and where pdb2gmx's default contradicts
  typical behaviour. Not a pKa predictor, and it says so.
- `caterva analyze` counts hydrogen bonds between catalytic side chains
  (the `gmx hbond` criterion, equal to it frame by frame on real
  lysozyme), and reports each distance's 95% confidence interval across
  replicas with the number of replicas needed to decide held or moved.
  `caterva md --summarise` reports the interval too.
- `caterva analyze` measures natively (no GROMACS needed), agreeing with
  `gmx distance` exactly on a real trajectory; `--gromacs` keeps the old
  route as a cross-check. An unwritable download cache no longer crashes
  `caterva prepare` or `caterva analyze`.
- A native .xtc reader (`caterva/md/xtc.py`), exact against `gmx trjconv`
  on real output, with periodic-image handling and RMSF (agreeing with
  `gmx rmsf`). `caterva complex --check` follows the ligand through every
  frame; `caterva fep --trajectory` chooses restraint anchors among
  C-alpha atoms that stay still.
- Thermodynamic integration beside MBAR and BAR, and `caterva fep
  --optimise`: thermodynamic length per step from a pilot leg and an
  equal-length schedule (Shenfeld et al. 2009). On real benzene output
  TI, MBAR and BAR agree, and 15 windows would do the work of 25.
 did the ligand keep its crystal pose, with
  symmetric poses counted as one (graph automorphisms from the .itp).
- `caterva fep`'s solvent build starts from a pristine topology, so an
  interrupted build can be re-run (solvate had counted the water twice).
 every inhibitor's target for an enzyme, per
  compound, species and isoform, marked as a benchmark only with two
  publications, a stated mode and a stated temperature.
- The API tests replay a recorded real BRENDA page for EC 2.7.1.1
  (`Tests/fixtures/recorded/`) instead of failing when BRENDA is down.
- `caterva complex`: builds the equilibrated complex `caterva fep` needs
  from a PDB entry and your ligand topology, posing the ligand on the
  crystal's by Kabsch superposition and refusing a different conformer or
  stereoisomer (a mirror image can pass an RMSD test).
- `caterva fep`: an absolute binding free-energy calculation (double
  decoupling, Boresch restraints with their analytic correction, BAR) run
  at the cited Ki's assay temperature and judged against `caterva bind`'s
  band by `--summarise`. Five methods added to `caterva/methods.py`, each
  DOI checked against Crossref. Run end to end on T4 lysozyme L99A with
  benzene (PDB 181L) with GROMACS 2026.1.

### Changed
- `caterva md` with no arguments now says `a setup needs --pdb and --out (or use --summarise DIR on a finished run)` (exit 2, through the parser's own error), and the other refusals it made after parsing go the same way, so a malformed request is refused before a run exists, in the terminal and in the studio alike. `caterva structure --chimerax` with no ranked entry refuses with exit 3 where it used to crash on an empty ranking.
- `caterva compose --subject NAME` no longer needs the network to read an enzyme name the nomenclature holds (see "One name policy" above), and `caterva --help` points at `caterva enzyme`.

### Fixed
- The frozen app's smoke check required the word "kimura" in `caterva sim --help`, which the archived population-genetics engine used to print; `sim` is now the Gillespie engine alone (`caterva sim ssa`), so the check would have refused every app folder and DMG. It now requires `ssa` and `Gillespie`, and the README written into the app folder describes `sim` as exact stochastic chemical kinetics and says the literature search needs a network connection (it used to say it was not included).
- The minimum macOS is 14.0, not 12: NumPy 2.2.6 and SciPy 1.15.3 are `macosx_14_0_arm64` wheels and libRoadRunner 2.8.0 is `macosx_14_0_universal2`. `LSMinimumSystemVersion`, the DMG's README and the docs say 14, and the shell checks `ProcessInfo` and shows a plain alert on an older macOS.
- `Caterva --smoke` ran the bundled server on the person's real data folder; it now passes a temporary `--data-dir` and removes it.
- `caterva compose --any-mode` now names the row its default would carry, taken from the resolver's own answer. It already asked the resolver for no mode, so it carries what the runner (and the TypeScript CLI without `--mode`) returns when no mode is sent. But its note about the default was worked out from the rows in that answer. For Trypanosoma cruzi hexokinase and ADP it carried 1.3 mM (BRENDA ref 640265) and did not mention that the default carries 1.5 mM, "competitive to ATP" (ref 640216). The request now sends the model's mode as `compare_mode`. The resolver answers exactly as it does with no mode, and reports in `mode_default` what the mode would have returned, from the same rows. The note names that row, its reference and stated mode, and why it differs. Parity with the no-mode answer covers the row carried, not the rows listed beside it: the default's row is added to the alternatives, so the printed spread is 1.3 to 1.5 mM either way, where the runner's candidates hold 1.3 mM alone.
- A Ki row saying "<mode> to X" is read as measured versus X, as "versus X" already was. "to" followed by a mode word is not read this way, so "mixed to non-competitive" is unchanged. Before, T. cruzi ADP's "competitive to ATP" read as measured against nothing and was carried for a glucose model with no remark. Now the report says it was measured versus ATP, not glucose. The 7 mM "noncompetitive to glucose" row (ref 640216) is now returned as `mechanismEvidence` against a competitive model of glucose; compose's report does not yet name it. Of the 766 Ki rows on the committed hexokinase, LDH and monoamine oxidase pages, four readings change, all on hexokinase.
- When an assay window re-selects a row, the carried row keeps its own commentary, unit and citation ("BRENDA ref 670748"). Before, the commentary was kept from the replaced row, so `row_scope`, the SOURCE ROW line and the CSV's source-row columns described a row that was not carried: LDH kcat re-selected to 32.0 1/s at pH 8 still read "pH 6.0 ... in presence of fructose 1,6-bisphosphate". When the request named no substrate and the chosen row is for another substrate, the search summary now says so ("re-selected to 32.0 1/s for NAD+ ... replacing 21.1 1/s for pyruvate"). Whether the window's row is already the one carried is now decided by value and commentary, not by value alone.
- `caterva analyze`: an angle in plane in the crystal no longer prints n/a for every replica. Each replica's cell gives the fractions on the clockwise face, on the anticlockwise face and flat, and the verdict says whether the replicas stayed in plane or left it. On the 21-frame lysozyme replica, Ser50–Asn46–Asn59 is anticlockwise in 8 of 21 frames. `scripts/md_smoke.py` now compares the fractions inside each face-table cell, and allows the native and GROMACS routes to differ by exactly one frame of one replica moving between flat and a face. Before, it compared no replica cell in the row allowed to differ, and then briefly allowed a frame off in every number of that row.
- The Ki parser matched a requested compound anywhere in a row, including
  its commentary, so the quinoline sulfonamide row "competitive versus
  NADH" came back as a Ki of NADH (0.00059 mM). It now matches the row's
  compound cell; `resolve_kinetic_value(..., "NADH", quantity="ki")` is
  not found, as it should be.
## [Unreleased: site]

### Fixed
- The website called BRENDA ref 739793's Ki "oxamate". It is not: the
  ref measures a quinoline sulfonamide against His-tagged human LDH-A, and
  its 0.00059 mM is competitive against NADH, not pyruvate. The hero and
  the example gallery now use the same paper's pyruvate row (0.00252 mM,
  noncompetitive, pH 7.5, 37 C) and draw noncompetitive inhibition (Vmax
  falls, Km holds). The two example queries naming oxamate are gone: BRENDA
  has no oxamate Ki for human LDH, so the resolver could not answer them.
  The 2026 entry below that says "oxamate" is kept as it was written.

## [0.3.1] - 2026-09-22

Nobody could tell what to type. The release worked and explained nothing,
which is a product nobody adopts.

### Added
- **`docs/USING_CATERVA.md`**, the user's guide: the one rule that explains
  most refusals (it recognises a *shape*, never a *subject*), what to type
  in the first three minutes, how to read a report section by section, and
  a recipe for each question a lab actually asks -- which step matters
  (`--screen`), what to measure next (`--design`), does the conclusion
  survive not knowing the constants (`--robustness`), is it physically
  possible in and out (`--scale`, `--predictions`). Every command in it was
  executed before it was written down.
- **`caterva/tests/test_using_caterva_guide.py`** pins the guide to the
  code: every flag it names must exist in the parser, every shape must be
  recognised by the grammar, every export format must be offered, every
  `sim` subcommand must exist, and the stated mechanism count must equal
  the grammar's. Verified by mutation: a renamed flag, a misspelt shape, a
  withdrawn export format and a stale count each fail it.

### Changed
- **`caterva` with no arguments is now the first lesson**, not a six-line
  usage: three commands worth typing in order, the shape-versus-subject
  rule, the flags that answer real questions, and the exit codes. The
  mechanism count in it is read from the grammar, so the message cannot
  claim a number the builder does not have.
- **The app folder's `README.txt`** carries the same quick start, because
  somebody who downloads a folder has no repository to read.
- README, `START_HERE.md`, the docs index and the v0.3.0 release notes
  point at the guide.

## [Unreleased]

Caterva narrows to enzymes: kinetics, structure and dynamics.

### Added
- **`caterva structure`**: an enzyme's PDB entries, grouped by UniProt
  protein (an EC number in one organism is often several proteins, and the
  command refuses to pick between them), ranked by the ligand asked for,
  method and resolution, with ligands, cofactors, metals and
  crystallisation additives kept apart, and each entry cited by its paper
  or, when unpublished, by its own DOI. `--chimerax` writes a script.
- **`caterva md`**: a GROMACS setup (mdp files, `run.sh`,
  `PROVENANCE.md`) in which every setting is measured, chosen or cited;
  with `--subject/--organism/--substrate` the temperature and pH come from
  the assay behind a cited kinetic constant. Run end to end with GROMACS
  2021 on LDHA (held 310.2 K for a measured 37 C); a CI job runs every
  stage on lysozyme.
- `caterva/methods.py`: the eleven method citations those outputs rest on,
  each DOI checked against Crossref.
- **`caterva prepare`**: a structure-preparation audit. Reads a PDB entry's
  mmCIF records and reports sequence differences from UniProt (whatever
  the depositors call them: 1L63's C54T/C97A are labelled 'conflict'),
  chain breaks, truncated side chains, alternate conformations,
  non-standard residues, the biological assembly and model quality, each
  ranked by distance to the catalytic residues. Those come from a cited
  M-CSA snapshot carried onto each chain by alignment, with the reference,
  its identity and the rejected candidates named. On 1I10 it finds LDH-A's
  catalytic Arg105 truncated in chain D and unmodelled in chain G, and
  recommends chains A or C. No new dependencies.
- **`caterva md` runs three replicas by default** from one minimised system,
  differing only in velocity seeds (all recorded), and **`caterva md
  --summarise DIR`** reports each replica's block-averaged error
  (Flyvbjerg & Petersen 1989), its effective sample count, and whether the
  replicas agree: consistent, replicas disagree, unconverged, or one sample.
  Exit 4 unless consistent.
- **`caterva analyze`**: in every replica, the distance between the
  functional groups of each pair of catalytic residues (M-CSA, mapped by
  `caterva prepare`) against the crystal, and the active-site pocket's RMSF
  against the rest of the protein; each called held/moved or rigid/mobile
  only when the replicas agree. Measured by `gmx distance` and `gmx rmsf`,
  with the commands written to analyze.sh.
- `docs/design/MD_ROADMAP.md`: what the dynamics side will add
  (structure-preparation audit, replicas by default, enzyme-specific
  analysis, ligand provenance, simulation beside measured Ki), and why each
  is better than running the engines by hand.

### Removed (archived)
- SIR/SEIR epidemiology, PCR, Monte Carlo π, population genetics
  (Wright-Fisher, two-locus), the Lennard-Jones cluster MD and the three ODE
  oscillators moved to `archive/legacy_domains/` with their tests. The
  engine, the API runner, the root CLI and the website no longer offer
  them. A query for one is refused with a message naming the archive,
  never answered with an enzyme simulation; v0.4.0 still runs them.
- `caterva sim` keeps only `ssa`.

### Changed
- The website's hero widget and example gallery show human LDH-A with and
  without oxamate, from recorded BRENDA constants (Km 0.03 mM, ref 286469;
  Ki 0.00059 mM, ref 739793), in place of an SIR outbreak with drifting
  parameters.

### Fixed
- The TypeScript record store resolved its directory through
  `os.homedir()`, and the jest suites' temporary `HOME` did not reach it, so
  test runs wrote thousands of records into the real `~/.terrium/records`.
  It now reads `HOME` first, and still loads records left in the old
  location.

## [0.4.0] - 2026-09-27

**Terrium is now Caterva.** Notes: `docs/releases/v0.4.0.md`.

### Changed
- **The name, everywhere.** Product, repository (`math12345678/caterva`),
  command (`caterva`), Python package (`caterva`, was `Terium`), download
  filenames, environment variables (`TERRIUM_*` to `CATERVA_*`) and the
  website. New logo: a C of eleven dots with a serif wordmark, in ink
  (`#1D201A`) on paper (`#F2EFE5`); see `docs/brand/`. The
  `terrium` command is kept as an alias. Entries below this one were passed
  through the same rename, so older command names read as `caterva`.
- **The engine command is `caterva-sim`** (was `terium`); `caterva sim` is
  the same thing.

### Removed
- **`Business/`, the pitch deck and seven confidential documents, from the
  repository and its whole history**, before it went public.

### Fixed
- The README quick start `cd main` after cloning `caterva`.
- The website credited a nonexistent "Terium" project at a nonexistent
  address; links pointed at domains that never existed.
- A tracked `.coverage` database, already listed in `.gitignore`.

## [0.3.4] - 2026-09-24

The first clean-checkout run of 0.3.3 read like a demo: a sourced model's
verdict said no search had run, and plain Michaelis-Menten was refused.

### Fixed
- **The bare `caterva` screen said sourced constants were "not wired
  yet"**, false since 0.3.3; it now shows the command. `compose --help`
  leads with a `--subject` example, and every help example is tested.
- **Naming the inhibited step did nothing** despite the note promising
  it. `feedback_inhibition` now wires the end product to the named step.
  `caterva/tests/test_feedback_inhibition_named_step.py`.
- The guide said twelve scenario presets; there are thirteen (now tested).
- **`"3 step phosphorylation cascade"` crashed** (any description
  starting with a digit gave an invalid model name).
- **The Hill-function trigger matched "uphill" and "downhill".**
- **The verdict read only one kind of provenance.** A model sourced by the
  literature search was graded STRUCTURAL with "none has been run", above
  a table of BRENDA citations. It now reads the search's results; a fully
  sourced model is GROUNDED. The behaviour caveat's count was wrong for
  the same reason. `caterva/tests/test_verdict_after_search.py`, which fails
  without the fix.
- **A withheld constant named an option that does not exist.** It now says
  to re-run with `--organism` set to an organism that has a measurement.

### Added
- **Every shape builds from its own `--shapes` description** (21 of 36 did
  not), and every example in the usage message and the guide builds.
  `caterva/tests/test_every_shape_builds_from_its_own_words.py`.
- **`--organism` reads common names and lower case** (`human`, `yeast`,
  `homo sapiens`) and says how it read them; `make cite` does the same.
  `caterva/compose/organisms.py`.
- **A misspelt substrate lists what BRENDA holds**; an unknown or
  incomplete EC number says so and exits 3; the verdict's remedy is the
  reason the search could not run.
- With no `--organism`, the report names the organism the search chose.

- **Plain Michaelis-Menten**, the `michaelis_menten` rule, at priority 45
  so every enzyme shape with more structure still wins.
  `caterva/tests/test_grammar_michaelis_menten.py`. The composer now builds
  12 of the twenty coverage questions, not 11.
- **"Try it on your own enzyme"** in `docs/OWNER_CHECKLIST.md`, with four
  enzymes run unscripted.

## [0.3.3] - 2026-09-22

The product's central claim -- every number traces to its source -- was
true of the code and unreachable from anything a person types.

### Fixed
- **A refused literature search exited 0.** This CLI's contract, in its own
  `--help`, is "0 produced everything asked for ... 3 something refused and
  said why (the report is still printed)". `--subject "lactate
  dehydrogenase"` asks for a search, the resolver refuses because that name
  is six different enzymes, and the report said so in prose while the
  process exited 0 — a script could not tell the search never ran. A search
  that could not be RUN (ambiguous name, missing `--substrate`, no
  literature layer, a crash) is now a refusal and exits 3; a search that
  ran and found nothing is an answer and exits 0, the answer being in the
  provenance table.

### Added
- **`caterva` is the command everywhere.** The wheel installs it beside
  `caterva` and `caterva-compose`, and `make setup` now installs the package
  itself, so in a checkout `caterva compose ...` works from any directory
  instead of `./.venv/bin/python -m caterva.app compose ...` from the root.
- **`make doctor` detects the macOS + iCloud failure** that makes it
  vanish. Python 3.13 skips `.pth` files carrying the macOS `hidden` flag,
  and iCloud Drive sets that flag on files inside `.venv` when the checkout
  is under `~/Desktop` or `~/Documents`. Measured on the owner's machine:
  `caterva --version` worked right after install and minutes later failed
  with `No module named 'caterva'` from the same interpreter. Nothing in that
  error points at iCloud, so the doctor names it and gives the fix.
- **`docs/OWNER_CHECKLIST.md`**: the owner's remaining steps, copy and
  paste, each with what you should see and what to do if you don't.
- **A placeholder now says what the search actually met.** The resolver
  distinguishes four outcomes and the report printed one invented sentence,
  "searched the km table and found nothing", for all of them -- which is
  not a summary but FALSE for two: the value may exist in other organisms
  and not have been substituted (ADR 0024: offered, never substituted), or
  papers may have been found with no number extractable from their free
  text. Measured live on EC 3.1.1.7 in *Homo sapiens*: kcat is "available
  in: Cimex lectularius, Drosophila melanogaster, Macroptilium
  atropurpureum, Mus musculus" and Ki is "candidate papers were found but a
  number was not extracted". Both had been reported as nothing found,
  sending a reader to stop looking for a number that is in the database.
  The summary sentence underneath no longer says "looked for and not
  found", which contradicted the table it sat under. `<input>`, the
  blackboard's label for a constraint the caller raised, is translated to
  "your own request" at the edge rather than leaking into a page a
  researcher is reading.
- **A composed model reports the conditions its values were measured
  under, and whether they can be mixed.** pH, temperature and buffer decide
  whether two constants belong in one model; `Measurement` has carried
  them since it was written and the CSV printed them, while the report a
  person actually reads did not. It now lists them per constant, names any
  source that stated none ("a fact about the paper, not a gap in the
  search"), and compares the ones that can be compared against
  `model_compatibility`'s own thresholds (1 pH unit, 10 °C), saying
  plainly when a model would describe an experiment nobody ran. With one
  constant it makes no comparison claim, because a reassurance about
  nothing reads like a check that passed.
- **A composed model reports what the evidence did not settle.** Where the
  resolver ranked more than one row equal, the report names the spread
  instead of presenting the pick as the answer: for EC 1.1.1.27 and
  pyruvate, *"2 sources report 2 values (BRENDA ref 286442, 286469),
  spanning 0.03 to 0.398 mM (13.3-fold). The model carries 0.03 — the
  resolver's pick, not a verdict"*. The rows were being dropped at the
  `Measurement` boundary, so a 13-fold disagreement arrived downstream as
  one confident cited number, which looks more settled than a placeholder
  rather than less. It distinguishes several papers disagreeing from one
  paper reporting several rows, because sending a reader to one paper to
  adjudicate itself is not advice. The lab-report path has printed this
  since it was written; this is the composed model catching up.
- **`compose` searches the literature.**
  `caterva compose "..." --subject 1.1.1.27 --organism "Homo sapiens"
  --substrate pyruvate` returns a model whose constants are BRENDA's, each
  with its reference, and every section below -- stability, the influence
  ranking, the time course, the verdict -- runs on those numbers. The
  exports carry them too, so an SBML file and the report beside it cannot
  disagree. A partial result stays partial: constants the search did not
  find keep the motif library's placeholder and are listed as
  *searched and not found*, which is a different fact from *not looked
  for*. Four pieces (ADR 0178): `caterva/checkout.py` makes the literature
  layer importable outside pytest; `ComposedModel` carries `organism` and
  `substrate` and fills the `ec_number`, `substrate` and `organism` fields
  BRENDA requires; `with_measured()` substitutes through
  `export.provenance_of`, the one place that decides an origin; and the
  CLI runs the search before the analyses, turning every failure into a
  note on the report rather than an error instead of it.
- **`scripts/cite.py` and `make cite`: real constants with real
  citations**, in one command.
  `make cite EC=1.1.1.27 SUBSTRATE=pyruvate ORGANISM="Homo sapiens"`
  returns `km = 0.03 mM` from `BRENDA ref 286469`, the papers that
  disagree and by how much, the conditions the value was measured under,
  and `--` for anything nothing measured. `--fixture` keeps the offline
  route. It re-implements none of the resolution, ranking or rendering:
  it builds `report_lab.py`'s payload and hands it over. Verified live on
  three enzymes (ADR 0178).
- **ADR 0178**, recording why it was unreachable: `compose --subject`
  never called `compose_and_parameterise`; that function failed every
  scout with `ModuleNotFoundError: fallback_logic` **while reporting
  `converged=True`**; with the path repaired it failed again because
  `parameter_requests()` never filled the `ec_number`, `substrate` and
  `organism` fields BRENDA requires; and the working entry point read a
  six-key JSON payload on stdin. The ADR lists the four things that would
  let `compose` search, and the guide says plainly that it does not.

### Fixed
- **Every BRENDA citation was being degraded to a bare enzyme-page URL.**
  `citation_text` looked for an attribute called `reference`; `Citation`
  declares `reference_id`. The attribute never existed, so every citation
  fell through to `url` and two measurements from two different papers
  produced the identical string. The same model's two constants now cite
  `BRENDA ref 286469` and `BRENDA ref 739793` -- different papers, as they
  always were. BRENDA has no working per-reference deep link, so the
  reference id was the only thing identifying which row a number came
  from, and it was the one field being dropped.
- **The verdict recommended a ranking it had just called worthless.** On a
  saturated model -- a three-step cascade at the library's placeholder
  values sits at 99.99% phosphorylated, so every sensitivity falls below
  the threshold -- the provenance section said "No constant here clears
  |S| = 0.01" while the one line labelled "Do this next" said "start with
  the top of its influence ranking". The remedy was a fixed string that
  never read the ranking. It now reads it, and says so when nothing is
  singled out. This is the defect `_settling_ranking` was written for
  (a ranking zeroed by a conservation law) in its other form.

## [0.3.0] - 2026-09-21

The first release that reaches GitHub's Releases page, and the first that
is downloadable as an app. v0.2.0 built and verified a wheel; the Release
itself needed a token the machine did not have, so the tag sat on the
remote with nothing attached. From this version a pushed tag is published
by a workflow with the run's own token, after it has rebuilt, reinstalled
and run everything it is about to attach (ADR 0177).

### Added
- **A release workflow.** `.github/workflows/release.yml`: on a `v*` tag
  (or by hand for an existing tag), builds the wheel and sdist, rebuilds
  them independently and fails if the checksums differ, installs the wheel
  into a fresh interpreter on Linux, macOS and Windows at Python 3.10 and
  3.13 and runs `caterva-compose` to a `VERDICT:` from an empty directory,
  freezes the app folders, and only then creates the Release with the
  notes, every artifact and one `SHA256SUMS`.
- **A downloadable app folder per platform** (`caterva-<version>-<os>-
  <arch>.tar.gz` / `.zip`, Linux x86_64, macOS arm64, Windows x86_64):
  one executable, `caterva`, with `caterva compose "..."` and
  `caterva sim ...`. No Python, no install. Built from the released wheel
  by `scripts/build_app.py`, which refuses the folder unless python-
  libsbml's extension is a separate replaceable file, every conveyed
  component's licence is inside, and the frozen binary runs from an empty
  directory. libSBML is in the folder three times (python-libsbml's copy
  and the copies libroadrunner and Antimony compile in); the script finds
  and lists them, and the release page carries the corresponding source
  of every version, and of the two libraries, beside the folders.
- **`caterva`, a single entry point.** `caterva/app.py` dispatches to the
  two existing commands unchanged (`python -m caterva.app` from the wheel;
  the executable in the folder). 83 modules in the wheel, up from 82.
- **`third_party_licenses/LGPL-2.1.txt`.** The LGPL text python-libsbml's
  wheel refers to but does not carry; the app folder ships it.
- **`requirements-release.txt`** pins PyInstaller for the release workflow
  only, with its licence (GPL-2.0-or-later WITH Bootloader-exception)
  recorded in the dependency-licence guard.

### Changed
- **Both artifacts are byte-reproducible from the commit.** The sdist is
  normalised after the build (sorted members, epoch mtimes, gzip mtime 0);
  0.2.0's notes said the wheel was and the sdist was not. Measured:
  identical `SHA256SUMS` from two independent checkouts of the tag.
- **NOTICE now states the licence position artifact by artifact.** The
  wheel and sdist name libSBML and do not convey it; the app folder does,
  and the section says how each LGPL-2.1 obligation is met (notice, and a
  separate replaceable file). The sentence "this repository has exactly
  one CI workflow and it publishes nothing" was true from 2026-08-15 to
  2026-09-19 and is replaced with that history. `docs/LICENSING.md` and the
  dependency-licence guard no longer say replacement is "a pip install
  away" without qualification.
- `SECURITY.md` names which versions receive fixes; it said there were no
  released builds.

### Fixed
- **`caterva-compose --export sbml` and `--export antimony` crashed from
  every installed copy of 0.2.0** with `FileNotFoundError`: two files the
  engine reads at import, `docs/data-sources.json` and
  `Tests/fixtures/identifiers/identifiers_org_namespaces.json`, were
  resolved relative to the checkout and shipped in neither the wheel nor
  the sdist. Copies now live in `caterva/core/data/`; the loaders read the
  checkout's original when it exists and the packaged copy otherwise, and
  `caterva/tests/test_packaged_data.py` fails if a copy and its original
  ever differ. Proved from an installed wheel in an empty directory. The
  0.2.0 notes' "Known limits" did not record this; it was found by reading
  every `Path(__file__)` in the package for the app folder.
- `CHANGELOG.md` carried a duplicated, truncated block (a second correction
  banner and a stale `[0.1.0] - 2026-09-19` section) introduced by the
  0.2.0 commit's edit anchoring on the wrong `## Unreleased`. Removed.

### Known limits, stated
- **Not on PyPI.** A separate decision; the name has not been checked.
- **Not signed.** The macOS and Windows folders carry no code signature;
  each folder's `README.txt` says what the operating system asks on first
  run. Signing needs certificates the repository does not hold.
- **No Intel-Mac folder.** Intel Mac users install the wheel.
- **The repository is still private**, so the Release is visible to
  collaborators. Going public is blocked by owner decisions listed in
  `docs/status/2026-09-21.md`, not by anything in this release.
- **The freeze could not be run where this was written** (no PyPI in the
  sandbox). The workflow's first run is the first real freeze; it verifies
  the folder by running it, and publishes nothing if that fails.

## [0.2.0] - 2026-09-19

The first release with built artifacts. A source distribution, a
pure-Python wheel, and two installed commands. 0.1.0 (below) was a tag and
a source archive; this is the version you can `pip install`. Everything
under the `Unreleased` heading further down was already in the tree; this
entry records what makes 0.2.0 an installable release rather than a
checkout.

### Added
- **Installable package.** `pip install caterva-0.2.0-py3-none-any.whl`
  installs `caterva` (engine, composer, agents; 82 modules) with pinned
  dependencies. Verified by installing the wheel into an empty directory
  and building a model from there with nothing of the repository on the
  path.
- **Two commands.** `caterva` (the simulation engine: `wf`, `kimura`, `ne`,
  `sweep`, `scenarios`, `ld`, `ssa`) and `caterva-compose` (the model
  builder and its analyses). Before this the composer was reachable only
  as `python -m caterva.compose` from a checkout.
- **A version.** `caterva.__version__` is the single source; `pyproject.toml`
  reads it, and `CITATION.cff` and `package.json` are kept equal to it.
  `caterva-compose` and the package metadata cannot disagree.
- **`scripts/build_release.py`.** Builds the sdist, then the wheel from
  the extracted sdist, checks the wheel against what the release notes
  claim (no tests, no conftest, LICENSE and NOTICE inside, every module
  under `caterva/`), and writes `SHA256SUMS`. With `SOURCE_DATE_EPOCH`
  pinned to the tagged commit the wheel is byte-reproducible; the sdist is
  content-identical but not byte-identical (setuptools writes fresh
  mtimes into `PKG-INFO`), and the script says so rather than hiding it.
- **A conveyance section in NOTICE** stating what the artifacts do and do
  not distribute: Caterva's own code only; python-libsbml (LGPL-2.1) is
  named as a dependency and not bundled, so its conveyance obligations do
  not attach. (This is also why there is no frozen desktop bundle in this
  release: PR #21's onefile DMG froze libSBML in, and that changes the
  obligations. See NOTICE.)

### Fixed
- **Packaging built nothing.** Setuptools' flat-layout discovery saw
  `caterva/` beside `Tests/`, `Business/`, `node_modules/` and a dozen more,
  and an editable install registered `dist-info` and no code: `import
  Caterva` failed from any directory but the repository root. Packages are
  now named explicitly. The sdist also swept the whole `Tests/` tree in
  through a case-folded `tests/` glob; a `MANIFEST.in` prunes it.
- **A wheel built straight from the tree carried `caterva/conftest.py`.**
  `MANIFEST.in` governs the sdist and `exclude-package-data` governs data
  files; neither excludes a module from a wheel built directly. Building
  the wheel from the sdist does, which is what the build script enforces.
- **ADR 0176's mutation table had no set file.** Seven mutations across
  four files, run through `scripts/mutate.py`, all caught.
- Everything under `Unreleased` below, which this release ships.

### Known limits, stated
- **Literature search needs the source checkout.** `caterva.agents` reaches
  into `Tests/` (the BRENDA resolvers) lazily; those modules are not part
  of the package. From the wheel, `caterva-compose ... --subject <enzyme>`
  builds the model and the verdict page says, correctly, that no search
  was run. Running the search means cloning the repository.
- **The api-server and landing site are not in this release.** They are
  TypeScript, deploy separately, and their test suite could not be run in
  the environment this release was built in (port binding is sandboxed).
  They are unversioned until they can be verified.
- **0.2.0, not 1.0.0.** The public API has not been frozen and the
  composer's library is eleven mechanisms. The number says "usable,
  changing," which is true.

## [0.1.0] - 2026-08-29

Tagged and released as a source archive only, deliberately: the licence
position rested on distributing nothing that contains libSBML, and a
source archive contains none. `pyproject.toml` said 0.1.0 but its
packaging built an empty install (see 0.2.0, Fixed), so this version was
never `pip install`-able. The record of the release and its measured
figures is in `docs/EXPERT_FEEDBACK.md` ("Seventy-ninth pass").

## Unreleased

### Added
- **ADR 0012**: kcat is resolved from literature but is not a simulation parameter.
- **ADR 0013**: Enzyme concentration bridges kcat to Vmax (Vmax = kcat * [E]0).
- **ADR 0014**: Python 3.10-3.12 support window documented with the correct
  constraint (libroadrunner + numpy, not libSBML).
- **ADR 0015**: A constitution rule that nothing executes is not enforced —
  adding caterva to requirements.txt passed every guard.
- **ADR 0016**: Cached results lose per-parameter provenance — schema column,
  persistence, cache read, and serialisation guard all implemented.
- 11 guard scripts with automated wiring check (`check_guard_wiring.py`).
- Documented-counts guard (`check_documented_counts.py`) that fails if README
  test/domain counts don't match the repository.
- Python support claim guard (`check_python_support_claim.py`) across all
  files that state the version window.
- Constitution Rules 7+8 guard (`check_forbidden_packages.py`) — forbids the
  tellurium umbrella package and verifies every ADR is indexed.
- **Eleventh simulation domain**: Michaelis-Menten with competitive
  inhibition (`v = Vmax·S / (Km·(1+I/Ki) + S)`), verified against the
  apparent-Km closed form `Km_app = Km·(1 + I/Ki)` and against plain MM
  exactly at I=0. Reachable end-to-end (engine, API dispatch, TS schema).
- **Python 3.13 support** (ADR 0014 follow-through): `numpy` and
  `libroadrunner` bumped to publish cp310-cp313 wheels, verified against
  PyPI with `--online`, not assumed from the pin bump alone.

### Changed
- Engine test suite: 715 -> 883 tests (Gillespie SSA, SSA bimolecular,
  SSA replicates, two-locus WF, competitive-inhibition MM).
- Literature test suite: 182 -> 214 tests.
- TypeScript test suite: 111 -> 224 tests (16 files).
- README Layout section now lists all six top-level directories.
- README domain count: ten -> eleven, kept consistent across both
  places it's stated (guarded by `check_documented_counts.py`).

### Fixed
- ADR 0016: parameter provenance now survives cache hits (was silently
  returning {} on every cached result).
- ADR 0014: the documented reason for the Python version constraint corrected
  in README, CONTRIBUTING, and requirements.txt.
- Rule 8: ADR indexing verified automatically; two unindexed ADRs found and
  fixed during guard development.
- README.md Layout and scripts/README.md stale counts corrected.
- Two real environment bugs: `pipeline.ts`'s and `scienceAgent.ts`'s health
  check / literature bridge both hardcoded `spawn("python3", ...)` instead
  of resolving the actual configured interpreter — silently wrong on any
  machine where the venv Python isn't literally named `python3` on PATH.
- A false capability claim: `RESOLVABLE_FIELDS` said the new domain's `ki`
  is resolved from BRENDA; nothing populates it, so it always silently fell
  back to a default. Narrowed the claim rather than fake a lookup path —
  same precedent as ADR 0012 excluding kcat.
- The parameter-provenance fix and the competitive-inhibition domain were
  both originally built on a branch that turned out to be 92 commits behind
  main; ported the real diffs onto current main by hand after the naive
  cherry-pick failed outright.

## 2026-07-25

### Added
- PCR amplification as a third live simulation domain: exact closed-form
  exponential growth, optional discrete-logistic plateau mode, validation
  with an `ok`/`flagged` distinction consistent with the rest of the engine.
  32 new tests, mutation-verified.
- Sandbox: `Dockerfile` + `.devcontainer/devcontainer.json` for a one-command
  reproducible environment.
- `Business/` scaffolding: incorporation checklist, cap table placeholder,
  fundraising tracker, roadmap.

## 2026-07-23

### Added
- Caterva simulation engine (`caterva_engine.py`): Michaelis-Menten
  enzyme kinetics and SIR/SEIR epidemiology, built on antimony/roadrunner
  rather than the full `tellurium` umbrella package.
- 258-test simulation-engine suite, verified against exact closed-form
  solutions, an independent solver (scipy), and property-based tests
  (Hypothesis) -- not just internal self-consistency.
- `requirements.txt` / `requirements-dev.txt`, `Makefile`, GitHub Actions CI,
  `scripts/check_env.py`, `README.md`.
- Investor pitch deck (`caterva_pitch_deck.pptx`).
- `tests/test_dependencies_declared.py`: automated guard that fails CI if
  any import isn't declared in `requirements*.txt`.

### Fixed
- `KM_PLAUSIBLE_MAX_MM` mismatch between the literature layer
  (`Tests/brenda_client.py`) and the simulation engine (1e4 vs 1e3) -- a
  real bug that would have let a Km value flagged as implausible upstream
  arrive as "confirmed" downstream. Pinned equal, with a regression test.
- CI dependency install failures: `libroadrunner==2.9.0` had no Python 3.10
  wheels (reverted to `2.7.0`), and `httpx`/`pydantic` were imported by
  `brenda_client.py` but never declared as dependencies.
- A broken git submodule reference: `Science-Agent-Pipeline` had been
  committed as a gitlink with no `.gitmodules`, which made GitHub Actions'
  checkout step fail outright. Untracked it; it's an independent repo.

## 2026-07-21 to 2026-07-22

### Added
- Initial BRENDA/KEGG/PubMed literature-scraping layer (`Tests/`), 124 tests.
- Verified project specification and planning documents (`Docw/`).
