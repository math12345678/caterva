# Caterva sandbox / Dev Container image: the Python simulation and
# literature stack, proven working at build time.
#
# This is deliberately a SECOND Dockerfile rather than the one at the
# repository root. The root Dockerfile builds the Node API server that
# docker-compose.yml runs and contains no Python interpreter at all; it
# replaced the original Python sandbox image in place, and because
# .devcontainer/devcontainer.json pointed at "../Dockerfile" by path, every
# Dev Container and Codespace built from this repo since then has been a
# Node image whose postCreateCommand ran `python scripts/check_env.py`
# against an interpreter that was not installed. Two images with two
# purposes now live in two files, which is what stops that recurring.
#
# Build:  docker build -f .devcontainer/Dockerfile -t caterva-sandbox .
# Run:    docker run -it --rm caterva-sandbox

FROM python:3.12-slim

# 3.12 sits inside the supported window and every pinned dependency
# publishes a cp312 wheel, so nothing here compiles on x86_64.
# See docs/adr/0014-python-version-support.md.

WORKDIR /workspaces/caterva

# make and git are here so `make test` and `git commit` work in a
# standalone `docker run`, not only under VS Code.
#
# 2026-11-01: this line also installed build-essential and libgsl-dev. Its
# comment said why: msprime, stdpopsim's C-extension dependency, has no
# Linux aarch64 wheel, so on an Apple Silicon `docker build` pip fell back
# to its sdist and needed GSL and a C toolchain (the libgsl-dev problem ADR
# 0021 records). stdpopsim left requirements.txt on 2026-08-16 (ADR 0061)
# and its manifest moved to archive/legacy_domains/ on 2026-11-01, so
# nothing installed here builds msprime, and every other direct pin
# publishes a Python 3.12 Linux wheel -- except that libroadrunner 2.8.0
# publishes no Linux aarch64 wheel and no sdist (PyPI, checked
# 2026-11-01), so a native arm64 build fails at pip with or without a
# compiler. Build with `--platform linux/amd64` on Apple Silicon.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        make \
        git \
    && rm -rf /var/lib/apt/lists/*

# Dependencies before source: editing a test must not re-download 120 MB of
# wheels.
COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements-dev.txt

COPY . .

# Fail here rather than in front of a contributor. This is the same script
# CI runs, so an image that builds has already integrated a real
# Michaelis-Menten model and compared the answer to the closed form.
RUN python scripts/check_env.py

CMD ["bash"]
