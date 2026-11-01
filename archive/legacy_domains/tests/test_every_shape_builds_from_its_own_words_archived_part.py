# Tests from caterva/tests/test_every_shape_builds_from_its_own_words.py that exercised domains archived on
# 2026-09-27. Kept for reference; not collected.

def test_the_guide_counts_the_scenario_presets_correctly() -> None:
    """The guide said "twelve teaching presets"; there were thirteen."""
    import subprocess
    import sys

    words = {10: "ten", 11: "eleven", 12: "twelve", 13: "thirteen",
             14: "fourteen", 15: "fifteen", 16: "sixteen"}
    listed = subprocess.run(
        [sys.executable, "-m", "caterva.app", "sim", "scenarios"],
        capture_output=True, text=True, cwd=ROOT, check=True,
    ).stdout
    count = sum(1 for line in listed.splitlines() if line[:1].isalpha())
    guide = (ROOT / "docs" / "USING_CATERVA.md").read_text()
    assert f"# {words[count]} teaching presets" in guide
