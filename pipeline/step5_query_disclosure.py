#!/usr/bin/env python3
"""Step 5: per-category PMC query disclosure and overlap handling.

For each of the 23 retained strata: the query string rebuilt with the repository's
build_query() from the modality configuration, whether every historical run's config_hash
equals the current configuration (i.e. the rebuilt query is the executed one), run count,
first/last execution timestamps, run-summed funnel, and cross-category overlap of
extracted figures. Executed query strings were not stored in run manifests
(query_strings empty in all runs) and run logs truncate them, so the rebuilt string is
exact only where the config hash matches. No LLM, no network.
"""
from __future__ import annotations

import csv
import glob
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
OUT = ROOT / "data/outputs/step5/query_disclosure"
EXCLUDED = {"CT_CHEST_VASC", "US_VASCULAR"}


def main() -> None:
    from openredu.config import MODALITY_CONFIG, GAP_FILL_MODALITY_CONFIG
    from openredu.tools.pmc_api import build_query
    OUT.mkdir(parents=True, exist_ok=True)
    runs = list(csv.DictReader(open(ROOT / "data/outputs/step5/qc_ledger/run_manifest_funnel.csv")))
    by_mod = defaultdict(list)
    for r in runs:
        if r["modality"] not in EXCLUDED:
            by_mod[r["modality"]].append(r)

    # cross-category overlap: same case_id extracted under >1 modality in extraction outputs
    mods_of = defaultdict(set)
    for pat in ["final/cases_*.jsonl", "processed/cases_*.jsonl", "processed_2017_2019/cases_*.jsonl"]:
        for f in glob.glob(str(ROOT / "data" / pat)):
            for line in open(f):
                if line.strip():
                    d = json.loads(line)
                    mods_of[d["case_id"]].add(d.get("modality"))
    pmc_mods = defaultdict(set)
    for cid, ms in mods_of.items():
        pmc_mods[cid.split("_")[0]] |= ms
    multi_case = sum(1 for ms in mods_of.values() if len(ms - EXCLUDED) > 1)
    multi_pmc = sum(1 for ms in pmc_mods.values() if len(ms - EXCLUDED) > 1)

    rows, queries = [], {}
    for m in sorted(by_mod):
        cfg = MODALITY_CONFIG.get(m) or GAP_FILL_MODALITY_CONFIG.get(m, {})
        cur_hash = hashlib.md5(json.dumps(cfg, sort_keys=True).encode()).hexdigest()
        rs = by_mod[m]
        qruns = [r for r in rs if int(r["pmc_query_hits"]) > 0]
        hashes = Counter(r["config_hash"] for r in qruns)
        years = Counter((r["year_start"] or "not recorded", r["year_end"] or "not recorded") for r in qruns)
        q_nodate = build_query(m)
        queries[m] = {"query_without_date_clause": q_nodate,
                      "date_clauses_recorded": [f"{a}:{b}[PDAT]" for a, b in years if a != "not recorded"],
                      "runs_with_matching_config_hash": sum(v for h, v in hashes.items() if h == cur_hash),
                      "runs_with_other_config_hash": sum(v for h, v in hashes.items() if h != cur_hash),
                      "historical_config_hashes": dict(hashes), "current_config_hash": cur_hash}
        ts = sorted(r["timestamp"] for r in rs if r["timestamp"])
        rows.append({
            "stratum": m, "runs_total": len(rs), "runs_with_query": len(qruns),
            "query_runs_config_hash_matches_current": queries[m]["runs_with_matching_config_hash"],
            "query_runs_other_config": queries[m]["runs_with_other_config_hash"],
            "date_filter_recorded_runs": sum(v for (a, _), v in years.items() if a != "not recorded"),
            "first_run": ts[0][:10] if ts else "", "last_run": ts[-1][:10] if ts else "",
            **{k: sum(int(r[k]) for r in rs) for k in ("pmc_query_hits", "license_passed", "figures_with_caption",
                                                        "rule_include", "extraction_success")},
        })
    with (OUT / "per_category_queries_and_flow.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    (OUT / "queries.json").write_text(json.dumps(queries, indent=2, ensure_ascii=False))
    summary = {
        "strata": len(rows),
        "query_runs": sum(r["runs_with_query"] for r in rows),
        # config-hash match = the keyword clause can be rebuilt from the current configuration; it is NOT
        # a preserved executed query (query strings were never stored; most runs lack the date clause)
        "query_runs_config_hash_matches_current": sum(r["query_runs_config_hash_matches_current"] for r in rows),
        "query_runs_config_match_with_date_range_recorded": sum(
            1 for r in runs if r["modality"] not in EXCLUDED and int(r["pmc_query_hits"]) > 0
            and r["year_start"] and r["year_end"] and r["config_hash"] == queries[r["modality"]]["current_config_hash"]),
        "query_runs_config_changed_since": sum(r["query_runs_other_config"] for r in rows),
        "hits_in_config_match_runs": sum(int(r["pmc_query_hits"]) for r in runs if r["modality"] not in EXCLUDED
                                         and int(r["pmc_query_hits"]) > 0
                                         and r["config_hash"] == queries[r["modality"]]["current_config_hash"]),
        "query_runs_with_date_filter_recorded": sum(r["date_filter_recorded_runs"] for r in rows),
        "execution_window": [min(r["first_run"] for r in rows if r["first_run"]), max(r["last_run"] for r in rows)],
        "overlap": {"case_ids_extracted_under_more_than_one_stratum": multi_case,
                    "pmcids_with_figures_in_more_than_one_stratum": multi_pmc,
                    "handling": "case_id = PMCID + figure ID; one record per case_id kept with source precedence "
                                "final > processed > processed_2017_2019 (final-corpus build script of the original collection, not included in this release); "
                                "an article may contribute figures to several strata."},
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
