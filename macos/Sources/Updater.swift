// In-app updates: Sparkle 2 checks a feed, downloads a zip of Caterva.app,
// checks it against the EdDSA key in Info.plist (SUPublicEDKey), and replaces
// the app. Nothing in the bundle holds a person's data (runs and settings are
// in ~/Library/Application Support/Caterva), so an update replaces code only.
//
// THE FEEDS (docs/studio/README.md, "Updates")
//   stable      https://github.com/math12345678/caterva/releases/latest/download/appcast.xml
//               GitHub serves the newest release that is not a prerelease.
//   prereleases the appcast.xml attached to the newest release of any kind,
//               whose address is read from the GitHub Releases API
//               (unauthenticated, so the answer is kept for an hour and a
//               failure falls back to the last good address, then to stable).
// The person chooses with "Include prereleases" in Settings; Info.plist's
// SUFeedURL is the stable one.
//
// WHAT HAPPENS AROUND AN INSTALL
// Sparkle quits the app to replace it. Quitting goes through
// AppDelegate.applicationShouldTerminate, which stops the server (stdin
// closed, SIGTERM, 5 s, SIGKILL) before the bundle is replaced, so no old
// server is left holding the data folder. If the page reports runs in
// progress, the shell asks before relaunching (confirmRelaunch).
//
// A development build (-D CATERVA_DEVELOPMENT) never checks: it runs from a
// checkout and has nothing to replace.

import AppKit
import Sparkle

/// What the page may ask about updates (WebBridge actions updateStatus,
/// checkForUpdates, setUpdateOptions, reportActiveRuns).
protocol UpdateBridging: AnyObject {
    func updateStatus() -> [String: Any]
    func checkForUpdates()
    func setUpdateOptions(automatic: Bool?, prereleases: Bool?)
    func setActiveRuns(_ count: Int)
}

/// The pure parts: which address the feed is at, and whether a release listing
/// names a usable one. Kept free of Sparkle and the network so
/// `Caterva --updater-selftest` can exercise them.
enum ReleaseFeed {
    static let repository = "math12345678/caterva"
    static let stable = "https://github.com/\(repository)/releases/latest/download/appcast.xml"
    static let listing = "https://api.github.com/repos/\(repository)/releases?per_page=15"
    static let assetName = "appcast.xml"
    static let timeToLive: TimeInterval = 3600

    /// Whether `text` is an appcast address this app is willing to follow:
    /// https, github.com, this repository's release downloads, and the right
    /// file name. The listing is data from the network; it does not get to
    /// point the updater anywhere else.
    static func isAcceptable(_ text: String) -> Bool {
        guard let url = URL(string: text), url.scheme == "https", url.host == "github.com",
              url.port == nil, url.user == nil, url.query == nil, url.fragment == nil else { return false }
        let prefix = "/\(repository)/releases/download/"
        guard url.path.hasPrefix(prefix), url.lastPathComponent == assetName else { return false }
        let tag = url.path.dropFirst(prefix.count).dropLast(assetName.count + 1)
        return !tag.isEmpty && !tag.contains("/") && tag != ".." && tag != "."
    }

    /// The appcast of the newest release that is not a draft and has one,
    /// prereleases included, from the Releases API's JSON (newest first).
    static func newestAppcast(in data: Data) -> String? {
        guard let releases = (try? JSONSerialization.jsonObject(with: data)) as? [[String: Any]] else { return nil }
        for release in releases {
            if release["draft"] as? Bool == true { continue }
            let assets = release["assets"] as? [[String: Any]] ?? []
            for asset in assets where asset["name"] as? String == assetName {
                if let address = asset["browser_download_url"] as? String, isAcceptable(address) { return address }
            }
        }
        return nil
    }

    /// Whether a bundle path is somewhere an update cannot replace it: a
    /// mounted disk image, or the read-only copy macOS runs a downloaded app
    /// from until it is moved.
    static func isRunningFromTransientLocation(_ path: String) -> Bool {
        path.hasPrefix("/Volumes/") || path.contains("/AppTranslocation/")
    }
}

final class UpdateController: NSObject, SPUUpdaterDelegate, UpdateBridging {
    private enum Key {
        static let prereleases = "Caterva.updates.prereleases"
        static let feed = "Caterva.updates.prereleaseFeed"
        static let feedDate = "Caterva.updates.prereleaseFeedAt"
    }

    /// Whether this build can update itself at all, and if not, why.
    let unavailableReason: String?
    private let defaults = UserDefaults.standard
    private var note: String?
    private var refreshing = false
    private var activeRuns = 0
    private var parkedRelaunch: (() -> Void)?
    weak var window: NSWindow?

    init(isDevelopment: Bool) {
        unavailableReason = isDevelopment ? "A development build runs from a checkout and does not update itself." : nil
        super.init()
    }

    /// Start Sparkle's own schedule. Called once, after launch.
    func start() {
        guard unavailableReason == nil else { return }
        controller.startUpdater()
        if prereleases { refreshFeed(force: false) {} }
    }

    // Created on first use, so that `self` exists to be its delegate; a
    // development build never touches it.
    private lazy var controller: SPUStandardUpdaterController = SPUStandardUpdaterController(
        startingUpdater: false, updaterDelegate: self, userDriverDelegate: nil)

    private var updater: SPUUpdater { controller.updater }

    var canCheck: Bool {
        unavailableReason == nil && updater.canCheckForUpdates
    }

    private var prereleases: Bool { defaults.bool(forKey: Key.prereleases) }

    // MARK: - Menu and page actions

    func checkForUpdates() {
        if let reason = unavailableReason { return explain("Updates are off in this build", reason) }
        if ReleaseFeed.isRunningFromTransientLocation(Bundle.main.bundlePath) {
            return explain("Move Caterva to the Applications folder first",
                           "Caterva is running from a disk image or a temporary location, where an update cannot replace it. "
                           + "Drag Caterva into Applications, eject the disk image, open it from there, and check again.")
        }
        guard !updater.sessionInProgress else { return }
        if prereleases {
            refreshFeed(force: true) { [weak self] in self?.controller.checkForUpdates(nil) }
        } else {
            note = nil
            controller.checkForUpdates(nil)
        }
    }

    func updateStatus() -> [String: Any] {
        let info = Bundle.main
        var status: [String: Any] = [
            "enabled": unavailableReason == nil,
            "reason": unavailableReason ?? NSNull(),
            "version": info.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "unknown",
            "build": info.object(forInfoDictionaryKey: "CFBundleVersion") as? String ?? "unknown",
            "prereleases": prereleases,
            "checking": refreshing,
            "note": note ?? NSNull(),
            "lastCheck": NSNull(),
            "automatic": false,
        ]
        if unavailableReason == nil {
            status["automatic"] = updater.automaticallyChecksForUpdates
            status["checking"] = refreshing || updater.sessionInProgress
            if let date = updater.lastUpdateCheckDate {
                status["lastCheck"] = ISO8601DateFormatter().string(from: date)
            }
        }
        return status
    }

    func setUpdateOptions(automatic: Bool?, prereleases wanted: Bool?) {
        guard unavailableReason == nil else { return }
        if let automatic { updater.automaticallyChecksForUpdates = automatic }
        if let wanted, wanted != prereleases {
            defaults.set(wanted, forKey: Key.prereleases)
            note = nil
            if wanted { refreshFeed(force: true) {} }
        }
    }

    func setActiveRuns(_ count: Int) {
        activeRuns = max(0, count)
        if activeRuns == 0, let go = parkedRelaunch {
            parkedRelaunch = nil
            go()
        }
    }

    // MARK: - The prerelease feed

    /// Read the newest release's appcast address from the Releases API into
    /// the user defaults, then call `done` (on the main queue) whatever the
    /// outcome: a failure keeps the last good address and says so in `note`.
    private func refreshFeed(force: Bool, done: @escaping () -> Void) {
        if !force, let when = defaults.object(forKey: Key.feedDate) as? Date,
           Date().timeIntervalSince(when) < ReleaseFeed.timeToLive,
           let kept = defaults.string(forKey: Key.feed), ReleaseFeed.isAcceptable(kept) {
            return done()
        }
        guard !refreshing, let url = URL(string: ReleaseFeed.listing) else { return done() }
        refreshing = true
        var request = URLRequest(url: url, cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: 20)
        request.setValue("application/vnd.github+json", forHTTPHeaderField: "Accept")
        request.setValue("Caterva-Studio-Updater", forHTTPHeaderField: "User-Agent")
        URLSession.shared.dataTask(with: request) { [weak self] data, response, error in
            DispatchQueue.main.async {
                guard let self else { return }
                self.refreshing = false
                let code = (response as? HTTPURLResponse)?.statusCode ?? 0
                if let data, error == nil, code == 200, let address = ReleaseFeed.newestAppcast(in: data) {
                    self.defaults.set(address, forKey: Key.feed)
                    self.defaults.set(Date(), forKey: Key.feedDate)
                    self.note = nil
                } else if let kept = self.defaults.string(forKey: Key.feed), ReleaseFeed.isAcceptable(kept) {
                    self.note = "GitHub's list of releases could not be read just now (\(Self.reason(code, error))), "
                        + "so the last known prerelease feed is used."
                } else {
                    self.note = "GitHub's list of releases could not be read (\(Self.reason(code, error))), "
                        + "so only stable releases are checked."
                }
                done()
            }
        }.resume()
    }

    private static func reason(_ code: Int, _ error: Error?) -> String {
        if code == 403 || code == 429 { return "GitHub is limiting requests from this network" }
        if code != 0 && code != 200 { return "HTTP \(code)" }
        return error?.localizedDescription ?? "no usable answer"
    }

    // MARK: - SPUUpdaterDelegate

    func feedURLString(for updater: SPUUpdater) -> String? {
        if prereleases, let kept = defaults.string(forKey: Key.feed), ReleaseFeed.isAcceptable(kept) { return kept }
        return ReleaseFeed.stable
    }

    /// Sparkle is about to quit the app and relaunch the new one. Quitting
    /// stops the server (AppDelegate.applicationShouldTerminate); the only
    /// thing to settle first is a run in progress.
    func updater(_ updater: SPUUpdater, shouldPostponeRelaunchForUpdate item: SUAppcastItem,
                 untilInvokingBlock installHandler: @escaping () -> Void) -> Bool {
        guard activeRuns > 0 else { return false }
        DispatchQueue.main.async { self.confirmRelaunch(item, proceed: installHandler) }
        return true
    }

    private func confirmRelaunch(_ item: SUAppcastItem, proceed: @escaping () -> Void) {
        guard activeRuns > 0 else { return proceed() }
        let alert = NSAlert()
        alert.alertStyle = .warning
        let noun = activeRuns == 1 ? "1 run is" : "\(activeRuns) runs are"
        alert.messageText = "\(noun) still going"
        alert.informativeText = "Caterva \(item.displayVersionString) is ready. Relaunching now stops the run"
            + (activeRuns == 1 ? "" : "s") + " and they will not finish. "
            + "If you wait, Caterva relaunches by itself when nothing is running."
        alert.addButton(withTitle: "Wait for the runs to finish")
        alert.addButton(withTitle: "Stop the runs and relaunch")
        let respond: (NSApplication.ModalResponse) -> Void = { [weak self] response in
            if response == .alertSecondButtonReturn {
                proceed()
            } else {
                self?.parkedRelaunch = proceed
            }
        }
        if let window { alert.beginSheetModal(for: window, completionHandler: respond) } else { respond(alert.runModal()) }
    }

    private func explain(_ title: String, _ text: String) {
        let alert = NSAlert()
        alert.messageText = title
        alert.informativeText = text
        if let window { alert.beginSheetModal(for: window) } else { alert.runModal() }
    }
}
