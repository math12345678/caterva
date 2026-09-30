/**
 * /: What this installation can do, and the runs you opened last.
 *
 * Placeholder from the contract skeleton (owner: ui). It shows no
 * number, because it has none from the backend yet.
 */
import { EmptyState } from "@/components/states/States";
import { Screen } from "@/components/screen/Screen";

export default function HomeScreen() {
  return (
    <Screen title="Home" purpose="What this installation can do, and the runs you opened last.">
      <EmptyState title="Not built yet">
        <p>This screen is reserved in the contract and has not been built.</p>
      </EmptyState>
    </Screen>
  );
}
