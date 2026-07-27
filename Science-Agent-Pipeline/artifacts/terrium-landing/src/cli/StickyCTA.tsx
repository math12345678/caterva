import { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import Magnetic from '@/components/ui/Magnetic';

const DISMISS_KEY = 'terrium:sticky-cta-dismissed';

export default function StickyCTA() {
  const [visible, setVisible] = useState(false);
  const [dismissed, setDismissed] = useState(() => {
    try {
      const raw = sessionStorage.getItem(DISMISS_KEY);
      if (!raw) return false;
      // Dismissal expires after 30 minutes
      const expiry = Number(raw);
      return Date.now() < expiry;
    } catch {
      return false;
    }
  });

  const handleDismiss = () => {
    setVisible(false);
    setDismissed(true);
    try {
      // Re-show after 30 minutes
      sessionStorage.setItem(DISMISS_KEY, String(Date.now() + 30 * 60 * 1000));
    } catch {
      // sessionStorage unavailable
    }
  };

  useEffect(() => {
    let lastY = 0;
    let ticking = false;

    const onScroll = () => {
      if (!ticking) {
        requestAnimationFrame(() => {
          const currentY = window.scrollY;
          const docHeight = document.documentElement.scrollHeight;
          const winHeight = window.innerHeight;
          const scrolledPast = currentY > winHeight * 0.6;
          const nearBottom = currentY + winHeight > docHeight - 200;
          const scrollingUp = currentY < lastY;

          // Show when scrolled past hero AND scrolling up, OR near bottom
          // Hide when reaching waitlist section
          const waitlistEl = document.getElementById('waitlist');
          const waitlistInView = waitlistEl
            ? waitlistEl.getBoundingClientRect().top < winHeight * 0.5
            : false;

          setVisible(
            !dismissed && !waitlistInView && (scrolledPast || nearBottom),
          );

          lastY = currentY;
          ticking = false;
        });
        ticking = true;
      }
    };

    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, [dismissed]);

  return (
    <AnimatePresence>
      {visible && (
        <motion.div
          initial={{ y: '100%', opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          exit={{ y: '100%', opacity: 0 }}
          transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
          className="sticky-cta"
        >
          <div className="max-w-3xl mx-auto flex items-center justify-between gap-4 cta-inner">
            <div className="flex items-center gap-3">
              <div className="hidden sm:flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-[#1D8A72] animate-pulse" />
                <span className="text-[13px] text-white/70 font-medium">
                  Ready to try scientific simulation?
                </span>
              </div>
              <span className="text-[11px] text-white/30 hidden md:inline">
                Pre-launch — pilot spots available
              </span>
            </div>

            <div className="flex items-center gap-2">
              <Magnetic strength={0.1}>
                <a
                  href="#waitlist"
                  className="inline-flex items-center gap-2 rounded-lg border border-[#1D8A72]/30 bg-[#1D8A72]/[0.08] px-4 py-2 text-[12px] text-[#1D8A72] font-medium transition-all duration-300 hover:bg-[#1D8A72]/[0.14] hover:shadow-[0_0_25px_rgba(29,138,114,0.15)]"
                >
                  Join waitlist
                  <svg className="w-3 h-3" viewBox="0 0 12 12" fill="none">
                    <path d="M2 6h7M6 2l4 4-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                </a>
              </Magnetic>

              <button
                onClick={handleDismiss}
                className="p-1.5 rounded-md text-white/20 hover:text-white/40 transition-colors"
                aria-label="Dismiss"
              >
                <svg className="w-3.5 h-3.5" viewBox="0 0 14 14" fill="none">
                  <path d="M3 3l8 8M11 3l-8 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                </svg>
              </button>
            </div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
