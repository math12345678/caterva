/**
 * The left rail: the reserved routes in three groups (Kinetics, Structure
 * & dynamics, Workspace) under Home, drawn quietly so the screen leads.
 * The current place wears the mark's signal dot, not a stripe. `/rates` is
 * listed only when the server says `caterva rates` is available.
 */
import {
  Activity,
  Atom,
  BookOpen,
  Boxes,
  ClipboardCheck,
  Dices,
  Gauge,
  History,
  House,
  Info,
  type LucideIcon,
  Magnet,
  Ruler,
  Settings2,
  Workflow,
} from "lucide-react";
import { Link, useLocation } from "wouter";

import { Lockup } from "@/components/brand/Mark";
import type { StudioRoute } from "@/routes";

export const ROUTE_ICONS: Record<string, LucideIcon> = {
  "/": House,
  "/compose": Workflow,
  "/constants": BookOpen,
  "/rates": Gauge,
  "/sim": Dices,
  "/bind": Magnet,
  "/structure": Boxes,
  "/prepare": ClipboardCheck,
  "/md": Atom,
  "/analyze": Ruler,
  "/history": History,
  "/settings": Settings2,
  "/about": Info,
};

export const GROUP_LABEL: Record<StudioRoute["group"], string | null> = {
  start: null,
  kinetics: "Kinetics",
  structure: "Structure & dynamics",
  workspace: "Workspace",
};

export function Rail({ routes, version }: { routes: StudioRoute[]; version: string | null }) {
  const [location] = useLocation();
  const groups = (["start", "kinetics", "structure", "workspace"] as const)
    .map((g) => ({ group: g, routes: routes.filter((r) => r.group === g) }))
    .filter((g) => g.routes.length);
  return (
    <nav className="rail" aria-label="Studio">
      <Link href="/" className="rail-brand" aria-label="Caterva Studio, home">
        <Lockup size={20} />
        <span className="rail-product">studio</span>
      </Link>
      <div className="rail-nav">
        {groups.map(({ group, routes: rs }) => {
          const label = GROUP_LABEL[group];
          return (
            <div className="rail-group" key={group} role="group" aria-label={label ?? "Start"}>
              {label ? <div className="rail-group-label">{label}</div> : null}
              {rs.map((r) => {
                const Icon = ROUTE_ICONS[r.path] ?? Activity;
                const current = r.path === "/" ? location === "/" : location === r.path || location.startsWith(`${r.path}/`);
                return (
                  <Link key={r.path} href={r.path} className="rail-link" aria-current={current ? "page" : undefined}>
                    <Icon size={15} aria-hidden="true" />
                    <span>{r.title}</span>
                  </Link>
                );
              })}
            </div>
          );
        })}
      </div>
      <div className="rail-foot">
        <span className="rail-version font-mono">{version ? `caterva ${version}` : "caterva"}</span>
      </div>
    </nav>
  );
}
