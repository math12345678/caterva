import { useMemo } from "react";
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
        <>
          <StaggeredLine
            key={i}
            text={line.text}
            className={line.className}
            delayOffset={
              line.delayOffset !== undefined ? line.delayOffset : i * 0.3
            }
          />
          {i < lines.length - 1 && <br />}
        </>
      ))}
    </>
  );
}
