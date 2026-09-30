/**
 * /sim: Exact stochastic kinetics (Gillespie SSA), seeded so every trajectory can be reproduced.
 *
 * Placeholder from the contract skeleton (owner: sci-kinetics). It shows no
 * number, because it has none from the backend yet.
 */
import { EmptyState } from "@/components/states/States";
import { Screen } from "@/components/screen/Screen";

export default function SimScreen() {
  return (
    <Screen title="Stochastic" purpose="Exact stochastic kinetics (Gillespie SSA), seeded so every trajectory can be reproduced.">
      <EmptyState title="Not built yet">
        <p>This screen is reserved in the contract and has not been built.</p>
      </EmptyState>
    </Screen>
  );
}
