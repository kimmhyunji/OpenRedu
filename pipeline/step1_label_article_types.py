#!/usr/bin/env python3
"""Step 1: label every v1 case with its source-article type and build corpus views.

Cases are never deleted. Each case gets an article-type tier and flags; corpus
views are produced by filtering on tiers listed in config/pipeline.yaml.
For each comparison policy the v1 APDR schedule matching is re-run (original
module, redirected output) to show per-topic case counts before/after.
No LLM. Inputs: v1 snapshot corpus + data/outputs/step1/article_meta.jsonl.
"""
from __future__ import annotations

import contextlib
import csv
import io
import json
import os
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
CFG = yaml.safe_load((ROOT / "config/pipeline.yaml").read_text())
SNAP = ROOT / CFG["snapshot_dir"]
OUT = ROOT / "data/outputs/step1"
S1 = CFG["step1_article_type"]

RX = {
    # image-corner sections are matched per heading (anchored) and in titles
    "image_corner_heading": re.compile(
        r"^(case |clinical |medical |radiology )?images?$|^interesting images?$|^images? (in|for|of)\b|"
        r"\bneuroimage\b|^imaging vignette$|^image (report|challenge|quiz)$|\bmuseum image\b|"
        r"^clinical (picture|vignettes?)$|\bquiz\b|^photo", re.I),
    "image_corner_title": re.compile(
        r"^images? in\b|\binteresting images?\b|\bimage challenge\b|\bwhat is your diagnosis\b|"
        r"\bquiz\b|\bphotoquiz\b", re.I),
    "review_heading": re.compile(r"\breviews?\b", re.I),
    "pictorial": re.compile(
        r"\bpictorial\b|\billustrated (review|essay)\b|\bimaging review\b|\beducational (review|exhibit)\b|"
        r"\bteaching (file|point review)\b|\bspectrum of imaging\b|\bimaging spectrum\b|"
        r"\bpictorial education\b|\bcase illustrated\b", re.I),
    "study_design": re.compile(
        r"\bretrospective\b|\bprospective\b|\bcohort\b|\bcomparative (evaluation|study|analysis)\b|"
        r"\brandomi[sz]ed\b|\btrial\b|\bmeta-analys[ie]s\b|\bsystematic review\b|\bcross-sectional\b|"
        r"\bcase-control\b|\bmulticent(er|re)\b|\bsingle-cent(er|re)\b|\bobservational\b", re.I),
    "case_word": re.compile(r"\bcase\b|\bcases\b|\breport\b", re.I),
    "review_word": re.compile(r"\breview\b", re.I),
    "case_series": re.compile(r"\bcase series\b|\bseries of \w+ (cases|patients)\b|"
                              r"\b(two|three|four|five|six|seven|eight|nine|ten|\d+) (cases|patients)\b", re.I),
    "case_title": re.compile(r"\bcase report\b|\ba case\b|\bcase of\b|\bcase series\b|\bcase presentation\b|"
                             r"\bpatient with\b|\b(year|month)[- ]old\b", re.I),
    "case_heading": re.compile(r"\bcase\b|\bcasos?\b|\bgrand round", re.I),
}


CASE_REPORT_JATS = {"case-report", "case-study"}


def label_article(meta: dict, title: str, abstract: str) -> dict:
    jats = meta.get("jats_article_type", "")
    headings = " | ".join(meta.get("subject_headings", []))
    pubtypes = meta.get("pubmed_pubtypes", [])
    title = title or meta.get("jats_title", "")
    flags = []
    heads = meta.get("subject_headings", [])
    if any(RX["image_corner_heading"].search(h.strip()) for h in heads) or \
            RX["image_corner_title"].search(title):
        flags.append("image_corner")
    if any(RX["review_heading"].search(h) and not RX["case_heading"].search(h) for h in heads):
        flags.append("review_heading")
    if RX["pictorial"].search(title) or RX["pictorial"].search(headings) or \
            RX["pictorial"].search(abstract[:400]):
        flags.append("pictorial")
    if RX["review_word"].search(title) and not RX["case_word"].search(title):
        flags.append("review_title_without_case")
    if RX["study_design"].search(title):
        flags.append("study_design_title")
    if "Review" in pubtypes and "Case Reports" not in pubtypes:
        flags.append("pubmed_review_not_case")
    case_signals = []
    if RX["case_heading"].search(headings):
        case_signals.append("heading")
    if "Case Reports" in pubtypes:
        case_signals.append("pubmed_case_reports")
    if RX["case_title"].search(title):
        case_signals.append("title")

    # JATS "case-study" is the JATS 1.2+ value for case reports (used by e.g.
    # Clinical Case Reports, Respirology Case Reports); treated as case-report.
    if jats in CASE_REPORT_JATS:
        tier = "T1_case_report" if not flags else "T2_case_report_flagged"
    elif case_signals and not flags:
        tier = "T3_possible_case_report"
    else:
        tier = "T4_non_case_report"
    return {
        "jats_article_type": jats, "subject_headings": meta.get("subject_headings", []),
        "pubmed_pubtypes": pubtypes, "flags": flags, "case_signals": case_signals,
        "case_series": bool(RX["case_series"].search(title)), "tier": tier,
    }


def run_matching(corpus_rows: list[dict], name: str) -> dict:
    """Re-run the v1 schedule matching on a corpus view (original module)."""
    import openredu.pipeline.report_apdr_schedule_coverage as cov
    vdir = OUT / "views" / name
    vdir.mkdir(parents=True, exist_ok=True)
    corpus_path = vdir / "cases.jsonl"
    with corpus_path.open("w") as f:
        for c in corpus_rows:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    (vdir / "manifest.json").write_text(json.dumps({"view": name, "cases": len(corpus_rows)}))
    os.environ["OPENREDU_APDR_CORPUS"] = str(corpus_path.relative_to(ROOT))
    cov.DATA = vdir / "mapping"
    cov.SCHEDULE_CSV = SNAP / CFG["v1"]["schedule_csv"]
    cov.TOPIC_KEYWORDS = cov._load_topic_keywords(SNAP / CFG["v1"]["topic_phrases"])
    with contextlib.redirect_stdout(io.StringIO()):
        cov.main()
    res = json.loads((vdir / "mapping/curriculum_mapping/apdr_schedule_coverage.json").read_text())
    return {t["schedule_entry_id"]: t for t in res["topics"]}


def main() -> None:
    cases = [json.loads(l) for l in (SNAP / CFG["v1"]["corpus"]).open()]
    meta = {json.loads(l)["pmcid"]: json.loads(l) for l in (OUT / "article_meta.jsonl").open()}
    missing = sorted({c["pmcid"] for c in cases} - set(meta))
    assert not missing, f"metadata missing for {len(missing)} PMCIDs"

    art_label: dict[str, dict] = {}
    for c in cases:
        p = c["pmcid"]
        if p not in art_label:
            art_label[p] = {"pmcid": p, "pmid": meta[p].get("pmid", ""),
                            "title": c.get("article_title") or meta[p].get("jats_title", ""),
                            "journal": c.get("journal") or meta[p].get("journal", ""),
                            "year": c.get("year"),
                            **label_article(meta[p], c.get("article_title", ""), c.get("abstract", ""))}
    with (OUT / "article_labels.jsonl").open("w") as f:
        for a in art_label.values():
            f.write(json.dumps(a, ensure_ascii=False) + "\n")
    case_labels = []
    with (OUT / "case_article_labels.jsonl").open("w") as f:
        for c in cases:
            a = art_label[c["pmcid"]]
            row = {"case_id": c["case_id"], "pmcid": c["pmcid"], "tier": a["tier"],
                   "jats_article_type": a["jats_article_type"], "flags": a["flags"],
                   "case_signals": a["case_signals"], "case_series": a["case_series"]}
            case_labels.append(row)
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    tier_of_case = {r["case_id"]: r["tier"] for r in case_labels}

    # ── distribution tables ──
    dist = {
        "articles_by_jats_type": Counter(a["jats_article_type"] or "(none)" for a in art_label.values()),
        "cases_by_jats_type": Counter(art_label[c["pmcid"]]["jats_article_type"] or "(none)" for c in cases),
        "articles_by_tier": Counter(a["tier"] for a in art_label.values()),
        "cases_by_tier": Counter(tier_of_case.values()),
        "articles_by_flag": Counter(fl for a in art_label.values() for fl in a["flags"]),
        "articles_by_flag_within_jats_case_report": Counter(
            fl for a in art_label.values() if a["jats_article_type"] in CASE_REPORT_JATS for fl in a["flags"]),
        "articles_case_series_title": sum(a["case_series"] for a in art_label.values()),
        "articles_title_keyword": {
            k: sum(bool(re.search(rx, a["title"], re.I)) for a in art_label.values())
            for k, rx in {"pictorial": r"pictorial", "illustrated review": r"illustrated review",
                          "pictorial review": r"pictorial review", "pictorial essay": r"pictorial essay",
                          "images in": r"\bimages? in\b", "interesting images": r"interesting images?"}.items()},
        "cases_by_tier_and_modality": defaultdict(Counter),
    }
    for c in cases:
        dist["cases_by_tier_and_modality"][c["modality"]][tier_of_case[c["case_id"]]] += 1

    # ── corpus views and matching impact ──
    v1_topics = json.loads((SNAP / CFG["v1"]["mapping_dir"] / "apdr_schedule_coverage.json").read_text())["topics"]
    eligible = [t for t in v1_topics if t["status"] != "excluded"]
    policies = {"v1_all": None, **S1["compare_policies"]}
    impact = {}
    per_topic = {t["schedule_entry_id"]: {"schedule_entry_id": t["schedule_entry_id"],
                                           "division": t["division"], "keyword": t["keyword"]}
                 for t in eligible}
    for name, tiers in policies.items():
        rows = cases if tiers is None else [c for c in cases if tier_of_case[c["case_id"]] in tiers]
        topics = run_matching(rows, name)
        counts = {sid: topics[sid]["n_cases"] for sid in per_topic}
        for sid, n in counts.items():
            per_topic[sid][f"n_{name}"] = n
        ns = sorted(counts.values())
        impact[name] = {
            "tiers": tiers, "cases": len(rows), "articles": len({c["pmcid"] for c in rows}),
            "topics_covered": sum(n > 0 for n in ns), "topics_zero": [
                f"{per_topic[s]['division']}: {per_topic[s]['keyword']}" for s, n in counts.items() if n == 0],
            f"topics_below_{S1['low_case_threshold']}": sum(0 < n < S1["low_case_threshold"] for n in ns),
            "median_cases_per_topic": (ns[len(ns) // 2] + ns[(len(ns) - 1) // 2]) / 2,
            "min": ns[0], "max": ns[-1],
        }
    with (OUT / "topic_counts_by_policy.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(next(iter(per_topic.values()))))
        w.writeheader()
        w.writerows(per_topic.values())

    # ── selected view (config include_tiers) ──
    sel = [c for c in cases if tier_of_case[c["case_id"]] in S1["include_tiers"]]
    sel_dir = OUT / "corpus_casereport_only"
    sel_dir.mkdir(exist_ok=True)
    with (sel_dir / "cases.jsonl").open("w") as f:
        for c in sel:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    (sel_dir / "manifest.json").write_text(json.dumps({
        "view": "step1_casereport_only", "include_tiers": S1["include_tiers"], "cases": len(sel),
        "source_corpus": CFG["v1"]["corpus"]}, indent=2))
    excl = [r for r in case_labels if r["tier"] not in S1["include_tiers"]]
    with (sel_dir / "excluded_cases.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["case_id", "pmcid", "exclusion_step", "reason_code",
                                          "jats_article_type", "flags"])
        w.writeheader()
        for r in excl:
            w.writerow({"case_id": r["case_id"], "pmcid": r["pmcid"], "exclusion_step": "step1_article_type",
                        "reason_code": r["tier"], "jats_article_type": r["jats_article_type"],
                        "flags": ";".join(r["flags"])})

    summary = {"distribution": json.loads(json.dumps(dist, default=dict)), "impact_by_policy": impact,
               "selected_view": {"include_tiers": S1["include_tiers"], "cases": len(sel),
                                 "articles": len({c['pmcid'] for c in sel}), "excluded_cases": len(excl)}}
    (OUT / "step1_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=dict))
    print(json.dumps({k: summary[k] for k in ("impact_by_policy", "selected_view")},
                     indent=2, ensure_ascii=False))
    print(json.dumps({k: dict(v) if isinstance(v, Counter) else v for k, v in dist.items()
                      if k != "cases_by_tier_and_modality"}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
