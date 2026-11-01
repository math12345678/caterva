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

# msprime is stdpopsim's C-extension dependency, and it publishes wheels
# only for manylinux x86_64, macOS and win_amd64 -- there is no Linux
# aarch64 wheel for any version. `docker build` on an Apple Silicon Mac
# produces a linux/arm64 image, so pip finds no wheel
# (`pip download msprime --only-binary=:all:` reports "from versions:
# none"), falls back to the sdist, and needs GSL and a C toolchain to build
# it. pip does not warn in that situation, it fails, and it takes the whole
# `pip install -r requirements-dev.txt` step and the image build down with
# it -- so these packages are load-bearing on arm64 even though x86_64
# never touches them. This is the concrete form of the libgsl-dev problem
# ADR 0021 records as "not installable in the review sandbox".
#
# make and git are here so `make test` and `git commit` work in a
# standalone `docker run`, not only under VS Code.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libgsl-dev \
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
