// The caterva mark as geometry: a C of eight dots, seven ink and one signal.
//
// CoreGraphics only, no AppKit, because two programs compile this file: the
// app (the loading and error views draw the mark) and macos/Icon/MakeIcon.swift
// (the app icon, drawn at every iconset size). One copy of the numbers keeps
// the icon and the window from drifting apart.
//
// The numbers are the measured ones from docs/brand/caterva-mark.svg
// (viewBox 236 172 514 634), the same as the page's
// src/components/brand/Mark.tsx. They are not redrawn by eye.

import CoreGraphics

enum MarkGeometry {
    struct Dot {
        let x: CGFloat
        let y: CGFloat
        let r: CGFloat
        let signal: Bool
    }

    struct Placed {
        let center: CGPoint
        let radius: CGFloat
        let signal: Bool
    }

    /// The SVG's viewBox: the tight bounds of the eight dots, y pointing down.
    static let viewBox = CGRect(x: 236, y: 172, width: 514, height: 634)

    /// In the order the dots sit along the C: the signal dot at the upper
    /// opening, round the back of the letter, to the lower opening. The
    /// loading animation travels in this order.
    static let dots: [Dot] = [
        Dot(x: 688.7, y: 309.3, r: 50.9, signal: true),
        Dot(x: 541.3, y: 242.6, r: 61.7, signal: false),
        Dot(x: 386.5, y: 281.7, r: 44.2, signal: false),
        Dot(x: 305.1, y: 403.8, r: 59.6, signal: false),
        Dot(x: 297.4, y: 569.0, r: 44.2, signal: false),
        Dot(x: 382.6, y: 697.4, r: 60.2, signal: false),
        Dot(x: 542.5, y: 744.6, r: 53.5, signal: false),
        Dot(x: 680.8, y: 684.5, r: 44.2, signal: false),
    ]

    /// Width over height of the mark, for sizing a view around it.
    static var aspect: CGFloat { viewBox.width / viewBox.height }

    /// Each dot fitted into `rect`, aspect preserved and centred. `yUp` is
    /// true for a context whose origin is at the bottom left (a bitmap
    /// context, an unflipped view or layer), false for a flipped one.
    static func place(in rect: CGRect, yUp: Bool) -> [Placed] {
        let scale = min(rect.width / viewBox.width, rect.height / viewBox.height)
        let width = viewBox.width * scale
        let height = viewBox.height * scale
        let originX = rect.minX + (rect.width - width) / 2
        let originY = rect.minY + (rect.height - height) / 2
        return dots.map { dot in
            let x = originX + (dot.x - viewBox.minX) * scale
            let down = (dot.y - viewBox.minY) * scale
            let y = yUp ? originY + height - down : originY + down
            return Placed(center: CGPoint(x: x, y: y), radius: dot.r * scale, signal: dot.signal)
        }
    }
}

/// The brand's colours as sRGB components (docs/brand/README.md), for code
/// that has no AppKit. The app wraps them in dynamic NSColors (Brand.swift).
enum BrandRGB {
    static let paper: UInt32 = 0xFDF8EE
    static let ink: UInt32 = 0x2A2D35
    static let signal: UInt32 = 0x5D7F8D
    static let signalOnInk: UInt32 = 0x9DB8C4
    static let quiet: UInt32 = 0x6A6E78
    static let quietOnInk: UInt32 = 0xA9ACB3
    static let caution: UInt32 = 0x946522
    static let cautionOnInk: UInt32 = 0xD9AD6A
    static let failure: UInt32 = 0xA63D35
    static let failureOnInk: UInt32 = 0xE08A80
    /// Ink at 14 % on paper, and paper at 16 % on ink: hairlines.
    static let rule: UInt32 = 0xE0DCD4
    static let ruleOnInk: UInt32 = 0x4C4E53
    /// A recessed well for monospaced text: ink at 5 % on paper, paper at 5 % on ink.
    static let well: UInt32 = 0xF2EEE5
    static let wellOnInk: UInt32 = 0x35373E

    static func components(_ hex: UInt32) -> (CGFloat, CGFloat, CGFloat) {
        (CGFloat((hex >> 16) & 0xFF) / 255, CGFloat((hex >> 8) & 0xFF) / 255, CGFloat(hex & 0xFF) / 255)
    }

    static func cgColor(_ hex: UInt32, alpha: CGFloat = 1) -> CGColor {
        let (r, g, b) = components(hex)
        let space = CGColorSpace(name: CGColorSpace.sRGB) ?? CGColorSpaceCreateDeviceRGB()
        return CGColor(colorSpace: space, components: [r, g, b, alpha]) ?? CGColor(gray: 0, alpha: alpha)
    }
}
