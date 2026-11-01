import TerminalWindow from "./TerminalWindow";
import Reveal from "./Reveal";

// How to get Caterva, which replaces a pricing table.
//
// That table offered a free tier "up to 10 simulations/month", a pilot tier
// with "priority support", a "classroom dashboard (beta)" and a "public
// simulation gallery". None of those exists. Caterva is Apache-2.0 software
// that runs on the machine that asks, and nothing is metered, so there is
// nothing to price.
//
// The facts below were read on 2026-09-29: the latest release is v0.4.0
// (2026-09-27) and its bundles carry `caterva compose` and `caterva sim`
// (caterva/app.py at v0.4.0). The structure and molecular dynamics tools
// were added after it and are on the main branch only. When a release
// carries them, this section changes with it.
const RELEASE = {
  tag: "v0.4.0",
  date: "2026-09-27",
  url: "https://github.com/math12345678/caterva/releases/tag/v0.4.0",
  platforms: ["macOS (Apple silicon)", "Linux x86_64", "Windows x86_64"],
  commands: ["compose", "sim"],
};

const MAIN_ONLY = ["structure", "md", "prepare", "analyze", "bind", "complex", "fep"];

const REPO = "https://github.com/math12345678/caterva";

export default function GetCaterva() {
  return (
    <section className="max-w-3xl mx-auto px-4 md:px-6 py-10" id="get">
      <Reveal>
        <div className="flex items-center gap-4 mb-6">
          <span className="text-muted text-[11px] font-mono font-medium">get</span>
          <span className="h-px flex-1 bg-gradient-to-r from-muted/20 to-transparent" />
        </div>
        <h2 className="section-header">Get Caterva</h2>
        <p className="font-sans text-[13px] text-fg/76 mb-8 -mt-2 max-w-lg">
          Free and open source under Apache-2.0. It runs on your machine,
          nothing is metered, and the literature lookups go straight from your
          computer to the databases.
        </p>

        <div className="grid gap-5 md:grid-cols-2">
          <TerminalWindow path={`~ — download ${RELEASE.tag}`}>
            <p className="text-[12px] text-fg/88 font-sans font-medium mb-1">
              Download a release
            </p>
            <p className="text-[11px] text-fg/70 leading-relaxed mb-3">
              {RELEASE.tag}, {RELEASE.date}. One folder with Python and every
              library inside, for {RELEASE.platforms.join(", ")}. Carries{" "}
              {RELEASE.commands.map((c, i) => (
                <span key={c}>
                  {i > 0 && " and "}
                  <code className="font-mono text-fg/88">caterva {c}</code>
                </span>
              ))}
              .
            </p>
            <a
              href={RELEASE.url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 text-[11px] font-mono text-signal hover:underline underline-offset-4"
            >
              {RELEASE.tag} on GitHub
              <span aria-hidden>↗</span>
            </a>
            <p className="mt-2 text-[10px] text-fg/60 font-mono">
              checksums in SHA256SUMS
            </p>
          </TerminalWindow>

          <TerminalWindow path="~ — from source">
            <p className="text-[12px] text-fg/88 font-sans font-medium mb-1">
              Build from the main branch
            </p>
            <p className="text-[11px] text-fg/70 leading-relaxed mb-3">
              Adds the structure and molecular dynamics tools no release
              carries yet:{" "}
              {MAIN_ONLY.map((c, i) => (
                <span key={c}>
                  {i > 0 && ", "}
                  <code className="font-mono text-fg/88">{c}</code>
                </span>
              ))}
              . Python 3.10 to 3.13; GROMACS installed separately for{" "}
              <code className="font-mono text-fg/88">md</code> and{" "}
              <code className="font-mono text-fg/88">fep</code>.
            </p>
            <pre className="cite-code-block text-[11px] leading-relaxed overflow-x-auto whitespace-pre">
              <code>{`git clone ${REPO}.git
cd caterva
make setup      # creates .venv (2-5 min)`}</code>
            </pre>
          </TerminalWindow>
        </div>

        <p className="mt-5 text-[11px] text-fg/66 font-sans">
          Questions and bugs:{" "}
          <a
            href={`${REPO}/issues`}
            target="_blank"
            rel="noopener noreferrer"
            className="text-signal hover:underline underline-offset-4"
          >
            GitHub issues
          </a>
          .
        </p>
      </Reveal>
    </section>
  );
}
