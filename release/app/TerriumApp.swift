// Terrium.app -- a window around the report builder, and nothing more.
//
// WHAT THIS IS
// ------------
// A native macOS shell that runs the bundled `terrium-report` binary and
// displays the document it returns. The binary is `scripts/report_lab.py`,
// frozen -- the same builder the CLI calls. This file does not simulate
// anything, does not fetch anything, and does not write a report.
//
// WHY IT MATTERS THAT IT DOES NOT
// -------------------------------
// scripts/demo.py states the rule, and the reason:
//
//     "A demo with its own rendering path is the worst kind of check that
//      cannot fail: it keeps looking impressive while the product it
//      advertises rots, and the discrepancy surfaces in front of the first
//      person who tries the real command."
//
// A desktop app is a demo that ships. So the document shown here is the
// builder's bytes, handed to viewer.html to typeset. If the builder starts
// failing, this window says so instead of showing a stale or invented
// document.
//
// NO NETWORK
// ----------
// The bundled BRENDA page is a committed fixture. This app makes no network
// requests at all, and the report it produces says so itself, in its own
// "What Terrium would not do" section -- which is where a reader looks
// before trusting a number.

import AppKit
import WebKit

// MARK: - Locating the bundled pieces

enum BundledResource {
    /// The frozen report builder, inside Contents/Resources.
    static func reportBinary() -> URL? {
        Bundle.main.url(forResource: "terrium-report", withExtension: nil)
    }

    /// The committed BRENDA page the report resolves Km from.
    static func fixture() -> URL? {
        Bundle.main.url(forResource: "brenda_ldh_fixture", withExtension: "html")
    }

    static func viewer() -> URL? {
        Bundle.main.url(forResource: "viewer", withExtension: "html")
    }
}

// MARK: - Running the builder

struct BuilderFailure: Error {
    let title: String
    let detail: String
}

enum ReportBuilder {
    /// The payload the CLI sends for this run.
    ///
    /// Kept identical to `scripts/demo.py`'s PAYLOAD on purpose: a shell that
    /// asked for something subtly different would be demonstrating a request
    /// nobody else makes.
    static func payload(fixture: URL) -> [String: Any] {
        [
            "title": "Lactate dehydrogenase in Homo sapiens",
            "question": "How fast is pyruvate consumed, and where did every number come from?",
            "ec": "1.1.1.27",
            "organism": "Homo sapiens",
            "fixture": fixture.path,
            "parameters": [["name": "km", "substrate": "pyruvate", "quantity": "km"]],
            "supplied": [
                ["name": "s0", "value": 10.0, "unit": "mM", "basis": "chosen for this run"],
                ["name": "vmax", "value": 0.25, "unit": "mM/s", "basis": "chosen for this run"],
            ],
            "s0": 10.0,
            "vmax": 0.25,
            "seed": 1,
        ]
    }

    /// Run the builder and return its parsed JSON.
    ///
    /// Every failure is returned as a `BuilderFailure` with something a person
    /// can act on. None is turned into an empty report: a window that shows
    /// nothing after a failed run is the shape this project keeps finding.
    static func run() throws -> [String: Any] {
        guard let binary = BundledResource.reportBinary() else {
            throw BuilderFailure(
                title: "The report builder is missing from this app",
                detail: "Contents/Resources/terrium-report was not found. "
                    + "The download is incomplete or damaged; fetch it again."
            )
        }
        guard let fixture = BundledResource.fixture() else {
            throw BuilderFailure(
                title: "The bundled BRENDA page is missing",
                detail: "Contents/Resources/brenda_ldh_fixture.html was not found. "
                    + "Terrium refuses to invent a Km rather than run without it."
            )
        }

        let process = Process()
        process.executableURL = binary
        let stdin = Pipe(), stdout = Pipe(), stderr = Pipe()
        process.standardInput = stdin
        process.standardOutput = stdout
        process.standardError = stderr

        let body = try JSONSerialization.data(withJSONObject: payload(fixture: fixture))

        do { try process.run() } catch {
            throw BuilderFailure(
                title: "The report builder would not start",
                detail: "\(error.localizedDescription)\n\nOn a first run macOS may "
                    + "quarantine the bundled binary. See the release notes."
            )
        }

        stdin.fileHandleForWriting.write(body)
        stdin.fileHandleForWriting.closeFile()

        let out = stdout.fileHandleForReading.readDataToEndOfFile()
        let err = stderr.fileHandleForReading.readDataToEndOfFile()
        process.waitUntilExit()

        guard let parsed = try? JSONSerialization.jsonObject(with: out) as? [String: Any] else {
            // Reported with the builder's own stderr. Swallowing this is how a
            // broken pipeline comes to look like an empty one.
            let text = String(data: err, encoding: .utf8) ?? ""
            throw BuilderFailure(
                title: "The report builder returned something unreadable",
                detail: "exit status \(process.terminationStatus)\n\n"
                    + (text.isEmpty ? "(no error output)" : String(text.suffix(1500)))
            )
        }
        return parsed
    }
}

// MARK: - Window

final class ViewerController: NSViewController, WKScriptMessageHandler {
    private var web: WKWebView!
    private var lastMarkdown = ""

    override func loadView() {
        let config = WKWebViewConfiguration()
        config.userContentController.add(self, name: "terrium")
        web = WKWebView(frame: NSRect(x: 0, y: 0, width: 940, height: 720), configuration: config)
        web.setValue(false, forKey: "drawsBackground")
        view = web
    }

    override func viewDidLoad() {
        super.viewDidLoad()
        guard let viewer = BundledResource.viewer() else {
            presentFatal("viewer.html is missing from this app bundle.")
            return
        }
        web.loadFileURL(viewer, allowingReadAccessTo: viewer.deletingLastPathComponent())
        // The first run starts once the page can receive the result.
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.35) { [weak self] in self?.runReport() }
    }

    private func presentFatal(_ message: String) {
        let alert = NSAlert()
        alert.messageText = "Terrium cannot start"
        alert.informativeText = message
        alert.alertStyle = .critical
        alert.runModal()
        NSApp.terminate(nil)
    }

    /// Hand a JSON payload to the page. Failures go through the same door as
    /// successes, so the viewer always knows which it got.
    private func deliver(_ object: [String: Any]) {
        guard let data = try? JSONSerialization.data(withJSONObject: object),
              let json = String(data: data, encoding: .utf8) else { return }
        web.evaluateJavaScript("window.terriumResult(\(json));")
    }

    func runReport() {
        web.evaluateJavaScript("window.terriumBusy && window.terriumBusy();")
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            let result: [String: Any]
            do {
                let parsed = try ReportBuilder.run()
                if let markdown = parsed["markdown"] as? String { self?.lastMarkdown = markdown }
                result = parsed
            } catch let failure as BuilderFailure {
                result = ["ok": false, "error": "\(failure.title)\n\n\(failure.detail)"]
            } catch {
                result = ["ok": false, "error": error.localizedDescription]
            }
            DispatchQueue.main.async { self?.deliver(result) }
        }
    }

    private func saveReport(_ markdown: String) {
        guard !markdown.isEmpty else { return }
        let panel = NSSavePanel()
        panel.nameFieldStringValue = "terrium-report.md"
        panel.allowedContentTypes = []
        panel.begin { response in
            guard response == .OK, let url = panel.url else { return }
            try? markdown.write(to: url, atomically: true, encoding: .utf8)
        }
    }

    func userContentController(_ controller: WKUserContentController,
                               didReceive message: WKScriptMessage) {
        guard let body = message.body as? [String: Any],
              let action = body["action"] as? String else { return }
        switch action {
        case "run": runReport()
        case "save": saveReport((body["markdown"] as? String) ?? lastMarkdown)
        default: break
        }
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    private var window: NSWindow!

    func applicationDidFinishLaunching(_ note: Notification) {
        let controller = ViewerController()
        window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 940, height: 720),
            styleMask: [.titled, .closable, .miniaturizable, .resizable],
            backing: .buffered, defer: false
        )
        window.title = "Terrium"
        window.titlebarAppearsTransparent = true
        window.contentViewController = controller
        window.center()
        window.setFrameAutosaveName("TerriumMain")
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ app: NSApplication) -> Bool { true }
}

// MARK: - Headless self-check
//
// `Terrium --selftest` runs the whole app-side path -- locate the bundled
// binary and fixture, send the payload, parse the reply, check the document
// discloses what it must -- and exits without opening a window.
//
// It exists because the build script could not otherwise verify the thing it
// ships. Its smoke test ran the frozen builder directly, which proves the
// builder works and says nothing about whether the app can find or drive it.
// Screen recording is unavailable in the build environment, so "launch it and
// look" was not a check either. This makes the app answerable.
func runSelfTest() -> Never {
    do {
        let result = try ReportBuilder.run()
        guard result["ok"] as? Bool == true,
              let markdown = result["markdown"] as? String, !markdown.isEmpty else {
            let reason = (result["error"] as? String) ?? "no document returned"
            FileHandle.standardError.write(Data("SELFTEST FAILED: \(reason)\n".utf8))
            exit(1)
        }
        // The disclosures that make this report worth shipping at all.
        for required in ["## Parameters", "## What Terrium would not do", "BRENDA"] {
            guard markdown.contains(required) else {
                FileHandle.standardError.write(
                    Data("SELFTEST FAILED: the report no longer contains \(required)\n".utf8))
                exit(1)
            }
        }
        print("SELFTEST OK: the app ran the bundled builder and got a "
              + "\(markdown.count)-character report with its provenance sections.")
        exit(0)
    } catch let failure as BuilderFailure {
        FileHandle.standardError.write(
            Data("SELFTEST FAILED: \(failure.title)\n\(failure.detail)\n".utf8))
        exit(1)
    } catch {
        FileHandle.standardError.write(
            Data("SELFTEST FAILED: \(error.localizedDescription)\n".utf8))
        exit(1)
    }
}

if CommandLine.arguments.contains("--selftest") { runSelfTest() }

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.regular)
app.run()
