#!/usr/bin/env python3
"""Step 5: reconstruct the Figure 2 corpus flow and decompose the
21,169 -> 18,602 step by reason, at case level where records allow.

Sources (read-only):
  - run manifests: data/manifests/manifest_*.json (per collection run funnel)
  - extraction outputs: data/{final,processed,processed_2017_2019}/cases_*.jsonl,
    data/processed_msk_ultrasound_recall_adjudicated/
  - reason ledgers: audits/manual_exclusion_ledger_20260718.jsonl,
    data/final_consolidated/excluded_manifest.jsonl,
    processed_msk_ultrasound_recall_adjudicated/manifest.json
  - freezes: apdr460_20260721_v1, abr25_2017_2026_nongap_v1, openredu_manuscript_2017_2026_v2
No LLM, no network. This historical compiler requires the internal inputs above.
For the released decisions and Table S2 counts without those inputs, run
python pipeline/replay_qc_exclusions.py.
"""
from __future__ import annotations

import ast
import csv
import glob
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "data"
OUT = ROOT / "data/outputs/step5/qc_ledger"
EXCLUDED_STRATA = {"CT_CHEST_VASC", "US_VASCULAR"}
CFG_SNAP_ERR = "data/outputs/v1_snapshot/data/error_excluded.json"
FUNNEL = ["pmc_query_hits", "nxml_fetched", "license_passed", "figures_with_caption", "rule_exclude",
          "uncertain_rejected", "rule_include", "extraction_failed", "extraction_success", "self_check_escalated"]
SOURCES = {
    "final": "final/cases_*.jsonl",
    "processed": "processed/cases_*.jsonl",
    "processed_2017_2019": "processed_2017_2019/cases_*.jsonl",
    "msk_ultrasound_recall": "processed_msk_ultrasound_recall_adjudicated/cases.jsonl",
}


def jl(path: Path):
    with path.open() as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def run_manifests() -> list[dict]:
    rows = []
    for f in sorted(glob.glob(str(D / "manifests/manifest_*.json"))):
        m = json.load(open(f))
        fun = m.get("funnel")
        fun = ast.literal_eval(fun) if isinstance(fun, str) else fun
        if not fun:
            continue
        mv = m.get("model_versions")
        rows.append({"manifest": Path(f).name, "run_id": m.get("run_id"), "modality": m.get("modality"),
                     "timestamp": m.get("timestamp"), "harvest_date": m.get("harvest_date"),
                     "year_start": m.get("year_start"), "year_end": m.get("year_end"),
                     "config_hash": m.get("config_hash"), "cache_mode": m.get("cache_mode"),
                     "query_strings_recorded": bool(m.get("query_strings") not in (None, "", "{}", {})),
                     **{k: int(fun.get(k, 0)) for k in FUNNEL}})
    return rows


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    # ── A. run-level funnel (Figure 2 as submitted) ──
    runs = run_manifests()
    with (OUT / "run_manifest_funnel.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(runs[0]))
        w.writeheader()
        w.writerows(runs)
    r23 = [r for r in runs if r["modality"] not in EXCLUDED_STRATA]
    fig2 = {k: sum(r[k] for r in r23) for k in FUNNEL}
    per_stratum = defaultdict(lambda: Counter())
    for r in r23:
        per_stratum[r["modality"]]["runs"] += 1
        for k in FUNNEL:
            per_stratum[r["modality"]][k] += r[k]

    # ── B. case-level universe of extraction outputs (23 strata) ──
    last: dict[str, tuple[str, dict]] = {}
    rows_seen = Counter()
    for src, pat in SOURCES.items():
        for f in glob.glob(str(D / pat)):
            for rec in jl(Path(f)):
                rows_seen[src] += 1
                last[rec["case_id"]] = (src, rec)
    apdr460 = {r["case_id"]: r for r in jl(D / "freeze/apdr460_20260721_v1/cases.jsonl")}
    v2_primary = {r["case_id"] for r in jl(D / "freeze/openredu_manuscript_2017_2026_v2/primary_cases.jsonl")}

    def stratum(cid: str) -> str:
        return (apdr460.get(cid) or last[cid][1]).get("modality", "")

    # Universe: unique case IDs whose extraction-output modality is one of the 23 strata, plus
    # v2 cases extracted in a vascular-bucket run and re-assigned to a retained stratum.
    universe = {c for c in last if last[c][1].get("modality") not in EXCLUDED_STRATA}
    reassigned_into_retained = {c for c in v2_primary if c not in universe}
    universe |= reassigned_into_retained
    # Cases re-labelled to a vascular bucket before the category-level exclusion.
    relabeled_vasc = {c for c in universe if c in apdr460 and apdr460[c].get("modality") in EXCLUDED_STRATA}

    # ── C. reason ledgers ──
    manual = {r["case_id"]: r for r in jl(ROOT / "audits/manual_exclusion_ledger_20260718.jsonl")}
    builder = {}
    for r in jl(D / "final_consolidated/excluded_manifest.jsonl"):
        builder.setdefault(r["case_id"], r)
    msk_manifest = json.load(open(D / "processed_msk_ultrasound_recall_adjudicated/manifest.json"))
    msk_excl = msk_manifest.get("promotion_excluded_cases")
    msk_excl = ast.literal_eval(msk_excl) if isinstance(msk_excl, str) else (msk_excl or [])
    msk_reason = {x["case_id"]: "+".join(x["reasons"]) for x in msk_excl}
    image_excl = {r["case_id"]: r for r in jl(ROOT / "audits/image_exclusions_20260718.jsonl")}
    viewer_reports = set(json.load(open(ROOT / CFG_SNAP_ERR))) if (ROOT / CFG_SNAP_ERR).exists() else set()

    ledger = []
    for cid in sorted(universe):
        if cid in v2_primary:
            continue
        src, rec = last[cid]
        if cid in relabeled_vasc:
            step, code = "category_level_qc", "stratum_reassigned_to_excluded_vascular_bucket"
        elif cid in manual:
            m = manual[cid]
            step, code = "manual_or_automated_qc_ledger", m["exclusion_reason"]
            method = m.get("exclusion_method")
        elif cid in image_excl:
            step, code = "image_integrity_audit", image_excl[cid].get("exclusion_reason") or "excluded_no_image"
        elif cid in viewer_reports:
            step, code = "viewer_error_report", "reported_via_viewer_exclude_button"
        elif cid in builder and builder[cid].get("reason_code") not in (None, "", "canonical_exclusion_ledger"):
            step, code = "corpus_builder_eligibility", builder[cid]["reason_code"]
        elif cid in builder:
            step, code = "manual_exclusion_list_pre_ledger", "manual_corpus_review_non_radiologic_figure"
        elif cid in msk_reason:
            step, code = "msk_ultrasound_recall_promotion", msk_reason[cid]
        else:
            step, code = "unknown", "unrecorded"
        ledger.append({"case_id": cid, "pmcid": rec.get("pmcid"), "stratum": stratum(cid), "source": src,
                       "exclusion_step": step, "reason_code": code,
                       "method": manual.get(cid, {}).get("exclusion_method", "")})
    with (OUT / "removed_case_ledger.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(ledger[0]))
        w.writeheader()
        w.writerows(ledger)

    # ── D. category-level exclusion (vascular buckets), for Figure 2 completeness ──
    vasc_in_v1 = Counter(r["modality"] for r in jl(D / "freeze/abr25_2017_2026_nongap_v1/cases.jsonl")
                         if r.get("modality") in EXCLUDED_STRATA)

    summary = {
        "A_figure2_as_submitted": {
            "definition": "Sum over collection-run manifests of the 23 retained strata (not unique articles/figures).",
            "n_runs": len(r23), "runs_with_query_strings_recorded": sum(r["query_strings_recorded"] for r in r23),
            **fig2},
        "B_case_level": {
            "extraction_output_rows_read": dict(rows_seen),
            "unique_extracted_cases_23_strata": len(universe),
            "of_which_reassigned_from_vascular_bucket_into_retained": len(reassigned_into_retained),
            "run_summed_extraction_success_minus_unique": fig2["extraction_success"] - len(universe),
            "v2_primary_cases": len(v2_primary),
            "removed_unique_cases": len(ledger),
        },
        "C_removed_by_step": dict(Counter(r["exclusion_step"] for r in ledger)),
        "C_removed_by_reason": dict(Counter(f"{r['exclusion_step']}:{r['reason_code']}" for r in ledger).most_common()),
        "C_manual_ledger_methods": dict(Counter(r["method"] for r in ledger if r["method"]).most_common()),
        "D_vascular_bucket_cases_in_primary_v1": dict(vasc_in_v1),
        "per_stratum_run_funnel": {k: dict(v) for k, v in sorted(per_stratum.items())},
    }
    (OUT / "qc_ledger_summary.json").write_text(json.dumps(summary, indent=2))
    with (OUT / "per_stratum_flow.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["stratum", "runs", *FUNNEL, "unique_extracted_cases", "removed_unique_cases", "v2_primary_cases"])
        removed_by = Counter(r["stratum"] for r in ledger)
        uni_by = Counter(stratum(c) for c in universe)
        v2_by = Counter(r["modality"] for r in jl(D / "freeze/openredu_manuscript_2017_2026_v2/primary_cases.jsonl"))
        for s, v in sorted(per_stratum.items()):
            w.writerow([s, v["runs"], *[v[k] for k in FUNNEL], uni_by.get(s, 0), removed_by.get(s, 0), v2_by.get(s, 0)])
    print(json.dumps({k: v for k, v in summary.items() if k != "per_stratum_run_funnel"}, indent=2))


if __name__ == "__main__":
    main()
