/**
 * The assistant on the page: the five features, Settings, the status line, History's mark and the key bridge.
 *
 * Every server answer here is a REAL recorded one (src/__fixtures__/api/assistant, README there): what the studio
 * server answered for a real captured compose result, with a fake transport behind it returning hand-written
 * replies. So these tests prove what the PAGE does with each outcome (accept, reject, fall back, off, cancel); they
 * do not say what a real model would write. The replies are named in the fixture names.
 */
import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { RunRecord } from "@/api/types";
import { AssistantSection } from "@/components/assistant/AssistantSection";
import { AssistantStatusItem } from "@/components/assistant/AssistantStatusItem";
import { DescribeAssist } from "@/components/assistant/DescribeAssist";
import { RunAssistant } from "@/components/assistant/RunAssistant";
import { RunRow } from "@/components/run/RunRow";
import { assistantKeyStatus, clearAssistantKey, setAssistantKey } from "@/lib/desktop";
import { makeQueryClient } from "@/lib/queries";

import answerAsk from "@/__fixtures__/api/assistant/answer-ask-accepted.json";
import answerDeclined from "@/__fixtures__/api/assistant/answer-ask-declined.json";
import answerDescribe from "@/__fixtures__/api/assistant/answer-describe-accepted.json";
import answerDescribeRejected from "@/__fixtures__/api/assistant/answer-describe-rejected.json";
import answerExplain from "@/__fixtures__/api/assistant/answer-explain-accepted.json";
import answerError from "@/__fixtures__/api/assistant/answer-explain-provider-error.json";
import answerRejected from "@/__fixtures__/api/assistant/answer-explain-rejected.json";
import answerMethods from "@/__fixtures__/api/assistant/answer-methods-accepted.json";
import answerNext from "@/__fixtures__/api/assistant/answer-next-accepted.json";
import answerTest from "@/__fixtures__/api/assistant/answer-test-accepted.json";
import confirmDescribe from "@/__fixtures__/api/assistant/confirm-describe.json";
import prepareAsk from "@/__fixtures__/api/assistant/prepare-ask-accepted.json";
import prepareAskRefused from "@/__fixtures__/api/assistant/prepare-ask-refused.json";
import prepareDescribe from "@/__fixtures__/api/assistant/prepare-describe-accepted.json";
import prepareDescribeFirst from "@/__fixtures__/api/assistant/prepare-describe-accepted-first-use.json";
import prepareExplain from "@/__fixtures__/api/assistant/prepare-explain-accepted.json";
import prepareExplainFirst from "@/__fixtures__/api/assistant/prepare-explain-accepted-first-use.json";
import prepareMethods from "@/__fixtures__/api/assistant/prepare-methods-accepted.json";
import prepareNext from "@/__fixtures__/api/assistant/prepare-next-accepted.json";
import prepareTestFirst from "@/__fixtures__/api/assistant/prepare-test-accepted-first-use.json";
import analysed from "@/__fixtures__/api/assistant/run-compose-analysed.json";
import settingsOn from "@/__fixtures__/api/assistant/settings-on.json";
import statusExplainOnly from "@/__fixtures__/api/assistant/status-explain-only.json";
import statusLocal from "@/__fixtures__/api/assistant/status-local.json";
import statusOff from "@/__fixtures__/api/assistant/status-off.json";
import statusReady from "@/__fixtures__/api/assistant/status-ready.json";
import settingsDefault from "@/__fixtures__/api/assistant/settings-default.json";
import ldh from "@/__fixtures__/api/kinetics/compose-ldh-gossypol.json";

import { json, mockServer, type SeenRequest, setSessionToken } from "./helpers";

interface Recorded {
  status: number;
  body: unknown;
}

const run = analysed.body.run as unknown as RunRecord;
const result = analysed.body.result as unknown;
const TEST_KEY = "sk-ant-api03-TESTKEYdoNotUse0123456789abcdefghijklmnop";

function wrap(node: React.ReactNode) {
  return <QueryClientProvider client={makeQueryClient()}>{node}</QueryClientProvider>;
}

function serve(routes: Record<string, Recorded | ((req: SeenRequest) => Recorded)>) {
  return mockServer((req) => {
    const key = `${req.method} ${req.url.split("?")[0]}`;
    const hit = routes[key];
    if (!hit) return undefined;
    const r = typeof hit === "function" ? hit(req) : hit;
    return json(r.status, r.body);
  });
}

beforeEach(() => setSessionToken("token"));
afterEach(() => {
  vi.unstubAllGlobals();
  delete (window as unknown as { webkit?: unknown }).webkit;
});

const posts = (seen: SeenRequest[], path: string) => seen.filter((r) => r.method === "POST" && r.url === path);

describe("with the assistant off", () => {
  it("says so in one line, shows no tool, and talks to nothing but the status route", async () => {
    const { seen } = serve({ "GET /api/assistant/status": statusOff });
    render(wrap(<RunAssistant run={run} result={result} />));
    expect(await screen.findByText(/Assistant off\./)).toBeInTheDocument();
    expect(screen.queryByRole("button")).toBeNull();
    expect(seen.filter((r) => r.url.startsWith("/api/assistant")).map((r) => r.url)).toEqual(["/api/assistant/status"]);
  });

  it("draws nothing at all where there is no query client, or no assistant on the server", async () => {
    const { container } = render(<RunAssistant run={run} result={result} />);
    expect(container).toBeEmptyDOMElement();
    serve({});
    const second = render(wrap(<RunAssistant run={run} result={result} />));
    await waitFor(() => expect(screen.queryByText(/Assistant/)).toBeNull());
    second.unmount();
  });

  it("offers nothing for a kind the assistant does not read", () => {
    serve({ "GET /api/assistant/status": statusReady });
    const { container } = render(wrap(<RunAssistant run={{ ...run, kind: "sim" }} result={result} />));
    expect(container).toBeEmptyDOMElement();
  });

  it("shows no tool whose switch is off", async () => {
    serve({ "GET /api/assistant/status": statusExplainOnly });
    render(wrap(<RunAssistant run={run} result={result} />));
    expect(await screen.findByRole("button", { name: "Explain this result" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Draft my methods" })).toBeNull();
    expect(screen.queryByRole("button", { name: /What should I measure next/ })).toBeNull();
    expect(screen.queryByLabelText("Ask this run")).toBeNull();
  });
});

describe("Explain this result", () => {
  it("stops at a preview of the exact payload on first use, and sends it only when agreed", async () => {
    const { seen } = serve({
      "GET /api/assistant/status": statusReady,
      "POST /api/assistant/prepare": prepareExplainFirst,
      "POST /api/assistant/send": answerExplain,
      "POST /api/assistant/confirm": { status: 200, body: {} },
    });
    render(wrap(<RunAssistant run={run} result={result} />));
    await userEvent.click(await screen.findByRole("button", { name: "Explain this result" }));
    expect(await screen.findByText("Before the first send")).toBeInTheDocument();
    expect(screen.getByText(/api\.anthropic\.com/, { selector: "strong" })).toBeInTheDocument();
    const payload = screen.getByLabelText("The request, as it will be sent");
    expect(payload.textContent).toBe(prepareExplainFirst.body.payload);
    const send = screen.getByRole("button", { name: "Send" });
    expect(send).toBeDisabled();
    expect(posts(seen, "/api/assistant/send")).toHaveLength(0);
    await userEvent.click(screen.getByRole("checkbox", { name: /I agree to send this to api\.anthropic\.com/ }));
    await userEvent.click(send);
    await screen.findByText("Assistant text, not a measurement");
    const sent = posts(seen, "/api/assistant/send")[0].body as Record<string, unknown>;
    expect(sent).toEqual({
      call_id: prepareExplainFirst.body.call_id,
      payload_sha256: prepareExplainFirst.body.payload_sha256,
      consent: true,
    });
    expect(posts(seen, "/api/assistant/prepare")[0].body).toEqual({ feature: "explain", run_id: run.id });
    const reply = answerExplain.body.content as { reply: { summary: string; worst_thing: string; terms: { term: string }[] } };
    expect(screen.getByText(reply.reply.summary)).toBeInTheDocument();
    expect(screen.getByText(reply.reply.worst_thing)).toBeInTheDocument();
    expect(screen.getByText(reply.reply.terms[0].term)).toBeInTheDocument();
    expect(screen.getByText(/every figure and name in it was found in your results/)).toBeInTheDocument();
    expect(document.querySelectorAll('svg[data-kind="ai"]').length).toBeGreaterThan(0);
  });

  it("sends at once once the feature has been agreed to, and keeps the payload one disclosure away", async () => {
    const { seen } = serve({
      "GET /api/assistant/status": statusReady,
      "POST /api/assistant/prepare": prepareExplain,
      "POST /api/assistant/send": answerExplain,
    });
    render(wrap(<RunAssistant run={run} result={result} />));
    await userEvent.click(await screen.findByRole("button", { name: "Explain this result" }));
    await screen.findByText("Assistant text, not a measurement");
    expect(posts(seen, "/api/assistant/send")[0].body).toEqual({
      call_id: prepareExplain.body.call_id,
      payload_sha256: prepareExplain.body.payload_sha256,
    });
    await userEvent.click(screen.getByRole("button", { name: /What was sent/ }));
    expect(screen.getByLabelText("The request that was sent").textContent).toBe(prepareExplain.body.payload);
  });

  it("can show what would be sent without sending", async () => {
    const { seen } = serve({ "GET /api/assistant/status": statusReady, "POST /api/assistant/prepare": prepareExplain });
    render(wrap(<RunAssistant run={run} result={result} />));
    await userEvent.click(await screen.findByRole("button", { name: "Show what Explain this result would send" }));
    expect(await screen.findByText("What would be sent")).toBeInTheDocument();
    expect(posts(seen, "/api/assistant/send")).toHaveLength(0);
    await userEvent.click(screen.getByRole("button", { name: "Not now" }));
    expect(screen.queryByText("What would be sent")).toBeNull();
  });

  it("re-prepares when 'include my data' is ticked, so the preview is what is sent", async () => {
    const { seen } = serve({ "GET /api/assistant/status": statusReady, "POST /api/assistant/prepare": prepareExplainFirst });
    render(wrap(<RunAssistant run={run} result={result} />));
    await userEvent.click(await screen.findByRole("button", { name: "Explain this result" }));
    await userEvent.click(await screen.findByRole("checkbox", { name: /Include my data/ }));
    await waitFor(() => expect(posts(seen, "/api/assistant/prepare")).toHaveLength(2));
    expect(posts(seen, "/api/assistant/prepare")[1].body).toEqual({ feature: "explain", run_id: run.id, include_data: true });
  });

  it("shows the engine's text and the reason, not the assistant's wording, when the wording is rejected", async () => {
    serve({
      "GET /api/assistant/status": statusReady,
      "POST /api/assistant/prepare": prepareExplain,
      "POST /api/assistant/send": answerRejected,
    });
    render(wrap(<RunAssistant run={run} result={result} />));
    await userEvent.click(await screen.findByRole("button", { name: "Explain this result" }));
    expect(await screen.findByText(/wording was rejected because it contained a figure that is not in your results/)).toBeInTheDocument();
    expect(screen.getByText("The engine's own words")).toBeInTheDocument();
    expect(screen.getByText(/VERDICT: STRUCTURAL/)).toBeInTheDocument();
    expect(screen.queryByText("Assistant text, not a measurement")).toBeNull();
    expect(screen.queryByText(/significantly higher/)).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: /Show the rejected wording and what failed/ }));
    expect(screen.getByText("0.5", { selector: ".font-mono" })).toBeInTheDocument();
    expect(screen.getAllByText(/significantly higher than the Ki/).length).toBeGreaterThan(0);
  });

  it("falls back to the engine's text, with the reason, when the provider fails", async () => {
    serve({
      "GET /api/assistant/status": statusReady,
      "POST /api/assistant/prepare": prepareExplain,
      "POST /api/assistant/send": answerError,
    });
    render(wrap(<RunAssistant run={run} result={result} />));
    await userEvent.click(await screen.findByRole("button", { name: "Explain this result" }));
    expect(await screen.findByText(/The engine's own text is below/)).toBeInTheDocument();
    expect(screen.getByText(/VERDICT: STRUCTURAL/)).toBeInTheDocument();
  });

  it("lets a person cancel while the assistant is thinking", async () => {
    let release: (r: Response) => void = () => undefined;
    const { seen } = mockServer((req) => {
      if (req.url === "/api/assistant/status") return json(200, statusReady.body);
      if (req.url === "/api/assistant/prepare") return json(200, prepareExplain.body);
      if (req.url === "/api/assistant/cancel") return json(200, { call_id: "x", cancelled: true });
      if (req.url === "/api/assistant/send") return new Promise<Response>((resolve) => (release = resolve)) as unknown as Response;
      return undefined;
    });
    render(wrap(<RunAssistant run={run} result={result} />));
    await userEvent.click(await screen.findByRole("button", { name: "Explain this result" }));
    await userEvent.click(await screen.findByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(posts(seen, "/api/assistant/cancel")).toHaveLength(1));
    expect(posts(seen, "/api/assistant/cancel")[0].body).toEqual({ call_id: prepareExplain.body.call_id });
    release(json(200, { ...answerExplain.body, outcome: "cancelled", content: null, error: { code: "cancelled", message: "Cancelled." } }));
    expect(await screen.findByText(/Cancelled\. Nothing from the assistant was used/)).toBeInTheDocument();
  });
});

describe("Draft my methods", () => {
  it("offers an editable draft with a copy button, and the engine's own methods text as the default", async () => {
    const writeText = vi.fn(async () => undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    const { seen } = serve({
      "GET /api/assistant/status": statusReady,
      "POST /api/assistant/prepare": prepareMethods,
      "POST /api/assistant/send": answerMethods,
      "POST /api/assistant/confirm": { status: 200, body: {} },
    });
    render(wrap(<RunAssistant run={run} result={result} />));
    await userEvent.click(await screen.findByRole("button", { name: "Draft my methods" }));
    const box = await screen.findByRole("textbox", { name: "Draft, yours to edit" });
    const draft = (answerMethods.body.content as { reply: { text: string } }).reply.text;
    expect(box).toHaveValue(draft);
    expect(screen.getByText("Caterva's own methods text")).toBeInTheDocument();
    await userEvent.type(box, " Edited by me.");
    expect(screen.getByRole("button", { name: "Back to the draft" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Copy" }));
    expect(writeText).toHaveBeenCalledWith(`${draft} Edited by me.`);
    await waitFor(() => expect(posts(seen, "/api/assistant/confirm")).toHaveLength(1));
    expect(posts(seen, "/api/assistant/confirm")[0].body).toEqual({ call_id: answerMethods.body.call_id, event: "edit" });
  });
});

describe("Ask this run", () => {
  it("sends the question, answers from the run, and keeps no history", async () => {
    const { seen } = serve({
      "GET /api/assistant/status": statusReady,
      "POST /api/assistant/prepare": prepareAsk,
      "POST /api/assistant/send": answerAsk,
    });
    render(wrap(<RunAssistant run={run} result={result} />));
    await userEvent.type(await screen.findByLabelText("Ask this run"), "Why is kcat a placeholder?");
    await userEvent.click(screen.getByRole("button", { name: "Ask" }));
    const reply = (answerAsk.body.content as { reply: { answer: string } }).reply.answer;
    expect(await screen.findByText(reply)).toBeInTheDocument();
    expect(posts(seen, "/api/assistant/prepare")[0].body).toEqual({
      feature: "ask",
      question: "Why is kcat a placeholder?",
      run_id: run.id,
    });
    expect(screen.getByText(/Each question stands alone; nothing is kept beyond this run/)).toBeInTheDocument();
  });

  it("says what it cannot do, in the server's words, for a question it refuses before sending", async () => {
    const { seen } = serve({ "GET /api/assistant/status": statusReady, "POST /api/assistant/prepare": prepareAskRefused });
    render(wrap(<RunAssistant run={run} result={result} />));
    await userEvent.type(await screen.findByLabelText("Ask this run"), "What is the Km of hexokinase?");
    await userEvent.click(screen.getByRole("button", { name: "Ask" }));
    expect(await screen.findByText(/I don't give values from memory/)).toBeInTheDocument();
    expect(posts(seen, "/api/assistant/send")).toHaveLength(0);
  });

  it("says it can only answer about this run when the assistant declines", async () => {
    serve({
      "GET /api/assistant/status": statusReady,
      "POST /api/assistant/prepare": prepareAsk,
      "POST /api/assistant/send": answerDeclined,
    });
    render(wrap(<RunAssistant run={run} result={result} />));
    await userEvent.type(await screen.findByLabelText("Ask this run"), "What colour is the model?");
    await userEvent.click(screen.getByRole("button", { name: "Ask" }));
    expect(await screen.findByText(/I can only answer about this run/)).toBeInTheDocument();
  });
});

describe("What should I measure next", () => {
  it("narrates the engine's ranking, and appears only when the engine ranked something", async () => {
    serve({
      "GET /api/assistant/status": statusReady,
      "POST /api/assistant/prepare": prepareNext,
      "POST /api/assistant/send": answerNext,
    });
    const first = render(wrap(<RunAssistant run={run} result={result} />));
    await userEvent.click(await screen.findByRole("button", { name: "What should I measure next" }));
    const reply = (answerNext.body.content as { reply: { narration: string } }).reply.narration;
    expect(await screen.findByText(reply)).toBeInTheDocument();
    expect(screen.getByText("settling_time", { selector: ".font-mono" })).toBeInTheDocument();
    expect(screen.getByText(/The engine's own ranking, best first/)).toBeInTheDocument();
    first.unmount();
    render(wrap(<RunAssistant run={ldh.run as unknown as RunRecord} result={ldh.result} />));
    await screen.findByRole("button", { name: "Explain this result" });
    expect(screen.queryByRole("button", { name: /What should I measure next/ })).toBeNull();
  });
});

describe("Describe it, in Compose", () => {
  const description = "pyruvate turned over by lactate dehydrogenase while gossypol competes for the site, in human";

  it("proposes, shows the engine's reading, and builds nothing until the person confirms", async () => {
    const onUse = vi.fn();
    const { seen } = serve({
      "GET /api/assistant/status": statusReady,
      "POST /api/assistant/prepare": prepareDescribeFirst,
      "POST /api/assistant/send": answerDescribe,
      "POST /api/assistant/confirm": confirmDescribe,
    });
    render(wrap(<DescribeAssist description={description} onUse={onUse} />));
    await userEvent.click(await screen.findByRole("button", { name: "Ask the assistant to interpret" }));
    await screen.findByText("Before the first send");
    expect(posts(seen, "/api/assistant/prepare")[0].body).toEqual({ feature: "describe", text: description });
    await userEvent.click(screen.getByRole("checkbox", { name: /I agree to send this to/ }));
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByText("Suggested by an assistant, not yet yours")).toBeInTheDocument();
    expect(screen.getByText("inhibition", { selector: "strong" })).toBeInTheDocument();
    expect(screen.getByText("competitive inhibition")).toBeInTheDocument();
    expect(screen.getByText(/It will be composed from: “Michaelis-Menten with a competitive inhibitor”/)).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: /Which kind/ })).toHaveValue("competitive");
    expect(screen.getByRole("textbox", { name: /Substrate/ })).toHaveValue("pyruvate");
    expect(onUse).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Use this and compose" }));
    await waitFor(() => expect(onUse).toHaveBeenCalledTimes(1));
    const use = onUse.mock.calls[0][0];
    expect(use.request).toEqual(confirmDescribe.body.request);
    expect(use.callId).toBe(answerDescribe.body.call_id);
    expect(use.provenance).toMatchObject({ kind: "chosen", by: "user", suggested_by: { assistant: "claude-sonnet-5-5" } });
    const confirm = posts(seen, "/api/assistant/confirm")[0].body as { event: string; choices: Record<string, unknown> };
    expect(confirm.event).toBe("confirm");
    expect(confirm.choices).toMatchObject({ shape: "inhibition", variant: "competitive", substrate: "pyruvate" });
  });

  it("will not let the person confirm a shape that needs a variant until one is chosen", async () => {
    const proposal = JSON.parse(JSON.stringify(answerDescribe.body));
    proposal.content.proposal.variant = null;
    serve({
      "GET /api/assistant/status": statusReady,
      "POST /api/assistant/prepare": prepareDescribe,
      "POST /api/assistant/send": { status: 200, body: proposal },
    });
    render(wrap(<DescribeAssist description={description} onUse={() => undefined} />));
    await userEvent.click(await screen.findByRole("button", { name: "Ask the assistant to interpret" }));
    expect(await screen.findByRole("button", { name: "Use this and compose" })).toBeDisabled();
    await userEvent.selectOptions(screen.getByRole("combobox", { name: /Which kind/ }), "uncompetitive");
    expect(screen.getByRole("button", { name: "Use this and compose" })).toBeEnabled();
  });

  it("shows the engine's refusal of a proposal, and no way to use it", async () => {
    serve({
      "GET /api/assistant/status": statusReady,
      "POST /api/assistant/prepare": prepareDescribe,
      "POST /api/assistant/send": answerDescribeRejected,
    });
    render(wrap(<DescribeAssist description="glycolysis" onUse={() => undefined} />));
    await userEvent.click(await screen.findByRole("button", { name: "Ask the assistant to interpret" }));
    expect(await screen.findByText(/proposal was rejected by the engine's own rules/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Use this and compose" })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: /Show the rejected wording and what failed/ }));
    expect(screen.getByText(/not one of the grammar's shapes/)).toBeInTheDocument();
  });

  it("is one calm line when the assistant is off, and nothing before the person has written something", async () => {
    serve({ "GET /api/assistant/status": statusOff });
    const off = render(wrap(<DescribeAssist description={description} onUse={() => undefined} />));
    expect(await screen.findByText(/Assistant off\./)).toBeInTheDocument();
    off.unmount();
    serve({ "GET /api/assistant/status": statusReady });
    render(wrap(<DescribeAssist description="  " onUse={() => undefined} />));
    expect(await screen.findByRole("button", { name: "Ask the assistant to interpret" })).toBeDisabled();
  });
});

describe("Settings, Assistant", () => {
  it("is Off, with one switch and nothing else, until it is switched on", async () => {
    const { seen } = serve({
      "GET /api/assistant/status": statusOff,
      "GET /api/assistant/settings": settingsDefault,
      "PUT /api/assistant/settings": { status: 200, body: { ...settingsDefault.body, enabled: true } },
    });
    render(wrap(<AssistantSection />));
    const toggle = await screen.findByRole("switch", { name: "The assistant is off" });
    expect(screen.queryByRole("combobox", { name: "Provider" })).toBeNull();
    expect(screen.getByText("Assistant off")).toBeInTheDocument();
    await userEvent.click(toggle);
    expect(posts(seen, "/api/assistant/settings").length + seen.filter((r) => r.method === "PUT").length).toBe(1);
    expect(seen.find((r) => r.method === "PUT")!.body).toEqual({ enabled: true });
  });

  it("shows provider, model, key present or absent, local only, a switch per feature and the spend guard", async () => {
    const { seen } = serve({
      "GET /api/assistant/status": statusReady,
      "GET /api/assistant/settings": settingsOn,
      "PUT /api/assistant/settings": { status: 200, body: settingsOn.body },
    });
    render(wrap(<AssistantSection />));
    await screen.findByRole("switch", { name: "The assistant is on" });
    expect(screen.getByRole("combobox", { name: "Provider" })).toHaveValue("anthropic");
    expect(screen.getByRole("combobox", { name: "Model" })).toHaveValue("claude-sonnet-5-5");
    expect(screen.getByText(/Present, kept in the macOS Keychain/)).toBeInTheDocument();
    expect(screen.getByText(/This page never shows a key, only whether one is present/)).toBeInTheDocument();
    for (const label of ["Describe it (Compose)", "Explain this result", "Draft my methods", "Ask this run", "What should I measure next"]) {
      expect(screen.getByRole("switch", { name: label })).toBeChecked();
    }
    expect(screen.getByRole("switch", { name: "Local only" })).not.toBeChecked();
    expect(screen.getByRole("textbox", { name: "Requests per hour" })).toHaveValue("20");
    expect(screen.getByRole("textbox", { name: "Tokens per reply" })).toHaveValue("1024");
    await userEvent.click(screen.getByRole("switch", { name: "Draft my methods" }));
    expect(seen.find((r) => r.method === "PUT")!.body).toEqual({
      features: { ...settingsOn.body.features, methods: false },
    });
    expect(screen.getByRole("button", { name: "Withdraw my agreements" })).toBeInTheDocument();
  });

  it("never offers a key field in a browser, and says where the key comes from", async () => {
    serve({ "GET /api/assistant/status": statusReady, "GET /api/assistant/settings": settingsOn });
    render(wrap(<AssistantSection />));
    await screen.findByRole("switch", { name: "The assistant is on" });
    expect(screen.queryByLabelText("Key")).toBeNull();
    expect(screen.getByText(/In a browser the key is never typed here/)).toBeInTheDocument();
    expect(screen.getByText(/CATERVA_ASSISTANT_KEY/)).toBeInTheDocument();
  });

  it("hands a key to the shell's bridge, clears the field, and never sends it to the server", async () => {
    const post = vi.fn(async (m: { action: string }) => (m.action === "assistantKeyStatus" ? "present" : null));
    (window as unknown as { webkit: unknown }).webkit = { messageHandlers: { caterva: { postMessage: post } } };
    const { seen } = serve({ "GET /api/assistant/status": statusReady, "GET /api/assistant/settings": settingsOn });
    render(wrap(<AssistantSection />));
    const field = await screen.findByLabelText("Key");
    expect(field).toHaveAttribute("type", "password");
    await userEvent.type(field, TEST_KEY);
    await userEvent.click(screen.getByRole("button", { name: "Store key" }));
    await waitFor(() => expect(post).toHaveBeenCalledWith({ action: "setAssistantKey", provider: "anthropic", key: TEST_KEY }));
    await waitFor(() => expect(field).toHaveValue(""));
    expect(JSON.stringify(seen.map((r) => [r.url, r.body]))).not.toContain(TEST_KEY);
    expect(document.body.textContent).not.toContain(TEST_KEY);
  });

  it("runs the connection test through the same preview and consent, sending one fixed line", async () => {
    const { seen } = serve({
      "GET /api/assistant/status": statusReady,
      "GET /api/assistant/settings": settingsOn,
      "POST /api/assistant/prepare": prepareTestFirst,
      "POST /api/assistant/send": answerTest,
    });
    render(wrap(<AssistantSection />));
    await userEvent.click(await screen.findByRole("button", { name: "Test the connection" }));
    await screen.findByText("Before the first send");
    expect(posts(seen, "/api/assistant/prepare")[0].body).toEqual({ feature: "test" });
    expect(screen.getByLabelText("The request, as it will be sent").textContent).toContain("Reply with the single word: ready");
    await userEvent.click(screen.getByRole("checkbox", { name: /I agree to send this to/ }));
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByText(/The assistant answered in/)).toBeInTheDocument();
  });

  it("is a single line on a server with no assistant", async () => {
    serve({});
    render(wrap(<AssistantSection />));
    expect(await screen.findByText("This server has no assistant.")).toBeInTheDocument();
  });
});

describe("the status line and History", () => {
  it("says where data can go whenever it can leave, and says nothing when the assistant is off", async () => {
    serve({ "GET /api/assistant/status": statusReady });
    const ready = render(wrap(<AssistantStatusItem />));
    const item = await screen.findByRole("link", { name: "Assistant active: sends to api.anthropic.com" });
    expect(item).toHaveAttribute("data-leaves", "true");
    ready.unmount();
    serve({ "GET /api/assistant/status": statusLocal });
    const local = render(wrap(<AssistantStatusItem />));
    const loc = await screen.findByRole("link", { name: "Assistant active: local model, nothing leaves this computer" });
    expect(loc).toHaveAttribute("data-leaves", "false");
    local.unmount();
    serve({ "GET /api/assistant/status": statusOff });
    const { container } = render(wrap(<AssistantStatusItem />));
    await waitFor(() => expect(container).toBeEmptyDOMElement());
  });

  it("marks a run that used the assistant", () => {
    const summary = { id: run.id, kind: run.kind, title: run.title, status: run.status, created_at: run.created_at, finished_at: run.finished_at, outcome: run.outcome };
    const { rerender } = render(<RunRow run={summary} href="/x" />);
    expect(screen.queryByText(/used an assistant/)).toBeNull();
    rerender(<RunRow run={summary} href="/x" assisted />);
    const row = screen.getByRole("link");
    expect(within(row).getByText(/used an assistant/)).toBeInTheDocument();
    expect(within(row).getByRole("img", { name: "suggested by an assistant, not a measurement" })).toBeInTheDocument();
  });
});

describe("the shell's key bridge", () => {
  it("answers null outside the app, and only present or absent inside it", async () => {
    expect(await setAssistantKey("anthropic", TEST_KEY)).toBeNull();
    expect(await clearAssistantKey("anthropic")).toBeNull();
    expect(await assistantKeyStatus("anthropic")).toBeNull();
    const post = vi.fn(async (m: { action: string }) => (m.action === "assistantKeyStatus" ? "present" : null));
    (window as unknown as { webkit: unknown }).webkit = { messageHandlers: { caterva: { postMessage: post } } };
    expect(await assistantKeyStatus("anthropic")).toBe("present");
    expect(await setAssistantKey("anthropic", TEST_KEY)).toBe(true);
    expect(await clearAssistantKey("anthropic")).toBe(true);
    expect(post.mock.calls.map((c) => (c[0] as { action: string }).action)).toEqual([
      "assistantKeyStatus", "setAssistantKey", "clearAssistantKey",
    ]);
    post.mockImplementation(async () => {
      throw new Error("could not store the key");
    });
    expect(await setAssistantKey("anthropic", TEST_KEY)).toBe(false);
    expect(await assistantKeyStatus("anthropic")).toBeNull();
  });
});
