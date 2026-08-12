/* ============================================================
   terrium — application entry
   Wires the inquiry terminal, the Evidence Cathedral, inspection
   mode, the three chapters, and the pilot invitation.
   ============================================================ */

import { qs, qsa, observeReveals, installVisibilityGuard, prefersReducedMotion } from './lib/dom.js';
import { RunState } from './lib/runState.js';
import { renderCathedral, wrapQuestion } from './cathedral/render.js';
import { Choreographer } from './cathedral/choreograph.js';
import { Inspector } from './cathedral/inspector.js';
import { DEMO_QUESTION, QUESTION_CHAMBER, MOBILE_JOURNEY } from './config/architecture.js';
import { initChapters } from './chapters/index.js';
import { initPilot } from './pilot.js';
import { initSystemMode, systemMode } from './modes/index.js';

function initTerminal({ onSubmit }) {
  const form = qs('[data-inquiry-form]');
  const input = qs('#question');
  const stateEl = qs('[data-terminal-state]');
  const sampleBtn = qs('[data-use-sample]');

  const autosize = () => {
    input.style.height = 'auto';
    input.style.height = `${input.scrollHeight}px`;
  };

  const armed = () => {
    const has = input.value.trim().length > 0;
    stateEl.textContent = has ? 'READY / PRESS ENTER' : 'AWAITING INPUT';
    stateEl.classList.toggle('is-armed', has);
  };

  input.addEventListener('input', () => { autosize(); armed(); });
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      form.requestSubmit();
    }
  });

  form.addEventListener('submit', (e) => {
    e.preventDefault();
    const q = input.value.trim() || DEMO_QUESTION;
    stateEl.textContent = 'ACCEPTED / 0007';
    stateEl.classList.add('is-armed');
    onSubmit(q);
  });

  sampleBtn.addEventListener('click', () => {
    input.value = DEMO_QUESTION;
    autosize();
    armed();
    form.requestSubmit();
  });

  autosize();
  armed();

  return {
    reset() {
      input.value = DEMO_QUESTION;
      autosize();
      armed();
      input.focus({ preventScroll: true });
    }
  };
}

/**
 * The heavy interactive sections — the atlas map, the orchestration console —
 * are built when they approach the viewport rather than during boot: the
 * terminal must be typeable immediately, and nothing below the hero is needed
 * before then.
 *
 * @param {string} sel     host selector
 * @param {() => Promise} load  dynamic import + init
 * @param {string} anchor  in-page link that must force an immediate build
 */
function mountWhenNear(sel, load, anchor) {
  const host = qs(sel);
  if (!host) return;
  let built = null;
  const build = () => {
    if (built) return built;
    /* A rejected dynamic import here would otherwise surface only as an
       unhandled rejection while the section sat empty and looked intentional.
       Named, so the console says which section is missing. */
    built = Promise.resolve()
      .then(load)
      .catch((err) => {
        console.error(`[terrium] deferred section "${sel}" failed to load; the rest of the page continues.`, err);
        const root = document.documentElement;
        root.dataset.bootFailed = root.dataset.bootFailed ? `${root.dataset.bootFailed} ${sel}` : sel;
      });
    return built;
  };
  if (prefersReducedMotion() || !('IntersectionObserver' in window)) {
    build();
    return;
  }
  const io = new IntersectionObserver((entries) => {
    entries.forEach((e) => {
      if (e.isIntersecting) { build(); io.disconnect(); }
    });
  }, { rootMargin: '500px 0px' });
  io.observe(host);

  /* A reader who jumps straight there from the navigation must not arrive at
     an empty stage while the observer is still deciding. */
  if (anchor) qsa(`a[href="${anchor}"]`).forEach((a) => a.addEventListener('click', build));
}

/**
 * Boot one subsystem without letting it take the others down.
 *
 * Every section on this page renders into an empty host element, and boot()
 * was a single straight-line sequence: one null selector anywhere — a renamed
 * hook, a section edited out — threw, and every subsystem after it never ran.
 * The page still looked deliberate, because an unbuilt section is an empty
 * div, so the failure mode was a quietly half-dead page with no symptom.
 *
 * That is the same shape as a guard that reports green on work it did not do.
 * So: contain the blast radius to one subsystem, and make the failure
 * *observable* — a console error naming the part that died, and a marker on
 * <html> listing them, so this can never again be invisible to anyone
 * inspecting the page.
 */
function safely(name, fn) {
  try {
    return fn();
  } catch (err) {
    console.error(`[terrium] "${name}" failed to initialise; the rest of the page continues.`, err);
    const root = document.documentElement;
    const failed = root.dataset.bootFailed ? `${root.dataset.bootFailed} ${name}` : name;
    root.dataset.bootFailed = failed;
    return null;
  }
}

function boot() {
  safely('visibility-guard', installVisibilityGuard);
  safely('reveals', observeReveals);
  safely('system-mode', initSystemMode);
  safely('chapters', initChapters);
  safely('pilot', initPilot);
  safely('atlas', () => mountWhenNear('[data-atlas]', () => import('./atlas/index.js').then((m) => m.initAtlas()), '#atlas'));
  safely('console', () => mountWhenNear('[data-console]', () => import('./console/index.js').then((m) => m.initConsole()), '#orchestration'));
  safely('microscope', () => mountWhenNear('[data-microscope]', () => import('./microscope/index.js').then((m) => m.initMicroscope()), '#microscope'));

  safely('cathedral', bootCathedral);
}

function bootCathedral() {
  const stageEl = qs('.stage');
  const cathedralEl = qs('[data-cathedral]');
  const viewport = qs('[data-viewport]');
  const railEl = qs('[data-rail]');
  const logEl = qs('[data-log]');
  const vaultLineEl = qs('[data-vault-line]');
  const tiersEl = qs('[data-tiers]');
  const journeyEl = qs('[data-journey]');
  const narrow = () => window.matchMedia('(max-width: 48rem)').matches;

  const inspector = new Inspector(document.body);
  const run = new RunState();

  let svg = null;
  let choreo = null;
  let terminal = null;

  const ensureCathedral = (question) => {
    if (!svg) {
      svg = renderCathedral(viewport, question);
      choreo = new Choreographer({ svg, stageEl, railEl, logEl, vaultLineEl });
      inspector.attach(svg);
      // Opening the panel narrows the drawing field, so the current frame has
      // to be re-fitted to the container that remains.
      inspector.onReframe = () => choreo?.refit();
      // On a phone the sheet leaves only a shallow band of architecture, so the
      // camera goes to the object being inspected and returns afterwards.
      inspector.onFrameNode = (id) => choreo?.frameNode(id);
      inspector.onReleaseFrame = () => choreo?.releaseNodeFrame();
    } else {
      const t = qs('[data-question-text]', svg);
      if (t) wrapQuestion(t, question, 500);
      const chamberNode = qs('[data-node="question-chamber"]', svg);
      if (chamberNode) chamberNode.setAttribute('aria-label', `Question chamber. ${question}`);
    }
  };

  const startRun = (question, { focus = true } = {}) => {
    ensureCathedral(question);
    cathedralEl.hidden = false;
    // Let the void reorganize before the architecture rises.
    requestAnimationFrame(() => {
      stageEl.classList.add('is-running');
      cathedralEl.classList.add('is-visible');
      run.start(question);
      /* Move keyboard focus into the architecture controls — but only when the
         reader asked for this run by submitting the question. A run started by
         a global mode change must leave the caret where it is: the dock is a
         radiogroup the reader arrows through, and a delayed focus landing here
         a second and a half later would pull them out of it mid-cycle. */
      if (focus) {
        const replay = qs('[data-replay]');
        if (replay) setTimeout(() => replay.focus({ preventScroll: true }), prefersReducedMotion() ? 60 : 1400);
      }
    });
  };

  /** Tier framing buttons; only meaningful once the run has completed. */
  const setFrameButtons = (active) => {
    qsa('.tier-btn', tiersEl).forEach((b) => {
      b.setAttribute('aria-pressed', String(b.dataset.frame === active));
    });
  };

  qsa('.tier-btn', tiersEl).forEach((btn) => {
    btn.addEventListener('click', () => {
      choreo?.moveCamera(btn.dataset.frame, false);
      setFrameButtons(btn.dataset.frame);
    });
  });

  /* --- mobile journey: walk the same architecture station by station --- */
  let station = MOBILE_JOURNEY.length - 1;
  const idxEl = qs('[data-journey-index]');
  const labelEl = qs('[data-journey-label]');
  const total = String(MOBILE_JOURNEY.length).padStart(2, '0');

  const goToStation = (i) => {
    station = Math.max(0, Math.min(MOBILE_JOURNEY.length - 1, i));
    const st = MOBILE_JOURNEY[station];
    choreo?.moveCamera(st.id, false);
    idxEl.textContent = `${String(station + 1).padStart(2, '0')} / ${total}`;
    labelEl.textContent = st.label;
    qs('[data-journey-prev]').disabled = station === 0;
    qs('[data-journey-next]').disabled = station === MOBILE_JOURNEY.length - 1;
  };

  qs('[data-journey-prev]').addEventListener('click', () => goToStation(station - 1));
  qs('[data-journey-next]').addEventListener('click', () => goToStation(station + 1));

  /** Show whichever explorer suits the viewport. */
  const showExplorer = (on) => {
    tiersEl.hidden = !on || narrow();
    journeyEl.hidden = !on || !narrow();
    if (on && narrow()) goToStation(MOBILE_JOURNEY.length - 1);
  };

  run.subscribe(({ stageIndex, question, mode }) => {
    if (!choreo) return;
    choreo.apply(stageIndex, question || DEMO_QUESTION);
    if (mode === 'complete') {
      choreo.settle();
      showExplorer(true);
      setFrameButtons('full');
    } else {
      showExplorer(false);
    }
  });

  terminal = initTerminal({ onSubmit: startRun });

  qs('[data-replay]').addEventListener('click', () => {
    inspector.close();
    choreo?.reset();
    run.replay();
  });

  qs('[data-skip]').addEventListener('click', () => {
    run.skipToEnd();
    choreo?.settle();
  });

  qs('[data-reset]').addEventListener('click', () => {
    inspector.close();
    run.reset();
    choreo?.reset();
    showExplorer(false);
    stageEl.classList.remove('is-running');
    cathedralEl.classList.remove('is-visible');
    setTimeout(() => { cathedralEl.hidden = true; }, prefersReducedMotion() ? 10 : 900);
    terminal.reset();
  });

  // Nav link to the system section restarts framing without losing state.
  qs('.nav a[href="#system"]').addEventListener('click', () => {
    if (run.mode === 'complete') choreo?.moveCamera('full');
  });

  /* --- the Evidence Cathedral answers SYSTEM MODE too ---
     RUN means the whole page is running, and the cathedral is the first
     thing on it: leaving the hero as an empty terminal while every section
     below it works would make the mode look like a section-level toggle.
     It is only auto-started once, though — re-running the architecture out
     from under someone who is reading their own completed run would
     destroy their result to demonstrate a mode. */
  let autoRan = false;
  systemMode.register('cathedral', (mode) => {
    document.documentElement.dataset.stageMode = mode;
    if ((mode === 'run' || mode === 'failure') && !autoRan && run.mode === 'idle') {
      autoRan = true;
      startRun(DEMO_QUESTION, { focus: false });
    }
  });
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', boot);
} else {
  boot();
}

export { QUESTION_CHAMBER };
