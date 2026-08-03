import { useEffect, useState, useCallback } from "react";
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
    query: "model an outbreak with beta 0.4 and gamma 0.1",
    label: "SIR Outbreak",
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

  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (e.key === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setOpen((prev) => !prev);
      }
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", down);
    return () => document.removeEventListener("keydown", down);
  }, []);

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
            className="fixed inset-0 bg-black/60 backdrop-blur-sm"
            onClick={() => setOpen(false)}
          />
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: -10 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: -10 }}
            transition={{ duration: 0.15, ease: "easeOut" }}
            className="relative w-full max-w-lg rounded-xl border border-white/[0.08] bg-[#0a0f0c] shadow-2xl shadow-[#1D8A72]/[0.03] overflow-hidden glass-deep"
          >
            <Command label="Command palette">
              <Command.Input
                placeholder="Search sections or try an example query\u2026"
                className="w-full bg-transparent px-4 py-3.5 text-[13px] text-white/80 outline-none placeholder:text-white/20 border-b border-white/[0.04]"
                autoFocus
              />
              <Command.List className="max-h-64 overflow-y-auto p-2 space-y-0.5">
                <Command.Group
                  heading={
                    <span className="text-[9px] text-white/20 uppercase tracking-wide px-2 py-1">
                      Navigate
                    </span>
                  }
                >
                  {NAV_ITEMS.map((item) => (
                    <Command.Item
                      key={item.id}
                      value={`nav:${item.id}`}
                      onSelect={handleSelect}
                      className="flex items-center gap-3 px-2 py-2 text-[12px] text-white/60 rounded-lg cursor-pointer aria-selected:bg-white/[0.04] aria-selected:text-white/90 transition-colors"
                    >
                      <span className="text-[#1D8A72]/60 text-[11px]">
                        {item.icon}
                      </span>
                      <span>{item.label}</span>
                    </Command.Item>
                  ))}
                </Command.Group>
                <Command.Group
                  heading={
                    <span className="text-[9px] text-white/20 uppercase tracking-wide px-2 py-1 pt-3">
                      Example Queries
                    </span>
                  }
                >
                  {EXAMPLE_QUERIES.map((item) => (
                    <Command.Item
                      key={item.query}
                      value={`query:${item.query}`}
                      onSelect={handleSelect}
                      className="flex items-center gap-3 px-2 py-2 text-[12px] text-white/60 rounded-lg cursor-pointer aria-selected:bg-white/[0.04] aria-selected:text-white/90 transition-colors"
                    >
                      <span className="text-white/20 text-[10px]">\u2318</span>
                      <span>{item.label}</span>
                      <span className="ml-auto text-white/20 text-[10px] truncate max-w-[180px]">
                        {item.query}
                      </span>
                    </Command.Item>
                  ))}
                </Command.Group>
                <Command.Empty className="px-2 py-4 text-[12px] text-white/30 text-center">
                  No results found.
                </Command.Empty>
              </Command.List>
              <div className="border-t border-white/[0.04] px-4 py-2 text-[10px] text-white/20 flex items-center gap-3">
                <span>
                  <kbd className="text-white/40">{"\u2191\u2193"}</kbd> navigate
                </span>
                <span>
                  <kbd className="text-white/40">{"\u21B5"}</kbd> select
                </span>
                <span>
                  <kbd className="text-white/40">esc</kbd> close
                </span>
              </div>
            </Command>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
