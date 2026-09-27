import { Fragment, useMemo } from "react";
import { motion } from "framer-motion";

interface StaggeredHeroProps {
  lines: { text: string; className: string; delayOffset?: number }[];
}

function StaggeredLine({
  text,
  className,
  delayOffset = 0,
}: {
  text: string;
  className: string;
  delayOffset?: number;
}) {
  const words = useMemo(() => text.split(" "), [text]);

  return (
    <span className={className}>
      {words.map((word, i) => (
        <motion.span
          key={i}
          style={{ display: "inline-block", whiteSpace: "pre" }}
          initial={{ opacity: 0, y: 28, rotateX: -15, filter: "blur(8px)" }}
          animate={{ opacity: 1, y: 0, rotateX: 0, filter: "blur(0px)" }}
          transition={{
            duration: 0.7,
            delay: delayOffset + i * 0.08,
            ease: [0.16, 1, 0.3, 1],
          }}
        >
          {word}
          {i < words.length - 1 ? " " : ""}
        </motion.span>
      ))}
    </span>
  );
}

export default function StaggeredHero({ lines }: StaggeredHeroProps) {
  return (
    <>
      {lines.map((line, i) => (
        // Fragment WITH A KEY, not `<>`.
        //
        // This was an anonymous `<>` with the key on StaggeredLine inside
        // it -- so the list element itself had no key, and React logged
        // the "unique key prop" warning. The consequence was not
        // cosmetic: it made the hero permanently invisible.
        //
        // CliApp polls the API continuously (waitlist count, run list,
        // pipeline status), so this subtree re-renders every couple of
        // seconds. Keyless children get remounted rather than reconciled,
        // and framer-motion's `initial` runs on mount -- so every poll
        // restarted the word animation from opacity 0. The stagger needs
        // ~1.5s to finish and never got it. Measured in the browser
        // before this fix: the first word sat at opacity 0.374 mid-flight
        // and every word after it at 0, with animationName "none".
        //
        // The result was a black screen with a nav bar. The headline, the
        // subtitle and the primary CTA were all in the DOM the whole
        // time, which is why nothing in the test suite caught it -- the
        // markup was correct and only the rendered pixels were wrong.
        <Fragment key={i}>
          <StaggeredLine
            text={line.text}
            className={line.className}
            delayOffset={
              line.delayOffset !== undefined ? line.delayOffset : i * 0.3
            }
          />
          {i < lines.length - 1 && <br />}
        </Fragment>
      ))}
    </>
  );
}
