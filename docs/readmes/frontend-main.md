# frontend-main

Part of [**Terrium**](https://github.com/Terrium-sim/main) — scientific computing for teaching labs.

The dashboard UI served by the Terrium web server.

Deliberately small — one page. The marketing site is
[`terrium-site`](https://github.com/Terrium-sim/terrium-site) and the landing page is
[`landing`](https://github.com/Terrium-sim/landing); both are separate products with their own build
chains, and folding them together would produce a repository with three
unrelated toolchains and no shared code.

## Running it

The dashboard is served by `src/web/server.ts` in
[`backend-main`](https://github.com/Terrium-sim/backend-main):

```bash
npm run web
open http://localhost:3000
```

## The split, and the risk it carries

The page's fetch URLs and the server's routes now live in different
repositories. That is exactly the drift that
`scripts/check_example_endpoints.py` in [`wiring-main`](https://github.com/Terrium-sim/wiring-main)
exists to catch: it resolves every documented endpoint against both servers'
real route tables and fails the build when one goes missing.

That guard needs the full checkout, which is why
[`main`](https://github.com/Terrium-sim/main) pulls every repository in as a submodule.

---

This repository is a submodule of [`Terrium-sim/main`](https://github.com/Terrium-sim/main). Clone the whole system with:

```bash
git clone --recursive https://github.com/Terrium-sim/main.git
```
