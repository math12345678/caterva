# Removing the confidential documents from git history

**Status: not done. This is a runbook, not a record of work.**

`61630fe` removed seven confidential documents from the *current* tree. They
are still in every earlier commit, and those commits are on GitHub. This
describes how to finish the job, what it costs, and what to decide first.

Nobody who wrote this is a lawyer or your security team.

---

## What is actually exposed

Seven files, each marked **"Confidential"** on its own pages, one also marked
**"Internal Use Only"**:

```
Docw/terrium_full.docx                    also: claims "Tellurium integration"
Docw/terrium_spec.docx                    also: 4 Tellurium claims
Docw/terrium_mvp_timeline.docx
Docw/terrium_poc_results.docx
Docw/terrium_technical_implementation.docx
Science-Agent-Pipeline/attached_assets/terrium_full_1784327975531.docx
Science-Agent-Pipeline/attached_assets/terrium_spec_1784327975531.docx
```

Verified reachable from `origin/main` — they were pushed, not merely committed
locally.

## Step 0, before anything else: push

**Twenty-eight commits are unpushed**, including `61630fe`, the commit that
removes these files. Until you push, none of it exists on GitHub — not the
removal, not the licence and privacy work, not the guards, not the ADRs.

```bash
git push origin main
```

That alone removes the files from the *current* state of the repository, which
is what a visitor sees. It does not touch history. If you do nothing else,
do this.

## Step 1: decide whether history matters

Two honest answers, and they lead different places.

**"The contents are not really sensitive."** These are a product spec, a
timeline, a proof-of-concept writeup and a roles table for a student project.
"Confidential" may be a template header rather than a considered judgement. If
so, pushing the removal is enough and history can stay. Say so in
`Business/INCORPORATION_CHECKLIST.md` so nobody re-opens this.

**"They should never have been public."** Then history has to be rewritten,
and there is a cost below that you should read before starting.

## Step 2 (only if rewriting): what it costs

- **Every commit hash after the first affected commit changes.** Anyone with a
  clone or fork has a history that no longer matches, and `git pull` will not
  reconcile it. For a project with no outside contributors yet, that cost is
  close to zero — which is why doing it now is far cheaper than later.
- **A force-push is required.** If the repository has branch protection, turn
  it off for the push and back on afterwards.
- **The dependabot branches on the remote** (there are several) will still
  contain the old objects. Delete them, or re-run the rewrite against `--all`.
- **GitHub keeps unreferenced objects reachable for a while** via the commit
  API. After a force-push, open a support request asking them to run garbage
  collection if the contents genuinely matter.
- **Anyone who already cloned still has the files.** A rewrite cannot reach
  them. If that population is non-empty and the contents matter, treat the
  material as disclosed and act accordingly rather than assuming a rewrite
  undoes it.

## Step 3: the commands

`git-filter-repo` is the tool the git project itself recommends; `filter-branch`
is deprecated and slow. It is not bundled — install it first.

```bash
pip install git-filter-repo

# Work on a throwaway clone. filter-repo refuses to run on a repo with a
# remote by default, and that default is protecting you.
cd ..
git clone --no-local terrium terrium-rewrite
cd terrium-rewrite

git filter-repo \
  --path Docw/ \
  --path Science-Agent-Pipeline/attached_assets/terrium_full_1784327975531.docx \
  --path Science-Agent-Pipeline/attached_assets/terrium_spec_1784327975531.docx \
  --invert-paths
```

Verify before pushing anything:

```bash
# Must print nothing.
git log --all --oneline -- Docw/ | head

# Must print nothing.
git rev-list --objects --all | grep -i 'terrium_spec\|terrium_full' | head
```

Then, and only after reading Step 2:

```bash
git remote add origin https://github.com/math12345678/terrium.git
git push --force --all origin
git push --force --tags origin
```

## What this repository does to stop it recurring

- `Docw/` and `Science-Agent-Pipeline/attached_assets/*.docx` are in
  `.gitignore`, so the files stay on disk and cannot be re-added by accident.
- `scripts/check_no_tellurium_integration_claims.py` reads `git ls-files` and
  scans `.docx`/`.pptx`, so a tracked document claiming Tellurium integration
  fails CI. It is what found the two duplicate copies.
- Neither of those checks confidentiality markings. **A guard that fails when a
  tracked document contains "Confidential" or "Internal Use Only" does not
  exist yet** and is the obvious next one to write. It is not written here
  because it would have to be told which documents are deliberately public,
  and that list is yours.

## One thing this does not solve

`check_investor_claims.py` used to check the numbers in four of those documents
against the repository. It cannot see them now. Those numbers still go to
investors; that check is a human one until the documents come back or the
claims move somewhere tracked.
