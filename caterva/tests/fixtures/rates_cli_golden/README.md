# Golden output of `caterva rates`, from before it had a library entry point

Each file is one invocation of the command on `examples/rates/puromycin.csv` (R's
`datasets::Puromycin`, the real table): its argv, exit code, stdout and stderr.

They were written by running the command exactly as it was on `origin/main`
at commit 3d10e64, before `caterva/rates/run.py` was extracted from
`__main__.main`, and the same invocations were then run on the refactored
code: all sixteen outputs were identical, byte for byte. The test
`caterva/tests/test_rates_cli_unchanged.py` keeps that true: it runs the
invocations again and compares.

Two things differ between machines and are masked on both sides of the
comparison: the Caterva version, and the Python, NumPy and SciPy versions the
methods paragraph and the JSON name. Nothing else is masked.

The literature layer is stubbed with a resolver that raises, so no run here
reads the network. The case `ec-unconvertible-unit` is the command declining a
comparison on its own, before the resolver is asked: Puromycin's substrate is in
ppm, which has no molar conversion.

Nothing in these files was edited by hand.
