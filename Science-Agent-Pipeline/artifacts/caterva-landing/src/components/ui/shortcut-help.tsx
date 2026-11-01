import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";

const SHORTCUTS: { keys: string; label: string }[] = [
  { keys: "\u2318K", label: "Open command palette" },
  { keys: "\u2318?\u2009/\u2009?", label: "Toggle this help" },
  { keys: "Esc", label: "Close dialogs / palette" },
  { keys: "J\u2009/\u2009\u2193", label: "Next section" },
  { keys: "K\u2009/\u2009\u2191", label: "Previous section" },
  { keys: "\u2191\u2193", label: "Navigate command history (in shell)" },
  { keys: "Tab", label: "Auto-complete (in shell)" },
];

export default function ShortcutHelp() {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (e.key === "?" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setOpen((p) => !p);
      } else if (e.key === "?" && !e.metaKey && !e.ctrlKey && !e.shiftKey) {
        const tag = (e.target as HTMLElement)?.tagName;
        if (tag !== "INPUT" && tag !== "TEXTAREA") {
          e.preventDefault();
          setOpen((p) => !p);
        }
      }
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", down);
    return () => document.removeEventListener("keydown", down);
  }, []);

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-50 flex items-center justify-center"
        >
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-surface/50 backdrop-blur-sm"
            onClick={() => setOpen(false)}
          />
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: -10 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95 }}
            transition={{ duration: 0.15, ease: "easeOut" }}
            className="relative w-full max-w-sm rounded-xl border border-fg/[0.16] bg-surface p-5 shadow-2xl"
          >
            <h2 className="text-fg/78 text-[13px] font-medium mb-4">
              Keyboard Shortcuts
            </h2>
            <div className="space-y-2">
              {SHORTCUTS.map((s) => (
                <div
                  key={s.keys}
                  className="flex items-center justify-between text-[12px]"
                >
                  <span className="text-fg/70">{s.label}</span>
                  <kbd className="rounded border border-fg/[0.12] px-1.5 py-0.5 text-[10px] text-fg/70 font-sans">
                    {s.keys}
                  </kbd>
                </div>
              ))}
            </div>
            <p className="mt-4 text-[10px] text-fg/66 text-center">
              Press{" "}
              <kbd className="rounded border border-fg/[0.12] px-1 py-0.5">
                ?
              </kbd>{" "}
              or{" "}
              <kbd className="rounded border border-fg/[0.12] px-1 py-0.5">
                {"\u2318?"}
              </kbd>{" "}
              to close
            </p>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
