// The one window: a WKWebView on the studio server's page, with a native view
// over it while there is no page to show (starting) or no server to show it
// from (the error view).
//
// Rules the window keeps (docs/studio/CONTRACT.md, section 16):
// - Only the server's own origin loads in the web view. A link anywhere else
//   (a citation, PubMed, RCSB) opens in the default browser.
// - <input type=file> gets the system open panel; an export the page builds
//   (a Blob with a download name, or an attachment from the server) goes
//   through a save panel as a WKDownload.
// - Unified title bar in the paper colour, ink in the dark appearance, and
//   it follows the page's own theme override (AppearanceMirror).
// - Minimum size 1024 x 680; the frame and the route are restored at launch.

import AppKit
import WebKit

final class StudioWindowController: NSWindowController, NSWindowDelegate, WKNavigationDelegate, WKUIDelegate, WKDownloadDelegate {
    static let minimumSize = NSSize(width: 1024, height: 680)
    static let frameName = "Caterva.MainWindow"
    private static let zoomKey = "Caterva.pageZoom"
    private static let zoomSteps: [CGFloat] = [0.75, 0.85, 1.0, 1.1, 1.25, 1.5, 1.75]

    var onRestart: (() -> Void)?

    private let isDevelopment: Bool
    private let container = NSView()
    private let bridge = WebBridge()
    private let mirror = AppearanceMirror()
    private var webView: WKWebView?
    private var titleObservation: NSKeyValueObservation?
    private var overlay: NSView?
    private var slowStart: DispatchWorkItem?
    private var baseURL: URL?
    private var origin: ServerOrigin?
    private(set) var showingPage = false
    private var pendingRoute: String?

    init(isDevelopment: Bool) {
        self.isDevelopment = isDevelopment
        let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1280, height: 820),
                              styleMask: [.titled, .closable, .miniaturizable, .resizable],
                              backing: .buffered, defer: false)
        window.title = isDevelopment ? "Caterva (development)" : "Caterva"
        window.titlebarAppearsTransparent = true
        window.titleVisibility = .visible
        window.toolbarStyle = .unified
        window.backgroundColor = Brand.ground
        window.contentMinSize = StudioWindowController.minimumSize
        window.isReleasedWhenClosed = false
        window.tabbingMode = .disallowed
        window.collectionBehavior.insert(.fullScreenPrimary)
        super.init(window: window)
        window.delegate = self
        window.contentView = container
        if !window.setFrameUsingName(StudioWindowController.frameName) {
            window.center()
        }
        window.setFrameAutosaveName(StudioWindowController.frameName)
        bridge.window = window
        mirror.window = window
    }

    required init?(coder: NSCoder) { nil }

    // MARK: - What the window shows

    func showLoading(_ message: String) {
        let view = LoadingView()
        view.message = message
        setOverlay(view)
        slowStart?.cancel()
        let later = DispatchWorkItem { [weak view] in
            view?.detailMessage = "Still starting. The first launch after installing can take longer while macOS checks the app's files."
        }
        slowStart = later
        DispatchQueue.main.asyncAfter(deadline: .now() + 10, execute: later)
    }

    func showProblem(_ problem: ServerProblem) {
        showingPage = false
        slowStart?.cancel()
        let view = ErrorView(problem: problem)
        view.onRestart = { [weak self] in self?.onRestart?() }
        setOverlay(view)
        webView?.isHidden = true
        window?.makeFirstResponder(view)
    }

    /// Load the page from a freshly started server, at `route` if it is one.
    func openPage(_ url: URL, route: String?) {
        guard let origin = ServerOrigin(url) else { return }
        self.origin = origin
        self.baseURL = url
        bridge.origin = origin
        (overlay as? LoadingView)?.message = "Opening the page"
        let web = webView ?? makeWebView()
        web.isHidden = true
        showingPage = false
        var target = url
        if let route = route ?? pendingRoute, StudioWindowController.isRoute(route),
           let routed = URL(string: route, relativeTo: url)?.absoluteURL, origin.contains(routed) {
            target = routed
        }
        pendingRoute = nil
        web.load(URLRequest(url: target))
    }

    /// The page's current route (path, query, fragment), if it is the server's page.
    var currentRoute: String? {
        guard let url = webView?.url, let origin, origin.contains(url), url.scheme == "http",
              var components = URLComponents(url: url, resolvingAgainstBaseURL: false) else { return nil }
        components.scheme = nil
        components.host = nil
        components.port = nil
        let route = components.string ?? "/"
        return StudioWindowController.isRoute(route) ? route : nil
    }

    /// A client-side route the page owns: begins with one slash, not the API,
    /// short, no control characters.
    static func isRoute(_ route: String) -> Bool {
        route.hasPrefix("/") && !route.hasPrefix("//") && !route.hasPrefix("/api/") && route != "/api"
            && route.count <= 2048 && route.unicodeScalars.allSatisfy { $0.value >= 0x20 && $0.value != 0x7F }
    }

    /// Move the page to `route` without reloading it: the page's router
    /// (wouter) follows the history API and popstate. Falls back to loading
    /// the route when the page is not up.
    func go(to route: String) {
        guard StudioWindowController.isRoute(route) else { return }
        guard showingPage, let webView, let baseURL else {
            pendingRoute = route
            return
        }
        let literal = (try? String(data: JSONSerialization.data(withJSONObject: [route]), encoding: .utf8))
            .map { String($0.dropFirst().dropLast()) } ?? "\"/\""
        let script = "history.pushState(null, '', \(literal)); window.dispatchEvent(new PopStateEvent('popstate', { state: null })); true"
        webView.evaluateJavaScript(script, in: nil, in: AppearanceMirror.world) { result in
            if case .failure = result, let url = URL(string: route, relativeTo: baseURL)?.absoluteURL {
                webView.load(URLRequest(url: url))
            }
        }
    }

    // MARK: - Commands

    var canNavigate: Bool { showingPage }
    var canGoBack: Bool { showingPage && (webView?.canGoBack ?? false) }
    var canGoForward: Bool { showingPage && (webView?.canGoForward ?? false) }

    func reloadPage() { if showingPage { webView?.reload() } }
    func goBack() { webView?.goBack() }
    func goForward() { webView?.goForward() }

    func zoom(by direction: Int) {
        guard let webView else { return }
        let steps = StudioWindowController.zoomSteps
        let current = steps.enumerated().min(by: { abs($0.element - webView.pageZoom) < abs($1.element - webView.pageZoom) })?.offset ?? 2
        let next = direction == 0 ? 2 : max(0, min(steps.count - 1, current + direction))
        webView.pageZoom = steps[next]
        UserDefaults.standard.set(Double(steps[next]), forKey: StudioWindowController.zoomKey)
    }

    // MARK: - Building the web view

    private func makeWebView() -> WKWebView {
        let controller = WKUserContentController()
        controller.addScriptMessageHandler(bridge, contentWorld: .page, name: WebBridge.name)
        controller.add(mirror, contentWorld: AppearanceMirror.world, name: AppearanceMirror.name)
        controller.addUserScript(WKUserScript(source: AppearanceMirror.source, injectionTime: .atDocumentEnd,
                                              forMainFrameOnly: true, in: AppearanceMirror.world))
        let configuration = WKWebViewConfiguration()
        configuration.userContentController = controller
        configuration.websiteDataStore = .default()
        configuration.preferences.javaScriptCanOpenWindowsAutomatically = false
        let version = Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "0"
        configuration.applicationNameForUserAgent = "CatervaStudio/\(version)"

        let web = WKWebView(frame: container.bounds, configuration: configuration)
        web.navigationDelegate = self
        web.uiDelegate = self
        web.allowsBackForwardNavigationGestures = true
        web.allowsMagnification = true
        web.underPageBackgroundColor = Brand.ground
        let savedZoom = UserDefaults.standard.double(forKey: StudioWindowController.zoomKey)
        if StudioWindowController.zoomSteps.contains(CGFloat(savedZoom)) { web.pageZoom = CGFloat(savedZoom) }
        if #available(macOS 13.3, *) { web.isInspectable = isDevelopment }
        web.translatesAutoresizingMaskIntoConstraints = false
        container.addSubview(web, positioned: .below, relativeTo: overlay)
        pin(web)
        titleObservation = web.observe(\.title, options: [.new]) { [weak self] web, _ in
            guard let self, let window = self.window else { return }
            let base = self.isDevelopment ? "Caterva (development)" : "Caterva"
            let title = web.title?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            window.title = title.isEmpty ? base : title
        }
        webView = web
        return web
    }

    private func pin(_ view: NSView) {
        NSLayoutConstraint.activate([
            view.leadingAnchor.constraint(equalTo: container.leadingAnchor),
            view.trailingAnchor.constraint(equalTo: container.trailingAnchor),
            view.topAnchor.constraint(equalTo: container.topAnchor),
            view.bottomAnchor.constraint(equalTo: container.bottomAnchor),
        ])
    }

    private func setOverlay(_ view: NSView?) {
        overlay?.removeFromSuperview()
        overlay = view
        guard let view else { return }
        view.translatesAutoresizingMaskIntoConstraints = false
        container.addSubview(view, positioned: .above, relativeTo: webView)
        pin(view)
    }

    /// The page painted: show it, and fade the loading view out (opacity only).
    private func revealPage() {
        guard let webView else { return }
        showingPage = true
        slowStart?.cancel()
        webView.isHidden = false
        guard let leaving = overlay else { return }
        overlay = nil
        if NSWorkspace.shared.accessibilityDisplayShouldReduceMotion {
            leaving.removeFromSuperview()
        } else {
            NSAnimationContext.runAnimationGroup({ context in
                context.duration = 0.35
                context.timingFunction = CAMediaTimingFunction(controlPoints: 0.16, 1, 0.3, 1)
                leaving.animator().alphaValue = 0
            }, completionHandler: { leaving.removeFromSuperview() })
        }
        window?.makeFirstResponder(webView)
    }

    // MARK: - WKNavigationDelegate

    func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction,
                 decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        guard let url = action.request.url else {
            decisionHandler(.cancel)
            return
        }
        let inside = origin?.contains(url) ?? false
        if action.shouldPerformDownload {
            decisionHandler(inside || url.scheme == "data" ? .download : .cancel)
            return
        }
        if inside {
            decisionHandler(.allow)
            return
        }
        decisionHandler(.cancel)
        if action.navigationType == .linkActivated, StudioWindowController.opensOutside(url) {
            NSWorkspace.shared.open(url)
        }
    }

    static func opensOutside(_ url: URL) -> Bool {
        ["http", "https", "mailto"].contains(url.scheme?.lowercased() ?? "")
    }

    func webView(_ webView: WKWebView, decidePolicyFor response: WKNavigationResponse,
                 decisionHandler: @escaping (WKNavigationResponsePolicy) -> Void) {
        if let http = response.response as? HTTPURLResponse,
           (http.value(forHTTPHeaderField: "Content-Disposition") ?? "").lowercased().hasPrefix("attachment") {
            decisionHandler(.download)
            return
        }
        decisionHandler(response.canShowMIMEType ? .allow : .download)
    }

    func webView(_ webView: WKWebView, navigationAction: WKNavigationAction, didBecome download: WKDownload) {
        download.delegate = self
    }

    func webView(_ webView: WKWebView, navigationResponse: WKNavigationResponse, didBecome download: WKDownload) {
        download.delegate = self
    }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        if !showingPage { revealPage() }
    }

    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        pageFailed(error)
    }

    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
        pageFailed(error)
    }

    private func pageFailed(_ error: Error) {
        let nsError = error as NSError
        // Cancelled (a new load replaced it) and "interrupted by policy change"
        // (the response became a download) are not failures.
        if nsError.domain == NSURLErrorDomain && nsError.code == NSURLErrorCancelled { return }
        if nsError.domain == "WebKitErrorDomain" && nsError.code == 102 { return }
        guard !showingPage else { return }
        showProblem(ServerProblem(
            title: "The page did not load",
            explanation: "The studio server said where it was listening, but the page could not be loaded from it: \(nsError.localizedDescription)",
            lines: [], logURL: Paths.serverLog, quarantineCommand: nil))
    }

    func webViewWebContentProcessDidTerminate(_ webView: WKWebView) {
        webView.reload()
    }

    // MARK: - WKUIDelegate

    func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration,
                 for action: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
        // target=_blank and window.open: the page's own routes stay in this
        // window, everything else goes to the default browser.
        if let url = action.request.url {
            if origin?.contains(url) ?? false, url.scheme == "http" {
                webView.load(URLRequest(url: url))
            } else if StudioWindowController.opensOutside(url) {
                NSWorkspace.shared.open(url)
            }
        }
        return nil
    }

    func webView(_ webView: WKWebView, runOpenPanelWith parameters: WKOpenPanelParameters,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping ([URL]?) -> Void) {
        guard let window else {
            completionHandler(nil)
            return
        }
        let panel = NSOpenPanel()
        panel.allowsMultipleSelection = parameters.allowsMultipleSelection
        panel.canChooseDirectories = parameters.allowsDirectories
        panel.canChooseFiles = true
        panel.resolvesAliases = true
        panel.beginSheetModal(for: window) { response in
            completionHandler(response == .OK ? panel.urls : nil)
        }
    }

    func webView(_ webView: WKWebView, runJavaScriptAlertPanelWithMessage message: String,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping () -> Void) {
        guard let window else {
            completionHandler()
            return
        }
        let alert = NSAlert()
        alert.messageText = message
        alert.addButton(withTitle: "OK")
        alert.beginSheetModal(for: window) { _ in completionHandler() }
    }

    func webView(_ webView: WKWebView, runJavaScriptConfirmPanelWithMessage message: String,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (Bool) -> Void) {
        guard let window else {
            completionHandler(false)
            return
        }
        let alert = NSAlert()
        alert.messageText = message
        alert.addButton(withTitle: "OK")
        alert.addButton(withTitle: "Cancel")
        alert.beginSheetModal(for: window) { response in completionHandler(response == .alertFirstButtonReturn) }
    }

    // MARK: - WKDownloadDelegate

    func download(_ download: WKDownload, decideDestinationUsing response: URLResponse,
                  suggestedFilename: String, completionHandler: @escaping (URL?) -> Void) {
        guard let window else {
            completionHandler(nil)
            return
        }
        let panel = NSSavePanel()
        panel.nameFieldStringValue = suggestedFilename
        panel.canCreateDirectories = true
        panel.isExtensionHidden = false
        panel.beginSheetModal(for: window) { response in
            guard response == .OK, let url = panel.url else {
                completionHandler(nil)
                return
            }
            // The save panel has already asked whether to replace an existing
            // file; WKDownload refuses to write over one, so move it to the Trash.
            if FileManager.default.fileExists(atPath: url.path) {
                try? FileManager.default.trashItem(at: url, resultingItemURL: nil)
            }
            completionHandler(url)
        }
    }

    func download(_ download: WKDownload, didFailWithError error: Error, resumeData: Data?) {
        guard let window else { return }
        let alert = NSAlert()
        alert.messageText = "The file was not saved"
        alert.informativeText = error.localizedDescription
        alert.beginSheetModal(for: window)
    }

    // MARK: - NSWindowDelegate

    func windowDidChangeEffectiveAppearance(_ notification: Notification) {
        webView?.underPageBackgroundColor = Brand.ground
    }
}
