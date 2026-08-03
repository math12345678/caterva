# Terrium sandbox image.
#
# Gives anyone -- a new contributor, a Kickstart mentor, the backend hire
# once that role is filled -- a single command to get an environment that
# genuinely matches CI, instead of relying on `make setup` working
# identically on every laptop.
#
# Build:  docker build -t terrium-sandbox .
# Run:    docker run -it --rm terrium-sandbox
# (drops into a shell with the environment already verified by check_env.py)
#
# NOTE: this could not be built or tested inside the agent sandbox that
# authored it (no docker binary there) -- verify with the build command
# above before relying on it.

FROM python:3.12-slim

# Python 3.10-3.13 is the supported range (see README.md); 3.12 is used here
# as a supported option (libroadrunner 2.8.0 / numpy 2.2.6 also ship cp313 wheels).

WORKDIR /terrium

# System deps: none should be required -- that's the entire point of using
# libroadrunner/antimony/python-libsbml instead of the tellurium umbrella
# package (see README.md "Do not pip install tellurium"). If a future
# dependency needs build tools, add them here rather than silently letting
# `pip install` fall back to compiling from source.

COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements-dev.txt

COPY . .

# Fail the build immediately if the environment doesn't actually work --
# this is the same script CI runs, so an image that builds successfully has
# already proven it can run a real Michaelis-Menten model end to end.
RUN python scripts/check_env.py

CMD ["bash"]
