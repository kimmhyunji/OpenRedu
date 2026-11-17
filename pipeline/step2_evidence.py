#!/usr/bin/env python3
"""Step 2: figure-scoped evidence for the verifier — re-export.

The code moved to src/openredu/core/figure_evidence.py so the extraction agent can use it
without importing pipeline/. This file keeps the existing imports (verifier, step3) working.
Output is byte-identical to the previous version (checked on the full v2.1 corpus).
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from openredu.core.figure_evidence import (  # noqa: E402,F401
    _FIG_REF,
    _SENT_SPLIT,
    build_evidence,
    cited_figures,
    figure_number,
    render_evidence,
    split_sentences,
)

if __name__ == "__main__":
    tests = {
        "CT angiography excluded pulmonary embolism (Figure  1 ).": {1},
        "Follow-up MRI (Figs. 2-4) showed regression.": {2, 3, 4},
        "Shown in Figure 2A,B and Figure 5.": {2, 5},
        "Compare Figures 1 and 3.": {1, 3},
        "No figure here, 12 patients.": set(),
        "Image 3 demonstrates the lesion.": {3},
    }
    for s, want in tests.items():
        got = cited_figures(s)
        assert got == want, (s, got, want)
    print("cited_figures tests passed")
