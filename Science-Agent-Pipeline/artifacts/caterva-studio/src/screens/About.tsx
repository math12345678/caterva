/**
 * /about: Version, licences, and what this installation can and cannot reach.
 *
 * Placeholder from the contract skeleton (owner: ui). It shows no
 * number, because it has none from the backend yet.
 */
import { EmptyState } from "@/components/states/States";
import { Screen } from "@/components/screen/Screen";

export default function AboutScreen() {
  return (
    <Screen title="About" purpose="Version, licences, and what this installation can and cannot reach.">
      <EmptyState title="Not built yet">
        <p>This screen is reserved in the contract and has not been built.</p>
      </EmptyState>
    </Screen>
  );
}
