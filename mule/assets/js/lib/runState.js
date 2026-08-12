/* ============================================================
   terrium — run state machine
   Drives the illustrated pipeline. Time-based but skippable,
   replayable, and fully readable in reduced-motion mode.
   ============================================================ */

import { STAGES, RUN_DURATION } from '../config/architecture.js';
import { prefersReducedMotion } from './dom.js';

const STAGE_IDS = STAGES.map((st) => st.id);

export class RunState {
  constructor() {
    this.listeners = new Set();
    this.stageIndex = 0;
    this.timers = [];
    this.playing = false;
    this.mode = 'idle'; // idle | running | complete
  }

  subscribe(fn) {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }

  emit(detail = {}) {
    const payload = {
      stage: STAGES[this.stageIndex],
      stageIndex: this.stageIndex,
      reached: STAGE_IDS.slice(0, this.stageIndex + 1),
      mode: this.mode,
      ...detail
    };
    this.listeners.forEach((fn) => fn(payload));
  }

  /** Has the pipeline reached a given stage id? */
  has(id) {
    return this.stageIndex >= STAGE_IDS.indexOf(id);
  }

  clearTimers() {
    this.timers.forEach((t) => clearTimeout(t));
    this.timers = [];
  }

  goTo(index, detail = {}) {
    this.stageIndex = Math.max(0, Math.min(STAGES.length - 1, index));
    this.emit(detail);
  }

  /** Start the sequence from the question. */
  start(question) {
    this.clearTimers();
    this.question = question;
    this.mode = 'running';
    this.playing = true;

    // Reduced motion: present the architecture fully assembled, then
    // step through states as discrete, readable changes.
    if (prefersReducedMotion()) {
      this.goTo(1, { question, jumped: true });
      let i = 2;
      const step = () => {
        if (i >= STAGES.length) {
          this.mode = 'complete';
          this.playing = false;
          this.emit({ question });
          return;
        }
        this.goTo(i, { question });
        i += 1;
        this.timers.push(setTimeout(step, 620));
      };
      this.timers.push(setTimeout(step, 400));
      return;
    }

    this.goTo(1, { question });
    STAGES.forEach((st, i) => {
      if (i < 2) return;
      this.timers.push(
        setTimeout(() => {
          this.goTo(i, { question });
          if (i === STAGES.length - 1) {
            this.mode = 'complete';
            this.playing = false;
            this.emit({ question });
          }
        }, st.at)
      );
    });
  }

  replay() {
    this.clearTimers();
    this.stageIndex = 0;
    this.mode = 'idle';
    this.emit({ question: this.question, resetting: true });
    // Allow a frame for structures to reset before re-running.
    this.timers.push(setTimeout(() => this.start(this.question), 260));
  }

  /** Jump straight to the completed composition. */
  skipToEnd() {
    this.clearTimers();
    this.mode = 'complete';
    this.playing = false;
    this.goTo(STAGES.length - 1, { question: this.question, jumped: true });
  }

  reset() {
    this.clearTimers();
    this.stageIndex = 0;
    this.mode = 'idle';
    this.playing = false;
    this.emit({ resetting: true, full: true });
  }
}

export { STAGE_IDS, RUN_DURATION };
