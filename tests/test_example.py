"""The offline example must reproduce the stored expected output."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_offline_example_matches_expected_output():
    out = subprocess.run([sys.executable, str(ROOT / "examples" / "run_offline_example.py")],
                         capture_output=True, text=True, check=True, cwd=ROOT).stdout
    assert out == (ROOT / "examples" / "expected_output.txt").read_text()
