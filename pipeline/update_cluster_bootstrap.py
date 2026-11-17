#!/usr/bin/env python3
"""Prospective update: article-level cluster bootstrap for the automated indicators.

Several figures from one article are not independent, so the Newcombe intervals of temporal_stability.py /
update_prospective_report.py treat figures as independent. Here articles (PMC identifiers) are resampled with
replacement within each comparison group; each replicate recomputes the ratio-of-sums proportion per group and the
difference. Percentile 95% intervals from 2,000 replicates (seed 20261020). Proportions are rounded once, from the
integer counts. Groups:
  update        prospective update (data/outputs/update_2026q3_v1), same indicator definitions
  recent/early  primary collection, publication 2025-2026 / 2017-2024 (temporal_stability.build_sets)
Writes data/outputs/update_cluster_v1/{summary.json, s13a.csv, s13b.csv}. No LLM. No network.
"""
from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).parent))
from temporal_stability import build_sets, newcombe  # noqa: E402

OUT = ROOT / "data/outputs/update_cluster_v1"
U = yaml.safe_load((ROOT / "config/pipeline.yaml").read_text())["update_2026q3"]
UPD = ROOT / U["out_dir"]
REPS, SEED = 2000, 20261020


def jl(p: Path):
    return [json.loads(l) for l in p.open()]


def update_sets() -> dict[str, list[dict]]:
    labels = jl(UPD / "case_article_labels.jsonl")
    t1t3 = jl(UPD / "cases_casereport.jsonl")
    build = [c for c in jl(UPD / "build/cases.jsonl") if c.get("corpus_source") == "update_2026q3"]
    excl = {r["case_id"] for r in csv.DictReader((UPD / "build/excluded_verifier.csv").open())
            if r["reason_code"] == "classification_not_supported"}
    linked = {json.loads(l)["case_id"] for l in (UPD / "build/assignments.jsonl").open()}
    u = lambda c, v: {"case_id": c["case_id"], "pmcid": c["pmcid"], "v": int(v)}
    return {
        "article_type_excluded": [u(r, r["tier"].startswith("T4")) for r in labels],
        "verifier_excluded": [u(c, c["case_id"] in excl) for c in t1t3],
        "needs_review": [u(c, bool(c["revision_labels"].get("finding_flag_not_supported"))) for c in build],
        "figure_scope_fallback": [u(c, c.get("finding_scope") != "figure") for c in build],
        "extraction_escalated": [u(c, "haiku" not in ((c.get("models_used") or {}).get("extraction") or "")) for c in build],
        "topic_linked": [u(c, c["case_id"] in linked) for c in build],
    }


def clusters(units: list[dict]) -> tuple[np.ndarray, np.ndarray]:
    k, n = defaultdict(int), defaultdict(int)
    for x in units:
        k[x["pmcid"]] += x["v"]
        n[x["pmcid"]] += 1
    keys = sorted(n)
    return np.array([k[a] for a in keys], float), np.array([n[a] for a in keys], float)


def boot(kn: tuple[np.ndarray, np.ndarray], rng: np.random.Generator) -> np.ndarray:
    k, n = kn
    idx = rng.integers(0, len(k), size=(REPS, len(k)))
    return k[idx].sum(1) / n[idx].sum(1)


def describe(units: list[dict]) -> dict:
    k, n = sum(x["v"] for x in units), len(units)
    per = defaultdict(int)
    for x in units:
        per[x["pmcid"]] += 1
    return {"events": k, "n": n, "pct": round(100 * k / n, 1), "articles": len(per),
            "articles_with_several_cases": sum(v > 1 for v in per.values()), "max_cases_per_article": max(per.values())}


def compare(a: list[dict], b: list[dict], rng: np.random.Generator) -> dict:
    """b minus a"""
    ba, bb = boot(clusters(a), rng), boot(clusters(b), rng)
    d = 100 * (bb - ba)
    ka, na = sum(x["v"] for x in a), len(a)
    kb, nb = sum(x["v"] for x in b), len(b)
    nd, nl, nh = newcombe(ka, na, kb, nb)
    pa, pb = 100 * np.percentile(ba, [2.5, 97.5]), 100 * np.percentile(bb, [2.5, 97.5])
    return {"a": {**describe(a), "cluster_ci": [round(float(pa[0]), 1), round(float(pa[1]), 1)]},
            "b": {**describe(b), "cluster_ci": [round(float(pb[0]), 1), round(float(pb[1]), 1)]},
            "difference_pct_points": round(100 * (kb / nb - ka / na), 1),
            "cluster_bootstrap_ci": [round(float(np.percentile(d, 2.5)), 1), round(float(np.percentile(d, 97.5)), 1)],
            "newcombe_independent_ci": [round(100 * nl, 1), round(100 * nh, 1)]}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)
    corpus = build_sets(False)
    upd = update_sets()
    res = {"replicates": REPS, "seed": SEED, "unit": "figure-level case; resampling unit = article (PMC identifier)",
           "s13a_update_vs_corpus_2025_2026": {}, "s13b_2025_2026_vs_2017_2024": {}}
    for k in upd:
        recent = [x for x in corpus[k] if x["period"] == "recent"]
        res["s13a_update_vs_corpus_2025_2026"][k] = compare(recent, upd[k], rng)
    for k, us in corpus.items():
        early = [x for x in us if x["period"] == "early"]
        recent = [x for x in us if x["period"] == "recent"]
        res["s13b_2025_2026_vs_2017_2024"][k] = compare(early, recent, rng)
    (OUT / "summary.json").write_text(json.dumps(res, indent=2) + "\n")
    for name, key in (("s13a.csv", "s13a_update_vs_corpus_2025_2026"), ("s13b.csv", "s13b_2025_2026_vs_2017_2024")):
        with (OUT / name).open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["indicator", "a_events", "a_n", "a_pct", "a_articles", "b_events", "b_n", "b_pct", "b_articles",
                        "difference_b_minus_a", "cluster_ci_low", "cluster_ci_high", "newcombe_low", "newcombe_high"])
            for k, r in res[key].items():
                w.writerow([k, r["a"]["events"], r["a"]["n"], r["a"]["pct"], r["a"]["articles"], r["b"]["events"], r["b"]["n"],
                            r["b"]["pct"], r["b"]["articles"], r["difference_pct_points"], *r["cluster_bootstrap_ci"],
                            *r["newcombe_independent_ci"]])
    for key in ("s13a_update_vs_corpus_2025_2026", "s13b_2025_2026_vs_2017_2024"):
        print(key)
        for k, r in res[key].items():
            print(f"  {k:<30} {r['a']['events']}/{r['a']['n']} ({r['a']['pct']}%) vs {r['b']['events']}/{r['b']['n']} "
                  f"({r['b']['pct']}%)  d={r['difference_pct_points']}  cluster {r['cluster_bootstrap_ci']}  "
                  f"newcombe {r['newcombe_independent_ci']}  [b articles {r['b']['articles']}, multi {r['b']['articles_with_several_cases']}]")


if __name__ == "__main__":
    main()
