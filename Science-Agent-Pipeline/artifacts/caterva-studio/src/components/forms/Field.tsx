/**
 * Form fields: one label, one control, a hint, and the server's own words
 * when it refuses the value.
 *
 * A 400 `malformed` names the request field it refused (`error.field`);
 * `fieldError(error, name)` gives that message to the field that owns it,
 * so the sentence argparse wrote lands under the input it is about rather
 * than at the top of the page.
 *
 * Controls are the platform's own where the platform's is good (text,
 * number, select): a native <select> opens the system menu, works with
 * every assistive technology, and needs no scroll lock (Radix's select
 * injects a <style> element the studio's Content Security Policy refuses).
 *
 * Nothing here pre-fills a value. A measured quantity (Km, kcat, Ki) is
 * never offered as a default (ADR 0012/0013); a screen that has a stated
 * default of the command passes it, and labels it as one, itself.
 */
import * as CheckboxPrimitive from "@radix-ui/react-checkbox";
import * as SwitchPrimitive from "@radix-ui/react-switch";
import { Check } from "lucide-react";
import {
  type AriaAttributes,
  createContext,
  forwardRef,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
  useCallback,
  useContext,
  useId,
  useMemo,
  useState,
} from "react";

import type { ApiError } from "@/api/types";
import { cn } from "@/lib/cn";

interface FieldIds {
  control: string;
  hint: string | undefined;
  error: string | undefined;
  invalid: boolean;
  required: boolean;
}

const FieldContext = createContext<FieldIds | null>(null);

/**
 * The fields a form refused to send because a required one was empty. A
 * form (RunForm) provides it; a Field whose control is listed shows its own
 * message and marks the control invalid, so nothing is requested until the
 * question can be asked.
 */
interface Validity {
  missing: ReadonlySet<string>;
}

const ValidityContext = createContext<Validity>({ missing: new Set() });

/** The controls a form must not submit empty: `required` or `aria-required`, with an id. */
const REQUIRED_CONTROLS = "input[required], input[aria-required='true'], select[required], select[aria-required='true'], textarea[required], textarea[aria-required='true']";

export function useRequiredCheck(): {
  missing: ReadonlySet<string>;
  provider: (children: ReactNode) => ReactNode;
  /** Looks at the form's required controls; returns true when all have a value. */
  check: (form: HTMLFormElement | null) => boolean;
  clear: (id: string) => void;
} {
  const [missing, setMissing] = useState<ReadonlySet<string>>(new Set());
  const check = useCallback((form: HTMLFormElement | null) => {
    if (!form) return true;
    const empty = Array.from(form.querySelectorAll<HTMLInputElement>(REQUIRED_CONTROLS)).filter(
      (c) => c.id && c.value.trim() === "",
    );
    setMissing(new Set(empty.map((c) => c.id)));
    if (empty.length) empty[0].focus();
    return empty.length === 0;
  }, []);
  const clear = useCallback((id: string) => setMissing((m) => (m.has(id) ? new Set([...m].filter((x) => x !== id)) : m)), []);
  const value = useMemo(() => ({ missing }), [missing]);
  const provider = useCallback(
    (children: ReactNode) => <ValidityContext.Provider value={value}>{children}</ValidityContext.Provider>,
    [value],
  );
  return { missing, provider, check, clear };
}

/** The message of a 400 that names this field (or one of its sub-keys), else null. */
export function fieldError(error: ApiError | null | undefined, name: string): string | null {
  if (!error || !error.field) return null;
  if (error.field === name || error.field.startsWith(`${name}.`) || error.field.startsWith(`${name}[`)) {
    return error.message;
  }
  return null;
}

export function Field({
  label,
  hint,
  error,
  optional = false,
  required = false,
  children,
  className,
}: {
  label: ReactNode;
  hint?: ReactNode;
  error?: string | null;
  optional?: boolean;
  /** The form will not send this empty: the control is aria-required and the form says so inline. */
  required?: boolean;
  children: ReactNode;
  className?: string;
}) {
  const id = useId();
  const validity = useContext(ValidityContext);
  const control = `${id}-control`;
  const emptyRequired = validity.missing.has(control);
  const shown = error ?? (emptyRequired ? requiredMessage(label) : null);
  const ids: FieldIds = {
    control,
    hint: hint ? `${id}-hint` : undefined,
    error: shown ? `${id}-error` : undefined,
    invalid: Boolean(shown),
    required,
  };
  return (
    <FieldContext.Provider value={ids}>
      <div className={cn("field", className)}>
        <label className="field-label" htmlFor={ids.control}>
          {label}
          {optional ? <span className="field-optional">optional</span> : null}
        </label>
        {children}
        {hint ? (
          <p className="field-hint" id={ids.hint}>
            {hint}
          </p>
        ) : null}
        {shown ? (
          <p className="field-error" id={ids.error} role="alert">
            {shown}
          </p>
        ) : null}
      </div>
    </FieldContext.Provider>
  );
}

/** "Organism is required." for a label that is text; a generic sentence otherwise. */
function requiredMessage(label: ReactNode): string {
  return typeof label === "string" ? `${label} is required: fill it in to continue.` : "This field is required: fill it in to continue.";
}

function useControlProps(own: {
  id?: string;
  required?: boolean;
  "aria-describedby"?: string;
  "aria-invalid"?: AriaAttributes["aria-invalid"];
  "aria-required"?: AriaAttributes["aria-required"];
}) {
  const ids = useContext(FieldContext);
  if (!ids) return own;
  const described = [own["aria-describedby"], ids.hint, ids.error].filter(Boolean).join(" ") || undefined;
  return {
    id: own.id ?? ids.control,
    "aria-describedby": described,
    "aria-invalid": own["aria-invalid"] ?? (ids.invalid ? true : undefined),
    "aria-required": own["aria-required"] ?? (ids.required || own.required ? true : undefined),
  };
}

export const TextInput = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement> & { mono?: boolean }>(
  function TextInput({ className, mono = false, ...props }, ref) {
    const control = useControlProps(props);
    return (
      <input
        ref={ref}
        type="text"
        autoComplete="off"
        spellCheck={false}
        {...props}
        {...control}
        className={cn("input", mono && "input-mono", className)}
      />
    );
  },
);

/**
 * A number typed as text, so the reader's own digits are kept as typed
 * ("6.0" stays "6.0") and the browser's spinner never nudges a value.
 * `unit` sits beside the box in DM Mono.
 */
export const NumberInput = forwardRef<
  HTMLInputElement,
  Omit<InputHTMLAttributes<HTMLInputElement>, "type"> & { unit?: string }
>(function NumberInput({ className, unit, ...props }, ref) {
  const control = useControlProps(props);
  const input = (
    <input
      ref={ref}
      type="text"
      inputMode="decimal"
      autoComplete="off"
      spellCheck={false}
      {...props}
      {...control}
      className={cn("input num", className)}
    />
  );
  if (!unit) return input;
  return (
    <span className="input-group">
      {input}
      <span className="input-unit">{unit}</span>
    </span>
  );
});

/** The value of a NumberInput as a number, or null when it is empty or not a number. */
export function parseNumber(text: string): number | null {
  const t = text.trim().replace(/−/g, "-");
  if (t === "") return null;
  if (!/^[-+]?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?$/.test(t)) return null;
  const n = Number(t);
  return Number.isFinite(n) ? n : null;
}

export const TextArea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(function TextArea(
  { className, ...props },
  ref,
) {
  const control = useControlProps(props);
  return <textarea ref={ref} spellCheck={false} {...props} {...control} className={cn("textarea", className)} />;
});

export const Select = forwardRef<HTMLSelectElement, SelectHTMLAttributes<HTMLSelectElement>>(function Select(
  { className, children, ...props },
  ref,
) {
  const control = useControlProps(props);
  return (
    <select ref={ref} {...props} {...control} className={cn("select", className)}>
      {children}
    </select>
  );
});

export function Checkbox({
  checked,
  onChange,
  label,
  hint,
  disabled,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: ReactNode;
  hint?: ReactNode;
  disabled?: boolean;
}) {
  const id = useId();
  return (
    <div className="check-row">
      <CheckboxPrimitive.Root
        id={id}
        className="check-box"
        checked={checked}
        disabled={disabled}
        onCheckedChange={(v) => onChange(v === true)}
        aria-describedby={hint ? `${id}-hint` : undefined}
      >
        <CheckboxPrimitive.Indicator>
          <Check size={12} strokeWidth={3} aria-hidden="true" />
        </CheckboxPrimitive.Indicator>
      </CheckboxPrimitive.Root>
      <span className="check-text">
        <label htmlFor={id} className="check-label">
          {label}
        </label>
        {hint ? (
          <span className="field-hint" id={`${id}-hint`}>
            {hint}
          </span>
        ) : null}
      </span>
    </div>
  );
}

export function Switch({
  checked,
  onChange,
  label,
  hint,
  disabled,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: ReactNode;
  hint?: ReactNode;
  disabled?: boolean;
}) {
  const id = useId();
  return (
    <div className="check-row">
      <SwitchPrimitive.Root
        id={id}
        className="switch"
        checked={checked}
        disabled={disabled}
        onCheckedChange={onChange}
        aria-describedby={hint ? `${id}-hint` : undefined}
      >
        <SwitchPrimitive.Thumb className="switch-thumb" />
      </SwitchPrimitive.Root>
      <span className="check-text">
        <label htmlFor={id} className="check-label">
          {label}
        </label>
        {hint ? (
          <span className="field-hint" id={`${id}-hint`}>
            {hint}
          </span>
        ) : null}
      </span>
    </div>
  );
}

/** A row of a form's actions: the primary one first, then the rest. */
export function FormActions({ children }: { children: ReactNode }) {
  return <div className="form-actions">{children}</div>;
}
