/**
 * The server's settings (theme, runs at once, confirm before delete), read
 * and written through react-query so every screen sees one copy.
 *
 * A theme change is applied to the page at once and then stored on the
 * server; if storing fails the page keeps the reader's choice for this
 * session and says the server did not record it, rather than flipping the
 * theme back under them.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef } from "react";

import { apiJson, apiPut } from "@/api/client";
import type { Settings, Theme } from "@/api/types";

import { describeError } from "./errors";
import { SettingsSchema } from "./schemas";
import { applyTheme, currentTheme } from "./theme";
import { notify } from "./toast";

export const SETTINGS_KEY = ["settings"] as const;

export function useSettings(enabled = true) {
  return useQuery({
    queryKey: SETTINGS_KEY,
    queryFn: () => apiJson<Settings>("/api/settings", {}, SettingsSchema),
    enabled,
    staleTime: 60_000,
  });
}

export function useSaveSettings() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (next: Settings) => apiPut<Settings>("/api/settings", next, SettingsSchema),
    onSuccess: (stored) => {
      client.setQueryData(SETTINGS_KEY, stored);
      // Offline mode and the GROMACS path change what capabilities report.
      void client.invalidateQueries({ queryKey: ["capabilities"] });
    },
  });
}

/** Choose a theme: applied now, stored on the server when settings are known. */
export function useSetTheme(): (choice: Theme) => void {
  const client = useQueryClient();
  const save = useSaveSettings();
  return useCallback(
    (choice: Theme) => {
      applyTheme(choice);
      const settings = client.getQueryData<Settings>(SETTINGS_KEY);
      if (!settings || settings.theme === choice) return;
      save.mutate(
        { ...settings, theme: choice },
        {
          onError: (e) =>
            notify("failed", "The theme was not saved on the server", { description: describeError(e).message }),
        },
      );
    },
    [client, save],
  );
}

/**
 * Once the server's settings arrive, adopt its theme if this browser
 * remembered a different one (a new browser, or a choice made in the
 * macOS app). Only the first answer is adopted; after that the reader's
 * own switches lead.
 */
export function useAdoptServerTheme(settings: Settings | undefined): void {
  const adopted = useRef(false);
  useEffect(() => {
    if (!settings || adopted.current) return;
    adopted.current = true;
    if (settings.theme !== currentTheme()) applyTheme(settings.theme);
  }, [settings]);
}
