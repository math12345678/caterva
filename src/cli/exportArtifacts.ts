/**
 * Write the two artifacts a run should be able to leave behind:
 * an annotated model, and a bibliography.
 *
 * WHY THIS FILE EXISTS AT ALL
 * ---------------------------
 * Both capabilities were built and neither was reachable. `scientific` had
 * no flag that produced either one.
 *
 * That is the same failure this codebase criticises everywhere else: a
 * reliability score computed and shown to nobody, a route documented and
 * never registered, a guard that reports on work it did not do. A feature
 * nobody can invoke does not exist, and the repository being able to point
 * at a module is worse than nothing, because it can then claim the
 * capability.
 *
 *   --export-model out.txt   Antimony with provenance in comments
 *                            (Sauro's mechanism: the assumption travels
 *                            inside the artifact, not in a console)
 *   --export-citations b.bib Every source behind the run, in BibTeX or RIS
 *                            (Katz's: a citation you cannot put in a
 *                            bibliography is a claim about a citation)
 *
 * The model builders and the exporters are Python; the provenance is
 * assembled here. Rather than reimplement either side, this module spawns
 * the same scripts over the same JSON protocol the resolver already uses.
 */

import { spawn } from 'child_process';
import { writeFile } from 'fs/promises';
import path from 'path';

import { REPO_ROOT, resolvePythonExecutable } from '../engine/teriumBridge';

export interface ExportProvenance {
  origin: string;
  citation?: string;
  organism?: string;
  source?: string;
  citationStatus?: string;
  crossSpecies?: boolean;
  reliability?: Record<string, string>;
  /** The same axes as (axis -> why), for the exported model's notes. */
  reliabilityReasons?: Record<string, string>;
  note?: string;
  /** The registry the citation came from, e.g. 'BRENDA', 'PubMed'. */
  citationSource?: string;
  /** Its accession within that registry. Structured rather than left
   *  embedded in `citation`, so the SBML annotator can ask whether a
   *  resolvable URI exists instead of regexing a display string. */
  referenceId?: string;
  /** NCBI Taxonomy id, only when something actually resolved it. Never
   *  inferred from `organism`, which is a name, not an identifier. */
  taxonId?: string;
}

export interface ModelExportRequest {
  domain: string;
  parameters: Record<string, number>;
  provenance: Record<string, ExportProvenance>;
  query?: string;
  runId?: string;
  /** The time course that ACTUALLY ran, for the SED-ML inside a COMBINE
   *  archive. Not defaulted anywhere: an archive describing an experiment
   *  nobody performed is reproducible and wrong. */
  endTime?: number;
  points?: number;
  /* `recorded` used to live here: the species the SED-ML report should
     record. It is gone because the exporter reads them from the MODEL now.
     A caller-supplied list is a second statement of something the model
     already makes -- and the two can disagree, which is how a competitively
     -inhibited run got an archive whose report omitted the inhibitor. */
  /** Citation file to bundle alongside the model, if one was produced. */
  bibtex?: string;
  /** Taxon of the organism the model is ABOUT. Written as the model-level
   *  `bqbiol:hasTaxon` in the SBML export, which is what lets a consumer
   *  spot a parameter measured in something else. */
  modelTaxonId?: string;
  /** EC number, written as `bqbiol:isVersionOf` on the model. */
  ecNumber?: string;
}

export interface ExportOutcome {
  ok: boolean;
  /** Written only on success. */
  path?: string;
  /** Parameters the exported model marks as unsourced, cross-species or
   * defaulted. Reported so the CLI can say so without re-reading the file. */
  unsourced?: string[];
  error?: string;
  /** 'antimony' | 'sbml' — which the exporter actually wrote. */
  format?: string;
  /** SBML only: how many MIRIAM RDF terms were written. */
  cvterms?: number;
  /** COMBINE archive only: what the archive contains. */
  entries?: string[];
  /** SBML only: identifiers with no resolvable URI form, which therefore
   *  travel as text. Reported rather than silently omitted — an absent
   *  annotation and a refused one look identical in the file. */
  refusedUris?: Array<{ parameter: string; accession: string; reason: string }>;
}

const SCRIPT_TIMEOUT_MS = 60_000;

function runPythonScript(script: string, payload: unknown): Promise<string> {
  return new Promise((resolve, reject) => {
    const executable = resolvePythonExecutable(REPO_ROOT);
    const scriptPath = path.join(REPO_ROOT, 'scripts', script);

    const proc = spawn(executable, [scriptPath], {
      cwd: REPO_ROOT,
      stdio: ['pipe', 'pipe', 'pipe'],
    });

    let stdout = '';
    let stderr = '';
    let settled = false;

    // A hung subprocess must not hang the CLI forever. The timer is
    // cleared on every exit path, and `settled` guards against a race
    // where the process exits as the timeout fires -- otherwise a slow but
    // successful export would report a timeout it did not have.
    const timer = setTimeout(() => {
      if (settled) return;
      settled = true;
      proc.kill('SIGKILL');
      reject(new Error(`${script} did not finish within ${SCRIPT_TIMEOUT_MS}ms`));
    }, SCRIPT_TIMEOUT_MS);

    proc.stdout.on('data', (chunk) => (stdout += chunk));
    proc.stderr.on('data', (chunk) => (stderr += chunk));

    proc.on('error', (err) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      reject(err);
    });

    proc.on('close', () => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      // The exit CODE is not the contract; the payload is. The script
      // reports its own failure as JSON on stdout and exits 1, so reading
      // the code first would discard the reason -- the same mistake
      // teriumRunner.ts had to be corrected for.
      if (!stdout.trim()) {
        reject(new Error(stderr.trim() || `${script} produced no output`));
        return;
      }
      resolve(stdout);
    });

    proc.stdin.write(JSON.stringify(payload));
    proc.stdin.end();
  });
}

/**
 * Write an Antimony model with its provenance in comments.
 *
 * Refuses rather than defaults: if a parameter is missing the script says
 * so and nothing is written. A file that quietly filled a gap would carry
 * comments claiming full provenance for a value nobody supplied, which is
 * the worst possible output of a provenance feature.
 */
/**
 * Antimony or SBML, chosen from the extension.
 *
 * Not a separate flag. `--export-model out.xml` and `--export-model out.txt`
 * asking for different formats is one decision in one place; a `--format`
 * flag beside a path is two, and they can disagree.
 */
export function modelFormatForPath(
  destination: string,
): 'antimony' | 'sbml' | 'omex' {
  if (/\.omex$/i.test(destination)) return 'omex';
  return /\.(xml|sbml)$/i.test(destination) ? 'sbml' : 'antimony';
}

export async function exportModel(
  request: ModelExportRequest,
  destination: string,
): Promise<ExportOutcome> {
  let raw: string;
  try {
    raw = await runPythonScript('export_annotated_model.py', {
      ...request,
      format: modelFormatForPath(destination),
      generatedAt: new Date().toISOString(),
    });
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : String(err) };
  }

  let parsed: {
    ok?: boolean;
    model?: string;
    /** Set instead of `model` for binary formats. */
    modelBase64?: string;
    entries?: string[];
    unsourced?: string[];
    error?: string;
    format?: string;
    cvterms?: number;
    unannotated?: string[];
    refusedUris?: Array<{ parameter: string; accession: string; reason: string }>;
  };
  try {
    parsed = JSON.parse(raw.trim());
  } catch {
    return { ok: false, error: `Model exporter returned unparseable output: ${raw.slice(0, 200)}` };
  }

  const isBinary = typeof parsed.modelBase64 === 'string';
  if (!parsed.ok || (typeof parsed.model !== 'string' && !isBinary)) {
    return { ok: false, error: parsed.error ?? 'Model exporter reported failure' };
  }

  try {
    if (isBinary) {
      // A zip written as a utf-8 string is silently corrupted: every byte
      // outside the ASCII range becomes U+FFFD and the file still has a
      // plausible size. Buffer, not string.
      await writeFile(destination, Buffer.from(parsed.modelBase64!, 'base64'));
    } else {
      await writeFile(destination, parsed.model!, 'utf-8');
    }
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : String(err) };
  }

  return {
    ok: true,
    path: destination,
    // SBML reports `unannotated` where Antimony reports `unsourced`. They
    // are the same question -- which parameters reached the file with no
    // stated origin -- so they are surfaced through one field rather than
    // leaving the caller to know which format it asked for.
    unsourced: parsed.unsourced ?? parsed.unannotated ?? [],
    format: parsed.format,
    cvterms: parsed.cvterms,
    refusedUris: parsed.refusedUris ?? [],
    entries: parsed.entries ?? [],
  };
}

export interface CitedValue {
  parameter: string;
  citationSource: string;
  referenceId?: string;
  url?: string;
  title?: string;
  value?: number;
  unit?: string;
  organism?: string;
}

/**
 * Pick the format from the file extension.
 *
 * Explicit rather than defaulting to BibTeX: writing RIS content into a
 * `.bib` file produces something that imports as one malformed record, and
 * the user finds out inside their reference manager rather than here.
 */
export function formatForPath(destination: string): 'bibtex' | 'ris' | null {
  const extension = path.extname(destination).toLowerCase();
  if (extension === '.bib' || extension === '.bibtex') return 'bibtex';
  if (extension === '.ris') return 'ris';
  return null;
}

export async function exportCitations(
  cited: CitedValue[],
  destination: string,
): Promise<ExportOutcome> {
  const format = formatForPath(destination);
  if (format === null) {
    return {
      ok: false,
      error:
        `Cannot tell which citation format to write from '${path.basename(destination)}'. ` +
        'Use a .bib or .ris extension — writing RIS into a .bib file produces ' +
        'a file that fails to import, and the failure surfaces in your ' +
        'reference manager rather than here.',
    };
  }

  let raw: string;
  try {
    raw = await runPythonScript('export_citations.py', { format, cited });
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : String(err) };
  }

  let parsed: { ok?: boolean; document?: string; entries?: number; error?: string };
  try {
    parsed = JSON.parse(raw.trim());
  } catch {
    return { ok: false, error: `Citation exporter returned unparseable output: ${raw.slice(0, 200)}` };
  }

  if (!parsed.ok || typeof parsed.document !== 'string') {
    return { ok: false, error: parsed.error ?? 'Citation exporter reported failure' };
  }

  try {
    await writeFile(destination, parsed.document, 'utf-8');
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : String(err) };
  }

  return { ok: true, path: destination };
}
