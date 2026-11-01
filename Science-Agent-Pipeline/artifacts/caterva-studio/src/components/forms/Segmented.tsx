/**
 * A segmented control: one of a few mutually exclusive choices, all
 * visible (a theme, a mode, a unit). It is a radio group underneath, so
 * arrow keys move between choices and a screen reader announces "1 of 3",
 * which is what it is; Radix supplies the roving focus.
 */
import * as RadioGroup from "@radix-ui/react-radio-group";
import type { ReactNode } from "react";

export interface SegmentOption<T extends string> {
  value: T;
  label: ReactNode;
  /** When the label is an icon alone. */
  ariaLabel?: string;
  disabled?: boolean;
}

export function Segmented<T extends string>({
  value,
  onChange,
  options,
  label,
  size = "md",
}: {
  value: T;
  onChange: (value: T) => void;
  options: readonly SegmentOption<T>[];
  /** The group's accessible name. */
  label: string;
  size?: "sm" | "md";
}) {
  return (
    <RadioGroup.Root
      className="segmented"
      data-size={size}
      value={value}
      onValueChange={(v) => onChange(v as T)}
      aria-label={label}
      orientation="horizontal"
      loop
    >
      {options.map((o) => (
        <RadioGroup.Item
          key={o.value}
          value={o.value}
          className="segmented-item"
          aria-label={o.ariaLabel}
          disabled={o.disabled}
        >
          {o.label}
        </RadioGroup.Item>
      ))}
    </RadioGroup.Root>
  );
}
