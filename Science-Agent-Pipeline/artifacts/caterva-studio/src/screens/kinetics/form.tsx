/**
 * The form pieces the kinetics screens share: a labelled field that shows
 * the server's 400 under the field it names, a checkbox, a segmented choice,
 * and the submit row with its keyboard shortcut.
 *
 * Composed locally until the ui owner's form components land; they hold no
 * numbers of their own. An empty number field sends nothing, so the
 * command's own default applies and the result marks it as a default.
 */
import { useId, type FormEvent, type KeyboardEvent, type ReactNode } from "react";

import type { ApiError } from "@/api/types";

/** The error to show under `field`, when the server's 400 named it. */
export function fieldError(error: ApiError | null, field: string): string | null {
  if (!error || error.code !== "malformed" || !error.field) return null;
  return error.field === field || error.field.startsWith(`${field}.`) ? error.message : null;
}

export function Field({
  label,
  hint,
  error,
  children,
}: {
  label: string;
  hint?: ReactNode;
  error?: string | null;
  children: (props: { id: string; "aria-invalid": boolean; "aria-describedby"?: string }) => ReactNode;
}) {
  const id = useId();
  const hintId = `${id}-hint`;
  const errorId = `${id}-error`;
  const describedBy = [hint ? hintId : null, error ? errorId : null].filter(Boolean).join(" ") || undefined;
  return (
    <div className="k-field">
      <label className="k-label" htmlFor={id}>
        {label}
      </label>
      {children({ id, "aria-invalid": Boolean(error), "aria-describedby": describedBy })}
      {hint ? (
        <span className="k-hint" id={hintId}>
          {hint}
        </span>
      ) : null}
      {error ? (
        <span className="k-field-error" id={errorId}>
          {error}
        </span>
      ) : null}
    </div>
  );
}

export function TextField({
  label,
  value,
  onChange,
  hint,
  error,
  placeholder,
  mono,
  list,
  required,
  onBlur,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  hint?: ReactNode;
  error?: string | null;
  placeholder?: string;
  mono?: boolean;
  list?: string;
  required?: boolean;
  onBlur?: () => void;
}) {
  return (
    <Field label={label} hint={hint} error={error}>
      {(props) => (
        <input
          {...props}
          className={mono ? "k-input font-mono" : "k-input"}
          value={value}
          placeholder={placeholder}
          list={list}
          required={required}
          spellCheck={false}
          autoComplete="off"
          onChange={(e) => onChange(e.target.value)}
          onBlur={onBlur}
        />
      )}
    </Field>
  );
}

/** A number typed as text, so an empty field means "not given". */
export function NumberField({
  label,
  value,
  onChange,
  hint,
  error,
  placeholder,
  integer,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  hint?: ReactNode;
  error?: string | null;
  placeholder?: string;
  integer?: boolean;
}) {
  return (
    <Field label={label} hint={hint} error={error}>
      {(props) => (
        <input
          {...props}
          className="k-input font-mono"
          inputMode={integer ? "numeric" : "decimal"}
          value={value}
          placeholder={placeholder}
          spellCheck={false}
          autoComplete="off"
          onChange={(e) => onChange(e.target.value)}
        />
      )}
    </Field>
  );
}

/** The text of a number field as a number, undefined when empty, NaN when unreadable. */
export function readNumber(text: string): number | undefined {
  const trimmed = text.trim();
  if (trimmed === "") return undefined;
  return Number(trimmed.replace(/−/g, "-"));
}

export function Check({
  label,
  checked,
  onChange,
  hint,
}: {
  label: ReactNode;
  checked: boolean;
  onChange: (checked: boolean) => void;
  hint?: ReactNode;
}) {
  const id = useId();
  return (
    <div className="k-check">
      <input id={id} type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      <label htmlFor={id}>
        {label}
        {hint ? <span className="k-hint block">{hint}</span> : null}
      </label>
    </div>
  );
}

export function Segmented<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: { value: T; label: string }[];
  onChange: (value: T) => void;
}) {
  return (
    <div className="k-field">
      <span className="k-label">{label}</span>
      <div className="k-segmented" role="radiogroup" aria-label={label}>
        {options.map((o) => (
          <button
            key={o.value}
            type="button"
            role="radio"
            aria-checked={o.value === value}
            data-state={o.value === value ? "on" : "off"}
            onClick={() => onChange(o.value)}
          >
            {o.label}
          </button>
        ))}
      </div>
    </div>
  );
}

const IS_MAC = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform);

/**
 * A form that submits on Enter in a field and on Cmd-Enter (Ctrl-Enter)
 * anywhere inside it, with the primary action and a cancel while running.
 */
export function RunForm({
  label,
  onSubmit,
  running,
  onCancel,
  children,
}: {
  label: string;
  onSubmit: () => void;
  running: boolean;
  onCancel?: () => void;
  children: ReactNode;
}) {
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!running) onSubmit();
  };
  const keys = (e: KeyboardEvent) => {
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey) && !running) {
      e.preventDefault();
      onSubmit();
    }
  };
  return (
    <form className="k-form" onSubmit={submit} onKeyDown={keys} aria-label={label} noValidate>
      {children}
      <div className="k-actions">
        <button type="submit" className="k-button k-button-primary" disabled={running}>
          {label}
        </button>
        {running && onCancel ? (
          <button type="button" className="k-button k-button-quiet" onClick={onCancel}>
            Cancel
          </button>
        ) : (
          <span className="k-kbd">{IS_MAC ? "⌘" : "Ctrl"} Enter</span>
        )}
      </div>
    </form>
  );
}
