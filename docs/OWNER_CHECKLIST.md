# What to do on your side

Written 2026-09-24 for the owner of this repository, after the v0.3.3 work.
Every command below was run before it was written down, except the three
that only you can run (they need your GitHub login or your Mac's
settings), and those say so.

---

## Where things stand

**You've already done the hard part.** On 2026-09-24 you cloned into
`~/Code/terrium`, ran `make setup`, got real cited constants, and published
**v0.3.3**.

Your run also showed two real problems, and both are fixed in **v0.3.4**:

- On a model whose constants all came from the literature, the verdict at
  the top said "no search has been run", directly above the table of
  citations. It now says **GROUNDED**.
- It only worked with certain wordings. Plain "Michaelis Menten" was
  refused, and so were 21 of the 36 shapes described in their own words.
  All 36 now build (see "Try it on your own enzyme" below).
- `--organism human` found nothing, and typos gave unhelpful answers. It
  now reads common names and tells you what to fix.

The release candidate `v0.3.4-rc.2` is on GitHub and building.

**What's left for you: update your copy (1 minute), then Steps 2 and 3
again with the new name (3 minutes).**

### Update your copy

```bash
cd ~/Code/terrium && source .venv/bin/activate
git pull
terrium --version
```

You should see `terrium 0.3.4`. You don't need `make setup` again.
Then re-run the rabbit command below: the verdict now says GROUNDED.

---

## Step 1 — Get a clean copy, outside iCloud (done ✅)

### Why

Your current folder, `~/Desktop/Coding/Terrium`, has three problems:

1. **It's on your Desktop, which iCloud syncs.** iCloud quietly marks
   files inside `.venv` as hidden, and Python 3.13 then ignores them, so
   `terrium` stops working at random with `No module named 'Terium'`.
   That, and the `Operation timed out` error you hit, are both iCloud.
2. **It's an old version.** It's on commit `54c3216`, from before any of
   this work.
3. **It has your own unsaved edits in it** (Business documents, some
   api-server files, README, Makefile). Updating it in place could collide
   with those.

A fresh copy somewhere else fixes all three, and leaves your old folder —
and those edits — exactly as they are.

### Do this

Open **Terminal** and paste these one block at a time:

```bash
mkdir -p ~/Code && cd ~/Code
git clone https://github.com/math12345678/terrium.git
cd terrium
```

You should see `Cloning into 'terrium'...` and a few progress lines.

```bash
make setup
```

This takes two to five minutes and downloads about 120 MB. It prints
nothing for a while in the middle — that's normal, not a hang. It ends
without the word `FAILED`.

```bash
source .venv/bin/activate
terrium --version
```

You should see:

```
terrium 0.3.4
```

The `(base)` in your prompt from Anaconda doesn't matter — `source
.venv/bin/activate` takes priority over it.

### Check it works with real data

```bash
terrium compose "Michaelis-Menten with a competitive inhibitor" --subject 1.1.1.27 --organism "Homo sapiens" --substrate pyruvate
```

It takes about twenty seconds. Scroll to **Where the numbers come from**.
You should see real values with real citations:

```
**2 of 3 constant(s) came from the literature**, searched for `1.1.1.27`
in Homo sapiens, substrate pyruvate.

| `reaction_Ki`   | 0.00059 mM | literature (Homo sapiens) | BRENDA ref 739793 |
| `reaction_Km`   | 0.03 mM    | literature (Homo sapiens) | BRENDA ref 286469 |
| `reaction_kcat` | 100.0 1/s  | **placeholder**           | no value in the organism requested; measurements exist in other organisms ... |
```

That is the whole point of Terrium, working on your machine.

The `placeholder` on kcat is correct, not a failure: nobody has measured
it in human LDH, and Terrium never borrows another species' number without
you asking. To ask, name one of the organisms it lists:

```bash
terrium compose "Michaelis-Menten with a competitive inhibitor" --subject 1.1.1.27 --organism "Oryctolagus cuniculus" --substrate pyruvate
```

Now all three constants are measured, in rabbit, and all three come from
one paper (`BRENDA ref 741355`), and the verdict at the top says
**GROUNDED**.

### Try it on your own enzyme

It is not limited to lactate dehydrogenase. Any enzyme works, if you give
it three things:

1. **The EC number**: search the enzyme's name on
   https://www.brenda-enzymes.org, and the number is at the top of its
   page (hexokinase is `2.7.1.1`).
2. **The substrate**, as BRENDA names it (`glucose`, `ethanol`,
   `acetylcholine`).
3. **The organism**: Latin (`Homo sapiens`) or a common name (`human`,
   `mouse`, `yeast`, `E. coli`). The report says how it read it.

```bash
terrium compose "Michaelis Menten" --subject 2.7.1.1 --organism "Homo sapiens" --substrate glucose
```

These were each run once, unscripted, on 2026-09-24:

| enzyme | organism | result |
|---|---|---|
| hexokinase `2.7.1.1`, glucose | human | Km 6.0 mM and kcat 40.1 1/s, both cited: **GROUNDED** |
| alcohol dehydrogenase `1.1.1.1`, ethanol | yeast | Km 5.7 mM and kcat 143 1/s, both cited: **GROUNDED** |
| chymotrypsin `3.4.21.1`, N-acetyl-L-tyrosine ethyl ester | cow | Km 1.17 mM and kcat 119.5 1/s, one paper: **GROUNDED** |
| acetylcholinesterase `3.1.1.7`, acetylcholine | human | Km cited; kcat never measured in human, so it says so |

When a number doesn't exist for your organism, it keeps a placeholder
and tells you which organisms *do* have one. It never makes one up.

If you mistype something, it tells you what to fix:

| you type | it says |
|---|---|
| `--substrate glucoze` | the substrates BRENDA holds for this enzyme, e.g. `D-glucose` |
| `--subject 9.9.9.9` | BRENDA has no enzyme 9.9.9.9, and how to look one up |
| `--subject 2.7.1` | that's an incomplete EC number; a full one has four parts |
| no `--substrate` | Km tables are per substrate, so add `--substrate` |

To see every shape it can build: `terrium compose --shapes`. Each line
there is something you can type as-is.

### If something goes wrong

Run this and read the lines marked `FAIL` — each one prints its own fix:

```bash
make doctor
```

If you're stuck, copy the last 30 lines of the terminal and paste them to
Claude.

### Every day after this

Each time you open a new Terminal window:

```bash
cd ~/Code/terrium && source .venv/bin/activate
```

Then `terrium` works. That's the only thing to remember.

---

## Step 2 — Check the release built (2 minutes)

Only you can see this page; it needs your GitHub login.

1. Open **https://github.com/math12345678/terrium/actions/workflows/release.yml**
2. Find the row labelled **`v0.3.4-rc.2`** (the newest one, at the top).
3. Look at the icon on the left of that row:

| you see | it means | do this |
|---|---|---|
| 🟡 yellow circle | still building | wait five minutes and refresh |
| ✅ green tick | everything passed | go to Step 3 |
| ❌ red cross | one part failed | click the row, click the red job, scroll to the bottom, copy the last 40 lines, paste them to Claude |

A red cross publishes nothing. There is no way for a failure here to put a
broken release on the page, so there's nothing to undo.

---

## Step 3 — Publish v0.3.4 (1 minute)

Only after Step 2 shows a **green tick**. In the Terminal from Step 1:

```bash
cd ~/Code/terrium
git fetch --tags
git tag -a v0.3.4 "v0.3.4-rc.2^{}" -m "Terrium v0.3.4"
git push origin v0.3.4
```

The quotes around `"v0.3.4-rc.2^{}"` matter — zsh treats `^` and `{}`
specially without them. The last line prints `* [new tag] v0.3.4 ->
v0.3.4`.

Wait about five minutes, then open
**https://github.com/math12345678/terrium/releases**. You should see
**Terrium v0.3.4** at the top with downloads for Mac, Linux and Windows.

To try the Mac download: download `terrium-0.3.4-macos-arm64.tar.gz`, then

```bash
cd ~/Downloads && tar xzf terrium-0.3.4-macos-arm64.tar.gz && cd terrium
xattr -dr com.apple.quarantine .
./terrium compose "a toggle switch between two repressors"
```

(The downloaded app can't do the literature search — only the copy from
Step 1 can. The app says so if you try.)

---

## Later, when you're ready — nothing here is urgent

### Your old folder

`~/Desktop/Coding/Terrium` still has your unsaved edits. Don't delete it.
When you want to deal with them, see what they are:

```bash
cd ~/Desktop/Coding/Terrium && git status
```

and ask Claude to help you save them onto a branch of the new copy. Once
that's done, the old folder can go, and with it the iCloud problem for
good.

### Three decisions before the repository can go public

These are choices, not tasks, and only you can make them. Nothing is
broken while they wait; the repository simply stays private.

1. **Confidential documents in the history.** Seven Word files marked
   "Confidential" were removed on 2026-08-16, but old copies still exist
   in git's history, so anyone who clones could dig them out. Either
   decide they aren't really sensitive, or have them scrubbed from history
   *before* going public (scrubbing afterwards is too late). The exact
   procedure is `docs/REMOVE_CONFIDENTIAL_FROM_HISTORY.md`.
2. **The `Business/` folder.** It includes a cap table and a fundraising
   tracker naming investors. Your unsaved edits add more Business
   documents. Decide whether those are meant to be public; if not, they
   need to move to a private repository first.
3. **Which GitHub name is the real one.** The code currently refers to
   three: `Terrium-sim/main`, `Terrium-sim/terrium` and
   `math12345678/terrium` (where everything actually is today). Pick one;
   Claude can then change every reference in one go.

### Things you do *not* need to do

- **Fix the `gh` login.** Nothing above uses it. (If you want Claude to
  be able to read the GitHub build logs itself: `gh auth login` and follow
  the prompts.)
- **PyPI** (`pip install terrium` from the internet). A separate decision;
  nothing depends on it.
- **Code signing.** It would remove the Mac security prompt, but needs a
  paid Apple Developer account ($99/year). The `xattr` line works without
  it.

---

## One-page cheat sheet

| I want to… | type |
|---|---|
| start working | `cd ~/Code/terrium && source .venv/bin/activate` |
| see what it can build | `terrium compose --shapes` |
| build a model | `terrium compose "a toggle switch between two repressors"` |
| build it with real constants | `terrium compose "..." --subject 1.1.1.27 --organism "Homo sapiens" --substrate pyruvate` |
| just get cited constants | `make cite EC=1.1.1.27 SUBSTRATE=pyruvate ORGANISM="Homo sapiens"` |
| see what's wrong with my setup | `make doctor` |
| read the full guide | `docs/USING_TERRIUM.md` |

`--subject` wants an **EC number** (like `1.1.1.27`), not a name —
"lactate dehydrogenase" means six different enzymes, and Terrium lists all
six rather than guessing. Find an enzyme's EC number by searching its name
on https://www.brenda-enzymes.org.
