/**
 * The claims behind a compose result, and the action that re-checks them.
 *
 * Every number in a compose run is a claim in a bundle the run wrote beside
 * its files (docs/studio/CONTRACT.md 11; ADR 0179): the pinned pages, the
 * rows read from them, and one claim per constant and starting amount,
 * each identified by its derivation. This section says what the bundle
 * holds, in the counts the server sent and the report's own `## Claims`
 * text, offers the bundle as the two files the run recorded, and carries
 * "Re-check this run": `POST /api/runs/{id}/verify`, the checker `caterva
 * verify` runs, which reads only the bundle's own files and shares no code
 * with what wrote them. The report comes back as the command prints it,
 * one line per check; the page adds the constant's name beside a claim ref
 * it knows, and nothing else. A report with nothing failed says each check
 * that ran still holds against the pinned bytes, not that the paper was
 * right, and lists what did not run.
 *
 * A result captured before bundles existed carries no `claims`: the action
 * is then disabled with the contract's sentence for a run without a bundle,
 * the same one the server answers 409 with (NO_CLAIMS_BUNDLE).
 */
import { Download, ListChecks } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";

import { downloadArtifact } from "@/api/runs";
import { type ClaimKind, type ClaimsSummary, type ComposeResult, NO_CLAIMS_BUNDLE, type RunRecord, type VerifyReport } from "@/api/types";
import { PRINTED, failedChecks, heldChecks, notChecked, notRunChecks, ranChecks, verifyRun } from "@/api/verify";
import { Disclosure } from "@/components/forms/Disclosure";
import { shortDigest } from "@/components/provenance/ProvenanceDetail";
import { MarkdownReport } from "@/components/report/Report";
import { Section } from "@/components/screen/Screen";
import { Loading } from "@/components/states/Loading";
import { ErrorState, RefusalState } from "@/components/states/States";
import { plain, plural } from "@/lib/copy";
import { describeError } from "@/lib/errors";
import { formatWhen } from "@/lib/format";
import { notify } from "@/lib/toast";

/** The kinds in the order the report's `## Claims` line counts them. */
const KIND_ORDER: readonly ClaimKind[] = ["cited", "chosen", "placeholder", "refused", "computed"];

/** The checker's name for the subject of the root claim, as its `root` line prints it. */
const ROOT_NAME = "model";

/** Each claim ref the result carries, beside the identifier of the number that carries it. */
export function claimNames(result: ComposeResult): Map<string, string> {
  const names = new Map<string, string>();
  for (const p of result.model.parameters) {
    if (p.provenance.claim && p.id) names.set(p.provenance.claim.id, p.id);
  }
  for (const s of result.model.species) {
    if (s.initial.provenance.claim) names.set(s.initial.provenance.claim.id, s.id);
  }
  if (result.claims) names.set(result.claims.root, ROOT_NAME);
  return names;
}

/** The report's own count line, from the server's counts: "8 claims: 2 cited, ...; 2 rows and 1 pinned page in the bundle." */
export function countsSentence(claims: ClaimsSummary): string {
  const total = KIND_ORDER.reduce((n, kind) => n + (claims.counts[kind] ?? 0), 0);
  const parts = KIND_ORDER.map((kind) => `${claims.counts[kind] ?? 0} ${kind}`);
  return `${plural(total, "claim")}: ${parts.join(", ")}; ${plural(claims.rows, "row")} and ${plural(claims.snapshots, "pinned page")} in the bundle.`;
}

const NOT_SAVED = (what: string) => (e: unknown) => notify("failed", `${what} was not saved`, { description: describeError(e).message });

type RecheckState =
  | { status: "idle" }
  | { status: "running" }
  | { status: "done"; report: VerifyReport }
  | { status: "failed"; error: unknown };

/**
 * The action, with the report under it. Rendered with `key={run.id}` so a
 * different run starts from idle; a report is never shown beside a run it
 * was not made for.
 */
export function Recheck({ run, claims, names }: { run: RunRecord; claims: ClaimsSummary | null; names: Map<string, string> }) {
  const [state, setState] = useState<RecheckState>({ status: "idle" });
  const whyId = useId();
  const live = useRef(true);
  useEffect(
    () => () => {
      live.current = false;
    },
    [],
  );
  const running = state.status === "running";
  const disabled = claims === null;
  const recheck = () => {
    if (disabled || running) return;
    setState({ status: "running" });
    verifyRun(run.id).then(
      (report) => {
        if (live.current) setState({ status: "done", report });
      },
      (error: unknown) => {
        if (live.current) setState({ status: "failed", error });
      },
    );
  };
  return (
    <div className="k-recheck">
      <div className="k-recheck-bar">
        <button
          type="button"
          className="btn"
          disabled={disabled || running}
          aria-describedby={disabled ? whyId : undefined}
          onClick={recheck}
        >
          <ListChecks size={13} aria-hidden="true" />
          {state.status === "done" ? "Re-check again" : "Re-check this run"}
        </button>
        {disabled ? (
          <p className="form-why" id={whyId}>
            {NO_CLAIMS_BUNDLE.replace(/^./, (c) => c.toUpperCase())}.
          </p>
        ) : (
          <p className="k-recheck-hint">
            Runs the checker <span className="font-mono">caterva verify</span> runs over this run&apos;s bundle: it reads only the
            bundle&apos;s own files and shares no code with what wrote them.
          </p>
        )}
      </div>
      {state.status === "running" ? <Loading label="Re-checking every claim against the pinned pages" size={28} /> : null}
      {state.status === "failed" ? <ErrorState error={state.error} inset onRetry={recheck} again="re-check again" /> : null}
      {state.status === "done" ? <VerifyReportView report={state.report} names={names} /> : null}
    </div>
  );
}

/**
 * A verify report as a plain list: the command's verdict sentence, its
 * summary line, then one line per check (ok, FAIL or n/a as the command
 * prints them, the check's name, the number it is about when the page
 * knows it, and the detail as the checker wrote it), and what was not
 * checked, with the reason. A check that did not run is n/a and counted
 * apart, never as held. A failure is drawn as the command draws it (exit
 * 3, "Refused"): the first failing check named, in its own words, never as
 * a red error.
 */
export function VerifyReportView({ report, names }: { report: VerifyReport; names: Map<string, string> }) {
  const ran = ranChecks(report);
  const skipped = notChecked(report);
  const failed = failedChecks(report);
  const first = failed[0];
  const summary =
    `${ran.length} checks: ${heldChecks(report).length} ok, ${failed.length} failed, ` +
    `${notRunChecks(report).length} did not run; ${skipped.length} not checked.`;
  return (
    <div className="k-verify" data-ok={report.ok ? "true" : "false"}>
      {first ? (
        <RefusalState
          title={`${plural(failed.length, "check")} did not hold against the pinned bytes`}
          reason={`${first.name}: ${first.detail}`}
          inset={false}
        />
      ) : (
        <p className="k-verify-verdict" role="status">
          <span className="state-kicker">Re-checkable</span>
          every check that ran holds against the pinned bytes; what did not run is listed below with the reason.
        </p>
      )}
      <p className="k-verify-summary muted">
        {summary} Re-checked {formatWhen(report.ran_at)}.
      </p>
      <ol className="k-checks" aria-label="Every check, as the checker printed it">
        {ran.map((c, i) => (
          <li key={`${i}-${c.name}`} data-ok={c.ok ? "true" : "false"} data-status={c.status}>
            <span className="k-check-ok">{PRINTED[c.status]}</span>
            <span className="k-check-name">{c.name}</span>
            <span className="k-check-about font-mono" title={c.claim ?? undefined}>
              {c.claim ? (names.get(c.claim) ?? shortDigest(c.claim)) : ""}
            </span>
            <span className="k-check-detail">{plain(c.detail)}</span>
          </li>
        ))}
      </ol>
      {skipped.length ? (
        <p className="k-invariants muted">Not checked: {skipped.map((c) => plain(c.detail)).join("; ")}</p>
      ) : null}
    </div>
  );
}

export function ClaimsSection({ result, run }: { result: ComposeResult; run: RunRecord }) {
  const claims = result.claims ?? null;
  const files = claims
    ? [claims.bundle, claims.listing]
        .map((name) => run.artifacts.find((a) => a.name === name))
        .filter((a): a is RunRecord["artifacts"][number] => a !== undefined)
    : [];
  return (
    <Section
      title="The claims behind the numbers"
      id="k-claims"
      aside={
        claims ? (
          <span className="font-mono" title={claims.root}>
            {shortDigest(claims.root)}
          </span>
        ) : undefined
      }
    >
      {claims ? (
        <>
          <p className="k-lede">
            Each number above is a claim whose id is its derivation, in a bundle this run wrote beside its files:{" "}
            {countsSentence(claims)} The root claim is the model over all of them. Activate a number for its derivation,
            down to the pinned page it rests on.
          </p>
          {claims.notes.length ? (
            <ul className="k-notes">
              {claims.notes.map((n) => (
                <li key={n}>{plain(n)}</li>
              ))}
            </ul>
          ) : null}
          {files.length ? (
            <div className="k-toolbar" role="group" aria-label="The bundle">
              {files.map((a) => (
                <button
                  key={a.name}
                  type="button"
                  className="btn btn-sm"
                  title={a.description}
                  onClick={() => void downloadArtifact(run.id, a.name).catch(NOT_SAVED(a.name))}
                >
                  <Download size={13} aria-hidden="true" />
                  {a.name}
                </button>
              ))}
              <span className="k-toolbar-label">
                unzipped, the folder is what <span className="font-mono">caterva verify</span> and{" "}
                <span className="font-mono">caterva why</span> take
              </span>
            </div>
          ) : null}
        </>
      ) : null}
      <Recheck key={run.id} run={run} claims={claims} names={claimNames(result)} />
      {claims ? (
        <Disclosure title="As the report prints it">
          <MarkdownReport source={claims.text} className="k-analysis-text" prose />
        </Disclosure>
      ) : null}
    </Section>
  );
}
