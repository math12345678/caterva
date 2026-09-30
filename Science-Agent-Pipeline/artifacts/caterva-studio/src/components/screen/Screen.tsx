/**
 * The frame of every screen: a Spectral title, one sentence of purpose, the
 * primary action, then the work. Screens own their content; this owns only
 * the frame, so every screen reads the same way.
 */
import type { ReactNode } from "react";

export function Screen({
  title,
  purpose,
  actions,
  children,
}: {
  title: string;
  purpose: string;
  actions?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <div className="screen">
      <header className="screen-header">
        <div>
          <h1 className="screen-title">{title}</h1>
          <p className="screen-purpose">{purpose}</p>
        </div>
        {actions ? <div className="screen-actions">{actions}</div> : null}
      </header>
      <div className="screen-body">{children}</div>
    </div>
  );
}
