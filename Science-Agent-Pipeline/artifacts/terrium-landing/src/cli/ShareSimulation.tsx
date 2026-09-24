import { useState, useMemo, useRef, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { toast } from "@/hooks/use-toast";
import { TEAL } from "@/lib/constants";

interface ShareSimulationProps {
  query: string;
  domain: string;
  runId?: string;
  parameters?: Record<string, unknown>;
  citationCount?: number;
  hasFlags?: boolean;
  className?: string;
}

function ShareIcon() {
  return (
    <svg className="w-3.5 h-3.5" viewBox="0 0 14 14" fill="none">
      <path
        d="M10 5l-6 4M10 5L5 2.5M10 5l-5 6.5M10 5l4-1.5v4"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function CopyIcon() {
  return (
    <svg className="w-3 h-3" viewBox="0 0 12 12" fill="none">
      <rect
        x="1"
        y="1"
        width="7"
        height="9"
        rx="1"
        stroke="currentColor"
        strokeWidth="1.2"
      />
      <path
        d="M4 1h6v7"
        stroke="currentColor"
        strokeWidth="1.2"
        strokeLinecap="round"
      />
    </svg>
  );
}

function CheckIcon() {
  return (
    <motion.svg
      width="14"
      height="14"
      viewBox="0 0 14 14"
      fill="none"
      initial={{ scale: 0 }}
      animate={{ scale: 1 }}
      transition={{ type: "spring", stiffness: 400, damping: 20 }}
    >
      <motion.path
        d="M2.5 7L5.5 10L11.5 4"
        stroke={TEAL}
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        initial={{ pathLength: 0 }}
        animate={{ pathLength: 1 }}
        transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
      />
    </motion.svg>
  );
}

function TwitterIcon() {
  return (
    <svg className="w-3 h-3" viewBox="0 0 14 14" fill="currentColor">
      <path d="M11.3 1.5h2L8.9 6.2l5 6.3H9.8L6.7 8.7l-3.4 3.8H1.3l4.7-5.1-4.9-6.2h4.2l2.8 3.5 3.2-3.5zm-.7 10.6h1.1L4.6 2.6H3.4l7.2 9.5z" />
    </svg>
  );
}

function LinkedInIcon() {
  return (
    <svg className="w-3 h-3" viewBox="0 0 14 14" fill="currentColor">
      <path d="M3.5 4.5h-2v7h2v-7zm-1-1.5a1.2 1.2 0 110-2.4 1.2 1.2 0 010 2.4zm8.5 3.5c0-1.5-.5-3-2.2-3-1 0-1.5.5-1.8 1h-.1V4.5H5v7h2V7.8c0-.8.2-1.6 1.2-1.6s1 .8 1 1.7v3.6h2V6.5z" />
    </svg>
  );
}

export default function ShareSimulation({
  query,
  domain,
  citationCount = 0,
  hasFlags = false,
  className = "",
}: ShareSimulationProps) {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const [copiedEmbed, setCopiedEmbed] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const showToast = (message: string) => {
    toast({
      title: message,
      duration: 2000,
    });
  };

  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    const handleClickOutside = (e: MouseEvent) => {
      if (
        containerRef.current &&
        !containerRef.current.contains(e.target as Node)
      ) {
        setOpen(false);
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    document.addEventListener("mousedown", handleClickOutside);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [open]);

  const { shareUrl, shareText, embedMarkdown } = useMemo(() => {
    // No route in the app reads q/domain/run/params back from location.search,
    // so a query string here would just be a dead link to the plain homepage.
    const url = `${window.location.origin}${window.location.pathname}`;

    // Only claim literature-verified provenance when the run actually has
    // citations and no unresolved caveats — matches the gating AgentSimulator
    // uses to show the provenance flags/citations panel.
    const isVerified = citationCount > 0 && !hasFlags;
    const provenanceClaim = isVerified
      ? "Verified ODE results with full provenance."
      : "Simulation run on Terrium.";
    const embedProvenanceClaim = isVerified
      ? "verified scientific simulations with full provenance"
      : "scientific simulations";

    const text = `I just ran a ${domain} simulation on Terrium: "${query}". ${provenanceClaim} ${url}`;

    const embed = `[![Terrium Simulation](https://terrium.app/og.png)](https://terrium.app)\n\n**${domain} simulation**: ${query}\n\n> Run on [Terrium](https://terrium.app) — ${embedProvenanceClaim}.`;

    return { shareUrl: url, shareText: text, embedMarkdown: embed };
  }, [query, domain, citationCount, hasFlags]);

  const handleCopy = () => {
    navigator.clipboard
      .writeText(shareText)
      .then(() => {
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
        showToast("Link copied to clipboard");
      })
      .catch(() => {
        showToast("Failed to copy link");
      });
  };

  const handleCopyEmbed = () => {
    navigator.clipboard
      .writeText(embedMarkdown)
      .then(() => {
        setCopiedEmbed(true);
        setTimeout(() => setCopiedEmbed(false), 2000);
        showToast("Embed code copied");
      })
      .catch(() => {
        showToast("Failed to copy embed code");
      });
  };

  const handleTwitter = () => {
    const url = `https://twitter.com/intent/tweet?text=${encodeURIComponent(shareText)}`;
    window.open(url, "_blank", "noopener,noreferrer,width=600,height=400");
  };

  const handleLinkedIn = () => {
    const url = `https://www.linkedin.com/sharing/share-offsite/?url=${encodeURIComponent(shareUrl)}`;
    window.open(url, "_blank", "noopener,noreferrer,width=600,height=500");
  };

  return (
    <div
      ref={containerRef}
      className={`relative inline-flex items-center ${className}`}
    >
      <motion.button
        onClick={() => setOpen(!open)}
        className="inline-flex items-center gap-1.5 rounded-lg border border-white/[0.08] bg-white/[0.02] px-3 py-1.5 text-[11px] text-white/40 hover:text-[#1D8A72] hover:border-[#1D8A72]/25 hover:bg-[#1D8A72]/[0.04] transition-all duration-300"
        whileHover={{ scale: 1.02 }}
        whileTap={{ scale: 0.97 }}
        aria-label="Share simulation"
        aria-expanded={open}
      >
        <ShareIcon />
        <span className="hidden sm:inline">share</span>
      </motion.button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: 8, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 8, scale: 0.95 }}
            transition={{ duration: 0.25, ease: [0.22, 1, 0.36, 1] }}
            className="absolute right-0 top-full mt-2 w-72 rounded-xl border border-white/[0.08] bg-[#0d1311] p-4 shadow-2xl z-50 backdrop-blur-xl"
          >
            <div className="flex items-center justify-between mb-3">
              <span className="text-[11px] text-white/50 font-medium">
                Share this simulation
              </span>
              <button
                onClick={() => setOpen(false)}
                className="text-white/20 hover:text-white/50 transition-colors p-2.5 -m-2.5"
                aria-label="Close share panel"
              >
                <svg className="w-3 h-3" viewBox="0 0 12 12" fill="none">
                  <path
                    d="M3 3l6 6M9 3l-6 6"
                    stroke="currentColor"
                    strokeWidth="1.5"
                    strokeLinecap="round"
                  />
                </svg>
              </button>
            </div>

            {/* Copy link */}
            <div className="flex items-center gap-2 mb-2">
              <motion.button
                onClick={handleCopy}
                className="flex-1 flex items-center justify-center gap-1.5 rounded-lg border border-[#1D8A72]/20 bg-[#1D8A72]/[0.06] py-2 text-[11px] text-[#1D8A72] transition-all duration-200 hover:bg-[#1D8A72]/[0.10]"
                whileHover={{ scale: 1.01 }}
                whileTap={{ scale: 0.98 }}
              >
                {copied ? <CheckIcon /> : <CopyIcon />}
                {copied ? "Copied!" : "Copy link"}
              </motion.button>
            </div>

            {/* Social buttons */}
            <div className="flex gap-2 mb-3">
              <motion.button
                onClick={handleTwitter}
                className="flex-1 flex items-center justify-center gap-1.5 rounded-lg border border-white/[0.08] bg-white/[0.02] py-2 text-[11px] text-white/40 hover:text-white/70 hover:border-white/[0.15] transition-all duration-200"
                whileHover={{ scale: 1.01 }}
                whileTap={{ scale: 0.98 }}
              >
                <TwitterIcon />
                <span className="hidden sm:inline">Tweet</span>
              </motion.button>
              <motion.button
                onClick={handleLinkedIn}
                className="flex-1 flex items-center justify-center gap-1.5 rounded-lg border border-white/[0.08] bg-white/[0.02] py-2 text-[11px] text-white/40 hover:text-white/70 hover:border-white/[0.15] transition-all duration-200"
                whileHover={{ scale: 1.01 }}
                whileTap={{ scale: 0.98 }}
              >
                <LinkedInIcon />
                <span className="hidden sm:inline">Post</span>
              </motion.button>
            </div>

            {/* Embed code */}
            <div className="border-t border-white/[0.04] pt-3">
              <div className="flex items-center justify-between mb-1.5">
                <span className="text-[10px] text-white/25 uppercase tracking-wide">
                  embed markdown
                </span>
                <motion.button
                  onClick={handleCopyEmbed}
                  className="text-[10px] text-white/25 hover:text-[#1D8A72] transition-colors flex items-center gap-1"
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.97 }}
                >
                  {copiedEmbed ? <CheckIcon /> : <CopyIcon />}
                  {copiedEmbed ? "copied" : "copy"}
                </motion.button>
              </div>
              <pre className="text-[10px] text-white/30 font-mono leading-relaxed bg-white/[0.02] rounded-lg p-2 overflow-x-auto max-h-24">
                {embedMarkdown}
              </pre>
            </div>

            {/* URL preview */}
            <div className="mt-3 text-[10px] text-white/20 truncate border-t border-white/[0.04] pt-2">
              <span className="text-white/15">url: </span>
              {shareUrl}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
