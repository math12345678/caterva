// `Caterva --smoke [--require-page]`: start the server the app would start,
// wait for its address, ask it for the page over a real socket, stop it, and
// say what happened, one line per step. No window, no window server.
//
// scripts/build_studio_app.py runs this against the assembled bundle, and CI
// runs it on the DMG's copy, so a Caterva.app whose server cannot start (a
// folder copied without its libraries, a quarantined library, a missing
// page) fails the build instead of the first person who opens it.
//
// What it reports about the page, and never the session token itself:
//   the built page     index.html with the placeholder replaced by a token
//   the not-built page the server's own page saying how to build the UI
// `--require-page` fails the second; a development build may pass it.
//
// The server is started with `--data-dir` pointing at a temporary folder (the
// environment's CATERVA_STUDIO_DATA_DIR wins when set), so running the smoke
// check never touches ~/Library/Application Support/Caterva.

import Foundation

enum Smoke {
    static let placeholder = "__CATERVA_SESSION_TOKEN__"

    enum Page {
        case built
        case notBuilt
        case placeholderLeft
        case unexpected(String)

        var line: String {
            switch self {
            case .built: return "the built page, with a session token in place of the placeholder"
            case .notBuilt: return "the server's not-built page (the API runs; the UI was not built into this copy)"
            case .placeholderLeft: return "a page that still carries the token placeholder: it was not served by caterva studio"
            case .unexpected(let what): return "not a studio page: \(what)"
            }
        }
    }

    static func run(requirePage: Bool) -> Int32 {
        func say(_ text: String) {
            print("caterva smoke: \(text)")
            fflush(stdout)
        }

        let resolved: StudioCommand
        do {
            resolved = try StudioCommand.resolve()
        } catch {
            say("FAIL \(error)")
            return 1
        }
        // The smoke run must not read or write the person's real runs and
        // settings: it gets a data folder of its own, removed afterwards,
        // unless the environment already names one (a development build).
        let scratch = FileManager.default.temporaryDirectory
            .appendingPathComponent("caterva-smoke-\(UUID().uuidString)", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: scratch) }
        let command = StudioCommand(executable: resolved.executable,
                                    baseArguments: resolved.baseArguments,
                                    workingDirectory: resolved.workingDirectory,
                                    dataDirectory: resolved.dataDirectory ?? scratch.path,
                                    isDevelopment: resolved.isDevelopment)
        say("command \(command.display(port: 0))")
        let events = DispatchQueue(label: "caterva.smoke")
        let server = StudioServer(callbackQueue: events)
        let arrived = DispatchSemaphore(value: 0)
        var address: URL?
        var early: StudioServer.Exit?
        server.onURL = { url in
            address = url
            arrived.signal()
        }
        server.onExit = { exit in
            early = exit
            arrived.signal()
        }
        let started = Date()
        do {
            try server.start(command, port: 0)
        } catch {
            say("FAIL could not launch \(command.executable.path): \(error.localizedDescription)")
            return 1
        }
        say("server started, pid \(server.pid.map(String.init) ?? "gone already")")
        _ = arrived.wait(timeout: .now() + StudioServer.startTimeout + 10)
        let (url, exit) = events.sync { (address, early) }
        guard let url else {
            let ended = exit ?? server.lastExit
            say("FAIL the server printed no address (\(ended?.summary ?? "still running after the timeout"))")
            for line in (ended?.lastLines ?? []).suffix(20) { say("  | \(line)") }
            say("log: \(server.logURL.path)")
            server.stop()
            return 1
        }
        say(String(format: "url %@ after %.1f s", url.absoluteString, Date().timeIntervalSince(started)))

        let (status, body, failure) = fetch(url)
        var ok = true
        if let failure {
            say("FAIL GET / did not answer: \(failure)")
            ok = false
        } else {
            let page = classify(body)
            say("GET / -> \(status), \(page.line)")
            switch page {
            case .built: break
            case .notBuilt: if requirePage { say("FAIL --require-page: this copy has no built page"); ok = false }
            case .placeholderLeft, .unexpected: ok = false
            }
            if status != 200 { ok = false }
        }

        server.stop()
        if let ended = server.lastExit {
            let clean: Bool
            if case .exited(0) = ended.cause { clean = true } else { clean = false }
            say("server stopped (\(ended.summary)) after its stdin closed and SIGTERM")
            if !clean {
                say("FAIL the server did not stop cleanly")
                for line in ended.lastLines.suffix(20) { say("  | \(line)") }
                ok = false
            }
        } else {
            say("FAIL the server did not stop within \(Int(StudioServer.stopGrace + 3)) s")
            ok = false
        }
        say(ok ? "OK" : "FAILED; log: \(server.logURL.path)")
        return ok ? 0 : 1
    }

    static func fetch(_ url: URL) -> (Int, String, String?) {
        var request = URLRequest(url: url, cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: 15)
        request.setValue("text/html", forHTTPHeaderField: "Accept")
        let session = URLSession(configuration: .ephemeral)
        let done = DispatchSemaphore(value: 0)
        var status = 0
        var body = ""
        var failure: String?
        session.dataTask(with: request) { data, response, error in
            if let error {
                failure = error.localizedDescription
            } else {
                status = (response as? HTTPURLResponse)?.statusCode ?? 0
                body = String(decoding: data ?? Data(), as: UTF8.self)
            }
            done.signal()
        }.resume()
        if done.wait(timeout: .now() + 20) == .timedOut { failure = "no answer in 20 s" }
        session.invalidateAndCancel()
        return (status, body, failure)
    }

    /// Which page `/` answered with, read from the `caterva-session` meta tag.
    static func classify(_ html: String) -> Page {
        guard let tag = html.range(of: "name=\"caterva-session\"") else {
            if html.range(of: "<html", options: .caseInsensitive) != nil {
                return .notBuilt
            }
            return .unexpected("no HTML in the answer")
        }
        let after = html[tag.upperBound...]
        guard let open = after.range(of: "content=\""),
              let close = after[open.upperBound...].firstIndex(of: "\"") else {
            return .unexpected("a caterva-session tag without content")
        }
        let value = after[open.upperBound..<close]
        if value == placeholder { return .placeholderLeft }
        if value.isEmpty { return .unexpected("an empty session token") }
        return .built
    }
}
