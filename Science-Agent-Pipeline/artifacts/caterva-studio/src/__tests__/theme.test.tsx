import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import settings from "./fixtures/api/settings.json";
import { ThemeSwitch } from "@/components/shell/ThemeSwitch";
import { SETTINGS_KEY } from "@/lib/settings";
import { applyTheme, currentTheme, readStoredTheme, resetThemeForTests, resolveTheme, THEME_STORAGE_KEY } from "@/lib/theme";

import { json, mockServer, setSessionToken } from "./helpers";

const setMedia = (q: string, v: boolean) =>
  (window as unknown as { __setMedia: (q: string, v: boolean) => void }).__setMedia(q, v);

beforeEach(() => {
  resetThemeForTests();
  setSessionToken("token");
});
afterEach(() => {
  vi.unstubAllGlobals();
  setMedia("(prefers-color-scheme: dark)", false);
});

describe("the theme", () => {
  it("follows the system by default: no attribute, so the stylesheet's media query decides", () => {
    expect(currentTheme()).toBe("system");
    applyTheme("system");
    expect(document.documentElement.dataset.theme).toBeUndefined();
    expect(resolveTheme("system")).toBe("light");
    setMedia("(prefers-color-scheme: dark)", true);
    expect(resolveTheme("system")).toBe("dark");
  });

  it("puts a manual choice on <html> and remembers it for the next first paint", () => {
    applyTheme("dark");
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe("dark");
    resetThemeForTests();
    expect(readStoredTheme()).toBe("dark");
    // A manual light choice wins over a dark operating system.
    setMedia("(prefers-color-scheme: dark)", true);
    applyTheme("light");
    expect(resolveTheme(currentTheme())).toBe("light");
  });

  it("ignores a stored value that is not a theme", () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, "sepia");
    expect(readStoredTheme()).toBe("system");
  });

  it("is switched from the top bar and stored with the server's settings, keeping keys the page does not edit", async () => {
    const { seen } = mockServer((req) => (req.method === "PUT" ? json(200, req.body) : undefined));
    const client = new QueryClient();
    client.setQueryData(SETTINGS_KEY, settings.body);
    render(
      <QueryClientProvider client={client}>
        <ThemeSwitch />
      </QueryClientProvider>,
    );
    const dark = screen.getByRole("radio", { name: "Dark" });
    expect(screen.getByRole("radio", { name: "Follow the system" })).toBeChecked();
    await userEvent.click(dark);
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(dark).toBeChecked();
    const put = seen.find((r) => r.method === "PUT");
    expect(put?.url).toBe("/api/settings");
    expect(put?.body).toEqual({ ...settings.body, theme: "dark" });
  });
});
