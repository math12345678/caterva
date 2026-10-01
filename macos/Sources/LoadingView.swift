// The mark as a view, and the loading view built on it.
//
// Loading is the mark's own dots in motion, never a spinner: the signal dot
// holds still and a wave of dimming travels from it round the C and back,
// dot by dot, in the order MarkGeometry lists them. Only opacity and scale
// change (transform and opacity, nothing that relayouts), on an exponential
// ease-out. With Reduce Motion on, the mark stands still and the words carry
// the state alone.

import AppKit
import QuartzCore

final class MarkView: NSView {
    var animating = false {
        didSet { if animating != oldValue { updateAnimation() } }
    }

    private var dotLayers: [CALayer] = []

    override init(frame: NSRect) {
        super.init(frame: frame)
        wantsLayer = true
        layer = CALayer()
        for _ in MarkGeometry.dots {
            let dot = CALayer()
            layer?.addSublayer(dot)
            dotLayers.append(dot)
        }
        NSWorkspace.shared.notificationCenter.addObserver(
            self, selector: #selector(displayOptionsChanged),
            name: NSWorkspace.accessibilityDisplayOptionsDidChangeNotification, object: nil)
    }

    required init?(coder: NSCoder) { nil }

    deinit { NSWorkspace.shared.notificationCenter.removeObserver(self) }

    override var intrinsicContentSize: NSSize { NSSize(width: NSView.noIntrinsicMetric, height: NSView.noIntrinsicMetric) }
    override var isFlipped: Bool { false }

    override func layout() {
        super.layout()
        placeDots()
    }

    override func setFrameSize(_ newSize: NSSize) {
        super.setFrameSize(newSize)
        placeDots()
    }

    private func placeDots() {
        CATransaction.begin()
        CATransaction.setDisableActions(true)
        for (dot, spot) in zip(dotLayers, MarkGeometry.place(in: bounds, yUp: true)) {
            let side = spot.radius * 2
            dot.bounds = CGRect(x: 0, y: 0, width: side, height: side)
            dot.position = spot.center
            dot.cornerRadius = spot.radius
        }
        CATransaction.commit()
        updateColors()
    }

    override func viewDidChangeEffectiveAppearance() {
        super.viewDidChangeEffectiveAppearance()
        updateColors()
    }

    override func viewDidMoveToWindow() {
        super.viewDidMoveToWindow()
        updateAnimation()
    }

    private func updateColors() {
        CATransaction.begin()
        CATransaction.setDisableActions(true)
        let ink = Brand.resolved(Brand.ink, in: effectiveAppearance)
        let signal = Brand.resolved(Brand.signal, in: effectiveAppearance)
        for (dot, geometry) in zip(dotLayers, MarkGeometry.dots) {
            dot.backgroundColor = geometry.signal ? signal : ink
        }
        CATransaction.commit()
    }

    @objc private func displayOptionsChanged() { updateAnimation() }

    private func updateAnimation() {
        for dot in dotLayers { dot.removeAllAnimations() }
        guard animating, window != nil, !NSWorkspace.shared.accessibilityDisplayShouldReduceMotion else { return }
        // Exponential ease-out, the page's --ease-out-expo.
        let easeOut = CAMediaTimingFunction(controlPoints: 0.16, 1, 0.3, 1)
        let period: CFTimeInterval = 1.8
        let step: CFTimeInterval = 0.12
        let now = CACurrentMediaTime()
        for (index, dot) in dotLayers.enumerated() where !MarkGeometry.dots[index].signal {
            let fade = CAKeyframeAnimation(keyPath: "opacity")
            fade.values = [1.0, 0.22, 1.0]
            fade.keyTimes = [0, 0.16, 1]
            fade.timingFunctions = [easeOut, easeOut]
            let shrink = CAKeyframeAnimation(keyPath: "transform.scale")
            shrink.values = [1.0, 0.78, 1.0]
            shrink.keyTimes = fade.keyTimes
            shrink.timingFunctions = fade.timingFunctions
            let group = CAAnimationGroup()
            group.animations = [fade, shrink]
            group.duration = period
            group.repeatCount = .infinity
            group.beginTime = now + Double(index) * step
            group.fillMode = .backwards
            dot.add(group, forKey: "wave")
        }
    }
}

/// The mark in motion above one line saying what is happening.
final class LoadingView: NSView {
    private let mark = MarkView()
    private let label = NSTextField(labelWithString: "")
    private let detail = NSTextField(wrappingLabelWithString: "")

    var message: String {
        get { label.stringValue }
        set {
            label.stringValue = newValue
            setAccessibilityLabel(newValue)
        }
    }

    /// A second, quieter line, for when the first has been on screen a while.
    var detailMessage: String? {
        get { detail.isHidden ? nil : detail.stringValue }
        set {
            detail.stringValue = newValue ?? ""
            detail.isHidden = newValue == nil
        }
    }

    override init(frame: NSRect) {
        super.init(frame: frame)
        wantsLayer = true
        label.font = Brand.text(14)
        label.textColor = Brand.quiet
        label.alignment = .center
        detail.font = Brand.text(12)
        detail.textColor = Brand.quiet
        detail.alignment = .center
        detail.isHidden = true
        detail.preferredMaxLayoutWidth = 380

        let stack = NSStackView(views: [mark, label, detail])
        stack.orientation = .vertical
        stack.alignment = .centerX
        stack.spacing = 18
        stack.setCustomSpacing(8, after: label)
        stack.translatesAutoresizingMaskIntoConstraints = false
        addSubview(stack)
        mark.translatesAutoresizingMaskIntoConstraints = false
        NSLayoutConstraint.activate([
            mark.heightAnchor.constraint(equalToConstant: 64),
            mark.widthAnchor.constraint(equalToConstant: 64 * MarkGeometry.aspect),
            stack.centerXAnchor.constraint(equalTo: centerXAnchor),
            stack.centerYAnchor.constraint(equalTo: centerYAnchor, constant: -24),
            detail.widthAnchor.constraint(lessThanOrEqualToConstant: 380),
        ])
        setAccessibilityElement(true)
        setAccessibilityRole(.progressIndicator)
    }

    required init?(coder: NSCoder) { nil }

    override func viewDidMoveToWindow() {
        super.viewDidMoveToWindow()
        mark.animating = window != nil
    }

    override func updateLayer() {
        layer?.backgroundColor = Brand.resolved(Brand.ground, in: effectiveAppearance)
    }

    override var wantsUpdateLayer: Bool { true }
}
