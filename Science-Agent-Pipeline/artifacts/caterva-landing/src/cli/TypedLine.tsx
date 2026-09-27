import { useEffect, useState } from "react";

interface TypedLineProps {
  command: string;
  delayMs?: number;
  speedMs?: number;
  onDone?: () => void;
}

// Types out a "$ command" line character by character, once, then stays put.
export default function TypedLine({
  command,
  delayMs = 0,
  speedMs = 22,
  onDone,
}: TypedLineProps) {
  const [shown, setShown] = useState("");
  const [done, setDone] = useState(false);

  useEffect(() => {
    let i = 0;
    let interval: ReturnType<typeof setInterval>;
    const start = setTimeout(() => {
      interval = setInterval(() => {
        i += 1;
        setShown(command.slice(0, i));
        if (i >= command.length) {
          clearInterval(interval);
          setDone(true);
          onDone?.();
        }
      }, speedMs);
    }, delayMs);
    return () => {
      clearTimeout(start);
      clearInterval(interval);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [command]);

  return (
    <div className="flex items-center gap-2">
      <span className="text-[#1D8A72]">$</span>
      <span className="text-white/90">{shown}</span>
      {!done && (
        <span className="inline-block h-4 w-2 bg-white/70 animate-pulse" />
      )}
    </div>
  );
}
