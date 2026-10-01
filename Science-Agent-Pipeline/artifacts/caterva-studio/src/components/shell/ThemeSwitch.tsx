/**
 * The theme switch: follow the system, paper, or ink. The choice is
 * applied at once and stored with the server's settings (src/lib/settings.ts).
 */
import { Monitor, Moon, Sun } from "lucide-react";

import { Segmented } from "@/components/forms/Segmented";
import type { Theme } from "@/api/types";
import { useSetTheme } from "@/lib/settings";
import { useTheme } from "@/lib/theme";

export function ThemeSwitch({ withText = false }: { withText?: boolean }) {
  const { choice } = useTheme();
  const setTheme = useSetTheme();
  return (
    <Segmented<Theme>
      label="Theme"
      size="sm"
      value={choice}
      onChange={setTheme}
      options={[
        { value: "system", label: withText ? <><Monitor size={13} aria-hidden="true" /> System</> : <Monitor size={13} aria-hidden="true" />, ariaLabel: withText ? undefined : "Follow the system" },
        { value: "light", label: withText ? <><Sun size={13} aria-hidden="true" /> Light</> : <Sun size={13} aria-hidden="true" />, ariaLabel: withText ? undefined : "Light" },
        { value: "dark", label: withText ? <><Moon size={13} aria-hidden="true" /> Dark</> : <Moon size={13} aria-hidden="true" />, ariaLabel: withText ? undefined : "Dark" },
      ]}
    />
  );
}
