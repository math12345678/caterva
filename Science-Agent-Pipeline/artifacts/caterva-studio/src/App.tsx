/**
 * The studio's shell: navigation from the route table, the connection to
 * the server, and the frame each screen renders into.
 *
 * Skeleton from the contract (owner: ui). It is deliberately plain and
 * working, so the science screens can be built inside it while the
 * foundation is designed: the ui owner replaces the look, and keeps the
 * behaviour (every route reachable, /rates gated, a page without a session
 * token saying so).
 */
import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { Suspense } from "react";
import { Link, Route, Switch, useLocation } from "wouter";

import { ApiRequestError, apiJson, sessionToken } from "@/api/client";
import { type Capabilities, type Health, STUDIO_API_VERSION } from "@/api/types";
import { Lockup } from "@/components/brand/Mark";
import { Loading } from "@/components/states/Loading";
import { EmptyState, ErrorState } from "@/components/states/States";
import { ROUTES, type StudioRoute } from "@/routes";

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
});

function visible(route: StudioRoute, capabilities: Capabilities | undefined): boolean {
  if (route.gate === "rates") return Boolean(capabilities?.rates.available);
  return true;
}

function Shell() {
  const [location] = useLocation();
  const health = useQuery({ queryKey: ["health"], queryFn: () => apiJson<Health>("/api/health") });
  const capabilities = useQuery({
    queryKey: ["capabilities"],
    queryFn: () => apiJson<Capabilities>("/api/capabilities"),
    enabled: health.isSuccess,
  });

  if (sessionToken() === null) {
    return (
      <main className="shell-message">
        <ErrorState
          error={{
            code: "unauthorized",
            message:
              "This page was not served by `caterva studio`. Start it with `caterva studio` and open the address it prints.",
          }}
        />
      </main>
    );
  }
  if (health.isPending) {
    return (
      <main className="shell-message">
        <Loading label="Connecting to the studio server" />
      </main>
    );
  }
  if (health.isError) {
    const error =
      health.error instanceof ApiRequestError
        ? health.error.error
        : { code: "unavailable" as const, message: String(health.error) };
    return (
      <main className="shell-message">
        <ErrorState error={error} />
      </main>
    );
  }
  if (health.data.api_version !== STUDIO_API_VERSION) {
    return (
      <main className="shell-message">
        <ErrorState
          error={{
            code: "unavailable",
            message: `This page speaks studio API ${STUDIO_API_VERSION} and the server speaks ${health.data.api_version}. Rebuild the page from the same checkout as the server.`,
          }}
        />
      </main>
    );
  }

  const routes = ROUTES.filter((r) => visible(r, capabilities.data));
  return (
    <div className="shell">
      <nav className="shell-nav" aria-label="Studio">
        <Link href="/" className="shell-brand" aria-label="Caterva Studio, home">
          <Lockup size={22} />
        </Link>
        <ul>
          {routes.map((r) => (
            <li key={r.path}>
              <Link href={r.path} aria-current={location === r.path ? "page" : undefined}>
                {r.title}
              </Link>
            </li>
          ))}
        </ul>
        <p className="shell-version font-mono">caterva {health.data.version}</p>
      </nav>
      <main className="shell-main" id="main">
        <Suspense fallback={<Loading label="Opening" />}>
          <Switch>
            {routes.map((r) => (
              <Route key={r.path} path={r.path} component={r.screen} />
            ))}
            <Route>
              <EmptyState title="No such screen">
                <p>
                  <Link href="/">Go to Home</Link>
                </p>
              </EmptyState>
            </Route>
          </Switch>
        </Suspense>
      </main>
    </div>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <Shell />
    </QueryClientProvider>
  );
}
