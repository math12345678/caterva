Caterva @VERSION@ for macOS (Apple silicon)

INSTALL
    Drag Caterva into Applications, then eject this disk image.

OPENING IT THE FIRST TIME
    This app is not signed with an Apple Developer ID and has not been
    notarised by Apple: the project does not hold a Developer ID. macOS
    therefore refuses the first open with a message that it "cannot verify"
    the app. To open it anyway, once per downloaded version:

    1. In Applications, Control-click (or right-click) Caterva and choose
       Open, then Open in the dialog.
    or
    2. Open it once, dismiss the message, then go to System Settings,
       Privacy & Security, scroll to the message about Caterva and choose
       Open Anyway.

    If the window then says the studio server could not start and mentions
    the quarantine mark, it shows the one Terminal command that clears it.

    Check what you downloaded before you do either: the release page lists
    a SHA-256 for this disk image (shasum -a 256 Caterva-@VERSION@-macos-arm64.dmg).

WHAT IT IS
    A window onto the Caterva engine, which runs as a local server on this
    Mac only (127.0.0.1, a fresh key every launch) and stops when you quit.
    Every number it shows says whether it is a cited measurement, fitted,
    computed, or a placeholder, and where it came from.

    Runs and settings: ~/Library/Application Support/Caterva
    Server log:        ~/Library/Logs/Caterva/studio-server.log

    Literature lookups use the network when you ask for them; the rest
    works offline. GROMACS (for molecular dynamics setup) is not included;
    install it separately and Caterva finds it.

REQUIREMENTS
    macOS 12 or later on Apple silicon (arm64).

LICENCES
    Caterva is under the Apache License 2.0. The app carries the Python
    runtime and the libraries Caterva uses, each under its own licence
    (libSBML under the GNU LGPL 2.1); their texts are inside the app, in
    Caterva.app/Contents/Resources/caterva/licenses/, and Help, Licences in
    the app shows them. Unaffiliated with Tellurium.

SOURCE AND DOCUMENTATION
    https://github.com/math12345678/caterva
