#!/usr/bin/env python3
"""Step 2: recover verifier results from responses that were saved but failed validation (no API call).

Two deterministic failure types seen in the full run:
  - an off-vocabulary laterality verdict (e.g. "bilateral" instead of supported/unclear/not_supported):
    the laterality verdict is set to "unclear"; every other field must still be valid
  - a JSON syntax error caused by a curly opening quote closed by a straight quote inside a reason
    string (“Fetus B"): the pair is rewritten as “Fetus B”
For each case whose run records are all not-ok, every saved attempt's raw_text is re-parsed with these two
repairs only. A recovered result is appended to the run file as a new record with "salvaged": true and the
repair applied, so it can be excluded or audited later. Nothing is deleted or overwritten.
Usage: python3 pipeline/step2_salvage.py --run runs/full_v3/nova-pro.jsonl
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).parent))
from step2_verifier import VERDICTS, valid  # noqa: E402
from step2_verifier import parse_json as parse  # noqa: E402

CURLY_MIXED = re.compile(r"“([^\"”\n]*)\"")


def repair(text: str) -> tuple[dict | None, list[str]]:
    fixes = []
    p = parse(text)
    if p is None and CURLY_MIXED.search(text):
        p = parse(CURLY_MIXED.sub(r"“\1”", text))
        fixes.append("curly_quote_pair")
    if isinstance(p, dict) and isinstance(p.get("laterality"), dict) and p["laterality"].get("verdict") not in VERDICTS:
        p["laterality"] = {**p["laterality"], "verdict": "unclear",
                           "original_verdict": p["laterality"].get("verdict")}
        fixes.append("laterality_off_vocabulary_to_unclear")
    return (p if valid(p) else None), fixes


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True, help="path relative to data/outputs/step2")
    args = ap.parse_args()
    path = ROOT / "data/outputs/step2" / args.run
    recs = defaultdict(list)
    for line in path.open():
        if line.strip():
            r = json.loads(line)
            recs[r["case_id"]].append(r)
    failed = [k for k, v in recs.items() if not any(x.get("ok") for x in v)]
    out = []
    for cid in failed:
        for r in reversed(recs[cid]):
            for a in reversed(r.get("attempts", [])):
                p, fixes = repair(a.get("raw_text") or "")
                if p is not None:
                    out.append({**{k: r[k] for k in ("case_id", "model_short", "model_id", "prompt_version") if k in r},
                                "attempts": [], "parsed": p, "ok": True, "salvaged": True, "repairs": fixes,
                                "salvaged_from_called_at": a.get("called_at"),
                                "salvaged_at": datetime.now(timezone.utc).isoformat(),
                                "input_tokens": 0, "output_tokens": 0})
                    break
            if out and out[-1]["case_id"] == cid:
                break
    with path.open("a") as f:
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(json.dumps({"failed_cases": len(failed), "salvaged": [(r["case_id"], r["repairs"]) for r in out],
                      "still_failed": sorted(set(failed) - {r["case_id"] for r in out})}, indent=2))


if __name__ == "__main__":
    main()
