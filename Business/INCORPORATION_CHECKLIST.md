# Incorporation checklist

Status: **not started.** This is a reference checklist, not a to-do list on a
deadline -- most of this should wait until there's a funding decision or a
paying pilot that actually requires a legal entity to exist.

This is not legal advice. Talk to an actual lawyer (many do free or
discounted work for students/founders through university clinics or
programs like Kickstart) before making any of these decisions for real.

## Before incorporating anything

- [ ] Decide if incorporation is even needed yet, or if operating as an
      unincorporated student project is fine until there's real revenue,
      a real hire, or a real investor requiring it
- [ ] If Kickstart (or any accelerator) requires an entity to receive
      funding, confirm exactly what structure and jurisdiction they require
      *before* picking one independently

## Entity type (decide with a lawyer, not from this checklist)

- [ ] Delaware C-corp vs. LLC vs. staying unincorporated -- tradeoffs differ
      based on whether outside equity investment is expected soon
- [ ] If a C-corp: standard for VC-backed startups, but has real ongoing
      compliance/tax overhead even pre-revenue
- [ ] If an LLC: simpler and cheaper to maintain, but most VCs will ask you
      to convert to a C-corp before investing anyway

## Once an entity type is chosen

- [ ] File formation documents (state-dependent)
- [ ] Get an EIN
- [ ] Open a business bank account (separate from personal -- do this even
      before full incorporation if any real money starts moving)
- [ ] Founder equity split and vesting schedule -- see `CAP_TABLE.md`
- [ ] IP assignment agreement -- make sure the actual codebase (Terium
      engine, BRENDA/KEGG scraper, landing page) is assigned to the company,
      not left ambiguously owned by whoever committed it
- [ ] Basic founder agreement covering what happens if someone leaves
      (directly relevant right now: the backend role isn't locked in yet --
      this should exist before, not after, that hire is finalized)

## Minors and incorporation (specific to this founder)

- [ ] If any founder is a minor, most US states require a parent/guardian
      to sign incorporation documents or hold shares in trust/custodial
      form until majority -- this needs a lawyer's input specifically, not
      a generic checklist item

- [ ] **Capacity to grant the licence, which is a separate question from
      incorporation.** The item above is about forming a company. This one
      applies even if no company is ever formed, and it sits underneath
      everything else in this repository.

      What is not in doubt: a minor can own copyright. Authorship and
      ownership do not have an age requirement.

      What is less settled: a licence grant is contract-like, and in most US
      states a contract entered into by a minor is *voidable by the minor* --
      capable of being disaffirmed, typically until majority or for some
      reasonable period after. Terrium's outbound Apache-2.0 grant and its
      acceptance of inbound contributions under the DCO
      (`docs/INBOUND_LICENSE.md`) are both grants made by a founder who is
      currently a minor.

      Practical effect today: close to none. Nobody is litigating this, and
      it does not stop the project, the repository, or contributions.

      Where it actually bites: diligence. A university partner formalising a
      collaboration, a foundation accepting a donation of the project, an
      acquirer, or a company whose legal team reviews dependencies may ask
      whether the licence they are relying on can be disaffirmed. It is
      cheaper to answer that now than to be asked it cold.

      The usual remedy is a parent or guardian countersigning the licence
      grant, or holding the copyright in trust until majority. Which is
      appropriate depends on the state and on what the project becomes -- ask
      the same lawyer the item above already requires. This is a flag, not
      advice; nobody involved in writing it is a lawyer.
