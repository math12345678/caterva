# business

Part of [**Terrium**](https://github.com/Terrium-sim/main) — scientific computing for teaching labs.

Strategy, pitch material, and the build-stage record. 83 files.

## `build-stages/`

The engineering diary — every stage documents what was built, what broke,
and what the failure taught. It is kept because the mistakes are the useful
part:

- a guard that printed *"every collected test ran"* while 275 tests failed
  to collect
- a documentation checker that reported 242 of 294 endpoints as fake, when
  it had been parsing half the route table and the real number was 19
- a model comparator that told every user *"Both jobs used the undefined
  model"* because it read a field off the wrong object
- a CSV exporter that wrote a blank cell for every genuine zero

These records are **not** rewritten to match the present. They describe what
was true on a date, and editing them to look better would destroy the only
thing that makes them worth keeping.

---

This repository is a submodule of [`Terrium-sim/main`](https://github.com/Terrium-sim/main). Clone the whole system with:

```bash
git clone --recursive https://github.com/Terrium-sim/main.git
```
