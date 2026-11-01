# Rates fixtures

Real answers of the studio server, for the Rates screen's component tests
(`src/screens/rates/rates.test.tsx`, `src/__tests__/ratesExports.test.ts`).
Nothing here is typed by hand, and none of it may be edited by hand.

## How they were produced

`caterva/tests/capture_studio_rates_fixtures.py`, run from the repository root:

    PYTHONPATH=$PWD python caterva/tests/capture_studio_rates_fixtures.py

It builds `caterva.studio.dispatch.App` over the full adapter registry and an
empty workspace and makes each request through `App.dispatch`, exactly as the
socket layer hands a request over: `POST /api/rates/preview` for the
`preview-*` files (each holds `{request, status, body}`), and `POST /api/runs`
with kind `rates`, polling `GET /api/runs/{id}`, then the run's `result` and
`events` for the `run-*` files (each holds `{captured, run, result_status,
result | error, events}`). `capabilities-rates.json` is `GET /api/capabilities`
with the rates adapter registered. The literature layer is never reached.

## The data

Every measurement is a value of `examples/rates/puromycin.csv`: R 4.6.0's
`datasets::Puromycin` (Treloar MA 1974, M.Sc. thesis, University of Toronto,
published in Bates DM and Watts DG 1988, *Nonlinear Regression Analysis and
Its Applications*, Wiley, Appendix A1.3; public domain). The tables are that file
itself, its treated rows alone, and its two lowest substrate concentrations.
The pasted, wide and messy tables are the same values saved the way a
spreadsheet or a plate reader saves them (tabs, decimal commas, a byte-order
mark, Windows line endings, one column per replicate): formats, not data. The
few bad cells in the messy table (`n/a`, an empty cell, a comma where the
others have points) contain no invented number.

## What each is

| file | what it shows |
|---|---|
| `preview-puromycin.json` | the file as it is: long layout, a group column, the file's own comments kept |
| `preview-pasted-decimal-comma.json` | a spreadsheet paste: tabs, decimal commas, CRLF, a byte-order mark, a blank line, units in brackets in the header |
| `preview-wide.json` | one substrate column and two replicate rate columns |
| `preview-messy.json` | rows skipped for a non-numeric cell, a blank cell and a stray decimal comma, each located by line and column |
| `preview-no-units.json` | two pasted columns with no header: not ready until the units are named |
| `preview-no-units-named.json` | the same, with the units named in the mapping |
| `preview-binary.json` | a workbook's bytes: refused with the reason |
| `preview-never-saturates.json` | the treated rows at the two lowest substrate concentrations |
| `run-puromycin-residuals.json` | the example fitted with the uncertainty taken from the residuals |
| `run-puromycin-replicates.json` | the same with the uncertainty pooled from replicates, proportional error |
| `run-never-saturates.json` | the low-concentration table: Km and Vmax are not determined, and the result says so |
| `run-literature-declined.json` | a literature comparison the command declines (ppm has no molar conversion): the report is kept |
| `run-refused-law-needs-inhibitor.json` | a refusal in the command's words: no result |
| `capabilities-rates.json` | the capabilities with `rates.available` true |
