/**
 * Settings, Assistant: off by default, and every part of it a choice.
 *
 * Changes are saved the moment they are made (like the theme), because this section is a set of switches and
 * a half-saved set of switches would be a misleading state. What it never does: show a key. The key is held by
 * the macOS Keychain (the shell hands it to the server over a private channel) or, in a browser or development
 * run, read from the CATERVA_ASSISTANT_KEY environment variable; this page can only say whether one is present.
 */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { type InputHTMLAttributes, useState } from "react";

import {
  type AssistantFeature,
  type AssistantSettings,
  forgetAssistantConsent,
  getAssistantSettings,
  putAssistantSettings,
} from "@/api/assistant";
import { Field, NumberInput, parseNumber, Select, Switch, TextArea, TextInput } from "@/components/forms/Field";
import { Section } from "@/components/screen/Screen";
import { clearAssistantKey, isDesktop, setAssistantKey } from "@/lib/desktop";
import { describeError } from "@/lib/errors";
import { notify } from "@/lib/toast";

import { CallView } from "./CallView";
import { ASSISTANT_STATUS_KEY, useAssistantCall, useAssistantStatus } from "./useAssistant";
import "./assistant.css";

/** A text box that commits when it loses focus, so typing a model name is not a request per letter. */
function Committed({
  value,
  onCommit,
  numeric = false,
  mono = false,
  ...rest
}: {
  value: string;
  onCommit: (v: string) => void;
  numeric?: boolean;
  mono?: boolean;
} & Omit<InputHTMLAttributes<HTMLInputElement>, "value" | "onChange">) {
  const [draft, setDraft] = useState<string | null>(null);
  const Input = numeric ? NumberInput : TextInput;
  return (
    <Input
      {...rest}
      {...(numeric ? {} : { mono })}
      value={draft ?? value}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={() => {
        if (draft !== null && draft !== value) onCommit(draft);
        setDraft(null);
      }}
      onKeyDown={(e) => {
        if (e.key === "Enter") (e.target as HTMLInputElement).blur();
      }}
    />
  );
}

const FEATURES: AssistantFeature[] = ["describe", "explain", "methods", "ask", "next"];
const SETTINGS_KEY = ["assistant", "settings"] as const;

export function AssistantSection() {
  const client = useQueryClient();
  const status = useAssistantStatus();
  const settings = useQuery({ queryKey: SETTINGS_KEY, queryFn: getAssistantSettings, retry: false });
  const [error, setError] = useState<string | null>(null);
  const [keyText, setKeyText] = useState("");
  const [models, setModels] = useState<string | null>(null);
  const test = useAssistantCall();
  const desktop = isDesktop();

  if (status.isError || settings.isError) {
    return (
      <Section title="Assistant">
        <p className="asst-off">This server has no assistant.</p>
      </Section>
    );
  }
  if (!status.data || !settings.data) return <Section title="Assistant" />;
  const s = status.data;
  const cfg = settings.data;
  const provider = s.providers.find((p) => p.name === cfg.provider);
  const model = cfg.models[cfg.provider] ?? "";
  const list = cfg.model_lists[cfg.provider] ?? [];

  const save = async (patch: Partial<Omit<AssistantSettings, "consent">>) => {
    setError(null);
    try {
      const stored = await putAssistantSettings(patch);
      client.setQueryData(SETTINGS_KEY, stored);
    } catch (e) {
      setError(describeError(e).message);
    } finally {
      void client.invalidateQueries({ queryKey: ASSISTANT_STATUS_KEY });
    }
  };

  const saveKey = async () => {
    const stored = await setAssistantKey(cfg.provider, keyText);
    setKeyText("");
    if (stored === true) notify("done", "Key stored in the Keychain");
    else notify("failed", "The key was not stored", { description: "The Keychain refused it, or it is not a usable key." });
    void client.invalidateQueries({ queryKey: ASSISTANT_STATUS_KEY });
  };

  const anyConsent = Object.keys(cfg.consent).length > 0;
  return (
    <Section title="Assistant" aside={<span className="asst-where">{s.indicator}</span>}>
      <div className="settings-form asst-settings">
        <Switch
          checked={cfg.enabled}
          onChange={(v) => void save({ enabled: v })}
          label={cfg.enabled ? "The assistant is on" : "The assistant is off"}
          hint="Off unless you switch it on. It explains and drafts from your results; it never runs anything, never sets a number, and every figure it writes is checked against your results first. Everything in the studio works without it."
        />
        {cfg.enabled ? (
          <>
            <Field label="Provider" hint={provider?.local ? "A model on this computer: nothing leaves it." : "What you send goes to this provider, under its own terms."}>
              <Select value={cfg.provider} onChange={(e) => void save({ provider: e.target.value })}>
                {s.providers.map((p) => (
                  <option key={p.name} value={p.name} disabled={cfg.local_only && !p.local}>
                    {p.label}
                    {p.local ? "" : ""}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Model" hint="A name your provider accepts. Edit the list below to keep the ones you use.">
              <Committed
                mono
                list="assistant-models"
                value={model}
                placeholder={provider?.local ? "for example, the name Ollama lists" : "a model name"}
                onCommit={(v) => void save({ models: { [cfg.provider]: v } })}
              />
              <datalist id="assistant-models">
                {list.map((m) => (
                  <option key={m} value={m} />
                ))}
              </datalist>
            </Field>
            <Field label="Models in the list" optional hint="One per line.">
              <TextArea
                rows={3}
                className="font-mono"
                value={models ?? list.join("\n")}
                onChange={(e) => setModels(e.target.value)}
                onBlur={() => {
                  if (models !== null) void save({ model_lists: { [cfg.provider]: models.split("\n").map((x) => x.trim()).filter(Boolean) } });
                  setModels(null);
                }}
              />
            </Field>
            {provider?.local ? (
              <Field label="Address of the model" hint="Must be on this computer (127.0.0.1 or localhost).">
                <Committed mono value={cfg.local_url} onCommit={(v) => void save({ local_url: v })} />
              </Field>
            ) : null}

            {s.key.needed ? (
              <div className="field">
                <span className="field-label">Key</span>
                <p className="asst-keystate" role="status">
                  {s.key.present
                    ? s.key.source === "environment"
                      ? "Present, read from the CATERVA_ASSISTANT_KEY environment variable."
                      : "Present, kept in the macOS Keychain."
                    : "Not set."}
                </p>
                {desktop ? (
                  <div className="asst-keyrow">
                    <TextInput
                      type="password"
                      autoComplete="off"
                      aria-label="Key"
                      value={keyText}
                      placeholder="Paste a key to store it"
                      onChange={(e) => setKeyText(e.target.value)}
                    />
                    <button type="button" className="btn btn-sm" disabled={keyText.trim().length < 8} onClick={() => void saveKey()}>
                      Store key
                    </button>
                    {s.key.present ? (
                      <button
                        type="button"
                        className="btn btn-sm btn-quiet"
                        onClick={() => void clearAssistantKey(cfg.provider).then(() => client.invalidateQueries({ queryKey: ASSISTANT_STATUS_KEY }))}
                      >
                        Remove key
                      </button>
                    ) : null}
                  </div>
                ) : (
                  <p className="field-hint">
                    In a browser the key is never typed here. Set CATERVA_ASSISTANT_KEY in the environment before starting the
                    studio; the Caterva app keeps it in the Keychain instead. {s.key.note ?? ""}
                  </p>
                )}
                <p className="field-hint">This page never shows a key, only whether one is present.</p>
              </div>
            ) : null}

            <Switch
              checked={cfg.local_only}
              onChange={(v) => void save(v ? { local_only: true, provider: "local" } : { local_only: false })}
              label="Local only"
              hint="Use only a model on this computer. Switching this on selects it."
            />

            <fieldset className="asst-features">
              <legend className="field-label">What the assistant may help with</legend>
              {FEATURES.map((f) => (
                <Switch
                  key={f}
                  checked={cfg.features[f]}
                  onChange={(v) => void save({ features: { ...cfg.features, [f]: v } })}
                  label={s.features[f].label}
                  hint={`Sends: ${s.features[f].sends}${cfg.consent[f] ? ` You agreed on ${cfg.consent[f].slice(0, 10)}.` : ""}`}
                />
              ))}
            </fieldset>

            <div className="k-row2">
              <Field label="Requests per hour" hint={`${s.spend.remaining} left this hour. A hard stop.`}>
                <Committed
                  numeric
                  inputMode="numeric"
                  value={String(cfg.max_calls_per_hour)}
                  onCommit={(v) => {
                    const n = parseNumber(v);
                    if (n !== null) void save({ max_calls_per_hour: Math.round(n) });
                  }}
                />
              </Field>
              <Field label="Tokens per reply" hint="The most one reply may use.">
                <Committed
                  numeric
                  inputMode="numeric"
                  value={String(cfg.max_tokens)}
                  onCommit={(v) => {
                    const n = parseNumber(v);
                    if (n !== null) void save({ max_tokens: Math.round(n) });
                  }}
                />
              </Field>
            </div>

            <div className="asst-actions">
              <button type="button" className="btn btn-sm" onClick={() => void test.run({ feature: "test" })} disabled={s.state !== "ready" && s.state !== "idle"}>
                Test the connection
              </button>
              {anyConsent ? (
                <button
                  type="button"
                  className="btn btn-sm btn-quiet"
                  onClick={() =>
                    void forgetAssistantConsent().then(() => {
                      void client.invalidateQueries({ queryKey: SETTINGS_KEY });
                      void client.invalidateQueries({ queryKey: ASSISTANT_STATUS_KEY });
                    })
                  }
                >
                  Withdraw my agreements
                </button>
              ) : null}
            </div>
            <p className="field-hint">The test sends one fixed line of text and nothing from your work.</p>
            <CallView call={test} waitLabel="Testing the connection">
              {(a) => <p className="asst-note">The assistant answered in {a.latency_ms ?? 0} ms.</p>}
            </CallView>
          </>
        ) : null}
        {error ? (
          <p className="field-error" role="alert">
            {error}
          </p>
        ) : null}
        {s.note ? <p className="field-hint">{s.note}</p> : null}
      </div>
    </Section>
  );
}
