/* ============================================================
   terrium — pilot invitation
   Accessible client-side validation. No network dependency:
   this is a pre-validation site, so submission is acknowledged
   honestly rather than pretending to deliver a message.
   ============================================================ */

import { qs, qsa } from './lib/dom.js';

const RULES = {
  'p-name': (v) => (v.trim().length >= 2 ? '' : 'Enter your name.'),
  'p-email': (v) => {
    if (!v.trim()) return 'Enter an institutional email address.';
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(v.trim())) return 'Enter a valid email address.';
    return '';
  },
  'p-institution': (v) => (v.trim().length >= 2 ? '' : 'Enter your institution or lab.'),
  'p-course': (v) => (v.trim().length >= 2 ? '' : 'Enter a course or domain.')
};

function setError(input, message) {
  const errEl = qs(`[data-error-for="${input.id}"]`);
  const field = input.closest('.field');
  if (!errEl) return;
  if (message) {
    errEl.textContent = message;
    errEl.hidden = false;
    input.setAttribute('aria-invalid', 'true');
    input.setAttribute('aria-describedby',
      [input.dataset.hintId, `${input.id}-error`].filter(Boolean).join(' '));
    errEl.id = `${input.id}-error`;
    field?.classList.add('has-error');
  } else {
    errEl.hidden = true;
    errEl.textContent = '';
    input.removeAttribute('aria-invalid');
    field?.classList.remove('has-error');
  }
}

export function initPilot() {
  const form = qs('[data-pilot-form]');
  if (!form) return;
  const status = qs('[data-pilot-status]');

  qsa('input, textarea', form).forEach((input) => {
    if (input.getAttribute('aria-describedby')) {
      input.dataset.hintId = input.getAttribute('aria-describedby');
    }
    input.addEventListener('blur', () => {
      const rule = RULES[input.id];
      if (rule) setError(input, rule(input.value));
    });
    input.addEventListener('input', () => {
      if (input.getAttribute('aria-invalid')) {
        const rule = RULES[input.id];
        if (rule) setError(input, rule(input.value));
      }
    });
  });

  form.addEventListener('submit', (e) => {
    e.preventDefault();
    // Annotated because a bare `null` initialiser infers `null`, so the
    // assignment below widens nothing and `firstInvalid.focus()` is an
    // error on a line that runs. The declaration is where the type lives.
    /** @type {HTMLElement | null} */
    let firstInvalid = null;

    Object.keys(RULES).forEach((id) => {
      const input = qs(`#${id}`, form);
      if (!input) return;
      const msg = RULES[id](input.value);
      setError(input, msg);
      if (msg && !firstInvalid) firstInvalid = input;
    });

    if (firstInvalid) {
      status.dataset.state = 'error';
      status.textContent = 'Some details are missing. Check the highlighted fields.';
      firstInvalid.focus();
      return;
    }

    status.dataset.state = 'ok';
    status.textContent =
      'Request captured in this prototype. Terrium is pre-validation, so no message has been sent — this demonstration does not transmit data.';
    form.classList.add('is-submitted');
    qs('.pilot__submit', form).disabled = true;
  });
}
