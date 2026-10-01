/**
 * /rates: reserved for `caterva rates`, which arrives from another branch.
 *
 * The route is listed only when /api/capabilities says `rates.available`;
 * until the command's own screen is written, this one says what is known
 * (the server's reason, or that the kind exists) and nothing else. It
 * shows no number.
 */
import { Screen } from "@/components/screen/Screen";
import { EmptyState, ErrorState } from "@/components/states/States";
import { Loading } from "@/components/states/Loading";
import { useCapabilities } from "@/lib/queries";

export default function RatesScreen() {
  const caps = useCapabilities();
  return (
    <Screen title="Rates" purpose="Reserved for `caterva rates`.">
      {caps.isPending ? (
        <Loading label="Asking the server" />
      ) : caps.isError ? (
        <ErrorState error={caps.error} />
      ) : caps.data.rates.available ? (
        <EmptyState title="This screen is not written yet">
          <p>
            This installation can run <code>caterva rates</code>; its screen arrives with the command's integration. Until then,
            run it in a terminal.
          </p>
        </EmptyState>
      ) : (
        <EmptyState title="Not in this installation">
          <p>{caps.data.rates.reason ?? "caterva rates is not available here."}</p>
        </EmptyState>
      )}
    </Screen>
  );
}
