/**
 * The example the Rates screen opens: R's `datasets::Puromycin`, the real table.
 *
 * The text below is examples/rates/puromycin.csv, byte for byte (a test holds
 * the two equal): the initial rates of galactosyltransferase in Golgi
 * membranes from cells treated with puromycin and from untreated cells,
 * Treloar MA (1974), published in Bates DM and Watts DG (1988), Nonlinear
 * Regression Analysis and Its Applications, Wiley, Appendix A1.3, and
 * distributed with R in the public domain. Nothing here is invented, and the
 * screen says where it came from when it is open.
 */
export const PUROMYCIN_FILENAME = "puromycin.csv";

export const PUROMYCIN_SOURCE =
  "R's datasets::Puromycin (Treloar 1974; Bates and Watts 1988), public domain";

export const PUROMYCIN_CSV = "# Initial rates of galactosyltransferase in Golgi membranes, from cells\n# treated with puromycin and from untreated cells.\n# Treloar MA (1974) Effects of Puromycin on Galactosyltransferase in Golgi\n# Membranes. M.Sc. thesis, University of Toronto. Published in Bates DM &\n# Watts DG (1988) Nonlinear Regression Analysis and Its Applications, Wiley,\n# Appendix A1.3, and distributed as R's datasets::Puromycin, where the\n# substrate column is called conc and the grouping column state.\n# Substrate concentration in parts per million; rate in counts/min/min.\nsubstrate (ppm),rate (counts/min/min),state\n0.02,76,treated\n0.02,47,treated\n0.06,97,treated\n0.06,107,treated\n0.11,123,treated\n0.11,139,treated\n0.22,159,treated\n0.22,152,treated\n0.56,191,treated\n0.56,201,treated\n1.10,207,treated\n1.10,200,treated\n0.02,67,untreated\n0.02,51,untreated\n0.06,84,untreated\n0.06,86,untreated\n0.11,98,untreated\n0.11,115,untreated\n0.22,131,untreated\n0.22,124,untreated\n0.56,144,untreated\n0.56,158,untreated\n1.10,160,untreated\n";
