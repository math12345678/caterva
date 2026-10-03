// What the window shows when there is no server to show a page from: it did
// not start, it refused, it timed out, it died while the page was open, or
// the executable is not in the bundle at all.
//
// A native view, not a page, because the page is exactly what is missing.
// It says which of those happened in plain words, shows the server's last
// lines (the reason it printed, or its traceback) where they can be read and
// copied, names the log file, and offers one action: Restart.

import AppKit

struct ServerProblem {
    let title: String
    let explanation: String
    let lines: [String]
    let logURL: URL?
    /// Set when the bundle is quarantined and the server failed to start:
    /// the command that clears the mark.
    let quarantineCommand: String?

    static func missing(_ failure: Error) -> ServerProblem {
        ServerProblem(title: "The studio server is not in this copy of Caterva",
                      explanation: String(describing: failure),
                      lines: [], logURL: nil, quarantineCommand: nil)
    }

    static func launchFailed(_ error: Error, logURL: URL) -> ServerProblem {
        ServerProblem(title: "The studio server could not be launched",
                      explanation: "macOS refused to run it: \(error.localizedDescription)",
                      lines: [], logURL: logURL, quarantineCommand: nil)
    }

    static func ended(_ exit: StudioServer.Exit, logURL: URL, appPath: String, quarantined: Bool) -> ServerProblem {
        let title: String
        let explanation: String
        switch (exit.cause, exit.beforeURL) {
        case (.timedOut, _):
            title = "The studio server did not start"
            explanation = "It had not said where it was listening after \(Int(StudioServer.startTimeout)) seconds, so Caterva stopped it. Its last lines are below."
        case (.exited(3), true):
            title = "The studio server refused to start"
            explanation = "It exited with status 3, which means it refused and said why. Its reason is in the last lines below."
        case (_, true):
            title = "The studio server did not start"
            explanation = "It ended (\(exit.summary)) before saying where it was listening. Its last lines are below."
        case (_, false):
            title = "The studio server stopped"
            explanation = "It ended (\(exit.summary)) while this window was open. Finished runs are kept in the data folder. Restart starts a new server and reopens the page where you were."
        }
        let command = quarantined && exit.beforeURL ? "xattr -dr com.apple.quarantine \(shellQuoted(appPath))" : nil
        return ServerProblem(title: title, explanation: explanation, lines: exit.lastLines,
                             logURL: logURL, quarantineCommand: command)
    }

    static func shellQuoted(_ path: String) -> String {
        "'" + path.replacingOccurrences(of: "'", with: "'\\''") + "'"
    }

    /// Everything on the view, as text, for Copy Details and bug reports.
    var details: String {
        var parts = [title, explanation]
        if !lines.isEmpty { parts.append(lines.joined(separator: "\n")) }
        if let logURL { parts.append("Log: \(logURL.path)") }
        let version = Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "unknown"
        parts.append("Caterva \(version), macOS \(ProcessInfo.processInfo.operatingSystemVersionString)")
        return parts.joined(separator: "\n\n")
    }
}

final class ErrorView: NSView {
    var onRestart: (() -> Void)?

    private let problem: ServerProblem

    init(problem: ServerProblem) {
        self.problem = problem
        super.init(frame: .zero)
        wantsLayer = true
        build()
    }

    required init?(coder: NSCoder) { nil }

    override var wantsUpdateLayer: Bool { true }

    override func updateLayer() {
        layer?.backgroundColor = Brand.resolved(Brand.ground, in: effectiveAppearance)
    }

    private func build() {
        let mark = MarkView()
        mark.translatesAutoresizingMaskIntoConstraints = false
        NSLayoutConstraint.activate([
            mark.heightAnchor.constraint(equalToConstant: 36),
            mark.widthAnchor.constraint(equalToConstant: 36 * MarkGeometry.aspect),
        ])

        let heading = NSTextField(wrappingLabelWithString: problem.title)
        heading.font = Brand.display(24)
        heading.textColor = Brand.ink
        heading.setAccessibilityRole(.staticText)

        let body = paragraph(problem.explanation)

        var views: [NSView] = [mark, heading, body]

        if !problem.lines.isEmpty {
            views.append(outputWell(problem.lines.joined(separator: "\n")))
        }

        if let command = problem.quarantineCommand {
            views.append(paragraph("macOS still marks this copy of Caterva as downloaded from the internet, and that can stop the server's libraries from loading: Open Anyway in Privacy & Security approves the app's main file but not the libraries inside it. If you trust this copy, clear the mark in Terminal, then press Restart:"))
            views.append(selectableMono(command))
        }

        if let logURL = problem.logURL {
            let log = selectableMono("Log: \(Paths.abbreviated(logURL))")
            log.textColor = Brand.quiet
            views.append(log)
        }

        let restart = NSButton(title: "Restart", target: self, action: #selector(restartPressed))
        restart.keyEquivalent = "\r"
        restart.bezelColor = Brand.signal
        let reveal = NSButton(title: "Show Log in Finder", target: self, action: #selector(revealLog))
        reveal.isEnabled = problem.logURL != nil
        let copy = NSButton(title: "Copy Details", target: self, action: #selector(copyDetails))
        let buttons = NSStackView(views: [restart, reveal, copy])
        buttons.orientation = .horizontal
        buttons.spacing = 10
        views.append(buttons)

        let column = NSStackView(views: views)
        column.orientation = .vertical
        column.alignment = .leading
        column.spacing = 14
        column.setCustomSpacing(22, after: mark)
        column.setCustomSpacing(22, after: views[views.count - 2])
        column.translatesAutoresizingMaskIntoConstraints = false
        addSubview(column)

        let width = column.widthAnchor.constraint(equalToConstant: 620)
        width.priority = .defaultHigh
        NSLayoutConstraint.activate([
            width,
            column.widthAnchor.constraint(lessThanOrEqualTo: widthAnchor, constant: -96),
            column.centerXAnchor.constraint(equalTo: centerXAnchor),
            column.centerYAnchor.constraint(equalTo: centerYAnchor, constant: -20),
            column.topAnchor.constraint(greaterThanOrEqualTo: topAnchor, constant: 32),
        ])
        for view in views where view !== mark && view !== buttons {
            view.widthAnchor.constraint(equalTo: column.widthAnchor).isActive = true
        }
    }

    private func paragraph(_ text: String) -> NSTextField {
        let field = NSTextField(wrappingLabelWithString: text)
        field.font = Brand.text(14)
        field.textColor = Brand.ink
        field.isSelectable = true
        return field
    }

    private func selectableMono(_ text: String) -> NSTextField {
        let field = NSTextField(wrappingLabelWithString: text)
        field.font = Brand.mono(12)
        field.textColor = Brand.ink
        field.isSelectable = true
        return field
    }

    /// The server's last lines, in a recessed well, scrolled to the end.
    private func outputWell(_ text: String) -> NSView {
        let scroll = NSScrollView()
        scroll.hasVerticalScroller = true
        scroll.hasHorizontalScroller = true
        scroll.autohidesScrollers = true
        scroll.borderType = .noBorder
        scroll.drawsBackground = true
        scroll.backgroundColor = Brand.well
        scroll.translatesAutoresizingMaskIntoConstraints = false
        scroll.heightAnchor.constraint(equalToConstant: 200).isActive = true
        scroll.wantsLayer = true
        scroll.layer?.cornerRadius = 6

        let textView = NSTextView()
        textView.isEditable = false
        textView.isSelectable = true
        textView.drawsBackground = false
        textView.font = Brand.mono(11.5)
        textView.textColor = Brand.ink
        textView.textContainerInset = NSSize(width: 10, height: 10)
        textView.isHorizontallyResizable = true
        textView.textContainer?.widthTracksTextView = false
        textView.textContainer?.containerSize = NSSize(width: CGFloat.greatestFiniteMagnitude, height: CGFloat.greatestFiniteMagnitude)
        textView.autoresizingMask = [.width]
        textView.string = text
        textView.setAccessibilityLabel("The server's last lines")
        scroll.documentView = textView
        DispatchQueue.main.async { textView.scrollToEndOfDocument(nil) }
        return scroll
    }

    @objc private func restartPressed() { onRestart?() }

    @objc private func revealLog() {
        guard let logURL = problem.logURL else { return }
        NSWorkspace.shared.activateFileViewerSelecting([logURL])
    }

    @objc private func copyDetails() {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(problem.details, forType: .string)
    }
}
