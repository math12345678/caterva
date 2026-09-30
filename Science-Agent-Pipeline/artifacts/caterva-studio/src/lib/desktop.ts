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
  | { action: "reveal"; path: string };

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
