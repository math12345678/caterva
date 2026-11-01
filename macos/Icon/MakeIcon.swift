// Draws Caterva.app's icon: the dotted-C mark on a paper tile, at every size
// an .iconset holds, written as PNGs that `iconutil -c icns` turns into
// Caterva.icns.
//
//   swiftc -parse-as-library macos/Icon/MakeIcon.swift macos/Sources/Mark.swift -o make-icon
//   ./make-icon <out>/Caterva.iconset [<out>/Caterva.icns]
//
// The optional second argument also packs the same PNGs into an .icns
// itself (the container is a type and a length before each PNG). The build
// uses iconutil's .icns; this one is for a machine where iconutil cannot
// run (a sandbox that refuses it the per-user temporary folder it writes
// to), so a development app still has its icon.
//
// Drawn from the mark's measured geometry (macos/Sources/Mark.swift, the same
// numbers as docs/brand/caterva-mark.svg) at each pixel size, not scaled from
// one large bitmap, so the 16 px icon's dots are placed on its own grid. The
// tile follows the macOS icon grid: an 824 px rounded square centred in a
// 1024 px canvas, corner radius 185.4 px at that size. Paper ground, ink
// dots, one signal dot, a hairline edge so the tile holds its shape on a
// paper-coloured desktop. No gradient, no gloss.
//
// Writes nothing but PNG files into the directory it is given, and refuses a
// directory that does not end in .iconset (iconutil's own rule).

import CoreGraphics
import Foundation
import ImageIO
import UniformTypeIdentifiers

@main
enum MakeIcon {
    /// (points, scale): the members of a macOS .iconset.
    static let members: [(Int, Int)] = [
        (16, 1), (16, 2), (32, 1), (32, 2), (128, 1), (128, 2), (256, 1), (256, 2), (512, 1), (512, 2),
    ]

    static func main() {
        let arguments = CommandLine.arguments.dropFirst()
        guard let target = arguments.first, target.hasSuffix(".iconset") else {
            FileHandle.standardError.write(Data("usage: make-icon <directory>.iconset\n".utf8))
            exit(2)
        }
        let directory = URL(fileURLWithPath: target, isDirectory: true)
        let icns = arguments.dropFirst().first.map { URL(fileURLWithPath: $0) }
        if let icns, icns.pathExtension != "icns" {
            FileHandle.standardError.write(Data("make-icon: the second argument must end in .icns\n".utf8))
            exit(2)
        }
        do {
            try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
            var chunks: [(String, Data)] = []
            for (points, scale) in members {
                let pixels = points * scale
                let name = scale == 1 ? "icon_\(points)x\(points).png" : "icon_\(points)x\(points)@2x.png"
                guard let image = draw(pixels: pixels) else {
                    throw NSError(domain: "make-icon", code: 1, userInfo: [NSLocalizedDescriptionKey: "could not draw \(pixels) px"])
                }
                let file = directory.appendingPathComponent(name)
                try write(image, to: file)
                print("\(name)  \(pixels) x \(pixels)")
                if let type = icnsType[name] { chunks.append((type, try Data(contentsOf: file))) }
            }
            if let icns {
                try pack(chunks).write(to: icns)
                print("\(icns.lastPathComponent)  \(chunks.count) images")
            }
        } catch {
            FileHandle.standardError.write(Data("make-icon: \(error.localizedDescription)\n".utf8))
            exit(1)
        }
    }

    /// The .icns element type that holds each iconset member as PNG.
    static let icnsType: [String: String] = [
        "icon_16x16.png": "icp4", "icon_16x16@2x.png": "ic11",
        "icon_32x32.png": "icp5", "icon_32x32@2x.png": "ic12",
        "icon_128x128.png": "ic07", "icon_128x128@2x.png": "ic13",
        "icon_256x256.png": "ic08", "icon_256x256@2x.png": "ic14",
        "icon_512x512.png": "ic09", "icon_512x512@2x.png": "ic10",
    ]

    /// 'icns', the total length, then per image its type and length (both
    /// counting their own 8 header bytes) and the PNG; lengths big-endian.
    static func pack(_ chunks: [(String, Data)]) -> Data {
        func bigEndian(_ value: Int) -> Data {
            withUnsafeBytes(of: UInt32(value).bigEndian) { Data($0) }
        }
        var body = Data()
        for (type, png) in chunks {
            body.append(Data(type.utf8))
            body.append(bigEndian(png.count + 8))
            body.append(png)
        }
        var file = Data("icns".utf8)
        file.append(bigEndian(body.count + 8))
        file.append(body)
        return file
    }

    static func draw(pixels: Int) -> CGImage? {
        let size = CGFloat(pixels)
        guard let space = CGColorSpace(name: CGColorSpace.sRGB),
              let context = CGContext(data: nil, width: pixels, height: pixels, bitsPerComponent: 8, bytesPerRow: 0,
                                      space: space, bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else {
            return nil
        }
        context.setShouldAntialias(true)
        context.interpolationQuality = .high
        let unit = size / 1024

        // The tile: 824 of 1024, centred, radius 185.4 (Apple's grid).
        let inset = 100 * unit
        let tile = CGRect(x: inset, y: inset, width: size - 2 * inset, height: size - 2 * inset)
        let radius = 185.4 * unit
        let path = CGPath(roundedRect: tile, cornerWidth: radius, cornerHeight: radius, transform: nil)

        // A soft drop shadow below the tile, as every Big Sur-style icon has;
        // omitted below 64 px, where it only muddies the edge.
        context.saveGState()
        if pixels >= 64 {
            context.setShadow(offset: CGSize(width: 0, height: -10 * unit), blur: 28 * unit,
                              color: BrandRGB.cgColor(BrandRGB.ink, alpha: 0.28))
        }
        context.addPath(path)
        context.setFillColor(BrandRGB.cgColor(BrandRGB.paper))
        context.fillPath()
        context.restoreGState()

        // Hairline edge: ink at low alpha, at least one device pixel.
        context.addPath(path)
        context.setStrokeColor(BrandRGB.cgColor(BrandRGB.ink, alpha: 0.12))
        context.setLineWidth(max(1, 4 * unit))
        context.strokePath()

        // The mark: 58 % of the tile's height, centred optically (the C's
        // opening carries less visual weight, so it sits a touch right).
        let markHeight = tile.height * 0.58
        let markWidth = markHeight * MarkGeometry.aspect
        let markRect = CGRect(x: tile.midX - markWidth / 2 + tile.width * 0.015,
                              y: tile.midY - markHeight / 2, width: markWidth, height: markHeight)
        for dot in MarkGeometry.place(in: markRect, yUp: true) {
            context.setFillColor(BrandRGB.cgColor(dot.signal ? BrandRGB.signal : BrandRGB.ink))
            let r = max(dot.radius, 0.75)
            context.fillEllipse(in: CGRect(x: dot.center.x - r, y: dot.center.y - r, width: 2 * r, height: 2 * r))
        }
        return context.makeImage()
    }

    static func write(_ image: CGImage, to url: URL) throws {
        guard let destination = CGImageDestinationCreateWithURL(url as CFURL, UTType.png.identifier as CFString, 1, nil) else {
            throw NSError(domain: "make-icon", code: 2, userInfo: [NSLocalizedDescriptionKey: "cannot write \(url.path)"])
        }
        CGImageDestinationAddImage(destination, image, [kCGImagePropertyDPIWidth: 72, kCGImagePropertyDPIHeight: 72] as CFDictionary)
        guard CGImageDestinationFinalize(destination) else {
            throw NSError(domain: "make-icon", code: 3, userInfo: [NSLocalizedDescriptionKey: "cannot finish \(url.path)"])
        }
    }
}
