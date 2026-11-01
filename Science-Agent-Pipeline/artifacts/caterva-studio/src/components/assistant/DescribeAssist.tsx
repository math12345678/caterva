/**
 * Compose "describe it": when the grammar could not read a description, offer to ask the assistant to interpret.
 *
 * The assistant returns a PROPOSAL, not a model: one of the grammar's own shapes, a count of steps or a named
 * variant where the engine would otherwise refuse to choose, and names that are in the person's own words. The
 * server has already checked it against the engine (a shape that is not in the library, an EC number the finder
 * did not list, a field it may not set, all rejected), and the description that would be composed is built by
 * Caterva from the shape's own line, never from the assistant's text. What the person sees is that proposal,
 * the engine's reading of it, and fields they can change; nothing is composed until they press the button, and
 * what they confirm is recorded as chosen by them with the assistant named as the source of the suggestion.
 */
import { useState } from "react";
import { Link } from "wouter";

import { type AssistantConfirmed, confirmAssistant, type Proposal } from "@/api/assistant";
import { Field, NumberInput, parseNumber, Select, TextInput } from "@/components/forms/Field";
import { ProvenanceMark } from "@/components/provenance/ProvenanceMark";
import { describeError } from "@/lib/errors";

import { AiCaption, CallView } from "./CallView";
import { useAssistantCall, useAssistantStatus, useHasQueryClient } from "./useAssistant";
import "./assistant.css";

export interface DescribeUse {
  request: Record<string, unknown>;
  callId: string;
  provenance: AssistantConfirmed["provenance"];
}

function ProposalView({ proposal, callId, onUse, onDismiss }: { proposal: Proposal; callId: string; onUse: (u: DescribeUse) => void; onDismiss: () => void }) {
  const [variant, setVariant] = useState(proposal.variant ?? "");
  const [stages, setStages] = useState(proposal.stages === null ? "" : String(proposal.stages));
  const [substrate, setSubstrate] = useState(String(proposal.request.substrate ?? ""));
  const [inhibitor, setInhibitor] = useState(String(proposal.request.inhibitor ?? ""));
  const [organism, setOrganism] = useState(String(proposal.request.organism ?? ""));
  const [ec, setEc] = useState(String(proposal.request.subject ?? ""));
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const confirm = async () => {
    setBusy(true);
    setError(null);
    const choices: Record<string, unknown> = { shape: proposal.shape };
    if (proposal.needs_stages) choices.stages = parseNumber(stages);
    if (proposal.variants.length) choices.variant = variant || null;
    choices.substrate = substrate.trim() || null;
    choices.inhibitor = inhibitor.trim() || null;
    choices.organism = organism.trim() || null;
    choices.subject_ec = ec || null;
    try {
      const done = (await confirmAssistant({ call_id: callId, event: "confirm", choices })) as AssistantConfirmed;
      onUse({ request: done.request, callId, provenance: done.provenance });
    } catch (e) {
      setError(describeError(e).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="asst-proposal">
      <p className="asst-caption">
        <ProvenanceMark provenance={{ kind: "ai" }} decorative />
        <span className="asst-caption-main">Suggested by an assistant, not yet yours</span>
      </p>
      <p>
        The assistant read your description as <strong className="font-mono">{proposal.shape}</strong>.
        {proposal.reading ? <> Caterva's own reading of it: <em>{proposal.reading}</em>.</> : null}
      </p>
      <p className="field-hint">It will be composed from: “{proposal.description}”</p>
      <div className="asst-fields">
        {proposal.needs_stages ? (
          <Field label="Number of steps" hint={`Up to ${proposal.max_stages}.`}>
            <NumberInput inputMode="numeric" value={stages} onChange={(e) => setStages(e.target.value)} />
          </Field>
        ) : null}
        {proposal.variants.length ? (
          <Field label="Which kind" hint="The engine will not choose this for you.">
            <Select value={variant} onChange={(e) => setVariant(e.target.value)}>
              <option value="">Choose one</option>
              {proposal.variants.map((v) => (
                <option key={v} value={v}>
                  {v}
                </option>
              ))}
            </Select>
          </Field>
        ) : null}
        <Field label="Substrate" optional>
          <TextInput value={substrate} onChange={(e) => setSubstrate(e.target.value)} />
        </Field>
        <Field label="Inhibitor" optional>
          <TextInput value={inhibitor} onChange={(e) => setInhibitor(e.target.value)} />
        </Field>
        <Field label="Organism" optional hint={proposal.organism_note ?? undefined}>
          <TextInput value={organism} onChange={(e) => setOrganism(e.target.value)} />
        </Field>
        {proposal.enzyme_candidates.length ? (
          <Field label="Enzyme" optional hint="Only enzymes the finder matched can be chosen.">
            <Select value={ec} onChange={(e) => setEc(e.target.value)}>
              <option value="">None: keep placeholders</option>
              {proposal.enzyme_candidates.map((c) => (
                <option key={c.ec} value={c.ec}>
                  EC {c.ec}, {c.name}
                </option>
              ))}
            </Select>
          </Field>
        ) : null}
      </div>
      {error ? (
        <p className="asst-note" role="alert">
          {error}
        </p>
      ) : null}
      <div className="asst-actions">
        <button type="button" className="btn btn-sm btn-primary" disabled={busy || (proposal.variants.length > 0 && !variant)} onClick={() => void confirm()}>
          Use this and compose
        </button>
        <button type="button" className="btn btn-sm btn-quiet" onClick={onDismiss}>
          Not this
        </button>
      </div>
    </div>
  );
}

function DescribeAssistInner({ description, onUse }: { description: string; onUse: (use: DescribeUse) => void }) {
  const status = useAssistantStatus();
  const call = useAssistantCall();
  if (status.isError || !status.data) return null;
  const s = status.data;
  if (s.state === "off") {
    return (
      <p className="asst-off">
        Assistant off. <Link href="/settings">Settings</Link> can switch it on.
      </p>
    );
  }
  if (s.state !== "ready" || !s.features.describe?.on) return null;
  const text = description.trim();
  return (
    <section className="asst asst-inline" aria-label="Ask the assistant to interpret">
      <p className="asst-where">{s.indicator}</p>
      <div className="asst-actions">
        <button
          type="button"
          className="btn btn-sm"
          disabled={!text || call.phase.name === "preparing" || call.phase.name === "sending"}
          onClick={() => void call.run({ feature: "describe", text })}
        >
          Ask the assistant to interpret
        </button>
        <button
          type="button"
          className="btn btn-sm btn-quiet"
          disabled={!text || call.phase.name === "preparing" || call.phase.name === "sending"}
          onClick={() => void call.show({ feature: "describe", text })}
        >
          Show what is sent
        </button>
      </div>
      {!text ? <p className="field-hint">Write your description first; it is what the assistant reads.</p> : null}
      <CallView call={call} waitLabel="Reading your description">
        {(answer) => {
          const content = answer.content as { proposal?: Proposal } | null;
          if (!content?.proposal) return null;
          return (
            <>
              <ProposalView proposal={content.proposal} callId={answer.call_id} onUse={onUse} onDismiss={call.reset} />
              <AiCaption model={answer.model} local={answer.local} />
            </>
          );
        }}
      </CallView>
    </section>
  );
}

export function DescribeAssist(props: { description: string; onUse: (use: DescribeUse) => void }) {
  return useHasQueryClient() ? <DescribeAssistInner {...props} /> : null;
}
