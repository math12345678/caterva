import { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

const API_BASE = import.meta.env.VITE_API_URL || '';

export default function WaitlistCounter() {
  const [count, setCount] = useState<number | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    const ctrl = new AbortController();
    fetch(`${API_BASE}/api/waitlist/count`, { signal: ctrl.signal })
      .then((r) => {
        if (!r.ok) throw new Error('Failed');
        return r.json();
      })
      .then((d) => setCount(d.count ?? 0))
      .catch(() => setError(true));
    return () => ctrl.abort();
  }, []);

  if (error || count === null || count === 0) return null;

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1], delay: 0.2 }}
        className="flex items-center gap-3 text-white/25"
      >
        <div className="flex items-center -space-x-2">
          {[0, 1, 2].map((i) => (
            <span
              key={i}
              className="inline-flex items-center justify-center w-6 h-6 rounded-full border border-white/[0.08] bg-[#1D8A72]/10 text-[9px] text-[#1D8A72] font-medium"
              style={{ zIndex: 3 - i }}
            >
              {String.fromCharCode(65 + i)}
            </span>
          ))}
        </div>
        <span className="text-[11px]">
          <span className="text-[#1D8A72] font-medium">{count}</span> researcher{count !== 1 ? 's' : ''} already joined
        </span>
      </motion.div>
    </AnimatePresence>
  );
}
