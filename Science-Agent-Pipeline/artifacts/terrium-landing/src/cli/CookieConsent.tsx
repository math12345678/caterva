import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

const STORAGE_KEY = 'terrium-cookie-consent';

export default function CookieConsent() {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) return;
    const timer = setTimeout(() => setVisible(true), 2000);
    return () => clearTimeout(timer);
  }, []);

  const dismiss = () => {
    setVisible(false);
    localStorage.setItem(STORAGE_KEY, 'dismissed');
  };

  return (
    <AnimatePresence>
      {visible && (
        <motion.div
          initial={{ y: 80, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          exit={{ y: 80, opacity: 0 }}
          transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
          className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 w-[calc(100%-2rem)] max-w-md"
        >
          <div className="rounded-xl border border-white/[0.08] bg-[#0A0E0C]/95 backdrop-blur-xl p-4 shadow-2xl shadow-black/40">
            <div className="flex items-start gap-3">
              <span className="text-[#F59E0B] text-[14px] shrink-0 mt-0.5">&#x1F36A;</span>
              <div className="flex-1 min-w-0">
                <p className="text-[11px] text-white/50 leading-relaxed mb-3">
                  We use essential cookies only — no tracking, no ads. Data sources (BRENDA, KEGG, PubMed) are queried server-side.
                </p>
                <div className="flex items-center gap-2">
                  <button
                    onClick={dismiss}
                    className="px-3 py-1.5 rounded-lg text-[11px] font-medium bg-[#1D8A72]/15 border border-[#1D8A72]/25 text-[#1D8A72] hover:bg-[#1D8A72]/25 transition-all"
                    aria-label="Accept cookies"
                  >
                    got it
                  </button>
                  <button
                    onClick={dismiss}
                    className="px-3 py-1.5 rounded-lg text-[11px] text-white/25 hover:text-white/45 transition-all"
                    aria-label="Dismiss cookie notice"
                  >
                    dismiss
                  </button>
                </div>
              </div>
            </div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
