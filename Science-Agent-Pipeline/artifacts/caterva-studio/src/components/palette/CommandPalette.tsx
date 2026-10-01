/**
 * The command palette, Cmd-K (Ctrl-K off macOS): go anywhere, start a
 * compose from what you typed, reopen a recent run, run the current
 * screen's primary action, switch the theme.
 *
 * It is a native <dialog> opened with showModal(): the browser contains
 * focus, makes the page behind it inert, and closes it on Escape, and no
 * script injects a <style> element the Content Security Policy would
 * refuse (Radix's dialog does, for its scroll lock). cmdk supplies the
 * filtering and the arrow-key list.
 *
 * "Compose" starts a real run of `caterva compose` with the typed text as
 * its description, exactly as `caterva compose "<text>"` would, and opens
 * it; if the server refuses (the kind is unavailable, the text is not a
 * description), its words are shown here and nothing is started.
 */
import { Command, defaultFilter } from "cmdk";
import { ArrowRight, CornerDownLeft, FlaskConical, History, Monitor, Moon, Play, Search, Sun } from "lucide-react";
import { Fragment, type ReactNode, useCallback, useEffect, useRef, useState } from "react";
import { useLocation } from "wouter";

import { createRun } from "@/api/runs";
import type { Capabilities, RunSummary } from "@/api/types";
import { describeError } from "@/lib/errors";
import { formatWhen } from "@/lib/format";
import { runHref, useJobActionsOptional } from "@/lib/jobs";
import { modKey, useHotkey } from "@/lib/keyboard";
import { useRunList } from "@/lib/queries";
import { useSetTheme } from "@/lib/settings";
import { ROUTES, type StudioRoute } from "@/routes";

import { RunStatusMark } from "@/components/shell/RunStatusMark";

import { useCommandRegistry } from "./commands";

const GROUP_TITLE: Record<StudioRoute["group"], string> = {
  start: "Go to",
  kinetics: "Kinetics",
  structure: "Structure & dynamics",
  workspace: "Workspace",
};

/** The compose item's value: never a screen's title, so it never outranks one. */
const COMPOSE_VALUE = "palette:compose-from-text";

/**
 * Rank by what an item is called first and by its description second: a
 * screen whose title matches the typed text always outranks one whose
 * purpose merely contains its letters in order, and the compose item, which
 * is always shown while there is text, is chosen by Enter only when no
 * screen, run or command matches at all.
 */
export function paletteFilter(value: string, search: string, keywords?: string[]): number {
  if (value === COMPOSE_VALUE) return 0.001;
  const byName = defaultFilter(value, search);
  const byWords = keywords?.length ? 0.3 * defaultFilter(keywords.join(" "), search) : 0;
  return Math.max(byName, byWords);
}

interface Section {
  key: string;
  /** Each item's [value, keywords], scored with the palette's own filter. */
  items: [string, string[]?][];
  node: ReactNode;
}

/**
 * cmdk sorts items inside a group but, with React's generated ids, cannot
 * find its groups to reorder them, and Enter takes the first selectable item
 * in document order. So the groups are ordered here, by their best item's
 * score, and the screen whose title matches comes before a group that only
 * matched in passing. With no text the order is the written one.
 */
export function orderSections<T extends Section>(sections: T[], search: string): T[] {
  if (!search) return sections;
  const best = (s: T) => Math.max(0, ...s.items.map(([v, k]) => paletteFilter(v, search, k)));
  return sections
    .map((section, i) => ({ section, i, score: best(section) }))
    .sort((x, y) => y.score - x.score || x.i - y.i)
    .map(({ section }) => section);
}

export function visibleRoutes(capabilities: Capabilities | undefined): StudioRoute[] {
  return ROUTES.filter((r) => (r.gate === "rates" ? Boolean(capabilities?.rates.available) : true));
}

export function CommandPalette({ capabilities }: { capabilities: Capabilities | undefined }) {
  const registry = useCommandRegistry();
  const { open, setOpen } = registry;
  const dialog = useRef<HTMLDialogElement>(null);
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [, navigate] = useLocation();
  const jobs = useJobActionsOptional();
  const setTheme = useSetTheme();
  const recent = useRunList({ limit: 8 }, open);

  useHotkey({ key: "k", mod: true }, () => setOpen(!open));

  useEffect(() => {
    const d = dialog.current;
    if (!d) return;
    if (open && !d.open) {
      setQuery("");
      setError(null);
      d.showModal();
      // showModal runs the dialog's own focusing steps after React's
      // autoFocus, and lands on cmdk's root; the reader types into the input.
      d.querySelector<HTMLInputElement>("[cmdk-input]")?.focus();
    } else if (!open && d.open) {
      d.close();
    }
  }, [open]);

  const close = useCallback(() => setOpen(false), [setOpen]);
  const go = useCallback(
    (href: string) => {
      close();
      navigate(href);
    },
    [close, navigate],
  );

  const compose = capabilities?.kinds.compose;
  const text = query.trim();

  const startCompose = useCallback(async () => {
    if (!text || busy) return;
    setBusy(true);
    setError(null);
    try {
      const { run } = await createRun("compose", { description: text });
      jobs?.track(run, "here");
      go(runHref(run));
    } catch (e) {
      setError(describeError(e).message);
    } finally {
      setBusy(false);
    }
  }, [text, busy, jobs, go]);

  const routes = visibleRoutes(capabilities);
  const groups = (["start", "kinetics", "structure", "workspace"] as const).map((g) => ({
    group: g,
    routes: routes.filter((r) => r.group === g),
  }));
  const runs: RunSummary[] = recent.data?.runs ?? [];

  const sections: Section[] = [];
  if (text) {
    sections.push({
      key: "start",
      items: [[COMPOSE_VALUE]],
      node: (
        <Command.Group heading="Start" value="start" forceMount>
          <Command.Item value={COMPOSE_VALUE} disabled={busy || compose?.available === false} onSelect={() => void startCompose()} forceMount>
            <FlaskConical size={15} aria-hidden="true" />
            <span className="palette-item-main">
              <span className="palette-item-title">
                Compose <span className="font-mono">“{text}”</span>
              </span>
              <span className="palette-item-sub">
                {compose?.available === false
                  ? `Not available: ${compose.reason ?? "this installation cannot run compose"}`
                  : busy
                    ? "Starting the run"
                    : `caterva compose "${text}"`}
              </span>
            </span>
            <CornerDownLeft size={13} aria-hidden="true" />
          </Command.Item>
        </Command.Group>
      ),
    });
  }
  if (registry.commands.length) {
    sections.push({
      key: "screen",
      items: registry.commands.map((c) => [`${c.title} ${c.id}`, c.keywords]),
      node: (
        <Command.Group heading="This screen" value="screen">
          {registry.commands.map((c) => (
            <Command.Item
              key={c.id}
              value={`${c.title} ${c.id}`}
              keywords={c.keywords}
              disabled={c.disabled}
              onSelect={() => {
                close();
                c.run();
              }}
            >
              <Play size={14} aria-hidden="true" />
              <span className="palette-item-main">
                <span className="palette-item-title">{c.title}</span>
                {c.hint ? <span className="palette-item-sub">{c.hint}</span> : null}
              </span>
            </Command.Item>
          ))}
        </Command.Group>
      ),
    });
  }
  for (const { group, routes: rs } of groups) {
    if (!rs.length) continue;
    sections.push({
      key: `routes-${group}`,
      items: rs.map((r) => [`${r.title} ${r.path}`, [r.purpose]]),
      node: (
        <Command.Group heading={GROUP_TITLE[group]} value={`routes-${group}`}>
          {rs.map((r) => (
            <Command.Item key={r.path} value={`${r.title} ${r.path}`} keywords={[r.purpose]} onSelect={() => go(r.path)}>
              <ArrowRight size={14} aria-hidden="true" />
              <span className="palette-item-main">
                <span className="palette-item-title">{r.title}</span>
                <span className="palette-item-sub">{r.purpose}</span>
              </span>
            </Command.Item>
          ))}
        </Command.Group>
      ),
    });
  }
  if (runs.length) {
    sections.push({
      key: "recent",
      items: runs.map((run) => [`${run.title} ${run.id} ${run.kind}`]),
      node: (
        <Command.Group heading="Recent runs" value="recent">
          {runs.map((run) => (
            <Command.Item key={run.id} value={`${run.title} ${run.id} ${run.kind}`} onSelect={() => go(runHref(run))}>
              <RunStatusMark status={run.status} meaning={run.outcome?.meaning ?? null} />
              <span className="palette-item-main">
                <span className="palette-item-title">{run.title}</span>
                <span className="palette-item-sub font-mono">
                  {run.kind} · {formatWhen(run.created_at)}
                </span>
              </span>
            </Command.Item>
          ))}
        </Command.Group>
      ),
    });
  } else if (recent.isError) {
    sections.push({
      key: "recent",
      items: [["recent runs unavailable"]],
      node: (
        <Command.Group heading="Recent runs" value="recent">
          <Command.Item value="recent runs unavailable" disabled>
            <History size={14} aria-hidden="true" />
            <span className="palette-item-sub">{describeError(recent.error).message}</span>
          </Command.Item>
        </Command.Group>
      ),
    });
  }
  const themes = [
    { value: "theme light paper", theme: "light", title: "Light theme", Icon: Sun },
    { value: "theme dark ink evening", theme: "dark", title: "Dark theme", Icon: Moon },
    { value: "theme follow the system", theme: "system", title: "Theme follows the system", Icon: Monitor },
  ] as const;
  sections.push({
    key: "theme",
    items: themes.map((t) => [t.value]),
    node: (
      <Command.Group heading="Theme" value="theme">
        {themes.map(({ value, theme, title, Icon }) => (
          <Command.Item
            key={value}
            value={value}
            onSelect={() => {
              setTheme(theme);
              close();
            }}
          >
            <Icon size={14} aria-hidden="true" />
            <span className="palette-item-main">
              <span className="palette-item-title">{title}</span>
            </span>
          </Command.Item>
        ))}
      </Command.Group>
    ),
  });

  return (
    <dialog
      ref={dialog}
      className="overlay palette"
      aria-label="Command palette"
      onClose={close}
      onCancel={(e) => {
        e.preventDefault();
        close();
      }}
      onClick={(e) => {
        // A click on the backdrop lands on the dialog element itself.
        if (e.target === dialog.current) close();
      }}
    >
      {open ? (
        <Command label="Command palette" loop shouldFilter filter={paletteFilter}>
          <div className="palette-input-row">
            <Search size={16} aria-hidden="true" />
            <Command.Input
              value={query}
              onValueChange={(v) => {
                setQuery(v);
                setError(null);
              }}
              placeholder="Go to a screen, open a run, or type a mechanism to compose"
              autoFocus
            />
          </div>
          {error ? (
            <p className="palette-error" role="alert">
              {error}
            </p>
          ) : null}
          <Command.List>
            <Command.Empty>No screen, run or command matches this text.</Command.Empty>
            {orderSections(sections, text).map((section) => (
              <Fragment key={section.key}>{section.node}</Fragment>
            ))}
          </Command.List>
          <div className="palette-foot" aria-hidden="true">
            <span>
              <kbd>↑</kbd>
              <kbd>↓</kbd> move
            </span>
            <span>
              <kbd>↵</kbd> choose
            </span>
            <span>
              <kbd>esc</kbd> close
            </span>
            <span className="palette-foot-end">
              <kbd>{modKey()}</kbd>
              <kbd>K</kbd> anywhere
            </span>
          </div>
        </Command>
      ) : null}
    </dialog>
  );
}
