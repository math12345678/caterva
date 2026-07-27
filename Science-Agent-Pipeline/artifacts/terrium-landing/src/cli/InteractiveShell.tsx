import { useEffect, useRef, useState, type ReactNode } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { totals } from '@/lib/testResults';

interface ShellLine {
  kind: 'input' | 'output';
  content: ReactNode;
}

interface InteractiveShellProps {
  onNavigate: (sectionId: string) => void;
  onSimulate: (domain: 'mm' | 'sir') => void;
}

const COMMANDS = [
  'help', 'about', 'domains', 'test', 'simulate', 'waitlist', 'whoami', 'ls', 'clear',
  'history', 'theme', 'status', 'export', 'cite', 'pricing', 'version',
  'glossary', 'playground', 'testimonials', 'compare',
];

function AboutOutput() {
  return (
    <div className="text-white/60 leading-relaxed">
      Scientific computing for teaching labs. A student asks a question in plain
      language; Terrium resolves the real parameters from the literature, runs the
      simulation, and shows its work — every number traceable to a citation.
    </div>
  );
}

function HelpOutput() {
  const rows: [string, string][] = [
    ['about', 'what terrium is'],
    ['domains', 'list simulation domains, live and planned'],
    ['test', 'jump to the real test suite results'],
    ['simulate [mm|sir]', 'jump to the live interactive simulator'],
    ['waitlist', 'join the waitlist'],
    ['pricing', 'view pricing plans'],
    ['cite', 'how to cite terrium in your work'],
    ['whoami', 'who built this'],
    ['history', 'show command history'],
    ['status', 'show pipeline service status'],
    ['version', 'show version info'],
    ['export', 'list supported export formats'],
    ['glossary', 'open the key terms and definitions reference'],
    ['playground', 'open the interactive kinetics & epidemiology demo'],
    ['testimonials', 'see what researchers are saying'],
    ['compare', 'compare traditional vs terrium workflow'],
    ['theme', 'show current theme'],
    ['ls', 'list this page as a filesystem'],
    ['clear', 'clear the terminal'],
  ];
  return (
    <div className="space-y-0.5">
      {rows.map(([cmd, desc]) => (
        <div key={cmd} className="flex gap-3">
          <span className="text-[#1D8A72] w-36 shrink-0">{cmd}</span>
          <span className="text-white/40">{desc}</span>
        </div>
      ))}
    </div>
  );
}

function DomainsOutput() {
  const domains = [
    ['enzyme-kinetics', 'live'],
    ['sir-seir-epidemiology', 'live'],
    ['pcr-amplification', 'planned'],
    ['monte-carlo', 'planned'],
    ['population-genetics', 'planned'],
    ['molecular-dynamics-setup', 'planned'],
  ];
  return (
    <div className="space-y-0.5">
      {domains.map(([name, status]) => (
        <div key={name} className="flex gap-3">
          <span
            className={status === 'live' ? 'text-[#1D8A72] w-36 shrink-0' : 'text-white/40 w-36 shrink-0'}
          >
            {name}
          </span>
          <span className="text-white/25 uppercase text-[9px] mt-0.5">{status}</span>
        </div>
      ))}
    </div>
  );
}

function Line({ line }: { line: ShellLine }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: -4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.15, ease: 'easeOut' }}
    >
      {line.kind === 'input' ? (
        <div className="flex gap-2">
          <span className="text-[#1D8A72] select-none" aria-hidden="true">$</span>
          <span className="text-white/80">{line.content}</span>
        </div>
      ) : (
        <div className="pl-4 text-[12px]">{line.content}</div>
      )}
    </motion.div>
  );
}

function VersionOutput() {
  return (
    <div className="space-y-0.5">
      <div className="flex gap-3">
        <span className="text-[#1D8A72] w-24 shrink-0">terrium-landing</span>
        <span className="text-white/40">v2.0.0 (pre-launch)</span>
      </div>
      <div className="flex gap-3">
        <span className="text-[#1D8A72] w-24 shrink-0">tellurium-engine</span>
        <span className="text-white/40">v1.0.0</span>
      </div>
      <div className="flex gap-3">
        <span className="text-[#1D8A72] w-24 shrink-0">react</span>
        <span className="text-white/40">v19</span>
      </div>
      <div className="flex gap-3">
        <span className="text-[#1D8A72] w-24 shrink-0">ode-solver</span>
        <span className="text-white/40">rk4 (adaptive)</span>
      </div>
    </div>
  );
}

function StatusOutput() {
  return (
    <div className="space-y-1">
      <div className="flex items-center gap-2 text-[#1D8A72]">
        <span className="w-1.5 h-1.5 rounded-full bg-[#1D8A72] animate-pulse" />
        <span>pipeline: operational</span>
      </div>
      <div className="flex items-center gap-2 text-white/40">
        <span className="w-1.5 h-1.5 rounded-full bg-[#1D8A72]/40" />
        <span>llm-resolver: connected</span>
      </div>
      <div className="flex items-center gap-2 text-white/40">
        <span className="w-1.5 h-1.5 rounded-full bg-[#1D8A72]/40" />
        <span>brenda-kegg: indexed</span>
      </div>
      <div className="flex items-center gap-2 text-white/40">
        <span className="w-1.5 h-1.5 rounded-full bg-yellow-500/40" />
        <span>pubmed: rate-limited</span>
      </div>
    </div>
  );
}

export default function InteractiveShell({ onNavigate, onSimulate }: InteractiveShellProps) {
  const [lines, setLines] = useState<ShellLine[]>([
    { kind: 'output', content: <span className="text-white/35">Terrium shell — type <span className="text-[#1D8A72]">help</span> to get started.</span> },
  ]);
  const [value, setValue] = useState('');
  const [history, setHistory] = useState<string[]>([]);
  const [historyIdx, setHistoryIdx] = useState<number | null>(null);
  const [showHints, setShowHints] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [lines]);

  const push = (kind: ShellLine['kind'], content: ReactNode) => setLines((l) => [...l, { kind, content }]);

  const run = (raw: string) => {
    const cmd = raw.trim();
    push('input', cmd);
    if (!cmd) return;

    const [head, ...rest] = cmd.split(/\s+/);

    switch (head.toLowerCase()) {
      case 'help':
        push('output', <HelpOutput />);
        break;
      case 'about':
        push('output', <AboutOutput />);
        break;
      case 'domains':
        push('output', <DomainsOutput />);
        break;
      case 'test': {
        const { passed, skipped, failed, total } = totals();
        push('output', (
          <span>
            <span className="text-[#1D8A72]">{passed} passed</span>
            {skipped > 0 && <span className="text-yellow-500/70">, {skipped} skipped</span>}
            <span className="text-white/40">, {failed} failed, {total} total</span>
            <span className="text-white/25"> — scrolling to full report...</span>
          </span>
        ));
        onNavigate('tests');
        break;
      }
      case 'simulate': {
        const domain = rest[0]?.toLowerCase() === 'sir' ? 'sir' : 'mm';
        push('output', <span className="text-white/40">opening the live simulator ({domain})...</span>);
        onSimulate(domain);
        onNavigate('simulate');
        break;
      }
      case 'waitlist':
        push('output', <span className="text-white/40">scrolling to the waitlist...</span>);
        onNavigate('waitlist');
        break;
      case 'whoami':
        push('output', (
          <span className="text-white/40">
            you&apos;re looking at a project built by <span className="text-[#1D8A72]">Smyan Reddy</span> and
            a small team, pre-launch, aiming for real classroom pilots.
          </span>
        ));
        break;
      case 'ls':
        push('output', (
          <div className="text-white/40">
            about.md&nbsp;&nbsp;domains.txt&nbsp;&nbsp;tests.log&nbsp;&nbsp;simulate/&nbsp;&nbsp;waitlist.form
          </div>
        ));
        break;
      case 'cat':
        if (rest[0] === 'about.md') push('output', <AboutOutput />);
        else if (rest[0] === 'domains.txt') push('output', <DomainsOutput />);
        else push('output', <span className="text-red-400/60">cat: {rest[0] ?? '(missing operand)'}: no such file</span>);
        break;
      case 'clear':
        setLines([]);
        return;
      case 'history':
        push('output', (
          <div className="space-y-0.5 max-h-32 overflow-y-auto">
            {history.length === 0 ? (
              <span className="text-white/25 italic">no commands yet</span>
            ) : (
              history.map((cmd, i) => (
                <div key={i} className="flex gap-3 text-white/35">
                  <span className="text-white/15 w-6 shrink-0 text-right">{i + 1}</span>
                  <span>{cmd}</span>
                </div>
              ))
            )}
          </div>
        ));
        break;
      case 'theme':
        push('output', (
          <div className="space-y-0.5">
            <span className="text-white/40">current theme: <span className="text-[#1D8A72]">dark-teal</span></span>
            <span className="text-white/20 text-[10px]">Available: dark-teal (only theme in pre-launch)</span>
          </div>
        ));
        break;
      case 'status':
        push('output', <StatusOutput />);
        break;
      case 'version':
        push('output', <VersionOutput />);
        break;
      case 'export':
        push('output', (
          <span className="text-white/40">
            export formats: <span className="text-[#1D8A72]">csv</span>,{' '}
            <span className="text-[#1D8A72]">json</span>,{' '}
            <span className="text-[#1D8A72]">sbml</span>. Use the export buttons in simulation results.
          </span>
        ));
        break;
      case 'cite':
        push('output', <span className="text-white/40">scroll to the citation section for BibTeX &amp; APA templates...</span>);
        onNavigate('cite');
        break;
      case 'pricing':
        push('output', <span className="text-white/40">opening pricing plans...</span>);
        onNavigate('pricing');
        break;
      case 'glossary':
        push('output', <span className="text-white/40">opening the key terms glossary...</span>);
        onNavigate('glossary');
        break;
      case 'playground':
        push('output', <span className="text-white/40">opening the interactive playground...</span>);
        onNavigate('playground');
        break;
      case 'testimonials':
        push('output', <span className="text-white/40">scrolling to researcher testimonials...</span>);
        onNavigate('testimonials');
        break;
      case 'compare':
        push('output', <span className="text-white/40">opening the workflow comparison...</span>);
        onNavigate('compare');
        break;
      case 'sudo':
        push('output', <span className="text-red-400/60">Nice try. This is a student project, not a shell into prod.</span>);
        break;
      default:
        push('output', (
          <span className="text-red-400/60">
            command not found: {head} <span className="text-white/20">(try `help`)</span>
          </span>
        ));
    }
  };

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    run(value);
    setHistory((h) => (value.trim() ? [...h, value] : h));
    setHistoryIdx(null);
    setValue('');
    setShowHints(false);
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'ArrowUp') {
      e.preventDefault();
      if (history.length === 0) return;
      const nextIdx = historyIdx === null ? history.length - 1 : Math.max(0, historyIdx - 1);
      setHistoryIdx(nextIdx);
      setValue(history[nextIdx]);
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (historyIdx === null) return;
      const nextIdx = historyIdx + 1;
      if (nextIdx >= history.length) {
        setHistoryIdx(null);
        setValue('');
      } else {
        setHistoryIdx(nextIdx);
        setValue(history[nextIdx]);
      }
    } else if (e.key === 'Tab') {
      e.preventDefault();
      const match = COMMANDS.find((c) => c.startsWith(value.toLowerCase()) && value.length > 0);
      if (match) setValue(match);
    }
  };

  const matchedHints = value.trim().length > 0
    ? COMMANDS.filter((c) => c.startsWith(value.toLowerCase()) && c !== value.toLowerCase())
    : [];

  return (
    <div
      onClick={() => inputRef.current?.focus()}
      className="cursor-text h-64 md:h-72 overflow-y-auto pr-1 [scrollbar-width:thin] relative"
    >
      <div className="space-y-1.5">
        {lines.map((l, i) => (
          <Line key={i} line={l} />
        ))}
        <form onSubmit={onSubmit} className="flex items-center gap-2 pt-1 relative">
          <span className="text-[#1D8A72] select-none" aria-hidden="true">$</span>
          <div className="flex-1 relative">
            <input
              ref={inputRef}
              value={value}
              onChange={(e) => { setValue(e.target.value); setShowHints(true); }}
              onKeyDown={onKeyDown}
              onBlur={() => setTimeout(() => setShowHints(false), 150)}
              autoFocus
              spellCheck={false}
              autoComplete="off"
              className="w-full bg-transparent outline-none text-white/80 caret-[#1D8A72] placeholder:text-white/15"
              placeholder="try `help`"
            />
            {showHints && matchedHints.length > 0 && (
              <div className="absolute left-0 top-full mt-1 rounded-lg border border-white/[0.06] bg-[#0a0f0c] py-1 min-w-[120px] shadow-xl z-10">
                {matchedHints.slice(0, 5).map((hint) => (
                  <button
                    key={hint}
                    type="button"
                    onMouseDown={(e) => { e.preventDefault(); setValue(hint); inputRef.current?.focus(); }}
                    className="block w-full text-left px-3 py-1 text-[11px] text-white/50 hover:bg-white/[0.04] hover:text-white/80 transition-colors"
                  >
                    {hint}
                  </button>
                ))}
              </div>
            )}
          </div>
        </form>
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
