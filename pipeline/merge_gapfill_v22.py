#!/usr/bin/env python3
"""Build isolated v2.2 inputs after the cardiac stress gap-fill verifier succeeds."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "data/outputs/step6_figure_scope/cases.jsonl"
NEW = ROOT / "data/outputs/gapfill_v22/gapfill_cases_casereport.jsonl"
BASE_LABELS = ROOT / "data/outputs/gapfill_v21/step1_view/case_article_labels.jsonl"
NEW_LABELS = ROOT / "data/outputs/gapfill_v22/step1_view/case_article_labels.jsonl"
BASE_VERIFIER = ROOT / "data/outputs/step2/runs/full_v3_figscope_merged/nova-pro.jsonl"
NEW_VERIFIER = ROOT / "data/outputs/step2/runs/full_v3_gapfill_v22/nova-pro.jsonl"
OUT = ROOT / "data/outputs/v2_2_input"
VERIFIER_OUT = ROOT / "data/outputs/step2/runs/full_v3_v22_final/nova-pro.jsonl"


def rows(path: Path):
    with path.open() as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


def ids(path: Path) -> list[str]:
    return [r["case_id"] for r in rows(path)]


def combine(paths: list[Path], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as target:
        for path in paths:
            with path.open("rb") as source:
                for line in source:
                    if line.strip():
                        target.write(line if line.endswith(b"\n") else line + b"\n")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    base_ids, new_ids = ids(BASE), ids(NEW)
    assert new_ids, "no new article-type-eligible cases"
    assert len(base_ids) == len(set(base_ids)) and len(new_ids) == len(set(new_ids))
    assert not set(base_ids) & set(new_ids), "case ID overlap with v2.2 input"
    assert not {r["pmcid"] for r in rows(BASE)} & {r["pmcid"] for r in rows(NEW)}, "PMCID overlap"

    base_label_rows = list(rows(BASE_LABELS))
    new_label_rows = list(rows(NEW_LABELS))
    base_label_ids = {r["case_id"] for r in base_label_rows}
    new_label_ids = {r["case_id"] for r in new_label_rows}
    assert set(base_ids) <= base_label_ids
    assert set(base_ids + new_ids) <= new_label_ids
    # The v2.2 view has the v2.1 labels followed by all newly classified labels.
    assert new_label_rows[:len(base_label_rows)] == base_label_rows
    assert len(new_label_ids) == len(new_label_rows), "duplicate article labels"

    base_ver = {r["case_id"] for r in rows(BASE_VERIFIER) if r.get("ok")}
    new_ver = {r["case_id"] for r in rows(NEW_VERIFIER) if r.get("ok")}
    assert set(base_ids) <= base_ver, "missing baseline verifier results"
    assert set(new_ids) <= new_ver, "missing new verifier results"
    assert not set(new_ids) & base_ver

    outputs = [OUT / "cases.jsonl", OUT / "case_article_labels.jsonl", VERIFIER_OUT]
    assert not any(p.exists() for p in outputs), "output already exists; inspect before rerunning"
    combine([BASE, NEW], outputs[0])
    # NEW_LABELS is the complete isolated view (v2.1 labels plus new labels).
    combine([NEW_LABELS], outputs[1])
    combine([BASE_VERIFIER, NEW_VERIFIER], outputs[2])
    summary = {"base_cases": len(base_ids), "new_cases": len(new_ids),
               "combined_cases": len(base_ids) + len(new_ids),
               "verifier_base_ok": len(base_ver), "verifier_new_ok": len(new_ver),
               "files": {str(p.relative_to(ROOT)): {"sha256": sha256(p)} for p in outputs}}
    (OUT / "merge_manifest.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
