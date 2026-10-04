// The application: the menus, the server's lifetime, and what the window
// shows while it lives.
//
// One server per launch, started before the window has anything to show and
// stopped when the app quits: stdin closed, SIGTERM, 5 s, SIGKILL
// (StudioServer.stop). The server's own rule, that it stops when its stdin
// closes, covers the case where this process dies without quitting.
//
// The menus are the standard macOS ones plus what the page cannot offer
// itself: Settings (Command-comma) moves the page to /settings, Reload, the
// data folder and the server log in Finder, and Help opening the repository's
// documents in the default browser. The Edit menu is the standard one so that
// Copy, Paste and Select All reach the web view through the responder chain.
//
// The route the page was on and the window's frame are kept in the user
// defaults, so the next launch opens where the last one closed.

import AppKit

final class AppDelegate: NSObject, NSApplicationDelegate, NSMenuItemValidation {
    static let repository = "https://github.com/math12345678/caterva"
    private static let routeKey = "Caterva.lastRoute"
    private static let firstRunKey = "Caterva.firstRunShown"

    private var controller: StudioWindowController?
    private var server: StudioServer?
    private var command: StudioCommand?
    private var quitting = false
    private var restarting = false

    // MARK: - Lifecycle

    func applicationDidFinishLaunching(_ notification: Notification) {
        let resolved = try? StudioCommand.resolve()
        command = resolved
        let window = StudioWindowController(isDevelopment: resolved?.isDevelopment ?? false)
        window.onRestart = { [weak self] in self?.restartServer() }
        controller = window
        NSApp.mainMenu = MainMenu.build(target: self)
        window.showWindow(nil)
        window.window?.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        startServer(route: UserDefaults.standard.string(forKey: AppDelegate.routeKey))
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }

    func applicationSupportsSecureRestorableState(_ app: NSApplication) -> Bool { true }

    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        rememberRoute()
        guard let server, server.isRunning else { return .terminateNow }
        quitting = true
        // Stopping can take the full grace period; the main thread keeps
        // drawing meanwhile and the reply comes when the server is gone.
        DispatchQueue.global(qos: .userInitiated).async {
            server.stop()
            DispatchQueue.main.async { sender.reply(toApplicationShouldTerminate: true) }
        }
        return .terminateLater
    }

    private func rememberRoute() {
        if let route = controller?.currentRoute {
            UserDefaults.standard.set(route, forKey: AppDelegate.routeKey)
        }
    }

    // MARK: - The server

    private func startServer(route: String?) {
        guard let controller else { return }
        let command: StudioCommand
        do {
            command = try StudioCommand.resolve()
        } catch {
            controller.showProblem(.missing(error))
            return
        }
        self.command = command
        controller.allowReveal(Paths.dataFolder(command))
        controller.showLoading(command.isDevelopment ? "Starting the studio server (development)" : "Starting the studio server")
        let server = StudioServer(callbackQueue: .main)
        server.onURL = { [weak self, weak controller] url in
            controller?.openPage(url, route: route)
            self?.showFirstRunIfNeeded()
        }
        server.onExit = { [weak self] exit in self?.serverEnded(exit) }
        self.server = server
        do {
            try server.start(command, port: 0)
        } catch {
            controller.showProblem(.launchFailed(error, logURL: server.logURL))
        }
    }

    private func serverEnded(_ exit: StudioServer.Exit) {
        guard !quitting, !restarting, let controller, let server else { return }
        let appPath = Bundle.main.bundlePath
        controller.showProblem(.ended(exit, logURL: server.logURL, appPath: appPath,
                                      quarantined: !(command?.isDevelopment ?? true) && isQuarantined(appPath)))
    }

    /// Stop whatever is running (off the main thread), then start afresh at
    /// the route the page was on.
    private func restartServer() {
        guard !restarting else { return }
        restarting = true
        let route = controller?.currentRoute ?? UserDefaults.standard.string(forKey: AppDelegate.routeKey)
        controller?.showLoading("Restarting the studio server")
        let previous = server
        DispatchQueue.global(qos: .userInitiated).async {
            previous?.stop()
            DispatchQueue.main.async { [weak self] in
                self?.restarting = false
                self?.startServer(route: route)
            }
        }
    }

    // MARK: - First run

    /// Once per installation: the app is not signed or notarised, what that
    /// means, and what the server does on this machine. The text is
    /// Resources/first-run.txt (macos/Resources/first-run.txt), so the DMG's
    /// README and this sheet are read and reviewed as text.
    private func showFirstRunIfNeeded() {
        let defaults = UserDefaults.standard
        guard !defaults.bool(forKey: AppDelegate.firstRunKey), let window = controller?.window,
              let url = Bundle.main.url(forResource: "first-run", withExtension: "txt"),
              let text = try? String(contentsOf: url, encoding: .utf8) else { return }
        let paragraphs = text.components(separatedBy: "\n\n")
        let alert = NSAlert()
        alert.messageText = paragraphs.first?.trimmingCharacters(in: .whitespacesAndNewlines) ?? "Caterva"
        alert.informativeText = paragraphs.dropFirst()
            .map { $0.replacingOccurrences(of: "\n", with: " ").trimmingCharacters(in: .whitespaces) }
            .joined(separator: "\n\n")
        alert.addButton(withTitle: "Continue")
        alert.beginSheetModal(for: window) { _ in defaults.set(true, forKey: AppDelegate.firstRunKey) }
    }

    // MARK: - Menu actions

    @objc func showAbout(_ sender: Any?) {
        let version = Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "unknown"
        let credits = NSMutableAttributedString()
        let body: [NSAttributedString.Key: Any] = [.font: NSFont.systemFont(ofSize: 11), .foregroundColor: NSColor.labelColor]
        credits.append(NSAttributedString(string:
            "Enzyme kinetics and molecular dynamics where every number says whether it was cited, measured, fitted or computed.\n\n"
            + "Caterva is free software under the Apache License 2.0. This app carries the Python runtime and the libraries "
            + "Caterva uses, each under its own licence; libSBML is under the GNU LGPL 2.1. Their texts are in the app "
            + "(Help, Licences), with those of the page's JavaScript packages and its typefaces, Spectral, "
            + "Atkinson Hyperlegible Next and DM Mono (SIL Open Font License 1.1). Enzyme names come from the "
            + "ExPASy ENZYME database (SIB Swiss Institute of Bioinformatics, CC BY 4.0); constants come from BRENDA "
            + "(CC BY 4.0) when you search the literature.\n\n"
            + "Not signed with an Apple Developer ID and not notarised.\n\n"
            + "Unaffiliated with Tellurium.", attributes: body))
        NSApp.orderFrontStandardAboutPanel(options: [
            .applicationName: "Caterva",
            .applicationVersion: version,
            .version: command?.isDevelopment == true ? "development build" : "",
            .credits: credits,
        ])
        NSApp.activate(ignoringOtherApps: true)
    }

    @objc func showSettings(_ sender: Any?) { controller?.go(to: "/settings") }
    @objc func goHome(_ sender: Any?) { controller?.go(to: "/") }
    @objc func goHistory(_ sender: Any?) { controller?.go(to: "/history") }
    @objc func reloadPage(_ sender: Any?) { controller?.reloadPage() }
    @objc func goBack(_ sender: Any?) { controller?.goBack() }
    @objc func goForward(_ sender: Any?) { controller?.goForward() }
    @objc func zoomIn(_ sender: Any?) { controller?.zoom(by: 1) }
    @objc func zoomOut(_ sender: Any?) { controller?.zoom(by: -1) }
    @objc func actualSize(_ sender: Any?) { controller?.zoom(by: 0) }
    @objc func restartServerAction(_ sender: Any?) { restartServer() }

    @objc func showDataFolder(_ sender: Any?) {
        let folder = Paths.dataFolder(command)
        if FileManager.default.fileExists(atPath: folder.path) {
            NSWorkspace.shared.activateFileViewerSelecting([folder])
        } else {
            explain("The data folder does not exist yet",
                    "The studio server creates \(Paths.abbreviated(folder)) the first time it starts.")
        }
    }

    @objc func showServerLog(_ sender: Any?) {
        let log = server?.logURL ?? Paths.serverLog
        if FileManager.default.fileExists(atPath: log.path) {
            NSWorkspace.shared.activateFileViewerSelecting([log])
        } else {
            explain("There is no server log yet", "It is written to \(Paths.abbreviated(log)) when the server starts.")
        }
    }

    @objc func showLicences(_ sender: Any?) {
        // The frozen folder's licences/ (scripts/build_app.py writes it), the
        // app's own LICENSE and NOTICE beside it, and the page's own
        // licences/ (THIRD-PARTY-NOTICES.txt for the page's JavaScript
        // packages, and the three typefaces' OFL texts), which the page build
        // writes and the wheel carries.
        guard let resources = Bundle.main.resourceURL else { return }
        let folder = resources.appendingPathComponent("caterva/licenses", isDirectory: true)
        let pageFolder = resources.appendingPathComponent("caterva/_internal/caterva/studio/static/licenses", isDirectory: true)
        let notice = resources.appendingPathComponent("caterva/NOTICE")
        let present = [folder, pageFolder, notice].filter { FileManager.default.fileExists(atPath: $0.path) }
        if present.isEmpty {
            explain("The licence files are not in this copy",
                    "A development build runs the server from a checkout; the licences are in the repository "
                    + "(LICENSE, NOTICE, third_party_licenses/).")
        } else {
            NSWorkspace.shared.activateFileViewerSelecting(present)
        }
    }

    @objc func openGuide(_ sender: Any?) { openRepository("blob/main/docs/USING_CATERVA.md") }
    @objc func openRepositoryHome(_ sender: Any?) { openRepository("") }
    @objc func reportIssue(_ sender: Any?) { openRepository("issues") }

    private func openRepository(_ path: String) {
        let text = path.isEmpty ? AppDelegate.repository : "\(AppDelegate.repository)/\(path)"
        if let url = URL(string: text) { NSWorkspace.shared.open(url) }
    }

    private func explain(_ title: String, _ text: String) {
        let alert = NSAlert()
        alert.messageText = title
        alert.informativeText = text
        if let window = controller?.window { alert.beginSheetModal(for: window) } else { alert.runModal() }
    }

    func validateMenuItem(_ item: NSMenuItem) -> Bool {
        switch item.action {
        case #selector(reloadPage(_:)), #selector(showSettings(_:)), #selector(goHome(_:)), #selector(goHistory(_:)),
             #selector(zoomIn(_:)), #selector(zoomOut(_:)), #selector(actualSize(_:)):
            return controller?.canNavigate ?? false
        case #selector(goBack(_:)):
            return controller?.canGoBack ?? false
        case #selector(goForward(_:)):
            return controller?.canGoForward ?? false
        default:
            return true
        }
    }
}

/// The menu bar, built in code (there is no nib).
enum MainMenu {
    static func build(target: AppDelegate) -> NSMenu {
        let bar = NSMenu()

        func item(_ title: String, _ action: Selector?, _ key: String = "",
                  _ modifiers: NSEvent.ModifierFlags = .command, to object: AnyObject? = nil) -> NSMenuItem {
            let entry = NSMenuItem(title: title, action: action, keyEquivalent: key)
            entry.keyEquivalentModifierMask = modifiers
            entry.target = object
            return entry
        }

        func submenu(_ title: String, _ items: [NSMenuItem]) -> NSMenu {
            let menu = NSMenu(title: title)
            items.forEach(menu.addItem)
            let holder = NSMenuItem(title: title, action: nil, keyEquivalent: "")
            holder.submenu = menu
            bar.addItem(holder)
            return menu
        }

        let services = NSMenu(title: "Services")
        let servicesItem = NSMenuItem(title: "Services", action: nil, keyEquivalent: "")
        servicesItem.submenu = services
        NSApp.servicesMenu = services
        _ = submenu("Caterva", [
            item("About Caterva", #selector(AppDelegate.showAbout(_:)), to: target),
            .separator(),
            item("Settings…", #selector(AppDelegate.showSettings(_:)), ",", to: target),
            .separator(),
            servicesItem,
            .separator(),
            item("Hide Caterva", #selector(NSApplication.hide(_:)), "h"),
            item("Hide Others", #selector(NSApplication.hideOtherApplications(_:)), "h", [.command, .option]),
            item("Show All", #selector(NSApplication.unhideAllApplications(_:))),
            .separator(),
            item("Quit Caterva", #selector(NSApplication.terminate(_:)), "q"),
        ])

        _ = submenu("File", [
            item("Show Data Folder in Finder", #selector(AppDelegate.showDataFolder(_:)), "d", [.command, .shift], to: target),
            item("Show Server Log in Finder", #selector(AppDelegate.showServerLog(_:)), to: target),
            .separator(),
            item("Restart Server", #selector(AppDelegate.restartServerAction(_:)), to: target),
            .separator(),
            item("Close Window", #selector(NSWindow.performClose(_:)), "w"),
        ])

        // Standard selectors with no target: they travel the responder chain
        // to the web view, which handles copy, paste, undo and select all.
        _ = submenu("Edit", [
            item("Undo", Selector(("undo:")), "z"),
            item("Redo", Selector(("redo:")), "z", [.command, .shift]),
            .separator(),
            item("Cut", #selector(NSText.cut(_:)), "x"),
            item("Copy", #selector(NSText.copy(_:)), "c"),
            item("Paste", #selector(NSText.paste(_:)), "v"),
            item("Paste and Match Style", #selector(NSTextView.pasteAsPlainText(_:)), "v", [.command, .option, .shift]),
            item("Delete", #selector(NSText.delete(_:))),
            item("Select All", #selector(NSText.selectAll(_:)), "a"),
        ])

        _ = submenu("View", [
            item("Reload Page", #selector(AppDelegate.reloadPage(_:)), "r", to: target),
            .separator(),
            item("Actual Size", #selector(AppDelegate.actualSize(_:)), "0", to: target),
            item("Zoom In", #selector(AppDelegate.zoomIn(_:)), "+", to: target),
            item("Zoom Out", #selector(AppDelegate.zoomOut(_:)), "-", to: target),
            .separator(),
            item("Enter Full Screen", #selector(NSWindow.toggleFullScreen(_:)), "f", [.command, .control]),
        ])

        _ = submenu("Go", [
            item("Back", #selector(AppDelegate.goBack(_:)), "[", to: target),
            item("Forward", #selector(AppDelegate.goForward(_:)), "]", to: target),
            .separator(),
            item("Home", #selector(AppDelegate.goHome(_:)), "h", [.command, .shift], to: target),
            item("History", #selector(AppDelegate.goHistory(_:)), "y", to: target),
        ])

        let window = submenu("Window", [
            item("Minimize", #selector(NSWindow.performMiniaturize(_:)), "m"),
            item("Zoom", #selector(NSWindow.performZoom(_:))),
            .separator(),
            item("Bring All to Front", #selector(NSApplication.arrangeInFront(_:))),
        ])
        NSApp.windowsMenu = window

        let help = submenu("Help", [
            item("Using Caterva", #selector(AppDelegate.openGuide(_:)), "?", to: target),
            item("Caterva on GitHub", #selector(AppDelegate.openRepositoryHome(_:)), to: target),
            item("Report a Problem", #selector(AppDelegate.reportIssue(_:)), to: target),
            .separator(),
            item("Licences", #selector(AppDelegate.showLicences(_:)), to: target),
        ])
        NSApp.helpMenu = help
        return bar
    }
}
