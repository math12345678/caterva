/**
 * The command registry the palette reads: every route (from the route
 * table) and every primary action a screen registers while it is shown.
 *
 * A screen makes its primary action reachable from Cmd-K with one line,
 * `useCommand({ id: "compose.submit", title: "Compose", run: submit })`,
 * and it leaves the palette when the screen does. That is how "every
 * action reachable by keyboard" holds without the palette knowing any
 * screen's internals.
 */
import { createContext, type ReactNode, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";

export interface Command {
  /** Unique while registered, e.g. "compose.submit". */
  id: string;
  title: string;
  /** A second line: what it will do, or why it cannot. */
  hint?: string;
  /** Words the palette also matches on. */
  keywords?: string[];
  run: () => void;
  disabled?: boolean;
}

interface Registry {
  commands: Command[];
  register(owner: string, commands: Command[]): () => void;
  open: boolean;
  setOpen(open: boolean): void;
}

const Context = createContext<Registry | null>(null);

export function CommandProvider({ children }: { children: ReactNode }) {
  const owners = useRef(new Map<string, Command[]>());
  const [version, setVersion] = useState(0);
  const [open, setOpen] = useState(false);

  const register = useCallback((owner: string, commands: Command[]) => {
    owners.current.set(owner, commands);
    setVersion((v) => v + 1);
    return () => {
      owners.current.delete(owner);
      setVersion((v) => v + 1);
    };
  }, []);

  const value = useMemo<Registry>(() => {
    void version; // the list below is read from the map this counter tracks
    return { commands: [...owners.current.values()].flat(), register, open, setOpen };
  }, [version, register, open]);

  return <Context.Provider value={value}>{children}</Context.Provider>;
}

export function useCommandRegistry(): Registry {
  const r = useContext(Context);
  if (!r) throw new Error("useCommandRegistry needs <CommandProvider>, which App mounts around every screen.");
  return r;
}

/** Register a screen's action in the palette while the screen is shown. */
export function useCommand(command: Command | null): void {
  const r = useContext(Context);
  const latest = useRef(command);
  latest.current = command;
  const id = command?.id ?? null;
  const title = command?.title;
  const hint = command?.hint;
  const disabled = command?.disabled;
  const keywords = command?.keywords?.join(" ");
  useEffect(() => {
    if (!r || id === null || title === undefined) return;
    return r.register(id, [
      {
        id,
        title,
        hint,
        disabled,
        keywords: keywords ? keywords.split(" ") : undefined,
        run: () => latest.current?.run(),
      },
    ]);
    // `r.register` is stable; re-register only when what the palette shows changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, title, hint, disabled, keywords]);
}
