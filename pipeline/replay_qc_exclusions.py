#!/usr/bin/env python3
"""Validate the public QC ledger, reproduce Table S2, and replay recorded exclusions.

No network, model calls, internal audit files or participant data are needed.
Without --input, validate the released ledger and print its counts. With --input
and --out, apply those historical figure-level decisions to supplied JSONL cases.
This replays recorded decisions; it does not independently re-adjudicate images.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "docs/data/retrieval/removed_case_ledger.csv"
SUMMARY = ROOT / "docs/data/retrieval/qc_ledger_summary.json"
GROUPS = {
    "not_radiologic_still_or_wrong_modality": {
        "manual_review_modality_mismatch_or_non_imaging",
        "manual_corpus_review_non_radiologic_figure", "reported_via_viewer_exclude_button", "non_still_media",
    },
    "modality_or_category_outside_collection": {
        "explicit_figure_modality_bucket_mismatch", "stratum_reassigned_to_excluded_vascular_bucket",
    },
    "nonhuman_subject": {"non_human_animal_case", "non_human_animal_study"},
    "original_image_unavailable": {"nxml_graphic_unavailable"},
    "unusable_extraction": {
        "invalid_na_extraction_or_noncase_figure", "diagnosis_extraction_failed_unclear",
        "diagnosis_extraction_failed_na", "extraction_self_check_not_passed",
        "extraction_self_check_not_passed+missing_image_file",
    },
}
EXPECTED = dict(zip(GROUPS, (859, 82, 157, 19, 21)))


def table_s2_group(reason: str) -> str:
    for group, reasons in GROUPS.items():
        if reason in reasons:
            return group
    raise ValueError(f"Unmapped QC reason: {reason}")


def validate_ledger(path: Path = LEDGER, summary_path: Path = SUMMARY) -> tuple[list[dict], dict]:
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    seen = set()
    for r in rows:
        cid, pmcid = r["case_id"], r["pmcid"]
        if cid in seen:
            raise ValueError(f"Duplicate figure ID: {cid}")
        if not re.fullmatch(r"PMC[0-9]+", pmcid) or not cid.startswith(pmcid + "_"):
            raise ValueError(f"Invalid figure/article identifier: {cid}")
        seen.add(cid)
        if r["table_s2_group"] != table_s2_group(r["reason_code"]):
            raise ValueError(f"Incorrect Table S2 group: {cid}")
        historical = r["original_reason_code"]
        if historical != r["reason_code"] and not (
            historical == "reason_not_recorded"
            and r["exclusion_step"] == "manual_exclusion_list_pre_ledger"
            and r["reason_code"] == "manual_corpus_review_non_radiologic_figure"
            and r["reason_provenance"] == "retrospective_group_category"
        ):
            raise ValueError(f"Undocumented reason recoding: {cid}")
    groups = dict(Counter(r["table_s2_group"] for r in rows))
    steps = dict(Counter(r["exclusion_step"] for r in rows))
    reasons = dict(Counter(f"{r['exclusion_step']}:{r['reason_code']}" for r in rows))
    methods = dict(Counter(r["method"] for r in rows if r["method"]))
    reference = json.loads(summary_path.read_text())
    for actual, expected, label in (
        (groups, EXPECTED, "Table S2"),
        (len(rows), reference["B_case_level"]["removed_unique_cases"], "removed cases"),
        (steps, reference["C_removed_by_step"], "exclusion steps"),
        (reasons, reference["C_removed_by_reason"], "reason categories"),
        (methods, reference["C_manual_ledger_methods"], "recorded methods"),
    ):
        if actual != expected:
            raise ValueError(f"QC ledger does not match published {label}")
    return rows, {"removed_cases": len(rows), "table_s2": groups,
                  "retrospectively_categorized_cases": sum(r["reason_provenance"] == "retrospective_group_category" for r in rows)}


def replay(cases: list[dict], ledger: list[dict], allow_partial: bool = False):
    decisions = {r["case_id"]: r for r in ledger}
    seen, kept, removed = set(), [], []
    for case in cases:
        cid = case["case_id"]
        if cid in seen:
            raise ValueError(f"Input must contain unique figures; duplicate: {cid}")
        seen.add(cid)
        if cid in decisions:
            if case.get("pmcid") != decisions[cid]["pmcid"]:
                raise ValueError(f"Input PMCID disagrees with ledger: {cid}")
            removed.append(decisions[cid])
        else:
            kept.append(case)
    missing = sorted(set(decisions) - seen)
    if missing and not allow_partial:
        raise ValueError(f"Input lacks {len(missing)} recorded exclusions; use --allow-partial for a subset")
    return kept, removed, missing


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, default=LEDGER)
    parser.add_argument("--input", type=Path, help="deduplicated figure-level extraction universe (JSONL)")
    parser.add_argument("--out", type=Path, help="new output directory")
    parser.add_argument("--allow-partial", action="store_true", help="allow an input subset; report exclusions not present")
    args = parser.parse_args()
    if bool(args.input) != bool(args.out):
        parser.error("--input and --out must be supplied together")
    ledger, summary = validate_ledger(args.ledger)
    if args.input:
        cases = [json.loads(line) for line in args.input.read_text().splitlines() if line.strip()]
        kept, removed, missing = replay(cases, ledger, args.allow_partial)
        # Never overwrite source cases or an earlier replay.
        args.out.mkdir(parents=True, exist_ok=False)
        (args.out / "retained_cases.jsonl").write_text("".join(json.dumps(c, ensure_ascii=False) + "\n" for c in kept))
        with (args.out / "applied_exclusions.csv").open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(ledger[0]))
            writer.writeheader()
            writer.writerows(removed)
        summary["replay"] = {"input_cases": len(cases), "retained_cases": len(kept),
                             "applied_exclusions": len(removed), "ledger_ids_absent_from_input": missing,
                             "matches_reported_stage_counts": len(cases) == 19740 and not missing and len(kept) == 18602}
        (args.out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
