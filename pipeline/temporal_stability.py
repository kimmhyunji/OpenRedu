#!/usr/bin/env python3
"""Publication period: do automated QC and mapping indicators change with article publication year? (stored data only)

All cases were processed by the same pipeline at about the same time, so this checks input drift by publication
era (older vs more recent articles), not drift of the models or pipeline over calendar time.

Indicators (unit = figure-level case):
  article_type_excluded   T4 share among article-type-labelled cases                      (v2_2_input/case_article_labels.jsonl)
  verifier_excluded       classification not supported among T1-T3 cases                  (v2_2_input/cases.jsonl, v2_2/excluded_verifier.csv)
  needs_review            finding not supported among retained cases                      (v2_2/cases.jsonl)
  figure_scope_fallback   second pass kept the article-level finding                       (v2_2/cases.jsonl finding_scope)
  extraction_escalated    first-pass extraction finished on a model other than Haiku       (v2_2/cases.jsonl models_used)
  topic_linked            at least one APDR link                                           (v2_2/assignments.jsonl)
  human_* (development)   original two-researcher labels on the 230 development cases        (data/dev_labels/extraction_labels.csv)

Periods: early 2017-2024 vs recent 2025-2026. Primary-collection cases only by default (supplementary searches used
different queries); --all-sources includes them. Recent-minus-early differences have Newcombe 95% CIs; a
modality-standardized difference reweights the recent period to the early period's modality mix. Per-year rows give a
Cochran-Armitage trend test. No LLM. No network.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

from scipy.stats import chi2, norm

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/outputs"
V1 = ROOT / "data/freeze/original_submission_corpus/cases.jsonl"
PRIMARY = {"final", "processed", "processed_2017_2019"}
YEARS = list(range(2017, 2027))


def wilson(k: int, n: int, z: float = 1.959964) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - h) / d, (c + h) / d)


def newcombe(k1: int, n1: int, k2: int, n2: int) -> tuple[float, float, float]:
    """difference p2 - p1 with the Newcombe hybrid score interval."""
    p1, p2 = k1 / n1, k2 / n2
    l1, u1 = wilson(k1, n1)
    l2, u2 = wilson(k2, n2)
    d = p2 - p1
    return d, d - math.sqrt((p2 - l2) ** 2 + (u1 - p1) ** 2), d + math.sqrt((u2 - p2) ** 2 + (p1 - l1) ** 2)


def trend(rows: list[tuple[int, int, int]]) -> float:
    """Cochran-Armitage test for trend over ordered years; rows = (score, events, n). Two-sided p."""
    N = sum(n for _, _, n in rows)
    K = sum(k for _, k, _ in rows)
    if N == 0 or K in (0, N):
        return float("nan")
    p = K / N
    t = sum(s * (k - n * p) for s, k, n in rows)
    v = p * (1 - p) * (sum(n * s * s for s, _, n in rows) - sum(n * s for s, _, n in rows) ** 2 / N)
    return float(2 * norm.sf(abs(t) / math.sqrt(v))) if v > 0 else float("nan")


def heterogeneity(rows: list[tuple[int, int, int]]) -> float:
    """chi-square test of equal proportions across years."""
    N = sum(n for _, _, n in rows)
    K = sum(k for _, k, _ in rows)
    p = K / N
    x = sum((k - n * p) ** 2 / (n * p * (1 - p)) for _, k, n in rows if n)
    return float(chi2.sf(x, len([r for r in rows if r[2]]) - 1))


def standardized(units: list[dict], key: str) -> float:
    """recent-period rate reweighted to the early period's modality mix, minus the early rate."""
    early = [u for u in units if u["period"] == "early"]
    recent = [u for u in units if u["period"] == "recent"]
    w = Counter(u["modality"] for u in early)
    by = defaultdict(list)
    for u in recent:
        by[u["modality"]].append(u[key])
    num = den = 0.0
    for m, n in w.items():
        if by[m]:
            num += n * sum(by[m]) / len(by[m])
            den += n
    return num / den - sum(u[key] for u in early) / len(early)


def build_sets(all_sources: bool = False) -> dict[str, list[dict]]:
    """indicator -> units {case_id, pmcid, year, period, modality, v}; also used by update_cluster_bootstrap.py."""
    args = argparse.Namespace(all_sources=all_sources)

    inp = {c["case_id"]: c for c in map(json.loads, (OUT / "v2_2_input/cases.jsonl").open())}
    fin = {c["case_id"]: c for c in map(json.loads, (OUT / "v2_2/cases.jsonl").open())}
    meta = {}
    for c in map(json.loads, V1.open()):
        meta[c["case_id"]] = (c.get("year"), c.get("modality"), c.get("corpus_source") or "final")
    for c in list(inp.values()) + list(fin.values()):
        meta[c["case_id"]] = (c.get("year"), c.get("modality"), c.get("corpus_source"))
    excluded = {r["case_id"] for r in csv.DictReader((OUT / "v2_2/excluded_verifier.csv").open())
                if r["reason_code"] == "classification_not_supported"}
    linked = Counter(json.loads(l)["case_id"] for l in (OUT / "v2_2/assignments.jsonl").open())

    def unit(cid: str, **vals) -> dict | None:
        y, mod, src = meta.get(cid, (None, None, None))
        if y is None or (not args.all_sources and src not in PRIMARY):
            return None
        y = int(y)
        return {"case_id": cid, "pmcid": cid.split("_")[0], "year": y, "period": "recent" if y >= 2025 else "early",
                "modality": mod, **vals}

    sets: dict[str, list[dict]] = {}
    labels = [json.loads(l) for l in (OUT / "v2_2_input/case_article_labels.jsonl").open()]
    sets["article_type_excluded"] = [u for u in (unit(r["case_id"], v=int(r["tier"].startswith("T4"))) for r in labels) if u]
    sets["verifier_excluded"] = [u for u in (unit(c, v=int(c in excluded)) for c in inp) if u]
    sets["needs_review"] = [u for u in (unit(c, v=int(bool(x["revision_labels"].get("finding_flag_not_supported"))))
                                        for c, x in fin.items()) if u]
    sets["figure_scope_fallback"] = [u for u in (unit(c, v=int(x.get("finding_scope") != "figure")) for c, x in fin.items()) if u]
    sets["extraction_escalated"] = [u for u in (unit(c, v=int("haiku" not in ((x.get("models_used") or {}).get("extraction") or "")))
                                                for c, x in fin.items()) if u]
    sets["topic_linked"] = [u for u in (unit(c, v=int(linked[c] > 0)) for c in fin) if u]

    dev = defaultdict(dict)
    for r in csv.DictReader((ROOT / "data/dev_labels/extraction_labels.csv").open(encoding="utf-8-sig")):
        if r["in_paper_230"] == "True":
            dev[r["case_id"]][r["axis"]] = int(r["label_correct"])
    for axis in ("classification", "finding", "diagnosis"):
        sets[f"human_{axis}_correct"] = [u for u in (unit(c, v=a[axis]) for c, a in dev.items() if axis in a) if u]

    return sets


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/outputs/temporal_stability_v1")
    ap.add_argument("--all-sources", action="store_true")
    args = ap.parse_args()
    out = ROOT / args.out
    out.mkdir(parents=True, exist_ok=True)
    sets = build_sets(args.all_sources)
    summary, yearly = {}, []
    for name, us in sets.items():
        for u in us:
            u[name] = u["v"]
        rows = [(y, sum(u["v"] for u in us if u["year"] == y), sum(1 for u in us if u["year"] == y)) for y in YEARS]
        for y, k, n in rows:
            lo, hi = wilson(k, n)
            yearly.append({"indicator": name, "year": y, "events": k, "n": n,
                           "pct": round(100 * k / n, 2) if n else "", "ci_low": round(100 * lo, 2) if n else "",
                           "ci_high": round(100 * hi, 2) if n else ""})
        e = [u["v"] for u in us if u["period"] == "early"]
        r = [u["v"] for u in us if u["period"] == "recent"]
        d, dl, dh = newcombe(sum(e), len(e), sum(r), len(r))
        summary[name] = {
            "early_2017_2024": {"events": sum(e), "n": len(e), "pct": round(100 * sum(e) / len(e), 2)},
            "recent_2025_2026": {"events": sum(r), "n": len(r), "pct": round(100 * sum(r) / len(r), 2)},
            "difference_pct_points": [round(100 * d, 2), round(100 * dl, 2), round(100 * dh, 2)],
            "modality_standardized_difference_pct_points": round(100 * standardized(us, name), 2),
            "trend_p_by_year": trend(rows), "heterogeneity_p_by_year": heterogeneity(rows),
        }
    with (out / "yearly.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(yearly[0]))
        w.writeheader()
        w.writerows(yearly)
    (out / "summary.json").write_text(json.dumps({
        "population": "all sources" if args.all_sources else "primary collection only (supplementary searches excluded)",
        "periods": {"early": "2017-2024", "recent": "2025-2026 (2026 partial)"},
        "scope": "Publication-era input drift under one processing run; not model or pipeline drift over calendar time, "
                 "not a prospective update. Automated indicators are not accuracy; human_* are the original researcher labels "
                 "on the 230 development cases.",
        "indicators": summary}, indent=2) + "\n")
    for k, s in summary.items():
        print(f"{k:<28} early {s['early_2017_2024']['pct']:>6}% (n={s['early_2017_2024']['n']:>6})  "
              f"recent {s['recent_2025_2026']['pct']:>6}% (n={s['recent_2025_2026']['n']:>5})  "
              f"diff {s['difference_pct_points']}  std {s['modality_standardized_difference_pct_points']:>6}  "
              f"trend p={s['trend_p_by_year']:.3g}")


if __name__ == "__main__":
    main()
