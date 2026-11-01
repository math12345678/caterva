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
//   the built page     index.html built from this package, holding no token
//   the not-built page the server's own page saying how to build the UI
// `--require-page` fails the second; a development build may pass it.
//
// It also checks the token arrangement (docs/studio/CONTRACT.md, section 4):
// the address the server printed carries the token in its URL fragment, no
// page the server answers holds it, /api/health without it is refused, and
// /api/health with it answers.
//
// The server is started with `--data-dir` pointing at a temporary folder (the
// environment's CATERVA_STUDIO_DATA_DIR wins when set), so running the smoke
// check never touches ~/Library/Application Support/Caterva.

import Foundation

enum Smoke {
    static let marker = "name=\"caterva-studio-page\""
    static let fragmentKey = "token"

    enum Page {
        case built
        case notBuilt
        case carriesToken
        case unexpected(String)

        var line: String {
            switch self {
            case .built: return "the built page, holding no session token"
            case .notBuilt: return "the server's not-built page (the API runs; the UI was not built into this copy)"
            case .carriesToken: return "a page that holds the session token: it must arrive in the URL fragment only"
            case .unexpected(let what): return "not a studio page: \(what)"
            }
        }
    }

    /// The token in an address's fragment, and the address without the fragment.
    static func split(_ url: URL) -> (base: URL, token: String?) {
        guard var components = URLComponents(url: url, resolvingAgainstBaseURL: false) else { return (url, nil) }
        var token: String?
        if let fragment = components.fragment {
            for pair in fragment.split(separator: "&") {
                let parts = pair.split(separator: "=", maxSplits: 1).map(String.init)
                if parts.count == 2, parts[0] == fragmentKey, !parts[1].isEmpty { token = parts[1] }
            }
        }
        components.fragment = nil
        return (components.url ?? url, token)
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
        let (base, token) = split(url)
        say(String(format: "url %@ after %.1f s", base.absoluteString, Date().timeIntervalSince(started)))
        var ok = true
        if token == nil {
            say("FAIL the address the server printed has no #\(fragmentKey)= fragment")
            ok = false
        } else {
            say("the address carries a session token in its URL fragment")
        }

        let (status, body, failure) = fetch(base)
        if let failure {
            say("FAIL GET / did not answer: \(failure)")
            ok = false
        } else {
            let page = classify(body, token: token)
            say("GET / -> \(status), \(page.line)")
            switch page {
            case .built: break
            case .notBuilt: if requirePage { say("FAIL --require-page: this copy has no built page"); ok = false }
            case .carriesToken, .unexpected: ok = false
            }
            if status != 200 { ok = false }
        }

        let health = base.appendingPathComponent("api/health")
        let (refusedStatus, _, refusedFailure) = fetch(health)
        if let refusedFailure {
            say("FAIL GET /api/health without the token did not answer: \(refusedFailure)")
            ok = false
        } else {
            say("GET /api/health without the token -> \(refusedStatus)")
            if refusedStatus != 401 { say("FAIL it must be refused with 401"); ok = false }
        }
        if let token {
            let (answered, _, answerFailure) = fetch(health, headers: ["X-Caterva-Session": token])
            if let answerFailure {
                say("FAIL GET /api/health with the token did not answer: \(answerFailure)")
                ok = false
            } else {
                say("GET /api/health with the token -> \(answered)")
                if answered != 200 { say("FAIL it must answer 200"); ok = false }
            }
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

    static func fetch(_ url: URL, headers: [String: String] = [:]) -> (Int, String, String?) {
        var request = URLRequest(url: url, cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: 15)
        request.setValue("text/html", forHTTPHeaderField: "Accept")
        for (name, value) in headers { request.setValue(value, forHTTPHeaderField: name) }
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

    /// Which page `/` answered with, read from the page marker.
    static func classify(_ html: String, token: String?) -> Page {
        if let token, html.contains(token) { return .carriesToken }
        guard html.range(of: marker) != nil else {
            if html.range(of: "<html", options: .caseInsensitive) != nil {
                return .notBuilt
            }
            return .unexpected("no HTML in the answer")
        }
        return .built
    }
}
