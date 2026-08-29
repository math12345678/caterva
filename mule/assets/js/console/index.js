/* ============================================================
   terrium — LIVE ORCHESTRATION CONSOLE

   Left: the scientific input. Centre: a vertical agent timeline.
   Right: the output workspace that assembles as the run proceeds.

   The console is a real state machine over the nine agents, not a
   scripted animation: each agent has a status, a visible input, a
   visible output and an inspectable detail, and the workspace only
   ever gains a block because an agent emitted it.
   ============================================================ */

import { qs, qsa, h, prefersReducedMotion } from '../lib/dom.js';
import { AGENTS, CSTATUS, SCENARIO, FAILURE_CASE } from '../config/console.js';
import { agentGlyph } from './glyphs.js';
import { buildBlock } from './workspace.js';

export class Console {
  constructor(root) {
    this.root = root;
    this.listEl = qs('[data-con-agents]', root);
    this.wsEl = qs('[data-con-workspace]', root);
    this.wsEmptyEl = qs('[data-con-empty]', root);
    this.liveEl = qs('[data-con-live]', root);
    this.stateEl = qs('[data-con-state]', root);
    /* Agent detail is not a shared pane. Each row owns its own
       [data-ag-detail] block, expanded in place by the delegated Inspect
       handler below, so that the input, output and failure behaviour sit
       against the agent they belong to rather than in a panel that makes the
       reader hold a position in a list while they read. */

    this.mode = 'success';        // success | failure
    this.playing = false;
    this.cursor = -1;            // index of the agent currently running
    this.timer = null;
    this.token = 0;
    this.opened = null;          // which agent's detail is expanded
  }

  /** Agent list for the current mode, with failure overrides folded in. */
  agents() {
    if (this.mode !== 'failure') return AGENTS;
    return AGENTS.map((a) => {
      const o = FAILURE_CASE.overrides[a.id];
      return o ? { ...a, ...o } : a;
    });
  }

  mount() {
    if (!this.listEl) return null;
    this.render();
    this.wire();
    return this;
  }

  /* ---------- construction ---------- */
  render() {
    this.listEl.replaceChildren(...this.agents().map((a) => this.agentRow(a)));
    this.resetWorkspace();
    this.setStateWord('IDLE');
  }

  agentRow(a) {
    const st = CSTATUS.queued;
    const row = h('li', {
      class: 'ag',
      dataset: { agent: a.id, tone: st.tone }
    }, [
      /* The spine node. Each agent's mark is structurally different, which is
         what makes nine specialised jobs look like nine specialised jobs. */
      h('div', { class: 'ag__spine' }, [
        h('span', { class: 'ag__mark' }, [agentGlyph(a.glyph)])
      ]),
      h('div', { class: 'ag__body' }, [
        h('div', { class: 'ag__head' }, [
          h('span', { class: 'ag__i mono', text: a.index }),
          h('h3', { class: 'ag__n', text: a.name }),
          h('span', { class: 'ag__t mono', dataset: { agTime: '' }, text: '' })
        ]),
        h('p', {
          class: 'ag__status mono',
          dataset: { agStatus: '' }
        }, [
          h('span', { class: 'ag__g', text: st.glyph }),
          h('span', { class: 'ag__w', text: st.word })
        ]),
        h('div', { class: 'ag__io' }, [
          h('div', { class: 'ag__io-r' }, [
            h('span', { class: 'label label--micro', text: 'IN' }),
            h('p', { text: a.input })
          ]),
          h('div', { class: 'ag__io-r ag__io-r--out' }, [
            h('span', { class: 'label label--micro', text: 'OUT' }),
            h('p', { dataset: { agOut: '' }, text: '\u2014' })
          ])
        ]),
        /* The critique's disclosure is not tucked into the detail drawer: an
           assumption the reader has to click to discover is an assumption
           the product is hiding. */
        a.disclosure
          ? h('p', { class: 'ag__disclosure', dataset: { agDisc: '' } }, [
              h('span', { class: 'ag__disc-g', text: '\u25B2' }),
              h('span', { text: a.disclosure })
            ])
          : null,
        h('button', {
          class: 'ag__inspect',
          type: 'button',
          dataset: { agInspect: a.id },
          'aria-expanded': 'false',
          text: 'Inspect'
        }),
        h('p', { class: 'ag__detail', dataset: { agDetail: '' }, hidden: true, text: a.detail })
      ].filter(Boolean))
    ]);
    return row;
  }

  /* ---------- status ---------- */
  /**
   * @param {string} id
   * @param {string} key
   * @param {{ time?: string }} [opts]
   */
  setStatus(id, key, { time } = {}) {
    const row = qs(`[data-agent="${id}"]`, this.listEl);
    if (!row) return;
    const st = CSTATUS[key];
    if (!st) return;
    row.dataset.tone = st.tone;
    row.dataset.state = key;
    const g = qs('.ag__g', row);
    const w = qs('.ag__w', row);
    if (g) g.textContent = st.glyph;
    if (w) w.textContent = st.word;
    if (time !== undefined) {
      const t = qs('[data-ag-time]', row);
      if (t) t.textContent = time;
    }
  }

  showOutput(id, text, terminal) {
    const row = qs(`[data-agent="${id}"]`, this.listEl);
    if (!row) return;
    const out = qs('[data-ag-out]', row);
    if (out) out.textContent = text;
    row.classList.add('is-resolved');
    if (terminal) {
      const t = qs('[data-ag-time]', row);
      if (t) t.textContent = terminal;
    }
  }

  setStateWord(word) {
    if (this.stateEl) this.stateEl.textContent = word;
  }

  announce(text) {
    if (this.liveEl) this.liveEl.textContent = text;
  }

  /* ---------- workspace ---------- */
  resetWorkspace() {
    if (!this.wsEl) return;
    this.wsEl.replaceChildren();
    if (this.wsEmptyEl) this.wsEmptyEl.hidden = false;
    this.root.classList.remove('is-built');
  }

  emit(key) {
    if (!this.wsEl || !key) return;
    const blk = buildBlock(key);
    if (!blk) return;
    if (this.wsEmptyEl) this.wsEmptyEl.hidden = true;
    this.wsEl.appendChild(blk);
    /* Reveal on the next frame so the entrance transition actually runs —
       a class set in the same frame the node is inserted never animates. */
    requestAnimationFrame(() => blk.classList.add('is-in'));
    this.root.classList.add('is-built');
    /* Keep the newest block in view inside the panel only — scrollIntoView
       here would drag the whole page. Note the scroller is the workspace
       frame, not the list inside it: setting scrollTop on the list itself
       does nothing, because the list is the thing that overflows. */
    const scroller = this.wsEl.closest('.con-ws') || this.wsEl;
    scroller.scrollTop = scroller.scrollHeight;
  }

  /* ---------- run control ---------- */
  reset() {
    clearTimeout(this.timer);
    this.token += 1;
    this.playing = false;
    this.cursor = -1;
    this.render();
    this.root.classList.remove('is-playing', 'is-done');
    this.setStateWord('IDLE');
    this.syncButtons();
  }

  start() {
    this.reset();
    this.playing = true;
    this.root.classList.add('is-playing');
    this.setStateWord('RUNNING');
    this.announce(
      this.mode === 'failure'
        ? 'Running the failure case: the same question where the illustrative evidence does not establish a required constant.'
        : 'Running the demonstration: nine agents, each with a distinct responsibility.'
    );
    this.syncButtons();
    this.step(0);
  }

  step(i) {
    const list = this.agents();
    const token = this.token;
    if (i >= list.length) {
      this.finish();
      return;
    }
    this.cursor = i;
    const a = list[i];

    /* Pause is only meaningful once an agent is actually running, and the
       cursor is what makes it meaningful — so the controls have to be synced
       here rather than only in start(), where the cursor is still -1. */
    this.syncButtons();

    this.setStatus(a.id, a.working, { time: 'RUNNING' });
    const row = qs(`[data-agent="${a.id}"]`, this.listEl);
    if (row) {
      row.classList.add('is-current');
      /* Scroll the timeline column, never the document: on a phone the
         console is taller than the viewport and pulling the page around
         under the reader mid-run is disorienting. */
      const col = this.listEl.parentElement;
      if (col && col.scrollHeight > col.clientHeight) {
        col.scrollTo({ top: row.offsetTop - col.clientHeight / 2 + row.offsetHeight / 2, behavior: prefersReducedMotion() ? 'auto' : 'smooth' });
      }
    }

    const dur = prefersReducedMotion() ? 90 : a.duration;
    this.timer = setTimeout(() => {
      if (token !== this.token) return;
      this.setStatus(a.id, a.settled);
      this.showOutput(a.id, a.output, a.terminal);
      if (row) { row.classList.remove('is-current'); row.classList.add('is-done'); }
      this.emit(a.emits);
      this.announce(`${a.index} ${a.name}: ${a.terminal}. ${a.output}.`);
      this.step(i + 1);
    }, dur);
  }

  finish() {
    this.playing = false;
    this.cursor = -1;
    clearTimeout(this.timer);
    this.root.classList.remove('is-playing');
    this.root.classList.add('is-done');
    if (this.mode === 'failure') {
      this.setStateWord('RETURNED TO USER');
      this.announce('Failure case complete. The run did not produce a final result; a clarification request was prepared instead.');
    } else {
      this.setStateWord('RUN COMPLETE');
      this.announce('Demonstration complete. An illustrated record was produced with one disclosed assumption.');
    }
    this.syncButtons();
  }

  pause() {
    if (!this.playing) return;
    clearTimeout(this.timer);
    this.token += 1;          // orphan the pending step
    this.playing = false;
    this.root.classList.remove('is-playing');
    this.setStateWord('PAUSED');
    this.announce('Run paused.');
    this.syncButtons();
  }

  resume() {
    if (this.playing || this.cursor < 0) return;
    this.playing = true;
    this.root.classList.add('is-playing');
    this.setStateWord('RUNNING');
    this.announce('Run resumed.');
    this.syncButtons();
    /* Re-run the agent that was interrupted rather than skipping it: it was
       mid-work when the reader paused, so its output was never shown. */
    this.step(this.cursor);
  }

  setMode(mode) {
    if (this.mode === mode) return;
    this.mode = mode;
    qsa('[data-con-mode]', this.root).forEach((b) => {
      const on = b.dataset.conMode === mode;
      b.classList.toggle('is-active', on);
      b.setAttribute('aria-pressed', on ? 'true' : 'false');
    });
    const note = qs('[data-con-note]', this.root);
    if (note) {
      note.textContent = mode === 'failure' ? FAILURE_CASE.note : SCENARIO.note;
    }
    const caseLabel = qs('[data-con-scenario]', this.root);
    if (caseLabel) {
      caseLabel.textContent = mode === 'failure' ? FAILURE_CASE.label : SCENARIO.label;
    }
    this.root.dataset.conCase = mode;
    this.reset();
    this.announce(
      mode === 'failure'
        ? 'Switched to the failure case. Press run demonstration to play it.'
        : 'Switched to the successful demonstration.'
    );
  }

  syncButtons() {
    const run = qs('[data-con-run]', this.root);
    const pause = qs('[data-con-pause]', this.root);
    if (run) {
      run.textContent = this.root.classList.contains('is-done') ? 'Replay demonstration' : 'Run demonstration';
    }
    if (pause) {
      const idle = this.cursor < 0 || this.root.classList.contains('is-done');
      pause.disabled = idle;
      /* While idle the control is disabled, so it must not read "Resume" —
         there is nothing to resume, and a dead verb invites a dead click. */
      pause.textContent = idle ? 'Pause' : (this.playing ? 'Pause' : 'Resume');
    }
  }

  /* ---------- wiring ---------- */
  wire() {
    qs('[data-con-run]', this.root)?.addEventListener('click', () => this.start());
    qs('[data-con-pause]', this.root)?.addEventListener('click', () => {
      if (this.playing) this.pause(); else this.resume();
    });
    qsa('[data-con-mode]', this.root).forEach((b) => {
      b.addEventListener('click', () => this.setMode(b.dataset.conMode));
    });

    /* Inspect is delegated: rows are rebuilt on every reset, so per-row
       listeners would be re-bound constantly and leak. */
    this.listEl.addEventListener('click', (e) => {
      const btn = e.target.closest('[data-ag-inspect]');
      if (!btn) return;
      const row = btn.closest('.ag');
      const detail = qs('[data-ag-detail]', row);
      if (!detail) return;
      const open = detail.hidden;
      detail.hidden = !open;
      btn.setAttribute('aria-expanded', open ? 'true' : 'false');
      btn.textContent = open ? 'Close' : 'Inspect';
      row.classList.toggle('is-open', open);
    });

    this.syncButtons();
  }

  /* ---------- global SYSTEM MODE ----------
     The console has a success case and a failure case, and the global
     modes decide which one is loaded and whether it plays by itself.

     RUN and FAILURE both start a run, so the reader who selects a mode
     and is scrolled here sees the system working rather than a stage
     waiting to be told to work. OBSERVE and TRACE stop it: both are modes
     for reading, and nine agents stepping through statuses while someone
     is trying to read a status is the opposite of that. */
  applyMode(mode) {
    this.root.dataset.mode = mode;

    if (mode === 'run' || mode === 'failure') {
      const want = mode === 'failure' ? 'failure' : 'success';
      /* setMode already resets, so starting after a change of case would
         otherwise fight it. */
      if (this.mode !== want) this.setMode(want);
      this.start();
      return;
    }

    /* observe / trace — hold still. The run is stopped rather than
       rewound: the reader may be part-way through inspecting an agent, and
       throwing that away to enforce a mode would be rude. */
    if (this.playing) this.pause();
  }
}

export function initConsole() {
  const root = qs('[data-console]');
  if (!root) return null;
  const con = new Console(root).mount();
  if (con) {
    import('../modes/index.js').then(({ systemMode }) => {
      systemMode.register('console', (mode) => con.applyMode(mode));
    });
  }
  return con;
}
