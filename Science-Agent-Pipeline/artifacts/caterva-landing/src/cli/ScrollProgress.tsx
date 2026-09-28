import { useEffect, useState } from "react";
import { motion, useScroll, useSpring } from "framer-motion";

export default function ScrollProgress() {
  const { scrollYProgress } = useScroll();
  const scaleY = useSpring(scrollYProgress, { stiffness: 200, damping: 30 });
  const [readingTime, setReadingTime] = useState(0);

  useEffect(() => {
    const start = Date.now();
    const id = window.setInterval(
      () => setReadingTime(Math.floor((Date.now() - start) / 1000)),
      1000,
    );
    return () => window.clearInterval(id);
  }, []);

  const mins = Math.floor(readingTime / 60);
  const secs = readingTime % 60;

  return (
    <div className="fixed top-0 left-0 right-0 z-[40] h-[2px]">
      <motion.div
        className="h-full bg-gradient-to-r from-signal/60 via-signal to-signal/60 origin-left"
        style={{ scaleX: scaleY }}
      />
    </div>
  );
}
