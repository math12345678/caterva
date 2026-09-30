/**
 * /rates: Reserved for caterva rates.
 *
 * Placeholder from the contract skeleton (owner: rates integrator). It shows no
 * number, because it has none from the backend yet.
 */
import { EmptyState } from "@/components/states/States";
import { Screen } from "@/components/screen/Screen";

export default function RatesScreen() {
  return (
    <Screen title="Rates" purpose="Reserved for `caterva rates`.">
      <EmptyState title="Not built yet">
        <p>This screen is reserved in the contract and has not been built.</p>
      </EmptyState>
    </Screen>
  );
}
