import { useEffect, useState } from 'react';
import AmbientLattice from './components/AmbientLattice';
import Hero from './components/Hero';
import VerificationConsole from './components/VerificationConsole';
import Terminal from './components/Terminal';
import PipelineFlow from './components/PipelineFlow';
import { Ledger, Contract, Constitution, SelfAudit, Close } from './components/Sections';

function Nav() {
  const [solid, setSolid] = useState(false);
  useEffect(() => {
    const on = () => setSolid(window.scrollY > 40);
    on();
    window.addEventListener('scroll', on, { passive: true });
    return () => window.removeEventListener('scroll', on);
  }, []);

  return (
    <nav
      className="fixed inset-x-0 top-0 z-50 transition-all duration-500"
      style={{
        background: solid ? 'rgba(5,6,7,0.72)' : 'transparent',
        backdropFilter: solid ? 'blur(14px)' : 'none',
        borderBottom: `1px solid ${solid ? '#1A1E20' : 'transparent'}`,
      }}
    >
      <div className="mx-auto flex max-w-[1140px] items-center gap-4 px-6 py-3.5">
        <a href="#top" className="font-sans text-[14px] font-medium tracking-[-0.01em] text-ink">
          Caterva
        </a>
        <span className="hidden font-mono text-[10px] tracking-[0.16em] text-faint sm:inline">
          SCIENTIFIC VERIFICATION ENGINE
        </span>
        <div className="ml-auto flex items-center gap-5 font-mono text-[12px]">
          <a href="#shell" className="hidden text-dim transition-colors hover:text-ink sm:inline">
            Shell
          </a>
          <a href="#architecture" className="hidden text-dim transition-colors hover:text-ink sm:inline">
            Architecture
          </a>
          <a href="#ledger" className="hidden text-dim transition-colors hover:text-ink md:inline">
            Ledger
          </a>
          <a
            href="#request"
            className="rounded-md border border-verified/45 px-3 py-1.5 text-verified transition-all duration-300 hover:bg-verified/10"
          >
            Request access
          </a>
        </div>
      </div>
    </nav>
  );
}

/** Thin scroll indicator. One of the few purely decorative things here. */
function Progress() {
  const [p, setP] = useState(0);
  useEffect(() => {
    const on = () => {
      const max = document.body.scrollHeight - window.innerHeight;
      setP(max > 0 ? window.scrollY / max : 0);
    };
    on();
    window.addEventListener('scroll', on, { passive: true });
    window.addEventListener('resize', on);
    return () => {
      window.removeEventListener('scroll', on);
      window.removeEventListener('resize', on);
    };
  }, []);
  return (
    <div className="fixed inset-x-0 top-0 z-[60] h-px">
      <div
        className="h-full bg-verified/70 transition-[width] duration-150 ease-out"
        style={{ width: `${p * 100}%` }}
      />
    </div>
  );
}

function Divider() {
  return (
    <div className="relative z-10 mx-auto max-w-[1140px] px-6">
      <div className="h-px bg-gradient-to-r from-transparent via-line to-transparent" />
    </div>
  );
}

export default function App() {
  return (
    <div id="top" className="relative min-h-screen bg-void">
      <AmbientLattice />
      <Progress />
      <Nav />

      <main className="relative">
        <Hero />

        {/* The console is the product arguing for itself: real simulation,
            real closed form, a real bug you can inject. */}
        <section className="relative z-10 mx-auto max-w-[1400px] px-4 pb-6">
          <div
            className="overflow-hidden rounded-lg border border-line"
            style={{ boxShadow: '0 40px 120px -50px rgba(0,0,0,1)' }}
          >
            <div className="h-[720px]">
              <VerificationConsole />
            </div>
          </div>
        </section>

        <Divider />
        <div id="shell">
          <Terminal />
        </div>

        <Divider />
        <div id="architecture">
          <PipelineFlow />
        </div>

        <Divider />
        <Contract />

        <Divider />
        <div id="ledger">
          <Ledger />
        </div>

        <Divider />
        <Constitution />

        <Divider />
        <SelfAudit />

        <Close />
      </main>

      <footer className="relative z-10 border-t border-line">
        <div className="mx-auto flex max-w-[1140px] flex-wrap items-center gap-x-6 gap-y-2 px-6 py-7 font-mono text-[11px] text-faint">
          <span className="text-dim">Caterva</span>
          <span>scientific computing for teaching labs</span>
          <span className="ml-auto flex gap-5">
            <a href="#ledger" className="transition-colors hover:text-ink">Ledger</a>
            <a href="#architecture" className="transition-colors hover:text-ink">Architecture</a>
            <a href="mailto:admin.terrium@gmail.com" className="transition-colors hover:text-ink">Contact</a>
          </span>
        </div>
      </footer>
    </div>
  );
}
