#!/usr/bin/env python3
"""A runner that fails the way the real one does: structured reason on
stdout, non-zero exit.

This is the exact shape that broke the first version of the resolver, which
read the exit code first and threw the reason away. The stub exists so that
regression has a test rather than a comment.
"""
import json
import sys

print(json.dumps({"ok": False, "error": "BRENDA returned 403 Forbidden"}))
sys.exit(1)
