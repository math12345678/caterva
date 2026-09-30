/**
 * /structure: An enzyme's experimental structures in the PDB, each with its method, resolution and citation.
 *
 * Placeholder from the contract skeleton (owner: sci-structure). It shows no
 * number, because it has none from the backend yet.
 */
import { EmptyState } from "@/components/states/States";
import { Screen } from "@/components/screen/Screen";

export default function StructureScreen() {
  return (
    <Screen title="Structures" purpose="An enzyme's experimental structures in the PDB, each with its method, resolution and citation.">
      <EmptyState title="Not built yet">
        <p>This screen is reserved in the contract and has not been built.</p>
      </EmptyState>
    </Screen>
  );
}
