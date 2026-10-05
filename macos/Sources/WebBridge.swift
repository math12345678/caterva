// The page's way to ask the shell for what a browser page cannot have: the
// path of a folder or file the person chooses, and a path shown in Finder.
//
// The contract (docs/studio/CONTRACT.md, section 16) names the handler and
// its three messages; the page's side is src/lib/desktop.ts in the studio
// package, which treats any answer that is not an absolute path as "none".
//
//   {action: "chooseDirectory", purpose}               -> "/abs/path" | null
//   {action: "chooseFile", purpose, extensions: [..]}  -> "/abs/path" | null
//   {action: "reveal", path}                           -> null
//   {action: "updateStatus"}                           -> {enabled, reason, version, build,
//                                                          lastCheck, automatic, prereleases,
//                                                          checking, note}
//   {action: "checkForUpdates"}                        -> null   (Sparkle's own window follows)
//   {action: "setUpdateOptions", automatic?, prereleases?} -> null
//   {action: "reportActiveRuns", count}                -> null   (how many runs the page sees
//                                                                 running, so an update asks
//                                                                 before it stops them)
//
// Only the studio server's own page, in the main frame, is answered. The
// panel is the person's choice, so a path comes back only when they chose
// one; the page never reads a file through this bridge, it only learns a
// location, which it then sends to the server under the rules of section 15.

import AppKit
import UniformTypeIdentifiers
import WebKit

/// The server's origin: http, a loopback host, the port it printed.
struct ServerOrigin: Equatable {
    let host: String
    let port: Int

    init?(_ url: URL) {
        guard url.scheme == "http", let host = url.host, let port = url.port,
              StudioServer.loopbackHosts.contains(host) else { return nil }
        self.host = host
        self.port = port
    }

    /// Whether `url` belongs to the page: the same origin, or a blob: URL the
    /// page minted (an export it built in memory), or about:blank.
    func contains(_ url: URL) -> Bool {
        switch url.scheme {
        case "http":
            return url.host == host && url.port == port
        case "blob":
            let inner = url.absoluteString.dropFirst("blob:".count)
            return URL(string: String(inner)).map(contains) ?? false
        case "about":
            return url.absoluteString == "about:blank" || url.absoluteString == "about:srcdoc"
        default:
            return false
        }
    }

    func matches(_ origin: WKSecurityOrigin) -> Bool {
        origin.protocol == "http" && StudioServer.loopbackHosts.contains(origin.host)
            && (origin.host == host || (["::1", "[::1]"].contains(origin.host) && ["::1", "[::1]"].contains(host)))
            && origin.port == port
    }
}

final class WebBridge: NSObject, WKScriptMessageHandlerWithReply {
    static let name = "caterva"
    static let actions = ["chooseDirectory", "chooseFile", "reveal", "updateStatus", "checkForUpdates",
                          "setUpdateOptions", "reportActiveRuns",
                          "setAssistantKey", "clearAssistantKey", "assistantKeyStatus"]

    weak var window: NSWindow?
    weak var updates: UpdateBridging?
    var origin: ServerOrigin?
    var assistantKeys: AssistantKeyBridge?
    /// Folders `reveal` may show: the server's data folder, which holds every
    /// run folder, plus each file or folder the person chose in a panel
    /// during this launch. Nothing else.
    var revealRoots: [URL] = []
    private var panelOpen = false

    /// Whether `path` is one of the roots or inside one, after links are
    /// resolved (a link inside a root cannot lead out of it).
    static func isRevealable(_ path: String, roots: [URL]) -> Bool {
        let target = URL(fileURLWithPath: path).resolvingSymlinksInPath().standardizedFileURL.path
        for root in roots {
            let base = root.resolvingSymlinksInPath().standardizedFileURL.path
            if target == base || target.hasPrefix(base.hasSuffix("/") ? base : base + "/") { return true }
        }
        return false
    }

    func userContentController(_ controller: WKUserContentController,
                               didReceive message: WKScriptMessage,
                               replyHandler: @escaping (Any?, String?) -> Void) {
        guard message.frameInfo.isMainFrame, let origin, origin.matches(message.frameInfo.securityOrigin) else {
            replyHandler(nil, "not the studio page")
            return
        }
        guard let body = message.body as? [String: Any], let action = body["action"] as? String else {
            replyHandler(nil, "a message needs an action")
            return
        }
        switch action {
        case "chooseDirectory":
            choose(directory: true, purpose: body["purpose"] as? String, extensions: [], reply: replyHandler)
        case "chooseFile":
            let extensions = (body["extensions"] as? [Any])?.compactMap { $0 as? String } ?? []
            choose(directory: false, purpose: body["purpose"] as? String, extensions: extensions, reply: replyHandler)
        case "reveal":
            guard let path = body["path"] as? String, path.hasPrefix("/"), !path.contains("\0") else {
                replyHandler(nil, "reveal needs an absolute path")
                return
            }
            guard WebBridge.isRevealable(path, roots: revealRoots) else {
                replyHandler(nil, "reveal only shows files in the studio's data folder or ones you chose")
                return
            }
            let url = URL(fileURLWithPath: path)
            guard FileManager.default.fileExists(atPath: url.path) else {
                replyHandler(nil, "nothing exists at \(path)")
                return
            }
            NSWorkspace.shared.activateFileViewerSelecting([url])
            replyHandler(nil, nil)
        case "updateStatus":
            guard let updates else { return replyHandler(nil, "updates are not available") }
            replyHandler(updates.updateStatus(), nil)
        case "checkForUpdates":
            guard let updates else { return replyHandler(nil, "updates are not available") }
            updates.checkForUpdates()
            replyHandler(nil, nil)
        case "setUpdateOptions":
            guard let updates else { return replyHandler(nil, "updates are not available") }
            let automatic = body["automatic"] as? Bool
            let prereleases = body["prereleases"] as? Bool
            guard automatic != nil || prereleases != nil else {
                return replyHandler(nil, "setUpdateOptions needs automatic or prereleases as true or false")
            }
            updates.setUpdateOptions(automatic: automatic, prereleases: prereleases)
            replyHandler(nil, nil)
        case "reportActiveRuns":
            guard let count = body["count"] as? Int, count >= 0, count < 10_000 else {
                return replyHandler(nil, "reportActiveRuns needs a count")
            }
            updates?.setActiveRuns(count)
            replyHandler(nil, nil)
        case "setAssistantKey":
            guard let assistantKeys, let provider = body["provider"] as? String, let key = body["key"] as? String else {
                replyHandler(nil, "could not store the key")
                return
            }
            replyHandler(assistantKeys.set(provider: provider, key: key), nil)
        case "clearAssistantKey":
            guard let assistantKeys, let provider = body["provider"] as? String else {
                replyHandler(nil, "could not remove the key")
                return
            }
            replyHandler(assistantKeys.clear(provider: provider), nil)
        case "assistantKeyStatus":
            replyHandler((body["provider"] as? String).map { assistantKeys?.status(provider: $0) ?? "absent" } ?? "absent", nil)
        default:
            replyHandler(nil, "unknown action \(action)")
        }
    }

    private func choose(directory: Bool, purpose: String?, extensions: [String],
                        reply: @escaping (Any?, String?) -> Void) {
        guard let window else {
            reply(nil, "no window")
            return
        }
        guard !panelOpen else {
            reply(nil, "a panel is already open")
            return
        }
        let panel = NSOpenPanel()
        panel.canChooseDirectories = directory
        panel.canChooseFiles = !directory
        panel.canCreateDirectories = directory
        panel.allowsMultipleSelection = false
        panel.resolvesAliases = true
        if let purpose, !purpose.isEmpty { panel.message = String(purpose.prefix(200)) }
        panel.prompt = directory ? "Choose Folder" : "Choose"
        let types = extensions
            .map { $0.trimmingCharacters(in: CharacterSet(charactersIn: ". ")) }
            .filter { !$0.isEmpty }
            .compactMap { UTType(filenameExtension: $0) }
        if !directory, !types.isEmpty { panel.allowedContentTypes = types }
        panelOpen = true
        panel.beginSheetModal(for: window) { [weak self] response in
            self?.panelOpen = false
            if response == .OK, let url = panel.url {
                self?.revealRoots.append(url)
                reply(url.path, nil)
            } else {
                reply(nil, nil)
            }
        }
    }
}

/// Mirrors the page's theme choice onto the window, so the title bar is ink
/// when the page is ink even while macOS is light, and the reverse.
///
/// Runs in its own content world, not the page's: the page cannot see it or
/// post to it, and it only reads one attribute of <html>, which the page sets
/// to "light" or "dark" when the person overrides the system appearance
/// (docs/studio/CONTRACT.md, section 17.2).
final class AppearanceMirror: NSObject, WKScriptMessageHandler {
    static let name = "catervaAppearance"
    static let world = WKContentWorld.world(name: "caterva-shell")
    static let source = """
    (() => {
      const root = document.documentElement;
      const post = () => {
        try { window.webkit.messageHandlers.\(name).postMessage(root.getAttribute("data-theme") || ""); } catch (e) {}
      };
      new MutationObserver(post).observe(root, { attributes: true, attributeFilter: ["data-theme"] });
      post();
    })();
    """

    weak var window: NSWindow?

    func userContentController(_ controller: WKUserContentController, didReceive message: WKScriptMessage) {
        guard message.frameInfo.isMainFrame, let theme = message.body as? String else { return }
        switch theme {
        case "dark": window?.appearance = NSAppearance(named: .darkAqua)
        case "light": window?.appearance = NSAppearance(named: .aqua)
        default: window?.appearance = nil
        }
    }
}
