/**
 * /bind: The measured binding free energy a simulation is held to, from cited Ki rows.
 *
 * Placeholder from the contract skeleton (owner: sci-kinetics). It shows no
 * number, because it has none from the backend yet.
 */
import { EmptyState } from "@/components/states/States";
import { Screen } from "@/components/screen/Screen";

export default function BindScreen() {
  return (
    <Screen title="Binding" purpose="The measured binding free energy a simulation is held to, from cited Ki rows.">
      <EmptyState title="Not built yet">
        <p>This screen is reserved in the contract and has not been built.</p>
      </EmptyState>
    </Screen>
  );
}
