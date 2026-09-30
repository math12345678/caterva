/**
 * /constants: Look up an enzyme's measured constants, each with the paper that measured it.
 *
 * Placeholder from the contract skeleton (owner: sci-kinetics). It shows no
 * number, because it has none from the backend yet.
 */
import { EmptyState } from "@/components/states/States";
import { Screen } from "@/components/screen/Screen";

export default function ConstantsScreen() {
  return (
    <Screen title="Constants" purpose="Look up an enzyme's measured constants, each with the paper that measured it.">
      <EmptyState title="Not built yet">
        <p>This screen is reserved in the contract and has not been built.</p>
      </EmptyState>
    </Screen>
  );
}
