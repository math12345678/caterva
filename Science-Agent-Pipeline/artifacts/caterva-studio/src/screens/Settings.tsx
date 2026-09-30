/**
 * /settings: Theme, how many runs at once, and where the workspace lives.
 *
 * Placeholder from the contract skeleton (owner: ui). It shows no
 * number, because it has none from the backend yet.
 */
import { EmptyState } from "@/components/states/States";
import { Screen } from "@/components/screen/Screen";

export default function SettingsScreen() {
  return (
    <Screen title="Settings" purpose="Theme, how many runs at once, and where the workspace lives.">
      <EmptyState title="Not built yet">
        <p>This screen is reserved in the contract and has not been built.</p>
      </EmptyState>
    </Screen>
  );
}
