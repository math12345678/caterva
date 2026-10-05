/**
 * The bridge to the macOS shell, when the page runs inside it.
 *
 * A browser page cannot learn a folder's path (an <input type=file> hands it
 * file contents, not a location), and `caterva md` and `caterva analyze` need
 * one. Inside Caterva.app the shell registers a WKScriptMessageHandlerWithReply
 * named "caterva" that answers the messages below with a native panel. In a
 * plain browser `isDesktop()` is false and screens fall back to a text field
 * for the path (docs/studio/CONTRACT.md, "Desktop bridge").
 */

type BridgeMessage =
  | { action: "chooseDirectory"; purpose: string }
  | { action: "chooseFile"; purpose: string; extensions: string[] }
  | { action: "reveal"; path: string }
  | { action: "updateStatus" }
  | { action: "checkForUpdates" }
  | { action: "setUpdateOptions"; automatic?: boolean; prereleases?: boolean }
  | { action: "reportActiveRuns"; count: number }
  | { action: "setAssistantKey"; provider: string; key: string }
  | { action: "clearAssistantKey"; provider: string }
  | { action: "assistantKeyStatus"; provider: string };

interface Bridge {
  postMessage(message: BridgeMessage): Promise<unknown>;
}

function bridge(): Bridge | null {
  const w = window as unknown as {
    webkit?: { messageHandlers?: { caterva?: Bridge } };
  };
  return w.webkit?.messageHandlers?.caterva ?? null;
}

export function isDesktop(): boolean {
  return bridge() !== null;
}

/** An absolute directory path, or null when cancelled or not in the app. */
export async function chooseDirectory(purpose: string): Promise<string | null> {
  const b = bridge();
  if (!b) return null;
  const answer = await b.postMessage({ action: "chooseDirectory", purpose });
  return typeof answer === "string" && answer.startsWith("/") ? answer : null;
}

/** An absolute file path, or null when cancelled or not in the app. */
export async function chooseFile(purpose: string, extensions: string[]): Promise<string | null> {
  const b = bridge();
  if (!b) return null;
  const answer = await b.postMessage({ action: "chooseFile", purpose, extensions });
  return typeof answer === "string" && answer.startsWith("/") ? answer : null;
}

/** Show a path in Finder. Does nothing outside the app. */
export async function reveal(path: string): Promise<void> {
  const b = bridge();
  if (b) await b.postMessage({ action: "reveal", path });
}

/**
 * What the shell reports about in-app updates (macos/Sources/Updater.swift).
 * `enabled` is false in a development build, with the reason; `lastCheck` is
 * an ISO 8601 time or null; `note` says when a feed could not be read.
 */
export interface UpdateStatus {
  enabled: boolean;
  reason: string | null;
  version: string;
  build: string;
  lastCheck: string | null;
  automatic: boolean;
  prereleases: boolean;
  checking: boolean;
  note: string | null;
}

function isUpdateStatus(value: unknown): value is UpdateStatus {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    typeof v.enabled === "boolean" &&
    typeof v.version === "string" &&
    typeof v.automatic === "boolean" &&
    typeof v.prereleases === "boolean" &&
    typeof v.checking === "boolean"
  );
}

/** The shell's update state, or null in a plain browser (or a shell without updates). */
export async function updateStatus(): Promise<UpdateStatus | null> {
  const b = bridge();
  if (!b) return null;
  const answer = await b.postMessage({ action: "updateStatus" });
  return isUpdateStatus(answer) ? answer : null;
}

/** Ask the shell to check now; Sparkle's own window shows the result. */
export async function checkForUpdates(): Promise<void> {
  const b = bridge();
  if (b) await b.postMessage({ action: "checkForUpdates" });
}

/** Turn automatic checks, or the prerelease feed, on or off. */
export async function setUpdateOptions(options: { automatic?: boolean; prereleases?: boolean }): Promise<void> {
  const b = bridge();
  if (b) await b.postMessage({ action: "setUpdateOptions", ...options });
}

/**
 * Tell the shell how many runs are going, so an update asks before it stops
 * them. Never throws: a shell that cannot take it just does not ask.
 */
export function reportActiveRuns(count: number): void {
  const b = bridge();
  if (b) void b.postMessage({ action: "reportActiveRuns", count }).catch(() => undefined);
}

/**
 * The assistant's key, kept by the shell in the login Keychain (CONTRACT.md 22.9). The page hands the key over
 * once and never stores it; the shell passes it to the server over a private channel. Outside the app there is no
 * bridge: the key then comes from the CATERVA_ASSISTANT_KEY environment variable and these return null.
 */
export async function setAssistantKey(provider: string, key: string): Promise<boolean | null> {
  const b = bridge();
  if (!b) return null;
  try {
    return (await b.postMessage({ action: "setAssistantKey", provider, key })) === null;
  } catch {
    return false;
  }
}

export async function clearAssistantKey(provider: string): Promise<boolean | null> {
  const b = bridge();
  if (!b) return null;
  try {
    await b.postMessage({ action: "clearAssistantKey", provider });
    return true;
  } catch {
    return false;
  }
}

/** "present" or "absent" from the Keychain, never the value; null outside the app. */
export async function assistantKeyStatus(provider: string): Promise<"present" | "absent" | null> {
  const b = bridge();
  if (!b) return null;
  try {
    const answer = await b.postMessage({ action: "assistantKeyStatus", provider });
    return answer === "present" ? "present" : "absent";
  } catch {
    return null;
  }
}

