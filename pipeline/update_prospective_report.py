#!/usr/bin/env python3
"""Prospective update: stage counts, time, cost, QC indicators versus the corpus, and new topic yield.

Reads <out_dir> of config `update_2026q3` (search/extract/assemble outputs, llm_calls.jsonl, build/) and the stored
publication-period reference (data/outputs/temporal_stability_v1/summary.json). Writes <out_dir>/report/summary.json and
indicators.csv. No LLM. No network.
"""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).parent))
from temporal_stability import newcombe, wilson  # noqa: E402

CFG = yaml.safe_load((ROOT / "config/pipeline.yaml").read_text())
U = CFG["update_2026q3"]
OUT = ROOT / U["out_dir"]
PRICES = {**{k: (v["in"], v["out"]) for k, v in CFG["ablation_r17"]["prices"].items()},
          CFG["step2_verifier"]["models"]["nova-pro"]["model_id"]: (CFG["step2_verifier"]["models"]["nova-pro"]["price_in"],
                                                                   CFG["step2_verifier"]["models"]["nova-pro"]["price_out"])}
MONTHS = {m: i for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}


def jl(p: Path):
    return [json.loads(l) for l in p.open()]


def ts(s: str) -> datetime:
    return datetime.fromisoformat(s)


def pubdate(s: str) -> datetime | None:
    p = s.replace(",", " ").split()
    try:
        y = int(p[0])
        m = MONTHS.get(p[1][:3], 1) if len(p) > 1 else 7
        d = int(p[2]) if len(p) > 2 and p[2].isdigit() else 15
        return datetime(y, m, d, tzinfo=timezone.utc)
    except (ValueError, IndexError):
        return None


def cost(calls: list[dict]) -> dict:
    by = Counter()
    tok = Counter()
    for c in calls:
        if not c.get("ok"):
            continue
        pin, pout = PRICES.get(c["model"], (float("nan"), float("nan")))
        by[c["model"]] += c.get("input_tokens", 0) * pin / 1e6 + c.get("output_tokens", 0) * pout / 1e6
        tok[(c["model"], "in")] += c.get("input_tokens", 0)
        tok[(c["model"], "out")] += c.get("output_tokens", 0)
    return {"usd_by_model": {k: round(v, 4) for k, v in by.items()}, "usd_total": round(sum(by.values()), 4),
            "calls_ok": sum(1 for c in calls if c.get("ok")), "calls_failed": sum(1 for c in calls if not c.get("ok")),
            "errors": dict(Counter(c.get("error") for c in calls if not c.get("ok"))),
            "tokens": {f"{m}|{d}": n for (m, d), n in tok.items()}}


def main() -> None:
    rep = OUT / "report"
    rep.mkdir(exist_ok=True)
    search = json.loads((OUT / "search_manifest.json").read_text())
    ex = json.loads((OUT / "extract_manifest.json").read_text())
    asm = json.loads((OUT / "assemble_summary.json").read_text())
    full_runs = [r for r in ex["runs"] if not r.get("limit")]
    stats = Counter()
    for r in ex["runs"]:  # the limited test run processed PMCIDs that the full run then skipped
        stats.update({k: v for k, v in r["stats"].items() if isinstance(v, int)})

    build = OUT / "build"
    cases = jl(build / "cases.jsonl")
    new = [c for c in cases if c.get("corpus_source") == "update_2026q3"]
    new_ids = {c["case_id"] for c in new}
    links = jl(build / "assignments.jsonl")
    new_links = [a for a in links if a["case_id"] in new_ids]
    excl = [r for r in csv.DictReader((build / "excluded_verifier.csv").open()) if r["case_id"] in
            {c["case_id"] for c in jl(OUT / "cases_casereport.jsonl")}]
    t1t3 = jl(OUT / "cases_casereport.jsonl")

    # stability of the existing corpus inside the combined build
    v22 = {(a["case_id"], a["schedule_entry_id"]) for a in jl(ROOT / "data/outputs/v2_2/assignments.jsonl")}
    old_in_build = {(a["case_id"], a["schedule_entry_id"]) for a in links if a["case_id"] not in new_ids}
    v22_cases = {c["case_id"] for c in jl(ROOT / "data/outputs/v2_2/cases.jsonl")}

    # topics
    before = Counter(sid for _, sid in v22)
    after_new = Counter(a["schedule_entry_id"] for a in new_links)
    first_case_topics = sorted(t for t in after_new if before[t] == 0)

    # time
    starts = [ts(r["started"]) for r in ex["runs"]]
    ends = [ts(r["finished"]) for r in ex["runs"]]
    vt = sorted(a["called_at"] for r in jl(ROOT / f"data/outputs/step2/runs/{U['verifier_run_id']}/nova-pro.jsonl")
                for a in r.get("attempts", []))
    # publication-to-processing lag is not reported: NCBI esummary PubDate is often the issue date ("2026", "2026 Dec")

    # indicators versus the corpus (primary collection by publication period, same definitions as temporal_stability)
    ref = json.loads((ROOT / "data/outputs/temporal_stability_v1/summary.json").read_text())["indicators"]
    labels = jl(OUT / "case_article_labels.jsonl")
    ind = {
        "article_type_excluded": (sum(r["tier"].startswith("T4") for r in labels), len(labels)),
        "verifier_excluded": (sum(r["reason_code"] == "classification_not_supported" for r in excl), len(t1t3)),
        "needs_review": (sum(bool(c["revision_labels"].get("finding_flag_not_supported")) for c in new), len(new)),
        "figure_scope_fallback": (sum(c.get("finding_scope") != "figure" for c in new), len(new)),
        "extraction_escalated": (sum("haiku" not in ((c.get("models_used") or {}).get("extraction") or "") for c in new), len(new)),
        "topic_linked": (len({a["case_id"] for a in new_links}), len(new)),
    }
    linked = {a["case_id"] for a in new_links}
    ref_cases = [c for c in cases if c.get("corpus_source") in ("final", "processed", "processed_2017_2019") and int(c["year"]) >= 2025]
    ref_linked = {a["case_id"] for a in links if a["case_id"] in {c["case_id"] for c in ref_cases}}
    no_cmr = lambda cs: [c for c in cs if c["modality"] != "CARDIOVASCULAR_MRI"]  # no APDR cardiac division
    mix = Counter(c["modality"] for c in ref_cases)
    bym = {}
    for c in new:
        bym.setdefault(c["modality"], []).append(c["case_id"] in linked)
    std = sum(n * sum(bym[m]) / len(bym[m]) for m, n in mix.items() if bym.get(m)) / sum(n for m, n in mix.items() if bym.get(m))
    topic_link_detail = {
        "excluding_cardiac_mri": {"update": [sum(c["case_id"] in linked for c in no_cmr(new)), len(no_cmr(new))],
                                  "corpus_2025_2026": [sum(c["case_id"] in ref_linked for c in no_cmr(ref_cases)), len(no_cmr(ref_cases))]},
        "update_standardized_to_corpus_2025_2026_modality_mix_pct": round(100 * std, 1)}
    rows = []
    for k, (e, n) in ind.items():
        lo, hi = wilson(e, n)
        r = ref[k]["recent_2025_2026"]
        d, dl, dh = newcombe(r["events"], r["n"], e, n)
        rows.append({"indicator": k, "update_events": e, "update_n": n, "update_pct": round(100 * e / n, 2),
                     "update_ci": f"{100 * lo:.1f}-{100 * hi:.1f}", "corpus_2025_2026_pct": r["pct"], "corpus_2025_2026_n": r["n"],
                     "corpus_2017_2024_pct": ref[k]["early_2017_2024"]["pct"],
                     "difference_vs_2025_2026_pct_points": f"{100 * d:.1f} ({100 * dl:.1f}, {100 * dh:.1f})"})
    with (rep / "indicators.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    calls = jl(OUT / "llm_calls.jsonl")
    vcalls = []
    for r in jl(ROOT / f"data/outputs/step2/runs/{U['verifier_run_id']}/nova-pro.jsonl"):
        for at in r.get("attempts", []):
            u = at.get("usage") or {}
            vcalls.append({"model": r["model_id"], "ok": bool(u), "input_tokens": u.get("inputTokens", 0),
                           "output_tokens": u.get("outputTokens", 0), "error": None if u else "no_usage"})
    summary = {
        "window": U["date_filter"], "generated_at": datetime.now(timezone.utc).isoformat(),
        "flow": {"query_hits_summed_over_categories": sum(c["hits"] for c in search["categories"].values()),
                 "candidate_articles_unique": search["unique_candidate_articles"],
                 "pipeline_stats_summed": dict(stats), "extracted_cases_unique": asm["unique_cases"],
                 "articles_with_cases": asm["articles"], "cross_category_duplicates": asm["cross_category_duplicate"],
                 "license_excluded": asm["license_excluded"], "after_article_type": asm["after_article_type"],
                 "tiers": asm["tiers"], "verifier_category_excluded": ind["verifier_excluded"][0],
                 "final_cases": len(new), "final_articles": len({c["pmcid"] for c in new}),
                 "needs_review": ind["needs_review"][0], "cases_with_topic_link": ind["topic_linked"][0],
                 "new_links": len(new_links)},
        "time": {"extraction_wall_hours": round((max(ends) - min(starts)).total_seconds() / 3600, 2),
                 "extraction_start_end": [min(starts).isoformat(), max(ends).isoformat()],
                 "verifier_wall_minutes_incl_retry": round((ts(vt[-1]) - ts(vt[0])).total_seconds() / 60, 1),
                 "note": "wall time includes Bedrock throttling retries; publication-to-processing lag not reported (issue dates)"},
        "cost_list_price": {"extraction": cost(calls), "verifier": cost(vcalls)},
        "topic_link_detail": topic_link_detail,
        "topics": {"topics_with_new_links": len(after_new), "first_case_topics": first_case_topics,
                   "per_topic_new_links": dict(after_new.most_common())},
        "existing_corpus_unchanged": {"cases": len(v22_cases & {c["case_id"] for c in cases}) == len(v22_cases),
                                      "links_identical": old_in_build == v22,
                                      "links_only_in_v22": len(v22 - old_in_build), "links_only_in_build": len(old_in_build - v22)},
        "indicators": rows,
        "scope": "One prospective ingestion of articles published after the corpus collection, with the unchanged current "
                 "pipeline. QC indicators are automated (independent verifier, rules); no human accuracy for the new cases.",
    }
    (rep / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str) + "\n")
    print(json.dumps({k: summary[k] for k in ("flow", "time", "topics", "existing_corpus_unchanged")}, indent=2, default=str))
    print(json.dumps(summary["cost_list_price"], indent=2)[:1500])
    for r in rows:
        print(r)


if __name__ == "__main__":
    main()
