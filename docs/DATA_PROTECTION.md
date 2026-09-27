# Data protection: what the site sends where

**Not legal advice.** This is a record of what the code actually does,
written so the question can be answered from evidence rather than from
memory. A lawyer should review it before launch.

This exists because the cookie banner said something specific and
reassuring that was not true, and nothing in the repository disagreed with
it — the same failure mode `docs/ARCHIVE_TRIAGE.md` names about the
documentation: *"a specific, confident, wrong claim is worse than no claim
at all."*

## Who Caterva's audience is

This matters for which rules apply. The four experts who reviewed this
project are at DSMZ (Braunschweig), Humboldt-Universität zu Berlin,
UMC Groningen, and NCSA (Illinois). Three of the four are in the EU. The
product targets teaching labs, which are disproportionately European and
public-sector. **Assume GDPR applies.**

## What the site sends to third parties

### Google Fonts — on every page load, before any consent

`Science-Agent-Pipeline/artifacts/caterva-landing/index.html` opens
`preconnect` to `fonts.googleapis.com` and `fonts.gstatic.com` and then
loads a stylesheet from them. `src/index.css` `@import`s the same URL.
`caterva-site/index.html`, `mule/index.html`,
`Science-Agent-Pipeline/artifacts/mockup-sandbox/index.html` and
`src/web/server.ts` do the same.

Loading a font from Google's CDN transmits the visitor's IP address to
Google. It happens on page load, before the consent banner appears (the
banner is on a 2-second timer) and regardless of what the visitor then
clicks.

**The licences are fine.** Google Fonts are released under the SIL Open
Font License 1.1 or Apache 2.0, both of which permit self-hosting and
redistribution. This is not a licensing problem.

**The transmission is the problem.** In January 2022 the Landgericht
München I (case 3 O 17493/20) awarded damages against a website operator
for embedding Google Fonts via Google's CDN without consent, on the basis
that the visitor's IP is personal data and its transfer was neither
necessary nor consented to. A wave of German warning letters followed. I
have not read the judgment itself and cannot verify its current status or
how broadly it has been followed — treat it as the reason to take advice,
not as the advice.

**The fix is cheap and removes the question entirely:** self-host the three
families the landing page actually uses — DM Mono, Newsreader, Space
Grotesk. The OFL explicitly permits it. Concretely:

1. Download the families from `fonts.google.com` (or `google-webfonts-helper`).
2. Put the `.woff2` files under `caterva-landing/public/fonts/`.
3. Replace the `@import` in `src/index.css` with local `@font-face` rules.
4. Delete the `preconnect` and stylesheet `<link>` from `index.html`.
5. Add the OFL text to `NOTICE` — self-hosting means redistributing, which
   the OFL permits on condition the licence travels with the files.

This was not done here because it needs the font binaries downloaded, which
this environment cannot do. Nothing else about it is difficult.

`mockup-sandbox/index.html` loads **28** font families from Google in one
request. That is template residue rather than a design decision, and it
should be deleted rather than self-hosted.

### Nothing else

The landing page's only other outbound hosts are links a user clicks
(`github.com`, `pubmed.ncbi.nlm.nih.gov`, `brenda-enzymes.org`,
`genome.jp`, `twitter.com`) and schema/namespace URIs that are never
fetched (`schema.org`, `w3.org`, `sbml.org`). There is no analytics, no
tag manager, no ad network, no session recorder. The banner's claim of "no
analytics, no ads" is accurate.

## What Caterva collects

**Waitlist email addresses.** `POST /waitlist`
(`Science-Agent-Pipeline/artifacts/api-server/src/routes/waitlist.ts`)
accepts an email and writes it to a JSON file on disk
(`WAITLIST_FILE`, default under the data directory).

An email address is personal data. Collecting it engages, at minimum:

- a lawful basis (consent is the obvious one for a waitlist),
- a privacy notice at the point of collection saying who is collecting it,
  why, how long it is kept, and how to have it deleted,
- a deletion route.

**There is no privacy policy in this repository.** Searching the landing
page for one returns only the cookie banner. That is a gap, and it is
cheaper to close before the first address is collected than after.

**Retention is unbounded.** The file is appended to and nothing prunes it.

## Cookies

`CookieConsent.tsx` writes one `localStorage` key,
`caterva-cookie-consent`, to remember that the banner was dismissed. It
sets no cookies and gates nothing — the banner is informational, not a
consent gate. That is a defensible design *if* nothing non-essential loads
before dismissal, which is precisely what the Google Fonts load breaks.

Note that a banner with only a dismiss button does not collect consent in
the GDPR sense. It informs. If the fonts move to self-hosted and nothing
else third-party is added, there is nothing that needs consenting to, and
the banner can stay informational — which is the simplest position to be
in and the one this recommends.

## Open items

| item | status |
|---|---|
| Self-host the three landing-page fonts | not done — needs the font binaries |
| Strip 28 Google font families from `mockup-sandbox` | not done |
| Write a privacy notice at the waitlist form | not done |
| Define a waitlist retention period and a deletion route | not done |
| Have all of the above reviewed | for a lawyer |

The cookie banner has been corrected in the meantime to say that Google
receives the visitor's IP, so that the page no longer states something
untrue while the underlying fix is pending. Correcting the sentence is not
the fix; removing the transmission is.
