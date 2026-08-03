import { useState, useEffect, useRef } from "react";
import { motion } from "framer-motion";

const NAV_ITEMS = [
  { id: "how", label: "How", icon: "⌂" },
  { id: "examples", label: "Demo", icon: "◉" },
  { id: "agent", label: "Agent", icon: "⚡" },
  { id: "simulate", label: "Sim", icon: "⟐" },
  { id: "pricing", label: "Plans", icon: "◆" },
];

export default function MobileBottomNav() {
  const [active, setActive] = useState("");
  const [hidden, setHidden] = useState(false);
  const lastScrollYRef = useRef(0);

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) setActive(entry.target.id);
        }
      },
      { threshold: 0.3, rootMargin: "0px 0px -40px 0px" },
    );
    NAV_ITEMS.forEach(({ id }) => {
      const el = document.getElementById(id);
      if (el) observer.observe(el);
    });
    return () => observer.disconnect();
  }, []);

  // Hide on fast scroll down, show on scroll up
  useEffect(() => {
    let ticking = false;
    const onScroll = () => {
      if (!ticking) {
        requestAnimationFrame(() => {
          const currentY = window.scrollY;
          const prev = lastScrollYRef.current;
          if (currentY > prev + 20 && currentY > 400) {
            setHidden(true);
          } else if (prev - currentY > 10) {
            setHidden(false);
          }
          lastScrollYRef.current = currentY;
          ticking = false;
        });
        ticking = true;
      }
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <motion.nav
      initial={{ y: 100 }}
      animate={{ y: hidden ? 100 : 0 }}
      transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
      className="md:hidden fixed bottom-0 left-0 right-0 z-30 border-t border-white/[0.04] bg-[#050807]/95 backdrop-blur-xl safe-area-bottom"
      role="navigation"
      aria-label="Mobile quick navigation"
    >
      <div className="flex items-center justify-around h-14 max-w-lg mx-auto">
        {NAV_ITEMS.map((item) => {
          const isActive = active === item.id;
          return (
            <a
              key={item.id}
              href={`#${item.id}`}
              className={`flex flex-col items-center justify-center gap-0.5 min-w-0 px-2 py-1 rounded-lg transition-all duration-300 ${
                isActive
                  ? "text-[#1D8A72]"
                  : "text-white/25 hover:text-white/50"
              }`}
              aria-current={isActive ? "true" : undefined}
            >
              <span className="text-[15px] leading-none">{item.icon}</span>
              <span className="text-[9px] uppercase tracking-wider leading-none">
                {item.label}
              </span>
              {isActive && (
                <motion.span
                  layoutId="mobile-nav-active"
                  className="absolute -top-px h-[2px] w-8 rounded-full bg-[#1D8A72]"
                  transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
                />
              )}
            </a>
          );
        })}
      </div>
    </motion.nav>
  );
}
