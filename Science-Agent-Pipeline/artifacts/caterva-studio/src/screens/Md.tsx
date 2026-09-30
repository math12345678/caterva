/**
 * /md: A GROMACS setup whose every parameter is measured, chosen or cited, and whether its replicas converged.
 *
 * Placeholder from the contract skeleton (owner: sci-structure). It shows no
 * number, because it has none from the backend yet.
 */
import { EmptyState } from "@/components/states/States";
import { Screen } from "@/components/screen/Screen";

export default function MdScreen() {
  return (
    <Screen title="Dynamics" purpose="A GROMACS setup whose every parameter is measured, chosen or cited, and whether its replicas converged.">
      <EmptyState title="Not built yet">
        <p>This screen is reserved in the contract and has not been built.</p>
      </EmptyState>
    </Screen>
  );
}
