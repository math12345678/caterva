/**
 * A name that is not exactly one enzyme, refused by the engine, with each
 * candidate it named (`Outcome.name_refusal`, the one name policy's refusal
 * as data). Shown under the refusal's own sentence so the person can pick
 * the enzyme they meant instead of retyping.
 *
 * With the finder in the form this is rare (the form sends an EC number),
 * but a link or a reopened run can still carry a name. The engine's
 * recommendation, when it has one, is marked "suggested" and, like every
 * row, is only chosen by a click. Choosing sets the form's enzyme; it does
 * not start a run.
 */
import type { NameRefusal } from "@/api/types";

/** The organism label inside a candidate's label: "EC 1.1.1.27 L-lactate dehydrogenase (human: LDHA, LDHB)". */
function organismOf(label: string | undefined): string | null {
  const m = label ? /\(([^():]+): / .exec(label) : null;
  return m ? m[1] : null;
}

export function NameRefusalChoices({
  refusal,
  onChoose,
}: {
  refusal: NameRefusal;
  /** Sets the form's enzyme to this EC number. Without it the candidates are listed, not offered. */
  onChoose?: (ec: string) => void;
}) {
  if (refusal.named_candidates.length === 0) return null;
  const suggestions = refusal.kind === "suggestions";
  return (
    <div className="enz-refusal">
      <h3 className="state-title">{suggestions ? "Did you mean" : "Which enzyme did you mean?"}</h3>
      <ul className="enz-refusal-list">
        {refusal.named_candidates.map((c) => {
          const usable = c.status === "active" ? c.ec : c.status === "transferred" && c.superseded_by.length === 1 ? c.superseded_by[0] : null;
          const organism = organismOf(c.label);
          const proteins = c.organism_proteins.map((p) => p.symbol);
          return (
            <li key={c.ec} className="enz-refusal-row">
              <span className="enz-refusal-body">
                <span className="enz-head">
                  <span className="enz-ec font-mono">EC {c.ec}</span>
                  <span className="enz-name">{c.name}</span>
                  {refusal.recommended === c.ec ? <span className="chip" data-tone="signal">suggested</span> : null}
                  {c.status !== "active" ? <span className="chip" data-tone="caution">{c.status}</span> : null}
                </span>
                <span className="enz-why">{c.why}</span>
                {organism && proteins.length ? <span className="enz-organism">{organism}: {proteins.join(", ")}</span> : null}
              </span>
              {onChoose && usable ? (
                <button type="button" className="btn btn-sm" onClick={() => onChoose(usable)}>
                  Use EC {usable}
                </button>
              ) : null}
            </li>
          );
        })}
      </ul>
      <p className="field-hint">Caterva will not pick one for you: a wrong EC number is a citation for the wrong enzyme.</p>
    </div>
  );
}
