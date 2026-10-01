/**
 * The frame of every screen: a Spectral title, one sentence of purpose, the
 * primary action, then the work. Screens own their content; this owns only
 * the frame, so every screen reads the same way.
 *
 * `Section` is the one level of structure inside a screen: a title on a
 * hairline, an aside (a count, a legend, an action) on the same line. It is
 * not a card; screens that need a bounded region for a reason (the viewer,
 * an ink slab of command output) draw that region themselves.
 */
import { type ReactNode, useEffect, useId } from "react";

import { cn } from "@/lib/cn";

export function Screen({
  title,
  purpose,
  actions,
  children,
  className,
}: {
  title: string;
  purpose: string;
  actions?: ReactNode;
  children?: ReactNode;
  className?: string;
}) {
  useEffect(() => {
    document.title = title === "Home" || title === "Caterva Studio" ? "Caterva Studio" : `${title} · Caterva Studio`;
  }, [title]);
  return (
    <div className={cn("screen", className)}>
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

export function Section({
  title,
  aside,
  children,
  id,
  className,
}: {
  title: string;
  aside?: ReactNode;
  children?: ReactNode;
  id?: string;
  className?: string;
}) {
  const auto = useId();
  const headingId = `${id ?? auto}-title`;
  return (
    <section className={cn("section", className)} id={id} aria-labelledby={headingId}>
      <div className="section-head">
        <h2 className="section-title" id={headingId}>
          {title}
        </h2>
        {aside ? <div className="section-aside">{aside}</div> : null}
      </div>
      {children}
    </section>
  );
}
