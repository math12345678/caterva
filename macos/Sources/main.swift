// Caterva.app's entry point.
//
//   Caterva                        the app: a window onto `caterva studio`
//   Caterva --smoke [--require-page]
//                                  start the server, fetch its page, stop it,
//                                  report; no window (scripts/build_studio_app.py
//                                  and CI run this)
//   Caterva --version              the version this bundle carries
//
// Nothing else is read from the command line. macOS adds its own arguments
// when it launches an app (-psn_..., -NSDocumentRevisionsDebugMode); they are
// left to AppKit.

import AppKit

let arguments = CommandLine.arguments.dropFirst()

if arguments.contains("--smoke") {
    exit(Smoke.run(requirePage: arguments.contains("--require-page")))
}

if arguments.contains("--version") {
    let version = Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "unknown"
    print("Caterva \(version)")
    exit(0)
}

let application = NSApplication.shared
let delegate = AppDelegate()
application.delegate = delegate
application.setActivationPolicy(.regular)
application.run()
