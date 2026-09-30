import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import fixture from "@/__fixtures__/api/contract/michaelis-menten-parameters.json";
import type { ProvenanceKind, SourcedValue } from "@/api/types";
import { ProvenanceMark, PROVENANCE_LABEL } from "@/components/provenance/ProvenanceMark";
import { Value } from "@/components/provenance/Value";

describe("ProvenanceMark", () => {
  it("gives each of the five kinds its own accessible name", () => {
    const kinds: ProvenanceKind[] = ["measured", "fitted", "computed", "placeholder", "chosen"];
    for (const kind of kinds) {
      const { unmount } = render(<ProvenanceMark provenance={{ kind, by: "user" }} />);
      const expected = kind === "chosen" ? "chosen by you" : PROVENANCE_LABEL[kind];
      expect(screen.getByRole("img", { name: expected })).toBeInTheDocument();
      unmount();
    }
  });
});

describe("Value, over the real contract fixture", () => {
  it("puts the citation one click from a measured number", async () => {
    const km = (fixture.searched.parameters as SourcedValue[]).find((v) => v.id === "reaction_Km")!;
    render(<Value v={km} />);
    await userEvent.click(screen.getByRole("button", { name: /reaction_Km|Km/ }));
    expect(await screen.findByText("BRENDA ref 641068")).toBeInTheDocument();
  });

  it("puts a placeholder's reason one click away, in the library's words", async () => {
    const km = (fixture.structure_only.parameters as SourcedValue[]).find((v) => v.id === "reaction_Km")!;
    expect(km.provenance.kind).toBe("placeholder");
    render(<Value v={km} />);
    await userEvent.click(screen.getByRole("button"));
    expect(await screen.findByText(km.provenance.reason!)).toBeInTheDocument();
  });
});
