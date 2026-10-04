// The `caterva studio` process: which command to run, running it, reading the
// one line that says where it is listening, and stopping it.
//
// Foundation only, no AppKit: `Caterva --smoke` uses this file with no window
// server, so a build machine can prove the bundled server starts and answers
// without opening a window.
//
// The contract (docs/studio/CONTRACT.md, sections 2 and 16) fixes the
// protocol. The shell runs `caterva studio --port N --no-browser --print-url`
// with stdin a pipe it holds open, reads stdout until the line
// `CATERVA_STUDIO_URL=<url>`, and gives up after 60 s. The server stops when
// that pipe closes, so a shell that crashes cannot leave a server behind; on
// an ordinary quit the shell closes the pipe, sends SIGTERM, waits 5 s and
// then sends SIGKILL.
//
// The URL is believed only if it names a loopback host. A line that names
// anything else is not followed: the shell would otherwise load whatever a
// replaced executable printed.

import Darwin
import Foundation

struct StudioCommand {
    /// Development override: the command to run instead of the bundled one,
    /// as a JSON array of strings or as words separated by spaces, the first
    /// an absolute path to an executable. The studio flags are appended.
    ///   CATERVA_STUDIO_COMMAND='/path/to/.venv/bin/python -m caterva.app studio'
    ///
    /// Honoured only by a build made with `-D CATERVA_DEVELOPMENT` (the
    /// `--dev` build of scripts/build_studio_app.py) AND when
    /// `CATERVA_STUDIO_DEV=1` is set or the marker file exists. A release
    /// build ignores these variables whatever the environment holds: an
    /// environment variable is something any process that starts the app can
    /// set, and it would otherwise choose the program the app runs.
    static let commandKey = "CATERVA_STUDIO_COMMAND"
    static let developmentKey = "CATERVA_STUDIO_DEV"
    /// An empty file whose presence, in a development build, switches the
    /// development variables on without setting an environment variable.
    static var developmentMarker: URL {
        let support = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first
            ?? URL(fileURLWithPath: NSHomeDirectory()).appendingPathComponent("Library/Application Support")
        return support.appendingPathComponent("Caterva/development-marker")
    }

    /// Whether the development variables count: a development build, and an
    /// explicit switch. Always false in a release build.
    static func developmentEnabled(environment: [String: String],
                                   markerExists: (URL) -> Bool = { FileManager.default.fileExists(atPath: $0.path) }) -> Bool {
        #if CATERVA_DEVELOPMENT
        return environment[developmentKey] == "1" || markerExists(developmentMarker)
        #else
        return false
        #endif
    }
    /// Working directory for the development command (a checkout, so that
    /// `python -m caterva.app` imports that checkout's package).
    static let directoryKey = "CATERVA_STUDIO_CWD"
    /// Passed as `--data-dir`, so a development build need not share the
    /// installed app's runs and settings.
    static let dataDirectoryKey = "CATERVA_STUDIO_DATA_DIR"

    let executable: URL
    let baseArguments: [String]
    let workingDirectory: URL?
    let dataDirectory: String?
    let isDevelopment: Bool

    enum Failure: Error, CustomStringConvertible {
        case bundledServerMissing(String)
        case notExecutable(String)
        case malformed(String)

        var description: String {
            switch self {
            case .bundledServerMissing(let path):
                return "The server is not inside this copy of Caterva: nothing at \(path). "
                    + "The app was assembled without its frozen `caterva` folder; download it again."
            case .notExecutable(let path):
                return "\(path) is not an executable file."
            case .malformed(let reason):
                return reason
            }
        }
    }

    static func resolve(bundle: Bundle = .main,
                        environment: [String: String] = ProcessInfo.processInfo.environment) throws -> StudioCommand {
        let development = developmentEnabled(environment: environment)
        let dataDirectory = development
            ? try absoluteDirectory(environment[dataDirectoryKey], key: dataDirectoryKey, mustExist: false) : nil
        if development, let raw = environment[commandKey]?.trimmingCharacters(in: .whitespacesAndNewlines), !raw.isEmpty {
            let words = try split(raw)
            guard let first = words.first, first.hasPrefix("/") else {
                throw Failure.malformed("\(commandKey) must start with an absolute path to an executable; it starts with \(words.first ?? "nothing").")
            }
            guard FileManager.default.isExecutableFile(atPath: first) else { throw Failure.notExecutable(first) }
            let directory = try absoluteDirectory(environment[directoryKey], key: directoryKey, mustExist: true)
            return StudioCommand(executable: URL(fileURLWithPath: first),
                                 baseArguments: Array(words.dropFirst()),
                                 workingDirectory: directory.map { URL(fileURLWithPath: $0, isDirectory: true) },
                                 dataDirectory: dataDirectory,
                                 isDevelopment: true)
        }
        let bundled = bundledExecutable(bundle)
        guard FileManager.default.fileExists(atPath: bundled.path) else { throw Failure.bundledServerMissing(bundled.path) }
        guard FileManager.default.isExecutableFile(atPath: bundled.path) else { throw Failure.notExecutable(bundled.path) }
        return StudioCommand(executable: bundled, baseArguments: ["studio"], workingDirectory: nil,
                             dataDirectory: dataDirectory, isDevelopment: false)
    }

    /// Caterva.app/Contents/Resources/caterva/caterva: the PyInstaller folder
    /// scripts/build_app.py writes, copied whole.
    static func bundledExecutable(_ bundle: Bundle) -> URL {
        let resources = bundle.resourceURL ?? bundle.bundleURL.appendingPathComponent("Contents/Resources")
        return resources.appendingPathComponent("caterva/caterva")
    }

    static func split(_ raw: String) throws -> [String] {
        if raw.hasPrefix("[") {
            guard let data = raw.data(using: .utf8),
                  let array = try? JSONSerialization.jsonObject(with: data) as? [String], !array.isEmpty else {
                throw Failure.malformed("\(commandKey) starts with [ but is not a JSON array of strings.")
            }
            return array
        }
        return raw.split(whereSeparator: { $0 == " " || $0 == "\t" }).map(String.init)
    }

    private static func absoluteDirectory(_ value: String?, key: String, mustExist: Bool) throws -> String? {
        guard let value = value?.trimmingCharacters(in: .whitespacesAndNewlines), !value.isEmpty else { return nil }
        guard value.hasPrefix("/") else { throw Failure.malformed("\(key) must be an absolute path; it is \(value).") }
        if mustExist {
            var isDirectory: ObjCBool = false
            guard FileManager.default.fileExists(atPath: value, isDirectory: &isDirectory), isDirectory.boolValue else {
                throw Failure.malformed("\(key) is not a directory: \(value).")
            }
        }
        return value
    }

    func arguments(port: Int) -> [String] {
        var arguments = baseArguments + ["--port", String(port), "--no-browser", "--print-url"]
        if let dataDirectory { arguments += ["--data-dir", dataDirectory] }
        return arguments
    }

    func display(port: Int) -> String {
        ([executable.path] + arguments(port: port)).joined(separator: " ")
    }

    /// The server inherits the shell's environment, less what would make the
    /// frozen interpreter load somebody else's Python or library: in a
    /// release build every PYTHON*, DYLD_* and CATERVA_STUDIO_* variable is
    /// dropped (the two the server needs are set after), in a development
    /// run only PYTHONHOME is.
    func environment(_ base: [String: String] = ProcessInfo.processInfo.environment) -> [String: String] {
        var environment = base
        environment.removeValue(forKey: "PYTHONHOME")
        if !isDevelopment {
            for key in Array(environment.keys)
            where key.hasPrefix("PYTHON") || key.hasPrefix("DYLD_") || key.hasPrefix("CATERVA_STUDIO_") {
                environment.removeValue(forKey: key)
            }
        }
        environment["PYTHONUNBUFFERED"] = "1"
        environment["PYTHONUTF8"] = "1"
        return environment
    }
}

final class StudioServer {
    static let urlPrefix = "CATERVA_STUDIO_URL="
    static let startTimeout: TimeInterval = 60
    static let stopGrace: TimeInterval = 5
    static let loopbackHosts: Set<String> = ["127.0.0.1", "::1", "[::1]", "localhost"]
    private static let tailLength = 40

    struct Exit {
        enum Cause {
            case exited(Int32)
            case signalled(Int32)
            case timedOut
        }

        let cause: Cause
        /// True when the process ended before printing its address.
        let beforeURL: Bool
        /// The last lines of stderr (and any stray stdout), oldest first.
        let lastLines: [String]

        var summary: String {
            switch cause {
            case .exited(let status): return "exit status \(status)"
            case .signalled(let signal): return "stopped by signal \(signal) (\(String(cString: strsignal(signal))))"
            case .timedOut: return "no address after \(Int(StudioServer.startTimeout)) s; stopped"
            }
        }
    }

    let logURL: URL
    var onURL: ((URL) -> Void)?
    var onExit: ((Exit) -> Void)?
    /// The last run's end, whether or not it was asked for.
    private(set) var lastExit: Exit?

    private let callbackQueue: DispatchQueue
    private let queue = DispatchQueue(label: "caterva.studio.server")
    private var process: Process?
    private var stdinPipe: Pipe?
    private var generation = 0
    private var stdoutRemainder = Data()
    private var stderrRemainder = Data()
    private var tail: [String] = []
    private var urlSeen = false
    private var stopRequested = false
    private var timedOut = false
    private var terminated = false
    private var openStreams = 0
    private var finished = false
    private var finishedSignal = DispatchSemaphore(value: 0)
    private var log: FileHandle?

    init(logURL: URL = Paths.serverLog, callbackQueue: DispatchQueue) {
        self.logURL = logURL
        self.callbackQueue = callbackQueue
    }

    var pid: Int32? { queue.sync { process?.processIdentifier } }
    var isRunning: Bool { queue.sync { process?.isRunning ?? false } }

    func start(_ command: StudioCommand, port: Int) throws {
        try queue.sync {
            if let running = process, running.isRunning {
                throw StudioCommand.Failure.malformed("The server is already running (pid \(running.processIdentifier)).")
            }
            generation += 1
            let current = generation
            stdoutRemainder = Data()
            stderrRemainder = Data()
            tail = []
            urlSeen = false
            stopRequested = false
            timedOut = false
            terminated = false
            finished = false
            openStreams = 2
            finishedSignal = DispatchSemaphore(value: 0)
            openLog(command.display(port: port))

            let child = Process()
            child.executableURL = command.executable
            child.arguments = command.arguments(port: port)
            child.environment = command.environment()
            if let directory = command.workingDirectory { child.currentDirectoryURL = directory }
            let input = Pipe(), output = Pipe(), errors = Pipe()
            child.standardInput = input
            child.standardOutput = output
            child.standardError = errors
            child.terminationHandler = { [weak self] _ in
                self?.queue.async { self?.terminatedProcess(current) }
            }
            do {
                try child.run()
            } catch {
                writeLog("could not launch: \(error.localizedDescription)\n")
                closeLog()
                throw error
            }
            process = child
            stdinPipe = input
            readUntilEOF(output.fileHandleForReading, generation: current, isStdout: true)
            readUntilEOF(errors.fileHandleForReading, generation: current, isStdout: false)
            queue.asyncAfter(deadline: .now() + StudioServer.startTimeout) { [weak self] in
                self?.startTimedOut(current)
            }
        }
    }

    /// Close stdin, SIGTERM, wait `grace` seconds, SIGKILL. Blocks; call it
    /// off the main thread when the main thread has a window to keep alive.
    func stop(grace: TimeInterval = StudioServer.stopGrace) {
        let (child, input, done): (Process?, Pipe?, DispatchSemaphore) = queue.sync {
            stopRequested = true
            return (process, stdinPipe, finishedSignal)
        }
        guard let child else { return }
        try? input?.fileHandleForWriting.close()
        if child.isRunning { kill(child.processIdentifier, SIGTERM) }
        if done.wait(timeout: .now() + grace) == .timedOut {
            if child.isRunning { kill(child.processIdentifier, SIGKILL) }
            _ = done.wait(timeout: .now() + 3)
        }
        done.signal()   // leave it signalled for any later waiter
    }

    // MARK: - Reading

    /// A blocking read loop per stream, on its own thread. `read(2)` rather
    /// than FileHandle.availableData, which raises an Objective-C exception
    /// on a read error that Swift cannot catch.
    private func readUntilEOF(_ handle: FileHandle, generation current: Int, isStdout: Bool) {
        let descriptor = handle.fileDescriptor
        Thread.detachNewThread { [weak self] in
            var buffer = [UInt8](repeating: 0, count: 65_536)
            while true {
                let count = buffer.withUnsafeMutableBytes { read(descriptor, $0.baseAddress, $0.count) }
                if count > 0 {
                    let data = Data(buffer[0..<count])
                    self?.queue.async { self?.consume(data, generation: current, isStdout: isStdout) }
                } else if count < 0 && errno == EINTR {
                    continue
                } else {
                    break
                }
            }
            try? handle.close()
            self?.queue.async { self?.streamClosed(current) }
        }
    }

    private func consume(_ data: Data, generation current: Int, isStdout: Bool) {
        guard current == generation else { return }
        if isStdout {
            stdoutRemainder.append(data)
            for line in takeLines(&stdoutRemainder) { stdoutLine(line) }
        } else {
            writeLog(data)
            stderrRemainder.append(data)
            for line in takeLines(&stderrRemainder) { remember(line) }
        }
    }

    private func takeLines(_ buffer: inout Data) -> [String] {
        var lines: [String] = []
        while let newline = buffer.firstIndex(of: 0x0A) {
            let lineData = buffer[buffer.startIndex..<newline]
            lines.append(String(decoding: lineData, as: UTF8.self).trimmingCharacters(in: CharacterSet(charactersIn: "\r")))
            buffer.removeSubrange(buffer.startIndex...newline)
        }
        return lines
    }

    private func stdoutLine(_ line: String) {
        if !urlSeen, line.hasPrefix(StudioServer.urlPrefix) {
            let value = String(line.dropFirst(StudioServer.urlPrefix.count)).trimmingCharacters(in: .whitespaces)
            if let url = StudioServer.loopbackURL(value) {
                urlSeen = true
                writeLog("listening at \(StudioServer.withoutFragment(url).absoluteString)\n")
                let callback = onURL
                callbackQueue.async { callback?(url) }
            } else {
                let shown = StudioServer.withoutFragment(URL(string: value)) ?? "(unreadable)"
                writeLog("ignored an address that is not a loopback http URL: \(shown)\n")
                remember("(the server printed an address that is not on this machine: \(shown))")
            }
            return
        }
        // The contract says nothing else reaches stdout. Anything that does
        // is kept, marked, so a stray print is visible rather than lost.
        writeLog("[stdout] \(line)\n")
        remember("[stdout] \(line)")
    }

    private func remember(_ line: String) {
        tail.append(line)
        if tail.count > StudioServer.tailLength { tail.removeFirst(tail.count - StudioServer.tailLength) }
    }

    /// The address without its fragment, which holds the session token: what
    /// may be written to a log or shown in a window.
    static func withoutFragment(_ url: URL) -> URL {
        var components = URLComponents(url: url, resolvingAgainstBaseURL: false)
        components?.fragment = nil
        return components?.url ?? url
    }

    static func withoutFragment(_ url: URL?) -> String? {
        url.map { withoutFragment($0).absoluteString }
    }

    /// `http://<loopback>:<port>/...` and nothing else.
    static func loopbackURL(_ value: String) -> URL? {
        guard let components = URLComponents(string: value),
              components.scheme == "http",
              let host = components.host, loopbackHosts.contains(host),
              let port = components.port, (1...65_535).contains(port),
              components.user == nil, components.password == nil,
              let url = components.url else { return nil }
        return url
    }

    // MARK: - Ending

    private func startTimedOut(_ current: Int) {
        guard current == generation, !urlSeen, !terminated, let child = process else { return }
        timedOut = true
        writeLog("no address after \(Int(StudioServer.startTimeout)) s; stopping the server\n")
        try? stdinPipe?.fileHandleForWriting.close()
        kill(child.processIdentifier, SIGTERM)
        let pid = child.processIdentifier
        queue.asyncAfter(deadline: .now() + StudioServer.stopGrace) { [weak self] in
            guard let self, current == self.generation, !self.terminated else { return }
            kill(pid, SIGKILL)
        }
    }

    private func terminatedProcess(_ current: Int) {
        guard current == generation else { return }
        terminated = true
        // A grandchild that inherited stdout or stderr can hold them open
        // after the server itself has gone; do not wait for it past 2 s.
        queue.asyncAfter(deadline: .now() + 2) { [weak self] in self?.finish(current) }
        if openStreams == 0 { finish(current) }
    }

    private func streamClosed(_ current: Int) {
        guard current == generation else { return }
        openStreams -= 1
        if terminated && openStreams == 0 { finish(current) }
    }

    private func finish(_ current: Int) {
        guard current == generation, !finished, let child = process else { return }
        finished = true
        for line in [stdoutRemainder, stderrRemainder].map({ String(decoding: $0, as: UTF8.self) }) where !line.isEmpty {
            remember(line)
        }
        stdoutRemainder = Data()
        stderrRemainder = Data()
        let cause: Exit.Cause
        if timedOut {
            cause = .timedOut
        } else if child.terminationReason == .uncaughtSignal {
            cause = .signalled(child.terminationStatus)
        } else {
            cause = .exited(child.terminationStatus)
        }
        let exit = Exit(cause: cause, beforeURL: !urlSeen, lastLines: tail)
        lastExit = exit
        writeLog("server ended: \(exit.summary)\(stopRequested ? " (asked to stop)" : "")\n")
        closeLog()
        try? stdinPipe?.fileHandleForWriting.close()
        process = nil
        stdinPipe = nil
        finishedSignal.signal()
        if !stopRequested {
            let callback = onExit
            callbackQueue.async { callback?(exit) }
        }
    }

    // MARK: - Log

    private func openLog(_ commandLine: String) {
        let manager = FileManager.default
        let directory = logURL.deletingLastPathComponent()
        try? manager.createDirectory(at: directory, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
        let previous = logURL.deletingPathExtension().appendingPathExtension("1.log")
        if manager.fileExists(atPath: logURL.path) {
            try? manager.removeItem(at: previous)
            try? manager.moveItem(at: logURL, to: previous)
        }
        manager.createFile(atPath: logURL.path, contents: nil, attributes: [.posixPermissions: 0o600])
        log = try? FileHandle(forWritingTo: logURL)
        let stamp = ISO8601DateFormatter().string(from: Date())
        let version = Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "unknown"
        writeLog("Caterva \(version), \(stamp)\n$ \(commandLine)\n")
    }

    private func writeLog(_ text: String) {
        writeLog(Data(text.utf8))
    }

    private func writeLog(_ data: Data) {
        guard let log else { return }
        do { try log.write(contentsOf: data) } catch { self.log = nil }
    }

    private func closeLog() {
        try? log?.close()
        log = nil
    }
}

/// Where the shell keeps what it writes, and where the server keeps its data.
enum Paths {
    /// The server's stderr, as the shell captured it, one file per launch
    /// (the previous launch's is kept beside it with `.1` before the suffix).
    static var serverLog: URL {
        let library = FileManager.default.urls(for: .libraryDirectory, in: .userDomainMask).first
            ?? URL(fileURLWithPath: NSHomeDirectory()).appendingPathComponent("Library")
        return library.appendingPathComponent("Logs/Caterva/studio-server.log")
    }

    /// The server's data folder: `--data-dir` when the shell passes one
    /// (CATERVA_STUDIO_DATA_DIR, for development), else the default the
    /// contract names for macOS (docs/studio/CONTRACT.md, section 11).
    static func dataFolder(_ command: StudioCommand?) -> URL {
        if let custom = command?.dataDirectory {
            return URL(fileURLWithPath: custom, isDirectory: true)
        }
        let support = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first
            ?? URL(fileURLWithPath: NSHomeDirectory()).appendingPathComponent("Library/Application Support")
        return support.appendingPathComponent("Caterva", isDirectory: true)
    }

    /// `~/...` for a path under the home folder, for display only.
    static func abbreviated(_ url: URL) -> String {
        (url.path as NSString).abbreviatingWithTildeInPath
    }
}

/// Whether macOS still marks `path` as downloaded from the internet. An
/// unsigned app approved with "Open Anyway" keeps the attribute on the files
/// inside it, and a quarantined library can then refuse to load in the
/// server process; the error view says what clears it.
func isQuarantined(_ path: String) -> Bool {
    getxattr(path, "com.apple.quarantine", nil, 0, 0, XATTR_NOFOLLOW) >= 0
}
