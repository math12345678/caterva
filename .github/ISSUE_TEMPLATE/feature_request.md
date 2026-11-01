---
name: Feature request
about: A new domain, a new capability, or a change to how something works
title: ''
labels: enhancement
assignees: ''
---

## What's the gap?

<!-- What can't Caterva currently do that this would let it do? -->

## If this is a new simulation domain

Please answer these before proposing an implementation approach -- see
`docs/adr/0002-pcr-not-modeled-as-an-ode.md` for why this matters:

- Is this fundamentally a continuous-time process (an ODE, like enzyme
  kinetics or SIR) or a discrete process (like PCR cycles)? Forcing the
  wrong one through the antimony/roadrunner pipeline creates unnecessary
  numerical error to manage.
- What's the exact closed-form solution, independent solver, or physical
  invariant this domain's tests would check against? If there isn't a good
  answer yet, that's worth figuring out before writing the implementation,
  not after.
- Does this domain use any parameter names that might collide with
  antimony reserved words (see `docs/adr/0004-gamma-reserved-keyword.md`)?

## Anything else worth knowing?

<!-- Prior art, related discussions, constraints. -->
