// Caterva.app's entry point.
//
//   Caterva                        the app: a window onto `caterva studio`
//   Caterva --smoke [--require-page]
//                                  start the server, fetch its page, stop it,
//                                  report; no window (scripts/build_studio_app.py
//                                  and CI run this)
//   Caterva --version              the version this bundle carries
//   Caterva --updater-selftest     check the update feed rules (no network, no window)
//
// On a macOS older than the one the bundled Python libraries were built for
// (14.0: NumPy 2.2 and SciPy 1.15 are macosx_14_0 wheels, libRoadRunner 2.8
// macosx_14_0_universal2), the app says so in a native alert and quits,
// instead of starting a server that cannot import them.
//
// Nothing else is read from the command line. macOS adds its own arguments
// when it launches an app (-psn_..., -NSDocumentRevisionsDebugMode); they are
// left to AppKit.

import AppKit

let arguments = CommandLine.arguments.dropFirst()

if arguments.contains("--version") {
    let version = Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "unknown"
    print("Caterva \(version)")
    exit(0)
}

if arguments.contains("--updater-selftest") {
    exit(UpdaterSelfTest.run())
}

if let problem = MacOSRequirement.problem() {
    if arguments.contains("--smoke") {
        print("caterva smoke: FAIL \(problem.title). \(problem.detail)")
        exit(1)
    }
    let application = NSApplication.shared
    application.setActivationPolicy(.regular)
    let alert = NSAlert()
    alert.alertStyle = .warning
    alert.messageText = problem.title
    alert.informativeText = problem.detail
    alert.addButton(withTitle: "Quit")
    application.activate(ignoringOtherApps: true)
    alert.runModal()
    exit(1)
}

if arguments.contains("--smoke") {
    exit(Smoke.run(requirePage: arguments.contains("--require-page")))
}

let application = NSApplication.shared
let delegate = AppDelegate()
application.delegate = delegate
application.setActivationPolicy(.regular)
application.run()
