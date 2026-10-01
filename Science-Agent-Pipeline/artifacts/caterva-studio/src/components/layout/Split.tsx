/**
 * The form | result split (and list | detail on History): two panes with a
 * hairline between them that can be dragged, or moved with the arrow keys
 * once focused. Below 1100 px the panes stack, because two columns of a
 * 1024 px window each lose the width a table of constants needs.
 *
 * react-resizable-panels writes a <style> element to set the cursor while
 * dragging, which the studio's Content Security Policy refuses; the global
 * cursor styles are switched off here and the handle's own CSS sets the
 * cursor instead.
 */
import { disableGlobalCursorStyles, Panel, PanelGroup, PanelResizeHandle } from "react-resizable-panels";
import { type ReactNode, useSyncExternalStore } from "react";

disableGlobalCursorStyles();

const NARROW = "(max-width: 1099px)";

function subscribe(onChange: () => void): () => void {
  if (typeof window.matchMedia !== "function") return () => {};
  const m = window.matchMedia(NARROW);
  m.addEventListener("change", onChange);
  return () => m.removeEventListener("change", onChange);
}

function narrow(): boolean {
  return typeof window.matchMedia === "function" && window.matchMedia(NARROW).matches;
}

export function Split({
  id,
  first,
  second,
  firstSize = 38,
  minFirst = 24,
  minSecond = 30,
  label = "Resize the panes",
}: {
  /** Remembers the sizes per split across visits (localStorage, by react-resizable-panels). */
  id: string;
  first: ReactNode;
  second: ReactNode;
  firstSize?: number;
  minFirst?: number;
  minSecond?: number;
  label?: string;
}) {
  const stacked = useSyncExternalStore(subscribe, narrow, () => false);
  if (stacked) {
    return (
      <div className="split-stacked">
        <div className="split-pane">{first}</div>
        <div className="split-pane">{second}</div>
      </div>
    );
  }
  return (
    <PanelGroup direction="horizontal" autoSaveId={`caterva.split.${id}`} className="split">
      <Panel defaultSize={firstSize} minSize={minFirst} className="split-pane">
        {first}
      </Panel>
      <PanelResizeHandle className="split-handle" aria-label={label} />
      <Panel minSize={minSecond} className="split-pane">
        {second}
      </Panel>
    </PanelGroup>
  );
}
