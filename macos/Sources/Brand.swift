// Colour and type for the native views: the loading view, the error view, the
// window's title bar. Only what the shell draws itself; the page has its own
// tokens (src/index.css) and the two meet at the title bar, which is paper in
// the light appearance and ink in the dark one, as the page is.
//
// Type is the system's: New York (the system serif) for the one heading a
// native view carries, the system face for text, SF Mono for paths and
// server output. The page bundles Spectral, Atkinson Hyperlegible Next and
// DM Mono; the shell draws a handful of lines before or instead of the page
// and does not load web fonts to do it.

import AppKit

enum Brand {
    static func dynamic(_ name: String, light: UInt32, dark: UInt32) -> NSColor {
        NSColor(name: NSColor.Name(name)) { appearance in
            appearance.bestMatch(from: [.aqua, .darkAqua]) == .darkAqua ? rgb(dark) : rgb(light)
        }
    }

    static func rgb(_ hex: UInt32) -> NSColor {
        let (r, g, b) = BrandRGB.components(hex)
        return NSColor(srgbRed: r, green: g, blue: b, alpha: 1)
    }

    /// The ground: paper in the light appearance, ink in the dark one.
    static let ground = dynamic("caterva.ground", light: BrandRGB.paper, dark: BrandRGB.ink)
    /// Text and solid shapes: ink on paper, paper on ink.
    static let ink = dynamic("caterva.ink", light: BrandRGB.ink, dark: BrandRGB.paper)
    /// Secondary text. 4.9:1 on paper, 6.9:1 on ink.
    static let quiet = dynamic("caterva.quiet", light: BrandRGB.quiet, dark: BrandRGB.quietOnInk)
    /// The one thing that matters in a view; the mark's eighth dot.
    static let signal = dynamic("caterva.signal", light: BrandRGB.signal, dark: BrandRGB.signalOnInk)
    static let caution = dynamic("caterva.caution", light: BrandRGB.caution, dark: BrandRGB.cautionOnInk)
    static let failure = dynamic("caterva.failure", light: BrandRGB.failure, dark: BrandRGB.failureOnInk)
    static let rule = dynamic("caterva.rule", light: BrandRGB.rule, dark: BrandRGB.ruleOnInk)
    static let well = dynamic("caterva.well", light: BrandRGB.well, dark: BrandRGB.wellOnInk)

    static func display(_ size: CGFloat) -> NSFont {
        let base = NSFont.systemFont(ofSize: size, weight: .regular)
        if let serif = base.fontDescriptor.withDesign(.serif) {
            return NSFont(descriptor: serif, size: size) ?? base
        }
        return base
    }

    static func text(_ size: CGFloat, weight: NSFont.Weight = .regular) -> NSFont {
        NSFont.systemFont(ofSize: size, weight: weight)
    }

    static func mono(_ size: CGFloat) -> NSFont {
        NSFont.monospacedSystemFont(ofSize: size, weight: .regular)
    }

    /// A CGColor for `color` as it resolves in `appearance`. Layers take
    /// CGColors, which do not follow the appearance by themselves.
    static func resolved(_ color: NSColor, in appearance: NSAppearance) -> CGColor {
        var result = color.cgColor
        appearance.performAsCurrentDrawingAppearance {
            result = color.cgColor
        }
        return result
    }
}
