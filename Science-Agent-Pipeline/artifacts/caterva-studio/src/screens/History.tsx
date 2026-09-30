/**
 * /history: Every run, its request, its outcome and its files, to reopen or export.
 *
 * Placeholder from the contract skeleton (owner: ui). It shows no
 * number, because it has none from the backend yet.
 */
import { EmptyState } from "@/components/states/States";
import { Screen } from "@/components/screen/Screen";

export default function HistoryScreen() {
  return (
    <Screen title="History" purpose="Every run, its request, its outcome and its files, to reopen or export.">
      <EmptyState title="Not built yet">
        <p>This screen is reserved in the contract and has not been built.</p>
      </EmptyState>
    </Screen>
  );
}
