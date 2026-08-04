/**
 * Interactive command line.
 *
 * Real input, real history, tab completion, and output that streams in a
 * line at a time. Commands compute their answers when invoked — see
 * lib/terminal.ts. Typing `run md` runs a golden-section search in the
 * browser and prints what it found.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { execute, COMMAND_NAMES, type Line } from '../lib/terminal';
import { useInView, useReducedMotion } from '../lib/motion';

const BOOT: Line[] = [
  { kind: 'dim', text: 'terrium verification shell · v0.4.2-alpha' },
  { kind: 'dim', text: "type 'help' for commands, or try 'verify md'" },
];

const KIND_CLASS: Record<Line['kind'], string> = {
  out: 'text-ink',
  dim: 'text-faint',
  ok: 'text-verified',
  warn: 'text-flagged',
  err: 'text-rejected',
  cmd: 'text-verified',
  head: 'text-ink font-bold tracking-[0.14em]',
  rule: '',
};

export default function Terminal() {
  const [sectionRef, inView] = useInView<HTMLDivElement>();
  const reduced = useReducedMotion();

  const [lines, setLines] = useState<Line[]>(BOOT);
  const [queue, setQueue] = useState<Line[]>([]);
  const [input, setInput] = useState('');
  const [history, setHistory] = useState<string[]>([]);
  const [histIdx, setHistIdx] = useState(-1);
  const [busy, setBusy] = useState(false);
  // True while a command's `run()` promise (e.g. a real /api/simulate
  // round-trip for a literature-backed query) hasn't resolved yet. Kept
  // separate from `busy` because the queue-drain effect below clears `busy`
  // whenever the queue is empty -- which it always is before the network
  // response arrives -- and that would re-enable input mid-request.
  const [resolving, setResolving] = useState(false);
  const [hasRun, setHasRun] = useState(false);

  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Drain the queue one line at a time so output streams rather than
  // appearing as a block. Under reduced motion, flush immediately.
  useEffect(() => {
    if (queue.length === 0) {
      if (busy) setBusy(false);
      return;
    }
    if (reduced) {
      setLines((l) => [...l, ...queue]);
      setQueue([]);
      return;
    }
    const t = window.setTimeout(() => {
      setLines((l) => [...l, queue[0]]);
      setQueue((q) => q.slice(1));
    }, 14);
    return () => window.clearTimeout(t);
  }, [queue, reduced, busy]);

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [lines]);

  const submit = useCallback(
    (raw: string) => {
      const cmd = raw.trim();
      setLines((l) => [...l, { kind: 'cmd', text: `> ${cmd}` }]);
      setInput('');
      setHistIdx(-1);
      if (cmd) setHistory((h) => [cmd, ...h].slice(0, 60));

      // Real network round-trips (literature-resolved run commands) can take
      // real time, so this is genuinely async, not a synchronous compute
      // dressed as one.
      setResolving(true);
      void execute(cmd).then(({ lines: out, clear }) => {
        setResolving(false);
        if (clear) {
          setLines([]);
          return;
        }
        setBusy(true);
        setQueue(out);
      });
    },
    [],
  );

  // Run one command automatically the first time the section is seen, so a
  // visitor who never types still sees the shell do something real.
  useEffect(() => {
    if (!inView || hasRun) return;
    setHasRun(true);
    const t = window.setTimeout(() => submit('verify md'), reduced ? 0 : 700);
    return () => window.clearTimeout(t);
  }, [inView, hasRun, submit, reduced]);

  const onKey = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      if (!busy) submit(input);
      return;
    }
    if (e.key === 'Tab') {
      e.preventDefault();
      const head = input.trim().toLowerCase();
      if (!head.includes(' ')) {
        const hit = COMMAND_NAMES.find((c) => c.startsWith(head));
        if (hit) setInput(hit + ' ');
      }
      return;
    }
    if (e.key === 'ArrowUp') {
      e.preventDefault();
      const i = Math.min(histIdx + 1, history.length - 1);
      if (i >= 0) {
        setHistIdx(i);
        setInput(history[i]);
      }
      return;
    }
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      const i = histIdx - 1;
      setHistIdx(i);
      setInput(i < 0 ? '' : history[i]);
    }
  };

  const ghost = (() => {
    const head = input.trim().toLowerCase();
    if (!head || head.includes(' ')) return '';
    const hit = COMMAND_NAMES.find((c) => c.startsWith(head) && c !== head);
    return hit ? hit.slice(head.length) : '';
  })();

  return (
    <section ref={sectionRef} className="relative z-10 mx-auto max-w-[1080px] px-6 py-24">
      <div
        className="mb-5 transition-all duration-700"
        style={{
          opacity: inView ? 1 : 0,
          transform: inView ? 'none' : 'translateY(10px)',
        }}
      >
        <div className="font-mono text-[10px] tracking-[0.18em] text-faint">
          INTERACTIVE
        </div>
        <h2 className="mt-2 font-sans text-[22px] font-medium tracking-[-0.01em] text-ink">
          Ask it yourself.
        </h2>
        <p className="mt-1 max-w-[60ch] font-sans text-[14px] leading-relaxed text-dim">
          A real shell. Every command computes its answer in your browser when
          you press enter — nothing here is a stored transcript.
        </p>
      </div>

      <div
        className="overflow-hidden rounded-md border border-line bg-panel/85 backdrop-blur-sm transition-all duration-700"
        style={{
          opacity: inView ? 1 : 0,
          transform: inView ? 'none' : 'translateY(14px)',
          transitionDelay: '90ms',
          boxShadow: '0 0 0 1px rgba(110,231,183,0.04), 0 24px 70px -30px rgba(0,0,0,0.9)',
        }}
        onClick={() => inputRef.current?.focus()}
      >
        <div className="flex items-center gap-2 border-b border-line px-4 py-2.5">
          <span className="h-2 w-2 rounded-full bg-rejected/60" />
          <span className="h-2 w-2 rounded-full bg-flagged/60" />
          <span className="h-2 w-2 rounded-full bg-verified/60" />
          <span className="ml-2 font-mono text-[10px] tracking-[0.12em] text-faint">
            terrium@verification — shell
          </span>
        </div>

        <div
          ref={scrollRef}
          className="h-[400px] overflow-y-auto px-4 py-3 font-mono text-[12.5px] leading-[1.65]"
        >
          {lines.map((l, i) =>
            l.kind === 'rule' ? (
              <div key={i} className="my-1.5 h-px w-full bg-line" />
            ) : (
              <div
                key={i}
                className={`whitespace-pre-wrap ${KIND_CLASS[l.kind]}`}
                style={
                  reduced
                    ? undefined
                    : { animation: 'lineIn 220ms cubic-bezier(0.16,1,0.3,1) both' }
                }
              >
                {l.text || ' '}
              </div>
            ),
          )}

          <div className="flex items-center gap-2">
            <span className="text-verified">{'>'}</span>
            <div className="relative flex-1">
              <input
                ref={inputRef}
                value={input}
                disabled={busy || resolving}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={onKey}
                spellCheck={false}
                autoComplete="off"
                aria-label="terminal input"
                className="w-full bg-transparent font-mono text-[12.5px] text-ink caret-verified outline-none disabled:opacity-50"
              />
              {resolving && (
                <span className="ml-2 text-[11px] text-faint">resolving…</span>
              )}
              {ghost && (
                <span className="pointer-events-none absolute left-0 top-0 font-mono text-[12.5px] text-faint">
                  <span className="invisible">{input}</span>
                  {ghost}
                </span>
              )}
            </div>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-line px-4 py-2 font-mono text-[10px] text-faint">
          <span>tab completes</span>
          <span>↑↓ history</span>
          <span className="ml-auto flex gap-2">
            {['help', 'verify md', 'mutate popgen', 'ledger', 'agents'].map((c) => (
              <button
                key={c}
                onClick={(e) => {
                  e.stopPropagation();
                  if (!busy && !resolving) submit(c);
                }}
                className="rounded-sm border border-line px-2 py-0.5 text-verified/80 transition-colors hover:border-verified/40 hover:text-verified"
              >
                {c}
              </button>
            ))}
          </span>
        </div>
      </div>
    </section>
  );
}
