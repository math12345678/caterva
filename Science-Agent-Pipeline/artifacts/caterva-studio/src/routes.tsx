/**
 * Every route the studio reserves, as one table: the navigation, the
 * command palette and the router all read it, so a screen cannot be
 * reachable from one and missing from another.
 *
 * Each path has its own screen file under src/screens/, owned as
 * docs/studio/CONTRACT.md's "Ownership map" says. `/rates` is gated: it is
 * listed only when /api/capabilities reports `rates.available`.
 */
import { lazy, type ComponentType, type LazyExoticComponent } from "react";

import type { RunKind } from "@/api/types";

export type RouteGroup = "start" | "kinetics" | "structure" | "workspace";

export interface StudioRoute {
  path: string;
  title: string;
  /** One sentence: what the screen is for. */
  purpose: string;
  group: RouteGroup;
  /** The run kinds this screen submits. */
  kinds: RunKind[];
  /** Shown only when this capability is available. */
  gate?: "rates";
  screen: LazyExoticComponent<ComponentType>;
}

export const ROUTES: StudioRoute[] = [
  {
    path: "/",
    title: "Home",
    purpose: "What this installation can do, and the runs you opened last.",
    group: "start",
    kinds: [],
    screen: lazy(() => import("@/screens/Home")),
  },
  {
    path: "/compose",
    title: "Compose",
    purpose: "Build a model from the shape of a mechanism, and see where every number in it came from.",
    group: "kinetics",
    kinds: ["compose"],
    screen: lazy(() => import("@/screens/Compose")),
  },
  {
    path: "/constants",
    title: "Constants",
    purpose: "Look up an enzyme's measured constants, each with the paper that measured it.",
    group: "kinetics",
    kinds: ["constants"],
    screen: lazy(() => import("@/screens/Constants")),
  },
  {
    path: "/rates",
    title: "Rates",
    purpose: "Reserved for `caterva rates`.",
    group: "kinetics",
    kinds: ["rates"],
    gate: "rates",
    screen: lazy(() => import("@/screens/Rates")),
  },
  {
    path: "/sim",
    title: "Stochastic",
    purpose: "Exact stochastic kinetics (Gillespie SSA), seeded so every trajectory can be reproduced.",
    group: "kinetics",
    kinds: ["sim"],
    screen: lazy(() => import("@/screens/Sim")),
  },
  {
    path: "/bind",
    title: "Binding",
    purpose: "The measured binding free energy a simulation is held to, from cited Ki rows.",
    group: "kinetics",
    kinds: ["bind"],
    screen: lazy(() => import("@/screens/Bind")),
  },
  {
    path: "/structure",
    title: "Structures",
    purpose: "An enzyme's experimental structures in the PDB, each with its method, resolution and citation.",
    group: "structure",
    kinds: ["structure"],
    screen: lazy(() => import("@/screens/Structure")),
  },
  {
    path: "/prepare",
    title: "Prepare",
    purpose: "Audit a PDB entry before simulating it, defects ranked by distance to the active site.",
    group: "structure",
    kinds: ["prepare"],
    screen: lazy(() => import("@/screens/Prepare")),
  },
  {
    path: "/md",
    title: "Dynamics",
    purpose: "A GROMACS setup whose every parameter is measured, chosen or cited, and whether its replicas converged.",
    group: "structure",
    kinds: ["md.setup", "md.summarise", "fep.status", "complex.check"],
    screen: lazy(() => import("@/screens/Md")),
  },
  {
    path: "/analyze",
    title: "Analyze",
    purpose: "Catalytic geometry and active-site flexibility across replicas, called a result only when they agree.",
    group: "structure",
    kinds: ["analyze"],
    screen: lazy(() => import("@/screens/Analyze")),
  },
  {
    path: "/history",
    title: "History",
    purpose: "Every run, its request, its outcome and its files, to reopen or export.",
    group: "workspace",
    kinds: [],
    screen: lazy(() => import("@/screens/History")),
  },
  {
    path: "/settings",
    title: "Settings",
    purpose: "Theme, how many runs at once, and where the workspace lives.",
    group: "workspace",
    kinds: [],
    screen: lazy(() => import("@/screens/Settings")),
  },
  {
    path: "/about",
    title: "About",
    purpose: "Version, licences, and what this installation can and cannot reach.",
    group: "workspace",
    kinds: [],
    screen: lazy(() => import("@/screens/About")),
  },
];

/** The route a run of `kind` is shown on. */
export function routeForKind(kind: RunKind): StudioRoute | undefined {
  return ROUTES.find((r) => r.kinds.includes(kind));
}
