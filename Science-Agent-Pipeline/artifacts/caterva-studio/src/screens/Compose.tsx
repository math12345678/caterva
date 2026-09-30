/**
 * /compose: Build a model from the shape of a mechanism, and see where every number in it came from.
 *
 * Placeholder from the contract skeleton (owner: sci-kinetics). It shows no
 * number, because it has none from the backend yet.
 */
import { EmptyState } from "@/components/states/States";
import { Screen } from "@/components/screen/Screen";

export default function ComposeScreen() {
  return (
    <Screen title="Compose" purpose="Build a model from the shape of a mechanism, and see where every number in it came from.">
      <EmptyState title="Not built yet">
        <p>This screen is reserved in the contract and has not been built.</p>
      </EmptyState>
    </Screen>
  );
}
