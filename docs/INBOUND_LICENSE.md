# What your contribution arrives under

**Short version:** you keep your copyright. You license the work to the
project under Apache-2.0, the same licence Terrium ships under. There is no
CLA to sign and no copyright to assign.

This is not legal advice. The university question below in particular needs
counsel, not a document written by the project it concerns.

## Why this file exists

`LICENSE` closes with the reasoning behind relicensing to Apache-2.0, and
one of the three reasons was this:

> Contributors. Terrium is taking on student contributors from multiple
> institutions. An all-rights-reserved repository cannot accept outside
> contributions cleanly — there is no inbound licence for the contribution
> to arrive under.

The problem was named. The answer was never written down anywhere. A
contributor who went looking for what happens to their work found a
paragraph explaining why the previous state was bad, and nothing saying what
the current state is.

That is a worse gap than it looks. Somebody deciding whether to spend a
weekend on a pull request is deciding what happens to a weekend of their
work, and "it's probably fine" is not an answer anyone should have to accept
from a project whose entire pitch is that claims should be checkable.

## The inbound licence

Apache-2.0 supplies it. Section 5, in full:

> **5. Submission of Contributions.** Unless You explicitly state otherwise,
> any Contribution intentionally submitted for inclusion in the Work by You
> to the Licensor shall be under the terms and conditions of this License,
> without any additional terms or conditions. Notwithstanding the above,
> nothing herein shall supersede or modify the terms of any separate license
> agreement you may have executed with Licensor regarding such
> Contributions.

So opening a pull request against this repository licenses that contribution
under Apache-2.0. This is the "inbound = outbound" arrangement, and it is
why no CLA is needed: the licence the project ships under already says what
happens to what arrives.

**You keep your copyright.** Apache-2.0 §5 is a licence grant, not a
transfer. Nobody is asking you to assign anything, and if a document ever
does ask you to, read it carefully — that is a materially different request.

## Sign-off (DCO)

Terrium uses the [Developer Certificate of Origin](https://developercertificate.org/),
the same lightweight mechanism the Linux kernel and most of the CNCF use. It
is one line per commit:

```bash
git commit -s -m "Fix the CSV zero-export bug"
```

which appends:

```
Signed-off-by: Your Name <your@email.example>
```

That line is you asserting the four points of the DCO — in plain terms, that
you wrote the contribution or have the right to submit it, and that you
understand it is public and recorded.

**One open question, stated rather than hidden.** This document describes
grants running in both directions — Terrium's outbound Apache-2.0 licence, and
your inbound contribution. Terrium's founder and copyright holder is currently
a minor. A minor can unambiguously *own* copyright, but a licence grant is
contract-like, and in most US states a minor's contract is voidable by that
minor. Nobody involved here is a lawyer and this is not advice; the question
is recorded, with what is and is not uncertain, in
[`Business/INCORPORATION_CHECKLIST.md`](../Business/INCORPORATION_CHECKLIST.md).
It changes nothing about contributing today. It is written down because a
contributor deserves to know the shape of what they are relying on, and
because finding it in someone else's diligence review is worse.

**Why a DCO and not a CLA.** A CLA is a contract that has to be read,
signed, tracked and stored, and it deters exactly the drive-by contribution
a small project most wants. The DCO is a statement you make in the commit
itself, with no paperwork on either side. It is weaker than a CLA and that
is the trade being made deliberately.

Sign-off is **not currently enforced in CI.** Adding a bot that rejects
unsigned commits is a decision with a cost — it blocks first-time
contributors on a step they have never heard of — and it has not been made.
Recording that it is unenforced is the point: a requirement nobody checks
should not be described as if it were.

## If you are a student, read this part

This is the piece most likely to cause a real problem, and it is the piece
this project cannot answer for you.

**Your university may have a claim on work you produce.** Institutional IP
policies vary enormously. Some claim anything made with university
resources; some claim only work arising from funded research; some claim
nothing from unpaid personal projects. Whether Terrium work falls inside
your institution's policy depends on that policy, on whether you are being
paid, on whose equipment you use, and on your specific enrolment or
employment terms.

If your university owns your contribution, then **you cannot license it
under Apache-2.0 and your DCO sign-off would be inaccurate** — not because
you were dishonest, but because you were not the one with the right to
grant.

What to do:

1. Read your institution's IP policy, or ask the technology-transfer or
   research office. They answer this question routinely and it is not an
   unusual thing to ask.
2. If it is unclear, ask before your first substantial contribution rather
   than after. Unwinding a contribution later is far worse than a week's
   delay.
3. If your institution does claim it, say so. There are normal ways to
   handle it — an institutional licence, a written release, or scoping your
   work to what falls outside the policy. None of them work retroactively
   and in silence.

The project will not treat this as a problem you created. It is a real
feature of how universities work, and asking about it is the responsible
thing rather than an obstacle.

## Third-party code in a contribution

Do not paste code from Stack Overflow, another repository, a textbook or a
model's output without checking what it is licensed under and saying so in
the pull request.

Terrium is Apache-2.0. Code arriving under GPL, or under no licence at all,
cannot simply be absorbed — `scripts/check_dependency_licenses.py` exists
because an unlicensed dependency was found in this tree, and the same
standard applies to a copied function.

If you are unsure whether something counts, say so in the PR. That is a
normal question, not an admission.

## What is deliberately not settled here

- **Enforcing sign-off in CI.** Unmade decision, cost stated above.
- **Whether a CLA becomes necessary at incorporation.** See
  `Business/INCORPORATION_CHECKLIST.md`; that is a lawyer's call and it may
  change this document.
- **Relicensing.** Apache-2.0 with no CLA means the project cannot
  unilaterally relicense contributions later. That is a real constraint,
  accepted knowingly: the alternative is asking every contributor to sign
  something, and the constraint is the price of not doing that.
