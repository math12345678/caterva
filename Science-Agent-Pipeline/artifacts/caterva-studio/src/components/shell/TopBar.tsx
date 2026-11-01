/**
 * The top bar: where you are (group, screen, and the run the screen is
 * showing, with its state), the job activity, the command palette and the
 * theme. The run shown is the one in the address (`?run=<id>`), so a
 * reload or a link from a notification lands on the same place.
 */
import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { useLocation, useSearch } from "wouter";

import { getRun } from "@/api/runs";
import { modKey } from "@/lib/keyboard";
import type { StudioRoute } from "@/routes";

import { useCommandRegistry } from "@/components/palette/commands";

import { JobActivity } from "./JobActivity";
import { GROUP_LABEL } from "./Rail";
import { Identified } from "@/components/run/Identified";
import { RunStatusMark } from "./RunStatusMark";
import { ThemeSwitch } from "./ThemeSwitch";

/** caterva/studio/routes.py RUN_ID_PATTERN. */
export const RUN_ID = /^[0-9]{8}-[0-9]{6}-[a-z]+(?:-[a-z]+)?-[0-9a-f]{8}$/;

/** The run named in the address (`?run=<id>`), when it is a well-formed run id. */
export function useShownRunId(): string | null {
  const search = useSearch();
  const id = new URLSearchParams(search).get("run");
  return id && RUN_ID.test(id) ? id : null;
}

export function TopBar({ routes }: { routes: StudioRoute[] }) {
  const [location] = useLocation();
  const route = routes.find((r) => (r.path === "/" ? location === "/" : location === r.path));
  const runId = useShownRunId();
  const run = useQuery({ queryKey: ["run", runId], queryFn: () => getRun(runId as string), enabled: runId !== null });
  const { setOpen } = useCommandRegistry();
  const group = route ? GROUP_LABEL[route.group] : null;
  return (
    <header className="topbar">
      <div className="topbar-context">
        {group ? (
          <>
            <span className="topbar-crumb">{group}</span>
            <span className="topbar-sep" aria-hidden="true">
              /
            </span>
          </>
        ) : null}
        <span className="topbar-title">{route?.title ?? "Not found"}</span>
        {runId && run.data ? (
          <>
            <span className="topbar-sep" aria-hidden="true">
              /
            </span>
            <span className="topbar-run" title={run.data.id}>
              <RunStatusMark status={run.data.status} meaning={run.data.outcome?.meaning ?? null} />
              <span className="topbar-run-title">
                <Identified text={run.data.title} />
              </span>
            </span>
          </>
        ) : null}
      </div>
      <div className="topbar-actions">
        <JobActivity />
        <button type="button" className="palette-trigger" onClick={() => setOpen(true)} aria-keyshortcuts="Meta+K Control+K">
          <Search size={14} aria-hidden="true" />
          <span className="palette-trigger-text">Go to, compose, open a run</span>
          <span className="kbd-group" aria-hidden="true">
            <kbd>{modKey()}</kbd>
            <kbd>K</kbd>
          </span>
        </button>
        <ThemeSwitch />
      </div>
    </header>
  );
}
