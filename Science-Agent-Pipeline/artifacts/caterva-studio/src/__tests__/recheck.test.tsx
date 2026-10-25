/**
 * Re-checking a compose run's claims bundle from the page, over the real
 * answers of `POST /api/runs/{id}/verify` (src/__fixtures__/api/kinetics,
 * README there): the hexokinase run as written, the same run after one
 * byte of its pinned page was changed, and a run that wrote no bundle. No
 * number in these tests is typed by hand.
 */
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import hexokinase from "@/__fixtures__/api/kinetics/compose-hexokinase-claims.json";
import verifyChanged from "@/__fixtures__/api/kinetics/verify-hexokinase-changed-byte.json";
import verifyOk from "@/__fixtures__/api/kinetics/verify-hexokinase.json";
import verifyNoBundle from "@/__fixtures__/api/kinetics/verify-no-bundle.json";
import { json, mockServer, setSessionToken } from "@/__tests__/helpers";
import { ApiRequestError } from "@/api/client";
import { type ApiError, type ComposeResult, NO_CLAIMS_BUNDLE, type RunRecord, SESSION_HEADER, type VerifyReport } from "@/api/types";
import { failedChecks, heldChecks, notChecked, notRunChecks, ranChecks, verifyRun } from "@/api/verify";
import { plain } from "@/lib/copy";
import { ClaimsSection, claimNames, countsSentence } from "@/screens/kinetics/Recheck";

const result = hexokinase.result as unknown as ComposeResult;
const run = hexokinase.run as unknown as RunRecord;
const passed = verifyOk.body as unknown as VerifyReport;
const changed = verifyChanged.body as unknown as VerifyReport;
const noBundle = verifyNoBundle.body as { error: ApiError };
const verifyPath = `/api/runs/${run.id}/verify`;
const km = result.model.parameters.find((p) => p.id === "reaction_Km")!.provenance.claim!;

function escape(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

afterEach(() => vi.unstubAllGlobals());

describe("verifyRun", () => {
  it("POSTs an empty object with the session header and hands back the checker's report", async () => {
    setSessionToken("t0k");
    const { seen } = mockServer((req) => (req.method === "POST" && req.url === verifyPath ? json(200, passed) : undefined));
    const report = await verifyRun(run.id);
    expect(seen).toHaveLength(1);
    expect(seen[0].body).toEqual({});
    expect(seen[0].headers.get(SESSION_HEADER)).toBe("t0k");
    expect(report).toEqual(passed);
    expect(report.ok).toBe(true);
    expect(report.checks.every((c) => c.ok)).toBe(true);
  });

  it("refuses a report whose check is not a boolean, rather than drawing it as passed", async () => {
    setSessionToken("t0k");
    const [first, ...rest] = passed.checks;
    mockServer(() => json(200, { ...passed, checks: [{ ...first, ok: "yes" }, ...rest] }));
    const e = await verifyRun(run.id).catch((x: unknown) => x);
    expect(e).toBeInstanceOf(ApiRequestError);
    expect((e as ApiRequestError).kind).toBe("contract");
    expect((e as ApiRequestError).error.field).toBe("checks.0.ok");
  });

  it("refuses a check whose ok and status disagree, rather than drawing one of them", async () => {
    setSessionToken("t0k");
    const [first, ...rest] = passed.checks;
    mockServer(() => json(200, { ...passed, checks: [{ ...first, ok: true, status: "failed" }, ...rest] }));
    const e = await verifyRun(run.id).catch((x: unknown) => x);
    expect(e).toBeInstanceOf(ApiRequestError);
    expect((e as ApiRequestError).kind).toBe("contract");
    expect((e as ApiRequestError).error.field).toBe("checks.0.status");
  });

  it("sorts the checker's lines as the command prints them", () => {
    expect(ranChecks(passed).length + notChecked(passed).length).toBe(passed.checks.length);
    expect(notChecked(passed).every((c) => c.name === "not checked" && c.ok)).toBe(true);
    expect(failedChecks(passed)).toEqual([]);
    expect(failedChecks(changed).length).toBeGreaterThan(0);
    expect(failedChecks(changed).every((c) => !c.ok && c.name !== "not checked")).toBe(true);
  });
});

describe("The claims section", () => {
  it("says what the bundle holds, from the server's counts, and offers its two files", () => {
    const claims = result.claims!;
    render(<ClaimsSection result={result} run={run} />);
    const section = screen.getByRole("region", { name: "The claims behind the numbers" });
    expect(section).toHaveTextContent(countsSentence(claims));
    for (const kind of ["cited", "chosen", "placeholder", "refused", "computed"]) {
      expect(countsSentence(claims)).toContain(`${claims.counts[kind]} ${kind}`);
    }
    const files = within(section).getByRole("group", { name: "The bundle" });
    for (const name of [claims.bundle, claims.listing]) {
      expect(run.artifacts.map((a) => a.name)).toContain(name);
      expect(within(files).getByRole("button", { name })).toBeInTheDocument();
    }
    expect(within(section).getByRole("button", { name: "Re-check this run" })).toBeEnabled();
    expect(within(section).queryByRole("list", { name: "Every check, as the checker printed it" })).toBeNull();
  });

  it("re-checks the run and lists every check as the checker printed it, naming the constant beside its claim", async () => {
    setSessionToken("t0k");
    const { seen } = mockServer((req) => (req.method === "POST" && req.url === verifyPath ? json(200, passed) : undefined));
    render(<ClaimsSection result={result} run={run} />);
    await userEvent.click(screen.getByRole("button", { name: "Re-check this run" }));
    const list = await screen.findByRole("list", { name: "Every check, as the checker printed it" });
    expect(seen.filter((r) => r.method === "POST").map((r) => r.url)).toEqual([verifyPath]);
    const ran = ranChecks(passed);
    const items = within(list).getAllByRole("listitem");
    expect(items).toHaveLength(ran.length);
    items.forEach((li, i) => {
      expect(li).toHaveAttribute("data-ok", "true");
      expect(li).toHaveTextContent(ran[i].name);
      expect(li).toHaveTextContent(plain(ran[i].detail));
    });
    expect(screen.getByRole("status")).toHaveTextContent("every check that ran holds against the pinned bytes");
    expect(heldChecks(passed)).toHaveLength(ran.length);
    expect(
      screen.getByText(new RegExp(`^${ran.length} checks: ${ran.length} ok, 0 failed, 0 did not run; ${notChecked(passed).length} not checked\\.`)),
    ).toBeInTheDocument();
    // The Km claim's checks carry the constant's name beside the ref the checker wrote.
    const kmChecks = ran.filter((c) => c.claim === km.id);
    expect(kmChecks.map((c) => c.name)).toEqual(expect.arrayContaining(["identity", "row locator", "certificate", "dominance"]));
    expect(within(list).getAllByText("reaction_Km")).toHaveLength(kmChecks.length);
    for (const el of within(list).getAllByText("reaction_Km")) expect(el).toHaveAttribute("title", km.id);
    // What the checker cannot do is listed with its reason, never left out.
    for (const c of notChecked(passed)) expect(screen.getByText(/^Not checked:/)).toHaveTextContent(plain(c.detail));
    expect(screen.getByRole("button", { name: "Re-check again" })).toBeEnabled();
  });

  it("shows a failed check naming the claim, in the checker's words, after a pinned byte was changed", async () => {
    setSessionToken("t0k");
    mockServer((req) => (req.method === "POST" && req.url === verifyPath ? json(200, changed) : undefined));
    render(<ClaimsSection result={result} run={run} />);
    await userEvent.click(screen.getByRole("button", { name: "Re-check this run" }));
    const failed = failedChecks(changed);
    expect(changed.ok).toBe(false);
    const notice = await screen.findByRole("region", { name: new RegExp(`^${failed.length} checks? did not hold against the pinned bytes$`) });
    // The first failing check is the page's bytes; its detail names the Km claim that rests on them.
    expect(failed[0].name).toBe("snapshot bytes");
    expect(failed[0].detail).toContain(km.id);
    expect(failed[0].detail).toContain("reaction_Km");
    expect(notice).toHaveTextContent(`${failed[0].name}: ${plain(failed[0].detail)}`);
    expect(notice).toHaveTextContent(km.id);
    const list = screen.getByRole("list", { name: "Every check, as the checker printed it" });
    const failedItems = within(list).getAllByRole("listitem").filter((li) => li.getAttribute("data-ok") === "false");
    expect(failedItems).toHaveLength(failed.length);
    expect(within(list).getAllByText("FAIL")).toHaveLength(failed.length);
    for (const c of failed.filter((c) => c.claim === km.id)) {
      expect(within(list).getByText(plain(c.detail))).toBeInTheDocument();
    }
    expect(screen.getByText(new RegExp(`^${ranChecks(changed).length} checks: .* ${failed.length} failed,`))).toBeInTheDocument();
    expect(screen.queryByRole("status")).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("draws a check that did not run as n/a, counts it apart, and never calls it held", async () => {
    // The hexokinase run carried every ordinal, so its dominance checks ran;
    // a run whose chosen row's ordinals were not carried gets this line
    // instead, as caterva/check/verify.py writes it. Only the state changes.
    const dominance = passed.checks.findIndex((c) => c.name === "dominance" && c.claim === km.id);
    expect(dominance).toBeGreaterThanOrEqual(0);
    const checks = passed.checks.map((c, i) => (i === dominance ? { ...c, status: "not run" as const } : c));
    const notRun: VerifyReport = { ...passed, checks };
    setSessionToken("t0k");
    mockServer((req) => (req.method === "POST" && req.url === verifyPath ? json(200, notRun) : undefined));
    render(<ClaimsSection result={result} run={run} />);
    await userEvent.click(screen.getByRole("button", { name: "Re-check this run" }));
    const list = await screen.findByRole("list", { name: "Every check, as the checker printed it" });
    const ran = ranChecks(notRun);
    const item = within(list).getAllByRole("listitem")[ran.indexOf(checks[dominance])];
    expect(item).toHaveAttribute("data-status", "not run");
    expect(item).toHaveTextContent(/^n\/a/);
    expect(within(list).getAllByText("n/a")).toHaveLength(1);
    expect(notRunChecks(notRun)).toHaveLength(1);
    expect(heldChecks(notRun)).toHaveLength(ran.length - 1);
    expect(
      screen.getByText(new RegExp(`^${ran.length} checks: ${ran.length - 1} ok, 0 failed, 1 did not run;`)),
    ).toBeInTheDocument();
    const verdict = screen.getByRole("status");
    expect(verdict).toHaveTextContent("every check that ran holds against the pinned bytes; what did not run is listed below");
    expect(verdict).not.toHaveTextContent("every derivation");
  });

  it("is disabled with the contract's sentence for a result that carries no bundle", () => {
    const before = { ...result, claims: null } as ComposeResult;
    render(<ClaimsSection result={before} run={run} />);
    const button = screen.getByRole("button", { name: "Re-check this run" });
    expect(button).toBeDisabled();
    expect(button).toHaveAccessibleDescription(new RegExp(escape(NO_CLAIMS_BUNDLE), "i"));
    expect(noBundle.error.message).toBe(NO_CLAIMS_BUNDLE);
    expect(screen.queryByRole("group", { name: "The bundle" })).toBeNull();
  });

  it("shows the server's 409 whole when the folder is gone after all", async () => {
    setSessionToken("t0k");
    mockServer((req) => (req.method === "POST" && req.url === verifyPath ? json(verifyNoBundle.status, noBundle) : undefined));
    render(<ClaimsSection result={result} run={run} />);
    await userEvent.click(screen.getByRole("button", { name: "Re-check this run" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(plain(noBundle.error.message));
    expect(screen.queryByRole("list", { name: "Every check, as the checker printed it" })).toBeNull();
  });

  it("maps each claim ref to the number that carries it, and the root to the model", () => {
    const names = claimNames(result);
    for (const p of result.model.parameters) expect(names.get(p.provenance.claim!.id)).toBe(p.id);
    for (const s of result.model.species) expect(names.get(s.initial.provenance.claim!.id)).toBe(s.id);
    expect(names.get(result.claims!.root)).toBe("model");
    expect(names.size).toBe(result.model.parameters.length + result.model.species.length + 1);
  });
});
