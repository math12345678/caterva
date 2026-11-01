// The oldest macOS this app runs on, and the message for an older one.
//
// 14.0, because the Python libraries inside the app are built for it:
// NumPy 2.2.6 and SciPy 1.15.3 ship macosx_14_0_arm64 wheels and
// libRoadRunner 2.8.0 a macosx_14_0_universal2 one (`vtool -show-build` on
// their extension modules says minos 14.0). scripts/build_studio_app.py
// writes the same number into Info.plist (LSMinimumSystemVersion), so
// Launch Services refuses an older macOS first; this check is for the paths
// that do not go through it (the executable run directly, `--smoke`).

import Foundation

enum MacOSRequirement {
    static let minimum = OperatingSystemVersion(majorVersion: 14, minorVersion: 0, patchVersion: 0)

    struct Problem {
        let title: String
        let detail: String
    }

    static func problem(_ info: ProcessInfo = .processInfo) -> Problem? {
        if info.isOperatingSystemAtLeast(minimum) { return nil }
        let running = info.operatingSystemVersion
        return Problem(
            title: "Caterva needs macOS \(minimum.majorVersion) or later",
            detail: "This Mac is running macOS \(running.majorVersion).\(running.minorVersion). "
                + "The scientific libraries inside Caterva are built for macOS \(minimum.majorVersion) and later, "
                + "so the app cannot run here. Update macOS, or run Caterva from its source on this Mac "
                + "(github.com/math12345678/caterva).")
    }
}
