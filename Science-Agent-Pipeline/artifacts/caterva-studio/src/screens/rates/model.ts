/**
 * What the Rates screen holds, apart from how it is drawn: the table's
 * source, the choices of the fit, the request they make, and the form a
 * reopened run's request fills again.
 *
 * A reopened run restores the dataset and the mapping exactly because the
 * request carries both: the text as the browser read it and the mapping the
 * server answered (every role, unit and decimal mark explicit), not a
 * detection that could come out differently next release.
 */
import type { RatesMapping, RatesPreview, RatesRequest, RatesSigmaOptions } from "@/api/types";
import { RATES_MAX_BYTES } from "@/api/types";
import { parseNumber } from "@/components/forms/Field";

/** The seven rate laws the engine can fit, with the one-line law it states. A test holds this to the engine's own list. */
export const RATE_LAWS: readonly { name: string; title: string; equation: string; inhibitor: boolean }[] = [
  { name: "michaelis-menten", title: "Michaelis-Menten", equation: "v = Vmax [S] / (Km + [S])", inhibitor: false },
  { name: "substrate-inhibition", title: "Substrate inhibition (Haldane)", equation: "v = Vmax [S] / (Km + [S] + [S]^2 / Ksi)", inhibitor: false },
  { name: "hill", title: "Hill", equation: "v = Vmax [S]^n / (K0.5^n + [S]^n)", inhibitor: false },
  { name: "competitive", title: "Competitive inhibition", equation: "v = Vmax [S] / (Km (1 + [I]/Ki) + [S])", inhibitor: true },
  { name: "uncompetitive", title: "Uncompetitive inhibition", equation: "v = Vmax [S] / (Km + [S] (1 + [I]/Ki'))", inhibitor: true },
  { name: "noncompetitive", title: "Noncompetitive (pure) inhibition", equation: "v = Vmax [S] / ((Km + [S]) (1 + [I]/Ki))", inhibitor: true },
  { name: "mixed", title: "Mixed inhibition", equation: "v = Vmax [S] / (Km (1 + [I]/Ki) + [S] (1 + [I]/Ki'))", inhibitor: true },
];

export type Origin = "file" | "paste" | "typed" | "example" | "run";

/** A table as the browser read it. The text is what is sent; nothing else about the file is. */
export interface Source {
  text: string;
  filename: string | null;
  origin: Origin;
  /** Said once under the table: bytes that were not UTF-8, for instance. */
  note?: string;
}

export type SigmaChoice = "" | "column" | "replicates" | "residuals";

export interface FitForm {
  model: string;
  sigma: SigmaChoice;
  /** The person chose it, so a new table does not overwrite it. */
  sigmaTouched: boolean;
  errorModel: "constant" | "proportional";
  level: string;
  significance: string;
  ec: string;
  /** A name a reopened run's finder starts from; never sent. */
  organism: string;
  substrate: string;
  inhibitor: string;
  isoform: string;
  enzymeConc: string;
  enzymeUnit: string;
}

export const EMPTY_FIT: FitForm = {
  model: "auto",
  sigma: "",
  sigmaTouched: false,
  errorModel: "constant",
  level: "",
  significance: "",
  ec: "",
  organism: "",
  substrate: "",
  inhibitor: "",
  isoform: "",
  enzymeConc: "",
  enzymeUnit: "uM",
};

/** The source of uncertainty a table offers first: its own sigma, else its replicates, else its residuals. */
export function defaultSigma(options: RatesSigmaOptions | null | undefined): SigmaChoice {
  if (!options) return "";
  if (options.column) return "column";
  if (options.replicates) return "replicates";
  return "residuals";
}

/** Whether a choice of uncertainty can be made of this table (the engine refuses two sources, and replicates it does not have). */
export function sigmaAllowed(choice: SigmaChoice, options: RatesSigmaOptions | null | undefined): string | null {
  if (!options || choice === "") return null;
  if (choice === "column") return options.column ? null : "the table has no standard-deviation column";
  if (options.column) return "the table has a standard-deviation column, and exactly one source of uncertainty is used";
  if (choice === "replicates" && !options.replicates) return "no condition was measured more than once";
  return null;
}

/** A level or significance typed as text: empty means the command's default. */
function number(text: string): number | string | undefined {
  const t = text.trim();
  if (!t) return undefined;
  const n = parseNumber(t);
  return n === null ? t : n;
}

export function ratesRequest(source: Source, preview: RatesPreview | null | undefined, form: FitForm, literature: boolean): RatesRequest {
  const request: RatesRequest = {
    dataset: {
      text: source.text,
      filename: source.filename,
      mapping: preview?.mapping ?? {},
    },
    sigma_from: form.sigma,
  };
  if (form.sigma === "replicates") request.error_model = form.errorModel;
  if (form.model && form.model !== "auto") request.model = form.model;
  const level = number(form.level);
  const significance = number(form.significance);
  if (level !== undefined) request.level = level as number;
  if (significance !== undefined) request.significance = significance as number;
  if (literature && form.ec.trim()) {
    request.ec = form.ec.trim();
    for (const key of ["organism", "substrate", "inhibitor", "isoform"] as const) {
      if (form[key].trim()) request[key] = form[key].trim();
    }
  }
  const conc = number(form.enzymeConc);
  if (conc !== undefined) {
    request.enzyme_concentration = conc as number;
    request.enzyme_unit = form.enzymeUnit;
  }
  return request;
}

function text(value: unknown): string {
  return typeof value === "string" ? value : typeof value === "number" && Number.isFinite(value) ? String(value) : "";
}

/** The source and the form a stored request was made from: the inverse of `ratesRequest`. */
export function requestState(request: Record<string, unknown>): { source: Source | null; mapping: RatesMapping; form: FitForm; literature: boolean } {
  const r = request as Partial<RatesRequest>;
  const dataset = r.dataset;
  const source: Source | null =
    dataset && typeof dataset.text === "string" ? { text: dataset.text, filename: dataset.filename ?? null, origin: "run" } : null;
  const sigma = r.sigma_from === "column" || r.sigma_from === "replicates" || r.sigma_from === "residuals" ? r.sigma_from : "";
  return {
    source,
    mapping: dataset?.mapping ?? {},
    literature: Boolean(r.ec),
    form: {
      ...EMPTY_FIT,
      model: text(r.model) || "auto",
      sigma,
      sigmaTouched: sigma !== "",
      errorModel: r.error_model === "proportional" ? "proportional" : "constant",
      level: text(r.level),
      significance: text(r.significance),
      ec: text(r.ec),
      organism: text(r.organism),
      substrate: text(r.substrate),
      inhibitor: text(r.inhibitor),
      isoform: text(r.isoform),
      enzymeConc: text(r.enzyme_concentration),
      enzymeUnit: text(r.enzyme_unit) || "uM",
    },
  };
}

// ---------------------------------------------------------------------------
// Reading the person's file
// ---------------------------------------------------------------------------

export const WORKBOOK_EXTENSIONS = /\.(xlsx|xlsm|xls|ods|numbers|pdf|docx?|zip|gz)$/i;

export type ReadResult = { ok: true; source: Source } | { ok: false; message: string };

export function sizeMessage(bytes: number): string {
  return `That is ${bytes.toLocaleString("en-US")} bytes, and a table is limited to ${RATES_MAX_BYTES.toLocaleString("en-US")} bytes. A rates table is tens of rows: send the part you want fitted.`;
}

/** Read a dropped or chosen file as text; the server does the rest. Nothing is sent from here. */
export async function readFile(file: File): Promise<ReadResult> {
  if (WORKBOOK_EXTENSIONS.test(file.name)) {
    return {
      ok: false,
      message: `${file.name} is not a text file. Export the sheet as CSV (or copy the cells and paste them here), and this page will read it.`,
    };
  }
  if (file.size > RATES_MAX_BYTES) return { ok: false, message: sizeMessage(file.size) };
  const text = await file.text();
  const replaced = (text.match(/�/g) ?? []).length;
  return {
    ok: true,
    source: {
      text,
      filename: file.name,
      origin: "file",
      note: replaced
        ? `${replaced} byte(s) in the file are not valid UTF-8 and show as replacement characters; save it as CSV (UTF-8) if a name or unit looks wrong.`
        : undefined,
    },
  };
}

export function readPasted(text: string): ReadResult {
  const bytes = new TextEncoder().encode(text).length;
  if (bytes > RATES_MAX_BYTES) return { ok: false, message: sizeMessage(bytes) };
  if (!text.trim()) return { ok: false, message: "The clipboard has no text in it. Copy the cells in your spreadsheet and try again." };
  return { ok: true, source: { text, filename: null, origin: "paste" } };
}

/** The sentence announced once when a table has been read. */
export function announcement(preview: RatesPreview): string {
  if (!preview.ready) return `The table cannot be fitted yet: ${preview.refusal ?? "see the problems listed"}`;
  const s = preview.summary;
  if (!s) return "The table was read.";
  const names = preview.columns.filter((c) => c.role).map((c) => `${c.name} as ${c.role}`);
  const skipped = s.rows_skipped ? `, ${s.rows_skipped} skipped` : "";
  return `Read ${s.rows_used} measurements${skipped}: ${names.join(", ")}.`;
}

// ---------------------------------------------------------------------------
// Roles
// ---------------------------------------------------------------------------

export const ROLE_CHOICES: readonly { value: string; label: string }[] = [
  { value: "substrate", label: "Substrate concentration" },
  { value: "rate", label: "Rate" },
  { value: "rate-replicate", label: "Rate (a replicate column)" },
  { value: "sigma", label: "Standard deviation of the rate" },
  { value: "inhibitor", label: "Inhibitor concentration" },
  { value: "group", label: "Group" },
  { value: "replicate", label: "Replicate number (not used)" },
  { value: "none", label: "Not used" },
];

/** The role a column plays now, as one of ROLE_CHOICES' values. */
export function roleOf(mapping: RatesMapping, index: number): string {
  const roles = (mapping.roles ?? {}) as Record<string, unknown>;
  if (Array.isArray(roles.rates) && roles.rates.includes(index)) return "rate-replicate";
  for (const role of ["substrate", "rate", "sigma", "inhibitor", "group", "replicate"]) if (roles[role] === index) return role;
  return "none";
}

/** The mapping with column `index` given `role`, and taken from whatever held that role before. */
export function withRole(mapping: RatesMapping, index: number, role: string): RatesMapping {
  const roles: Record<string, unknown> = { ...((mapping.roles ?? {}) as Record<string, unknown>) };
  for (const key of ["substrate", "rate", "sigma", "inhibitor", "group", "replicate"]) if (roles[key] === index) roles[key] = null;
  const rates = Array.isArray(roles.rates) ? (roles.rates as number[]).filter((i) => i !== index) : [];
  roles.rates = rates;
  if (role === "rate-replicate") {
    roles.rates = [...rates, index].sort((a, b) => a - b);
    roles.rate = null;
  } else if (role !== "none") {
    roles[role] = index;
    if (role === "rate") roles.rates = [];
  }
  return { ...mapping, roles };
}

/** The concentration and rate units a table can be expressed in, for the conversion choices. */
export const CONCENTRATION_TARGETS = ["M", "mM", "uM", "nM"] as const;
export const RATE_TARGETS = ["M/s", "mM/s", "uM/s", "nM/s", "M/min", "mM/min", "uM/min", "nM/min"] as const;

export function unitLabel(unit: string): string {
  return unit.replace(/^u/, "µ").replace(/\/u/, "/µ");
}
