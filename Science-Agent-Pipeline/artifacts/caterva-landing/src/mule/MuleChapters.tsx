import { useEffect, useRef } from "react";
import chaptersHtml from "./chapters.html?raw";
import "./mule.css";

/**
 * The MuleRun chapters, merged into the main site: the Evidence Cathedral,
 * the system atlas, the orchestration console, the evidence rail, the
 * evidence microscope, the separated trust layer and the runtimes.
 *
 * They were a standalone page of plain modules (no framework), and they stay
 * that way: rewriting ~9,000 lines of choreography in React would risk the
 * very animations worth keeping. React owns this one element; the modules
 * own everything inside it. Their stylesheet is scoped under `.mule` so it
 * cannot restyle the page around it, and the pieces they used to append to
 * <body> (the mode dock, the inspector, a live region) attach here instead.
 *
 * On paper, the whole block reads as one ink chapter: the same move as the
 * terminal slabs elsewhere on the page, at full width.
 */
export default function MuleChapters() {
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = root.current;
    if (!el) return;
    let cancelled = false;
    import("./js/main.js").then((m) => {
      if (!cancelled) m.bootMule(el);
    });

    // The system-mode dock is fixed to the viewport. It belongs to these
    // chapters, so it is shown only while they are on screen, and never over
    // the paper sections' own bottom bar.
    const io = new IntersectionObserver(
      ([entry]) => {
        el.classList.toggle("is-offstage", !entry.isIntersecting);
        // The paper sections' bottom bar and back-to-top step aside while
        // the ink chapters (which have their own controls there) are shown.
        document.documentElement.classList.toggle("mule-in-view", entry.isIntersecting);
      },
      { rootMargin: "-20% 0px -20% 0px" },
    );
    io.observe(el);
    return () => {
      cancelled = true;
      io.disconnect();
      document.documentElement.classList.remove("mule-in-view");
    };
  }, []);

  return (
    <div
      ref={root}
      className="mule is-offstage"
      // Static markup from the original page, authored in this repository.
      dangerouslySetInnerHTML={{ __html: chaptersHtml }}
    />
  );
}
