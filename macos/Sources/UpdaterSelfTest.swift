// `Caterva --updater-selftest`: the update feed rules, run against fixed
// inputs, with no network and no window. scripts/build_studio_app.py runs it
// on the assembled bundle, so a build whose rules drifted is not shipped.

import Foundation

enum UpdaterSelfTest {
    static func run() -> Int32 {
        var failures: [String] = []
        func expect(_ condition: Bool, _ what: String) {
            if !condition { failures.append(what) }
        }

        let base = "https://github.com/math12345678/caterva/releases/download"
        expect(ReleaseFeed.isAcceptable("\(base)/v0.5.1/appcast.xml"), "a release's appcast is accepted")
        expect(ReleaseFeed.isAcceptable("\(base)/v0.5.1-rc.1/appcast.xml"), "a prerelease's appcast is accepted")
        expect(ReleaseFeed.isAcceptable(ReleaseFeed.stable) == false, "the stable address is not a per-tag address")
        for bad in [
            "http://github.com/math12345678/caterva/releases/download/v1/appcast.xml",
            "https://example.com/math12345678/caterva/releases/download/v1/appcast.xml",
            "https://github.com.example.com/math12345678/caterva/releases/download/v1/appcast.xml",
            "https://github.com/someone-else/caterva/releases/download/v1/appcast.xml",
            "https://github.com/math12345678/caterva/releases/download/v1/other.xml",
            "https://github.com/math12345678/caterva/releases/download/v1/appcast.xml?x=1",
            "https://github.com/math12345678/caterva/releases/download//appcast.xml",
            "https://github.com/math12345678/caterva/releases/download/a/b/appcast.xml",
            "https://github.com:8443/math12345678/caterva/releases/download/v1/appcast.xml",
            "https://user@github.com/math12345678/caterva/releases/download/v1/appcast.xml",
            "file:///tmp/appcast.xml",
            "",
        ] {
            expect(!ReleaseFeed.isAcceptable(bad), "refused: \(bad)")
        }

        func listing(_ releases: [[String: Any]]) -> Data {
            (try? JSONSerialization.data(withJSONObject: releases)) ?? Data()
        }
        func release(_ tag: String, draft: Bool = false, asset: String? = "appcast.xml", url: String? = nil) -> [String: Any] {
            var assets: [[String: Any]] = [["name": "Caterva-1-macos-arm64.zip", "browser_download_url": "\(base)/\(tag)/Caterva.zip"]]
            if let asset { assets.append(["name": asset, "browser_download_url": url ?? "\(base)/\(tag)/\(asset)"]) }
            return ["tag_name": tag, "draft": draft, "assets": assets]
        }
        expect(ReleaseFeed.newestAppcast(in: listing([release("v0.5.1-rc.2"), release("v0.5.0")])) == "\(base)/v0.5.1-rc.2/appcast.xml",
               "the newest release wins, a prerelease included")
        expect(ReleaseFeed.newestAppcast(in: listing([release("v0.6.0", draft: true), release("v0.5.0")])) == "\(base)/v0.5.0/appcast.xml",
               "a draft is skipped")
        expect(ReleaseFeed.newestAppcast(in: listing([release("v0.6.0", asset: nil), release("v0.5.0")])) == "\(base)/v0.5.0/appcast.xml",
               "a release with no appcast is skipped")
        expect(ReleaseFeed.newestAppcast(in: listing([release("v0.6.0", url: "https://example.com/appcast.xml")])) == nil,
               "an address outside the repository is never followed")
        expect(ReleaseFeed.newestAppcast(in: Data("not json".utf8)) == nil, "an unreadable answer gives nothing")
        expect(ReleaseFeed.newestAppcast(in: Data("{\"message\":\"API rate limit exceeded\"}".utf8)) == nil,
               "a rate-limit answer gives nothing")

        expect(ReleaseFeed.isRunningFromTransientLocation("/Volumes/Caterva 0.5.1/Caterva.app"), "a disk image is transient")
        expect(ReleaseFeed.isRunningFromTransientLocation("/private/var/folders/x/AppTranslocation/ABC/d/Caterva.app"),
               "a translocated app is transient")
        expect(!ReleaseFeed.isRunningFromTransientLocation("/Applications/Caterva.app"), "Applications is not transient")

        let plist = Bundle.main.infoDictionary ?? [:]
        expect((plist["SUFeedURL"] as? String).flatMap(URL.init(string:)) != nil, "Info.plist carries a feed address")
        let key = (plist["SUPublicEDKey"] as? String).flatMap { Data(base64Encoded: $0) }
        expect(key?.count == 32, "Info.plist carries a 32-byte EdDSA public key")

        if failures.isEmpty {
            print("caterva updater self-test: OK")
            return 0
        }
        for failure in failures { print("caterva updater self-test: FAIL \(failure)") }
        return 1
    }
}
