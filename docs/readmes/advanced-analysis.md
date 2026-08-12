# advanced-analysis

Part of [**Terrium**](https://github.com/Terrium-sim/main) — scientific computing for teaching labs.

Analysis scripts and the figures they produce.

Every figure is regenerated from the engine rather than drawn by hand, so a
change in the simulation shows up in the picture:

`01_michaelis_menten` · `02_competitive_inhibition` · `03_sir` · `04_seir` ·
`05_gillespie_ssa` · `06_wright_fisher` · `07_pcr`

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python scripts/generate_figures.py
```

`venv/` is gitignored — it is 629 MB.

---

This repository is a submodule of [`Terrium-sim/main`](https://github.com/Terrium-sim/main). Clone the whole system with:

```bash
git clone --recursive https://github.com/Terrium-sim/main.git
```
