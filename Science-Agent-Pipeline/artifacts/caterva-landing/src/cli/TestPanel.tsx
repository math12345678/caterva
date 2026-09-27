import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { TEST_SUITES, SKIP_EXPLANATION, totals } from "@/lib/testResults";

function FileRow({
  file,
  index,
}: {
  file: { file: string; passed: number; skipped: number; failed: number };
  index: number;
}) {
  const total = file.passed + file.skipped + file.failed;
  const passPct = total > 0 ? (file.passed / total) * 100 : 0;

  return (
    <motion.div
      initial={{ opacity: 0, x: -8 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.3, delay: index * 0.03 }}
      className="group"
    >
      <div className="flex items-center justify-between gap-4 text-[12px] py-1.5">
        <div className="flex items-center gap-2 min-w-0 flex-1">
          <motion.span
            initial={{ scale: 0 }}
            animate={{ scale: 1 }}
            transition={{
              delay: index * 0.03 + 0.1,
              type: "spring",
              stiffness: 300,
            }}
            className={`w-1.5 h-1.5 rounded-full shrink-0 ${
              file.failed > 0
                ? "bg-red-400"
                : file.skipped > 0
                  ? "bg-yellow-400"
                  : "bg-[#1D8A72]"
            }`}
          />
          <span className="text-white/60 truncate group-hover:text-white/80 transition-colors">
            {file.file}
          </span>
        </div>
        <span className="flex gap-3 shrink-0 font-mono text-[11px]">
          <span className="text-[#1D8A72]">{file.passed} passed</span>
          {file.skipped > 0 && (
            <span className="text-yellow-500/70">{file.skipped} skipped</span>
          )}
          {file.failed > 0 && (
            <span className="text-red-400">{file.failed} failed</span>
          )}
        </span>
      </div>
      <div className="h-1 w-full bg-white/[0.03] rounded-full overflow-hidden">
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${passPct}%` }}
          transition={{ duration: 0.6, delay: index * 0.03, ease: "easeOut" }}
          className={`h-full rounded-full ${
            file.failed > 0
              ? "bg-red-400/40"
              : file.skipped > 0
                ? "bg-yellow-400/40"
                : "bg-[#1D8A72]/40"
          }`}
        />
      </div>
    </motion.div>
  );
}

function AnimatedCount({
  value,
  suffix = "",
}: {
  value: number;
  suffix?: string;
}) {
  const [display, setDisplay] = useState(0);
  useEffect(() => {
    const duration = 600;
    const steps = 20;
    const increment = value / steps;
    let current = 0;
    const id = window.setInterval(() => {
      current += increment;
      if (current >= value) {
        setDisplay(value);
        window.clearInterval(id);
      } else {
        setDisplay(Math.round(current));
      }
    }, duration / steps);
    return () => window.clearInterval(id);
  }, [value]);
  return (
    <>
      {display}
      {suffix}
    </>
  );
}

export default function TestPanelBody() {
  const { passed, skipped, failed, total } = totals();

  return (
    <div>
      <div className="mb-4 text-white/90">
        <span className="text-[#1D8A72]">$</span> caterva test --run --no-skip
        -v
      </div>

      {TEST_SUITES.map((suite, si) => (
        <div key={suite.name} className="mb-6">
          <div className="flex items-center gap-2 text-[11px] mb-3">
            <span className="inline-flex items-center gap-1 rounded bg-white/[0.04] px-2 py-0.5 text-white/30">
              {suite.workingDirectory}
            </span>
            <span className="text-white/20">— {suite.name}</span>
          </div>
          <div className="space-y-1">
            {suite.files.map((f, i) => (
              <FileRow key={f.file} file={f} index={i} />
            ))}
          </div>
        </div>
      ))}

      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.3 }}
        className="mt-6 pt-4 border-t border-white/[0.04] flex items-center gap-3 text-[13px]"
      >
        <span className="text-white/70 font-semibold">
          <AnimatedCount value={total} /> total
        </span>
        <span className="w-px h-3 bg-white/[0.06]" />
        <span className="text-[#1D8A72]">
          <AnimatedCount value={passed} /> passed
        </span>
        {skipped > 0 && (
          <>
            <span className="w-px h-3 bg-white/[0.06]" />
            <span className="text-yellow-500/70">
              <AnimatedCount value={skipped} /> skipped
            </span>
          </>
        )}
        <span className="w-px h-3 bg-white/[0.06]" />
        {failed > 0 ? (
          <span className="text-red-400">
            <AnimatedCount value={failed} />
          </span>
        ) : (
          <span className="text-white/30">
            <AnimatedCount value={0} /> failed
          </span>
        )}
      </motion.div>

      {skipped > 0 && (
        <div className="mt-4 text-[11px] text-white/30 leading-relaxed border border-yellow-500/15 bg-yellow-500/[0.03] px-3 py-2">
          <span className="text-yellow-500/60 font-medium">skip note: </span>
          {SKIP_EXPLANATION}
        </div>
      )}
    </div>
  );
}
