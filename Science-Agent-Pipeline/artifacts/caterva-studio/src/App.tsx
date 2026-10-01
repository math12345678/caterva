/**
 * The studio's shell: the rail, the top bar, the status line, the command
 * palette and the notifications, around whichever screen the address names.
 *
 * Before any of that, three things are checked, each with its own sentence
 * because each needs a different remedy: the page carries a session token
 * (it was served by `caterva studio`), the server answers, and it speaks
 * the same API version this page was built for. A server that stops
 * answering after the page loaded keeps the shell on screen (the work on
 * it is still worth reading) and says so above the screen.
 */
import { QueryClientProvider } from "@tanstack/react-query";
import { type ReactNode, Suspense, useState } from "react";
import { Link, Route, Switch } from "wouter";

import { sessionToken } from "@/api/client";
import { STUDIO_API_VERSION } from "@/api/types";
import { CommandPalette, visibleRoutes } from "@/components/palette/CommandPalette";
import { CommandProvider } from "@/components/palette/commands";
import { Rail } from "@/components/shell/Rail";
import { StatusLine } from "@/components/shell/StatusLine";
import { TopBar } from "@/components/shell/TopBar";
import { Loading } from "@/components/states/Loading";
import { EmptyState, ErrorState } from "@/components/states/States";
import { Toaster } from "@/components/toast/Toaster";
import { JobsProvider } from "@/lib/jobs";
import { makeQueryClient, useCapabilities, useHealth } from "@/lib/queries";
import { useAdoptServerTheme, useSettings } from "@/lib/settings";

function ShellMessage({ children }: { children: ReactNode }) {
  return (
    <main className="shell-message" id="main">
      <div>{children}</div>
    </main>
  );
}

function Shell() {
  const health = useHealth();
  const ready = health.isSuccess && health.data.api_version === STUDIO_API_VERSION;
  const capabilities = useCapabilities(ready);
  const settings = useSettings(ready);
  useAdoptServerTheme(settings.data);

  if (sessionToken() === null) {
    return (
      <ShellMessage>
        <ErrorState
          title="This page was not opened by the studio server"
          error={{
            code: "unauthorized",
            message:
              "It carries no session token, so the server would refuse every request. Start it with `caterva studio` (or open Caterva.app) and use the address it prints.",
          }}
        />
      </ShellMessage>
    );
  }
  if (health.isPending) {
    return (
      <ShellMessage>
        <Loading label="Connecting to the studio server" size={44} />
      </ShellMessage>
    );
  }
  if (!health.data) {
    return (
      <ShellMessage>
        <ErrorState
          error={health.error}
          action={
            <button type="button" className="btn" onClick={() => void health.refetch()}>
              Try again
            </button>
          }
        />
      </ShellMessage>
    );
  }
  if (health.data.api_version !== STUDIO_API_VERSION) {
    return (
      <ShellMessage>
        <ErrorState
          title="This page and the server were built apart"
          error={{
            code: "unavailable",
            message: `This page speaks studio API ${STUDIO_API_VERSION} and the server speaks ${health.data.api_version}. Rebuild the page from the same checkout as the server.`,
          }}
        />
      </ShellMessage>
    );
  }

  const routes = visibleRoutes(capabilities.data);
  return (
    <div className="app">
      <a className="skip-link" href="#main">
        Skip to the screen
      </a>
      <Rail routes={routes} version={health.data.version} />
      <TopBar routes={routes} />
      <main className="main" id="main" tabIndex={-1}>
        {health.isError ? (
          <div className="server-lost" role="alert">
            <ErrorState
              inset
              title="The studio server stopped answering"
              error={health.error}
              action={
                <button type="button" className="btn btn-sm" onClick={() => void health.refetch()}>
                  Check again
                </button>
              }
            />
          </div>
        ) : null}
        <Suspense
          fallback={
            <div className="screen">
              <Loading label="Opening the screen" />
            </div>
          }
        >
          <Switch>
            {routes.map((r) => (
              <Route key={r.path} path={r.path} component={r.screen} />
            ))}
            <Route>
              <div className="screen">
                <EmptyState title="There is no screen at this address">
                  <p>
                    <Link href="/">Go to Home</Link>, or press the command palette's key to go anywhere.
                  </p>
                </EmptyState>
              </div>
            </Route>
          </Switch>
        </Suspense>
      </main>
      <StatusLine
        health={health.data}
        healthError={health.isError ? health.error : null}
        capabilities={capabilities.data}
        capabilitiesError={capabilities.isError ? capabilities.error : null}
      />
      <CommandPalette capabilities={capabilities.data} />
      <Toaster />
    </div>
  );
}

export default function App() {
  const [client] = useState(makeQueryClient);
  return (
    <QueryClientProvider client={client}>
      <CommandProvider>
        <JobsProvider>
          <Shell />
        </JobsProvider>
      </CommandProvider>
    </QueryClientProvider>
  );
}
