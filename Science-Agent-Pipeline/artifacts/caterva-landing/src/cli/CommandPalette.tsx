import { useEffect, useRef, useState, useCallback } from "react";
import { Command } from "cmdk";
import { motion, AnimatePresence } from "framer-motion";

const NAV_ITEMS = [
  { id: "domains", label: "Simulation Domains", icon: "\u25C7" },
  { id: "tests", label: "Test Results", icon: "\u2713" },
  { id: "agent", label: "Agent Simulator", icon: "\u26A1" },
  { id: "runs", label: "Recent Runs", icon: "\u21BB" },
  { id: "simulate", label: "Live Simulator", icon: "\u25A6" },
  { id: "waitlist", label: "Join Waitlist", icon: "\u2709" },
];

const EXAMPLE_QUERIES = [
  {
    query: "simulate lactate dehydrogenase with pyruvate",
    label: "LDH Kinetics",
  },
  {
    query: "competitive inhibition of lactate dehydrogenase by oxamate",
    label: "LDH + oxamate",
  },
  { query: "enzyme kinetics km 5 vmax 10", label: "MM Kinetics" },
];

export default function CommandPalette({
  onNavigate,
  onQuery,
}: {
  onNavigate: (id: string) => void;
  onQuery: (q: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const previousFocusRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (e.key === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setOpen((prev) => !prev);
      }
      if (e.key === "Escape") setOpen(false);
      // cmdk keeps DOM focus pinned to the input and never wires Tab, so without this
      // Tab escapes the dialog onto obscured background controls.
      if (open && e.key === "Tab") e.preventDefault();
    };
    document.addEventListener("keydown", down);
    return () => document.removeEventListener("keydown", down);
  }, [open]);

  useEffect(() => {
    if (open) {
      previousFocusRef.current = document.activeElement as HTMLElement | null;
    } else {
      previousFocusRef.current?.focus?.();
      previousFocusRef.current = null;
    }
  }, [open]);

  const handleSelect = useCallback(
    (value: string) => {
      setOpen(false);
      if (value.startsWith("nav:")) {
        const id = value.slice(4);
        document
          .getElementById(id)
          ?.scrollIntoView({ behavior: "smooth", block: "start" });
      } else if (value.startsWith("query:")) {
        onQuery(value.slice(6));
        setTimeout(() => {
          document
            .getElementById("agent")
            ?.scrollIntoView({ behavior: "smooth", block: "start" });
        }, 100);
      }
    },
    [onQuery],
  );

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-50 flex items-start justify-center pt-[15vh]"
        >
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-surface/60 backdrop-blur-sm"
            onClick={() => setOpen(false)}
          />
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: -10 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: -10 }}
            transition={{ duration: 0.15, ease: "easeOut" }}
            className="relative w-full max-w-lg rounded-xl border border-fg/[0.16] bg-surface shadow-2xl shadow-signal/[0.03] overflow-hidden glass-deep"
            role="dialog"
            aria-modal="true"
            aria-label="Command palette"
          >
            <Command label="Command palette">
              <Command.Input
                placeholder="Search sections or try an example query\u2026"
                className="w-full bg-transparent px-4 py-3.5 text-[13px] text-fg/85 outline-none placeholder:text-fg/66 border-b border-fg/[0.08]"
                autoFocus
              />
              <Command.List className="max-h-64 overflow-y-auto p-2 space-y-0.5">
                <Command.Group
                  heading={
                    <span className="text-[9px] text-fg/66 uppercase tracking-wide px-2 py-1">
                      Navigate
                    </span>
                  }
                >
                  {NAV_ITEMS.map((item) => (
                    <Command.Item
                      key={item.id}
                      value={`nav:${item.id}`}
                      keywords={[item.label]}
                      onSelect={handleSelect}
                      className="flex items-center gap-3 px-2 py-2 text-[12px] text-fg/80 rounded-lg cursor-pointer aria-selected:bg-fg/[0.04] aria-selected:text-fg/92 transition-colors"
                    >
                      <span className="text-signal/60 text-[11px]">
                        {item.icon}
                      </span>
                      <span>{item.label}</span>
                    </Command.Item>
                  ))}
                </Command.Group>
                <Command.Group
                  heading={
                    <span className="text-[9px] text-fg/66 uppercase tracking-wide px-2 py-1 pt-3">
                      Example Queries
                    </span>
                  }
                >
                  {EXAMPLE_QUERIES.map((item) => (
                    <Command.Item
                      key={item.query}
                      value={`query:${item.query}`}
                      onSelect={handleSelect}
                      className="flex items-center gap-3 px-2 py-2 text-[12px] text-fg/80 rounded-lg cursor-pointer aria-selected:bg-fg/[0.04] aria-selected:text-fg/92 transition-colors"
                    >
                      <span className="text-fg/66 text-[10px]">\u2318</span>
                      <span>{item.label}</span>
                      <span className="ml-auto text-fg/66 text-[10px] truncate max-w-[180px]">
                        {item.query}
                      </span>
                    </Command.Item>
                  ))}
                </Command.Group>
                <Command.Empty className="px-2 py-4 text-[12px] text-fg/70 text-center">
                  No results found.
                </Command.Empty>
              </Command.List>
              <div className="border-t border-fg/[0.08] px-4 py-2 text-[10px] text-fg/66 flex items-center gap-3">
                <span>
                  <kbd className="text-fg/70">{"\u2191\u2193"}</kbd> navigate
                </span>
                <span>
                  <kbd className="text-fg/70">{"\u21B5"}</kbd> select
                </span>
                <span>
                  <kbd className="text-fg/70">esc</kbd> close
                </span>
              </div>
            </Command>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
