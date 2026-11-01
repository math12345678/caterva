import { Fragment } from "react";

interface StaggeredHeroProps {
  lines: { text: string; className: string; delayOffset?: number }[];
}

/**
 * The hero headline, rendered as plain text.
 *
 * This used to animate every word in from opacity 0 with a blur and a 3D
 * tilt, staggered over about 1.5 s. That had two costs. It once made the
 * hero permanently invisible: CliApp re-renders on every API poll, keyless
 * children remounted, and each remount restarted the words from opacity 0
 * (the fix was the keyed Fragment below). And it put a blank page in front
 * of every visitor for the length of the stagger, on a site whose voice is
 * quiet and unhurried. The headline is the most important text on the
 * page; it should be there on first paint, with no script needed to see it.
 *
 * `delayOffset` is accepted and ignored so callers need not change.
 */
export default function StaggeredHero({ lines }: StaggeredHeroProps) {
  return (
    <>
      {lines.map((line, i) => (
        <Fragment key={i}>
          <span className={line.className}>{line.text}</span>
          {i < lines.length - 1 && <br />}
        </Fragment>
      ))}
    </>
  );
}
