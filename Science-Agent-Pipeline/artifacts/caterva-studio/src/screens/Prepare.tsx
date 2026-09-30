/**
 * /prepare: Audit a PDB entry before simulating it, defects ranked by distance to the active site.
 *
 * Placeholder from the contract skeleton (owner: sci-structure). It shows no
 * number, because it has none from the backend yet.
 */
import { EmptyState } from "@/components/states/States";
import { Screen } from "@/components/screen/Screen";

export default function PrepareScreen() {
  return (
    <Screen title="Prepare" purpose="Audit a PDB entry before simulating it, defects ranked by distance to the active site.">
      <EmptyState title="Not built yet">
        <p>This screen is reserved in the contract and has not been built.</p>
      </EmptyState>
    </Screen>
  );
}
