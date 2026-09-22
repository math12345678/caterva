# Third-party licence texts

Texts that a downloadable bundle must carry and that no installed package
provides on its own. Terrium's own licence is `../LICENSE` (Apache-2.0);
what Terrium conveys, and under which terms, is `../NOTICE`.

| file | why it is here |
|---|---|
| `LGPL-2.1.txt` | The GNU Lesser General Public License, version 2.1 (February 1999), as published by the Free Software Foundation. python-libsbml is licensed under it, and its wheel ships libSBML's own terms (`LICENSE.txt`) but not the LGPL text those terms point at. A bundle that conveys libSBML must supply this text (LGPL-2.1 §6). Copied 2026-09-21 from the xz package's copy on the build machine (Homebrew) and cross-checked against cairo's and glib's copies: the terms and conditions (sections 0 to 16) are identical in all three; they differ only in the FSF's own address line and the sample notice in the appendix, which the FSF has revised over the years. This is the current revision (URL form). |

The wheel and sdist do not include this directory: `pyproject.toml`'s
`license-files` names `LICENSE` and `NOTICE` only, and `MANIFEST.in` does
not add it. Only `scripts/build_app.py` reads it.
