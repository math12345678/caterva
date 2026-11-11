/**
 * A substrate Caterva chose must be on screen beside the Km it chose it for.
 *
 * ADR 0182: when a question names an enzyme but no substrate, the API
 * chooses the best-measured one from BRENDA and states it as a flag
 * ("substrate chosen: D-glucose -- ..."). The page used to clear every flag
 * on the refusal path, which is the path a hexokinase question with no
 * enzyme concentration takes: the Km arrived seeded in the form, resolved
 * for a substrate the student never typed, with nothing naming it.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import AgentSimulator from "../cli/AgentSimulator";
import ChoiceNotes, { splitChoiceFlags } from "../cli/ChoiceNotes";

const CHOSEN =
  "substrate chosen: D-glucose -- most Km and kcat rows for EC 2.7.1.1 in Homo sapiens. " +
  "Alternatives: ATP (Km 106 rows); D-mannose (Km 9 rows). Name the substrate in the query " +
  '("<enzyme> with <substrate>") to use another.';

afterEach(() => vi.unstubAllGlobals());

describe("splitChoiceFlags", () => {
  it("separates the choices from the other flags, keeping their order", () => {
    expect(
      splitChoiceFlags([
        "assumed: organism = Homo sapiens.",
        CHOSEN,
        "inhibitor chosen: oxamate -- most Ki rows.",
        "Resolved KM=6 mM from brenda_exact.",
      ]),
    ).toEqual({
      choices: [CHOSEN, "inhibitor chosen: oxamate -- most Ki rows."],
      others: ["assumed: organism = Homo sapiens.", "Resolved KM=6 mM from brenda_exact."],
    });
  });

  it("does not take a flag that only mentions a choice mid-sentence", () => {
    expect(splitChoiceFlags(["the substrate chosen: by you"]).choices).toEqual([]);
  });
});

describe("ChoiceNotes", () => {
  it("renders nothing when nothing was chosen", () => {
    const { container } = render(<ChoiceNotes flags={["assumed: organism = Homo sapiens."]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows each choice in full, with its alternatives", () => {
    render(<ChoiceNotes flags={[CHOSEN]} />);
    const notes = screen.getByTestId("choice-notes");
    expect(notes).toHaveTextContent("substrate chosen: D-glucose");
    expect(notes).toHaveTextContent("ATP (Km 106 rows)");
  });
});

describe("the refusal path keeps the choice on screen", () => {
  it("shows the chosen substrate beside the seeded Km", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (url === "/api/resolve") {
          return new Response(
            JSON.stringify({
              error: "RequiredParametersMissingError",
              message: "Cannot simulate 'mm': vmax is unresolved.",
              missingKeys: ["vmax"],
              domain: "mm",
              resolvedParameters: { km: 6 },
              details: { vmax: "State the enzyme concentration." },
              parameterProvenance: {
                km: { origin: "resolved", citation: "BRENDA (ref 641068)" },
                vmax: { origin: "default", unresolvedReason: "enzyme_conc_not_supplied" },
              },
              flags: [CHOSEN, "assumed: organism = Homo sapiens."],
            }),
            { status: 422 },
          );
        }
        return new Response("[]", { status: 200 });
      }),
    );
    render(<AgentSimulator />);
    fireEvent.change(screen.getByPlaceholderText(/simulate/i), {
      target: { value: "hexokinase in humans" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^resolve$/i }));
    await screen.findByTestId("server-refusal");
    expect(screen.getByTestId("choice-notes")).toHaveTextContent("substrate chosen: D-glucose");
    expect(screen.getByText("assumed: organism = Homo sapiens.")).toBeInTheDocument();
  });
});
