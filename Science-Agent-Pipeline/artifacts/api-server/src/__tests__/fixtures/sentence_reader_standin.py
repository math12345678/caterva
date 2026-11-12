"""Stand-in for `python -m caterva.compose.read` in the API's tests.

Answers with the reading the real reader printed for the same sentence
against live BRENDA (sentence_readings.json, recorded 2026-11-11), so the
tests of how the API USES a reading are offline. The reader itself is pinned
offline by caterva/tests/test_compose_read.py.
"""
import json
import sys
from pathlib import Path

readings = json.loads((Path(__file__).with_name("sentence_readings.json")).read_text())["readings"]
query = sys.argv[1]
if query not in readings:
    print(json.dumps({"error": f"no recorded reading for {query!r}"}))
    sys.exit(1)
reading = readings[query]
print(json.dumps(reading))
sys.exit(0 if reading.get("ec") and not reading.get("refusal") else 3)
