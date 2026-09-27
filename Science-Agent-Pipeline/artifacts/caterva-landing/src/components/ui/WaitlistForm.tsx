import React, { useState, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { TEAL } from "@/lib/constants";
import Magnetic from "@/components/ui/Magnetic";

function CheckIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
      <motion.path
        d="M3 8.5L6.5 12L13 4"
        stroke={TEAL}
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        initial={{ pathLength: 0 }}
        animate={{ pathLength: 1 }}
        transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
      />
    </svg>
  );
}

function LoadingDots() {
  return (
    <span className="flex items-center gap-0.5">
      {[0, 1, 2].map((i) => (
        <motion.span
          key={i}
          className="w-1 h-1 rounded-full bg-white inline-block"
          animate={{ opacity: [0.2, 1, 0.2] }}
          transition={{ duration: 1, repeat: Infinity, delay: i * 0.2 }}
        />
      ))}
    </span>
  );
}

export const WaitlistForm: React.FC<{
  large?: boolean;
  className?: string;
}> = ({ large, className = "" }) => {
  const [val, setVal] = useState("");
  const [sent, setSent] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [shaking, setShaking] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const validate = (v: string) => {
    if (!v.trim()) return "Email is required";
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v)) return "Invalid email";
    return "";
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const err = validate(val);
    if (err) {
      setError(err);
      setShaking(true);
      setTimeout(() => setShaking(false), 400);
      inputRef.current?.focus();
      return;
    }
    setError("");
    setLoading(true);
    try {
      const response = await fetch("/api/waitlist", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: val.trim() }),
      });
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.message || "Signup failed");
      }
      setSent(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  };

  return (
    <AnimatePresence mode="wait">
      {sent ? (
        <motion.div
          key="success"
          initial={{ opacity: 0, scale: 0.92, y: 8 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.92 }}
          transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
          className={className}
        >
          <div className="rounded-lg border border-[#1D8A72]/15 bg-[#1D8A72]/[0.02] p-5 flex items-center gap-4">
            <div className="w-10 h-10 rounded-full flex items-center justify-center shrink-0 bg-[#1D8A72]/10">
              <CheckIcon />
            </div>
            <div>
              <p className="font-sans text-[14px] text-white/80 font-medium">
                You&apos;re on the list.
              </p>
              <p className="text-[12px] text-white/30 mt-0.5">
                We&apos;ll notify you when your spot is ready. Typically 1–2
                weeks.
              </p>
            </div>
          </div>
        </motion.div>
      ) : (
        <motion.form
          key="form"
          onSubmit={handleSubmit}
          className={`flex flex-col sm:flex-row gap-3 ${className}`}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
        >
          <div className="flex-1 relative">
            <motion.input
              ref={inputRef}
              type="email"
              value={val}
              onChange={(e) => {
                setVal(e.target.value);
                if (error) setError("");
              }}
              placeholder="Enter your email"
              aria-label="Email address"
              aria-describedby={
                error ? "waitlist-error waitlist-privacy" : "waitlist-privacy"
              }
              disabled={loading}
              className={`w-full rounded-lg border bg-white/[0.02] px-4 py-3 text-[13px] font-mono text-white/80 outline-none placeholder:text-white/15 transition-all duration-200 ${
                error ? "border-red-500/30" : "border-white/[0.06]"
              }`}
              animate={shaking ? { x: [0, -6, 6, -4, 4, 0] } : { x: 0 }}
              transition={{ duration: 0.35 }}
            />
            <AnimatePresence>
              {error && (
                <motion.p
                  id="waitlist-error"
                  role="alert"
                  className="absolute -bottom-5 left-0 text-[8px] text-red-400/60 tracking-wide"
                  initial={{ opacity: 0, y: -4 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -2 }}
                >
                  {error}
                </motion.p>
              )}
            </AnimatePresence>
          </div>

          <Magnetic strength={0.15}>
            <motion.button
              type="submit"
              disabled={loading}
              className={`rounded-lg border border-[#1D8A72]/20 px-6 py-3 text-[11px] font-mono tracking-[0.15em] uppercase text-white bg-[#1D8A72]/90 hover:bg-[#1D8A72] transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed ${
                large ? "px-8 py-4 text-[12px]" : ""
              }`}
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.97 }}
            >
              {loading ? <LoadingDots /> : "Join Waitlist"}
            </motion.button>
          </Magnetic>

          {/*
            The notice has to be HERE, beside the field, not only in a
            document somebody would have to go looking for. Transparency
            about personal data attaches at the moment of collection, and
            this form collected an email address with no statement of any
            kind -- not who takes it, not why, not how to get it back.

            Deliberately specific rather than reassuring. "We respect your
            privacy" says nothing; "stored in a file on our server, no
            mailing service, email us to have it deleted" is checkable, and
            every clause of it was read out of src/routes/waitlist.ts.

            `aria-describedby` on the input points here, so a screen reader
            reaches the notice before the field is filled rather than after.
          */}
          <p
            id="waitlist-privacy"
            className="mt-3 text-[10px] leading-relaxed text-white/30 font-mono"
          >
            Your email is stored on our own server so we can tell you when
            Caterva is ready. Not shared, not sold, no mailing list, no
            tracking. Email{" "}
            <a
              href="mailto:admin.terrium@gmail.com"
              className="underline hover:text-white/50"
            >
              admin.terrium@gmail.com
            </a>{" "}
            to have it removed. What we collect and what we do not:{" "}
            <a
              href="https://github.com/math12345678/caterva/blob/main/docs/PRIVACY.md"
              className="underline hover:text-white/50"
              target="_blank"
              rel="noreferrer"
            >
              docs/PRIVACY.md
            </a>
            .
          </p>
        </motion.form>
      )}
    </AnimatePresence>
  );
};
