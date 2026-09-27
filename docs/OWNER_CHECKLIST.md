# What to do on your side

Written 2026-09-27, after Terrium became **Caterva** and the repository went
public. Each command below was run before it was written down, except the
ones that need your GitHub login, and those say so.

---

## Where things stand

**Done for you:**

- The repository is **<https://github.com/math12345678/caterva>**, public.
- The name is Caterva everywhere: the website, the docs, the command
  (`caterva`), the Python package (`caterva`) and the downloads. The logo's
  crystal mark is unchanged; its wordmark now reads "caterva".
- Your cap table, fundraising tracker, pitch deck and the seven old
  "Confidential" Word files are **gone from the repository and from its
  entire history.**
- The license (Apache-2.0), code of conduct, contributing guide and security
  policy are in place, and GitHub shows them on the repository page.

**What's left for you: four steps, about fifteen minutes.**

---

## Step 1 — A fresh copy (5 minutes)

The history was rewritten to remove the private files, so your
`~/Code/terrium` copy can no longer `git pull`. Replace it:

```bash
cd ~/Code
mv terrium terrium-old
git clone https://github.com/math12345678/caterva.git
cd caterva
make setup
source .venv/bin/activate
caterva --version
```

You should see `caterva 0.4.0`. Then the real-data check:

```bash
caterva compose "Michaelis Menten" --subject 2.7.1.1 --organism human --substrate glucose
```

It ends in a table with Km 6.0 mM (BRENDA ref 641068) and kcat 40.1 1/s
(BRENDA ref 739603), and the verdict at the top says **GROUNDED**.

Once that works, `~/Code/terrium-old` can be deleted. `terrium` still works
as a command, so old notes don't break.

**Every day after this:**

```bash
cd ~/Code/caterva && source .venv/bin/activate
```

---

## Step 2 — Ask GitHub to finish the cleanup (5 minutes, important)

Removing files from history stops them being reachable from any branch or
tag. **GitHub still keeps the old commits in its cache**, and they can be
opened by anyone who knows an old commit ID (this was checked: an old commit
still loads). The pull requests also hold copies. Only GitHub can purge them.

1. Open **<https://support.github.com/contact>** and log in.
2. Choose **"Remove sensitive data"** (or "Other" if that option is not
   listed).
3. Paste this:

> Repository: math12345678/caterva (formerly math12345678/terrium).
> On 2026-09-27 I rewrote the repository's history to remove sensitive
> files, and force-pushed every branch and tag. Please run garbage
> collection and remove cached views of the old commits, including those
> referenced by pull requests, so that these paths are no longer reachable:
> `Business/` (all files), `Docw/` (all files), `terrium_pitch_deck.pptx`,
> `Science-Agent-Pipeline/attached_assets/terrium_full_1784327975531.docx`,
> `Science-Agent-Pipeline/attached_assets/terrium_spec_1784327975531.docx`.

Anyone who cloned the repository while those files were visible still has
them. That cannot be undone from here.

---

## Step 3 — The picture people see when the link is shared (1 minute)

GitHub does not let this be set from the command line.

1. Open **<https://github.com/math12345678/caterva/settings>**.
2. Under **Social preview**, click **Edit → Upload an image**.
3. Choose `Logo.png` from your `~/Code/caterva` folder.

---

## Step 4 — Check the release (2 minutes)

Open **<https://github.com/math12345678/caterva/releases>**. **Caterva
v0.4.0** should be at the top, marked "Latest", with downloads for Mac,
Linux and Windows. If it is not there, open
**<https://github.com/math12345678/caterva/actions/workflows/release.yml>**,
and if the newest row has a red cross, click it, copy the last 40 lines of
the red job, and paste them to Claude.

To try the Mac download:

```bash
cd ~/Downloads && tar xzf caterva-0.4.0-macos-arm64.tar.gz && cd caterva
xattr -dr com.apple.quarantine .
./caterva compose "a toggle switch between two repressors"
```

(The downloaded app builds and simulates models but cannot search the
literature; the copy from Step 1 can. The app says so if you try.)

---

## Later, when you're ready

### Your business files

They are no longer in the repository, but they are not lost:
`~/Desktop/Coding/Terrium` still has them, untouched, along with the old
history. Keep that folder, or move `Business/` somewhere private (a private
repository, or a folder outside iCloud) before deleting it.

The build-stage records (`Business/build-stages/`, how the project was built,
mistakes included) went with the rest of `Business/`. They are engineering
history rather than business data. If you would like them public again, ask
Claude to restore them under `docs/build-stages/` after you have read them.

### The name "caterva" on PyPI

There is an unrelated project called **caterva** (a compression library from
the Blosc team) that already owns the name `caterva` on PyPI. Nothing here
needs PyPI today. If you ever publish there, the package will need a
different name there, such as `caterva-bio`; the command can stay `caterva`.

### Things you do *not* need to do

- **Code signing** for the Mac download (it needs a paid Apple Developer
  account; the `xattr` line above works without it).
- **Anything about the old name.** GitHub redirects
  `github.com/math12345678/terrium` to the new address.

---

## Cheat sheet

| I want to… | type |
|---|---|
| start working | `cd ~/Code/caterva && source .venv/bin/activate` |
| see what it can build | `caterva compose --shapes` |
| build a model | `caterva compose "a toggle switch between two repressors"` |
| build it with real constants | `caterva compose "Michaelis Menten" --subject 2.7.1.1 --organism human --substrate glucose` |
| just get cited constants | `make cite EC=1.1.1.27 SUBSTRATE=pyruvate ORGANISM="Homo sapiens"` |
| see what's wrong with my setup | `make doctor` |
| read the full guide | `docs/USING_CATERVA.md` |

`--subject` wants an **EC number** (like `2.7.1.1`): search the enzyme's name
on <https://www.brenda-enzymes.org> and copy the number at the top of its
page. `--organism` takes a Latin name or a common one (`human`, `mouse`,
`yeast`, `E. coli`).
