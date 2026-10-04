Caterva @VERSION@ for macOS (Apple silicon)

INSTALL
    Drag Caterva into Applications, then eject this disk image.

OPENING IT THE FIRST TIME
    This app is not signed with an Apple Developer ID and has not been
    notarised by Apple: the project does not hold a Developer ID. macOS
    therefore refuses the first open with a message that it cannot verify
    the app. To open it anyway, once per downloaded version:

    1. Try to open Caterva from Applications and dismiss the message. Then
       open System Settings, Privacy & Security, scroll down to the message
       about Caterva, click Open Anyway and enter your login password.
       (Apple's page "Open a Mac app from an unknown developer" gives this
       route; the button stays available for about an hour after the
       attempt. Control-click, Open is no longer offered for an app like
       this one on recent macOS, so it is not listed here.)

    2. If the window then says the studio server could not start, or macOS
       keeps refusing, remove the download mark yourself: open Terminal and
       run

           xattr -dr com.apple.quarantine /Applications/Caterva.app

       then open Caterva again. (Open Anyway approves the app's main file
       but not the libraries inside it; this command clears them all.) The
       window shows the same command when it detects the mark.

    Check what you downloaded before you do either: the release page lists
    a SHA-256 for this disk image (shasum -a 256 Caterva-@VERSION@-macos-arm64.dmg).

UPDATES
    This is the first kind of Caterva that updates itself, so install this
    copy by hand, as above. After that, new versions arrive inside the app:
    Caterva menu, Check for Updates, or Settings, Updates (which also has the
    switches for checking automatically, about once a day, and for including
    prereleases). The app asks before it installs, closes itself, and opens
    the new version; your runs and settings are in the folder named below,
    not in the app, so an update leaves them alone. Each update is checked
    against a key built into the app before it installs. That is not an Apple
    approval: the app still has no Developer ID, and the steps above are for
    the first install of a copy you downloaded yourself. If macOS ever does
    refuse an updated copy, use the same steps. Install Caterva in
    Applications first: an update cannot replace an app that is still running
    from this disk image.

WHAT IT IS
    A window onto the Caterva engine, which runs as a local server on this
    Mac only (127.0.0.1, a fresh key every launch) and stops when you quit.
    Every number it shows says whether it is a cited measurement, fitted,
    computed, or a placeholder, and where it came from.

    Runs and settings: ~/Library/Application Support/Caterva
    Server log:        ~/Library/Logs/Caterva/studio-server.log

    Literature lookups (BRENDA, UniProt, RCSB, NCBI, PubChem) use the
    network when you ask for them, and the update check asks GitHub about
    once a day unless you turn it off in Settings; the rest works offline. GROMACS (for molecular dynamics setup) is not included;
    install it separately and Caterva finds it.

REQUIREMENTS
    macOS 14 (Sonoma) or later on Apple silicon (arm64). The scientific
    libraries inside the app (NumPy, SciPy, libRoadRunner) are built for
    macOS 14; on an older macOS the app says so and quits.

LICENCES
    Caterva is under the Apache License 2.0. The app carries the Python
    runtime and the libraries Caterva uses, each under its own licence
    (libSBML under the GNU LGPL 2.1); their texts are inside the app, in
    Caterva.app/Contents/Resources/caterva/licenses/, and Help, Licences in
    the app shows them. The page's own JavaScript packages and its three
    typefaces (SIL Open Font License 1.1) are listed, with their licence
    texts, in THIRD-PARTY-NOTICES.txt beside them. Enzyme names come from the
    ExPASy ENZYME database (SIB Swiss Institute of Bioinformatics, CC BY 4.0)
    and constants from BRENDA (CC BY 4.0); NOTICE has the attributions.
    Unaffiliated with Tellurium.

SOURCE AND DOCUMENTATION
    https://github.com/math12345678/caterva
