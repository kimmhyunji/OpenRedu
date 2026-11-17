#!/usr/bin/env python3
"""Step 5: build the v2 corpus, v2 mapping and revision outputs.

v2 corpus = Step 1 corpus (article-type tiers per config) minus cases whose verifier
classification verdict is in the configured exclusion set (
classification not_supported only). Every case carries revision labels (article tier,
verifier verdicts, finding flag). Mapping = Step 3 assertion/depiction matching with the
configured policy (suspected included, policy F) on the v2 corpus, lexical (L) concept gate.

Outputs (data/outputs/v2/ or --out):
  cases.jsonl, manifest.json, assignments.jsonl (with sampling metadata),
  topic_coverage_table2.csv, figure2_flow.json, exclusion_alternatives.json,
  case_provenance_v2.csv, sampling_readiness.json
No LLM calls.
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CFG = yaml.safe_load((ROOT / "config/pipeline.yaml").read_text())
SNAP = ROOT / CFG["snapshot_dir"]
V = CFG["step2_verifier"]
DIVISIONS = ["Breast", "Chest", "GI", "GU", "MSK", "NM", "Neuro", "Peds", "US"]
DIV_NAMES = {"Breast": "Breast", "Chest": "Chest", "GI": "Gastrointestinal", "GU": "Genitourinary",
             "MSK": "Musculoskeletal", "NM": "Nuclear Medicine", "Neuro": "Neuroradiology",
             "Peds": "Pediatric Radiology", "US": "Ultrasound"}


def jl(path: Path):
    with path.open() as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def verdict(p: dict, field: str) -> str:
    return ((p or {}).get(field) or {}).get("verdict") or ""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verifier", default=f"data/outputs/step2/runs/{V['full_run_id']}/{V['final_model']}.jsonl")
    ap.add_argument("--out", default="data/outputs/v2")
    ap.add_argument("--allow-partial", action="store_true",
                    help="proceed when some cases lack a verifier result (they are kept, labelled verified=False)")
    ap.add_argument("--concept-expansion", choices=["none", "umls_synonyms"], default=None)
    # v2.1 (gap-fill) inputs; defaults reproduce v2
    ap.add_argument("--step1-corpus", default="data/outputs/step1/corpus_casereport_only/cases.jsonl")
    ap.add_argument("--labels", default="data/outputs/step1/case_article_labels.jsonl")
    ap.add_argument("--version", default="v2")
    ap.add_argument("--gapfill-summary", action="append", default=None,
                    help="gap-fill summary json; repeat for successive supplementary retrievals")
    args = ap.parse_args()
    out = ROOT / args.out
    out.mkdir(parents=True, exist_ok=True)

    step1 = list(jl(ROOT / args.step1_corpus))
    tiers = {r["case_id"]: r for r in jl(ROOT / args.labels)}
    ver = {}
    for r in jl(ROOT / args.verifier):
        if r.get("ok"):
            ver[r["case_id"]] = r          # later records supersede earlier ones
    missing = [c["case_id"] for c in step1 if c["case_id"] not in ver]
    if missing and not args.allow_partial:
        sys.exit(f"verifier results missing for {len(missing)} cases; rerun with --allow-partial for a dry run")

    excl_fields = V.get("corpus_exclusion_fields", ["classification"])
    kept, excluded, labels = [], [], {}
    alt = Counter()
    for c in step1:
        cid = c["case_id"]
        p = (ver.get(cid) or {}).get("parsed")
        lab = {
            "article_type_tier": tiers[cid]["tier"], "article_type_flags": tiers[cid]["flags"],
            "verifier_model": V["models"][V["final_model"]]["model_id"] if p else "",
            "verifier_prompt_version": (ver.get(cid) or {}).get("prompt_version", ""),
            "verifier_classification": verdict(p, "classification"), "verifier_finding": verdict(p, "finding"),
            "verifier_laterality": verdict(p, "laterality"),
            "verifier_diagnosis_article": verdict(p, "diagnosis_article"),
            "verifier_diagnosis_in_figure": verdict(p, "diagnosis_in_figure"),
            "verifier_normalized_diagnosis": verdict(p, "normalized_diagnosis"),
            "finding_flag_not_supported": verdict(p, "finding") == "not_supported",
            "verified": bool(p),
        }
        labels[cid] = lab
        cls_bad = lab["verifier_classification"] == "not_supported"
        fnd_bad = lab["verifier_finding"] == "not_supported"
        alt["classification_only"] += cls_bad
        alt["finding_only"] += fnd_bad
        alt["classification_or_finding"] += cls_bad or fnd_bad
        alt["classification_or_finding_or_diagnosis_article"] += cls_bad or fnd_bad or \
            lab["verifier_diagnosis_article"] == "not_supported"
        if any(lab[f"verifier_{f}"] == "not_supported" for f in excl_fields):
            excluded.append({"case_id": cid, "pmcid": c["pmcid"], "exclusion_step": "step2_verifier",
                             "reason_code": "+".join(f"{f}_not_supported" for f in excl_fields
                                                     if lab[f"verifier_{f}"] == "not_supported")})
        else:
            kept.append({**c, "revision_labels": lab})

    with (out / "cases.jsonl").open("w") as f:
        for c in kept:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    with (out / "excluded_verifier.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["case_id", "pmcid", "exclusion_step", "reason_code"])
        w.writeheader()
        w.writerows(excluded)
    n_step1 = len(step1)
    (out / "exclusion_alternatives.json").write_text(json.dumps({
        "step1_cases": n_step1, "verified_cases": len(ver.keys() & {c["case_id"] for c in step1}),
        "excluded_if": {k: {"cases": v, "share": round(v / n_step1, 4), "remaining": n_step1 - v} for k, v in alt.items()},
        "applied": excl_fields}, indent=2))
    (out / "manifest.json").write_text(json.dumps({
        "version": args.version, "generated_at": datetime.now(timezone.utc).isoformat(),
        "git_commit": subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=ROOT).stdout.strip(),
        "source": args.step1_corpus, "article_labels": args.labels,
        "article_type_include_tiers": CFG["step1_article_type"]["include_tiers"],
        "verifier": {"model": V["models"][V["final_model"]]["model_id"], "prompt_version": V["prompt_version"],
                     "run": args.verifier, "exclusion_fields": excl_fields},
        "cases": len(kept), "pmcids": len({c["pmcid"] for c in kept}), "has_unverified_cases": bool(missing),
        "verifier_missing_cases": len(missing),
        "matching": {"concept_gate": args.concept_expansion or CFG["step3_assertion"].get("concept_expansion", "none"),
                     "include_suspected": CFG["step3_assertion"].get("include_suspected"),
                     "keep_depicted": CFG["step3_assertion"].get("keep_depicted"),
                     "depicted_false_requires_case_not_shown": CFG["step3_assertion"].get("depicted_false_requires_case_not_shown")}}, indent=2))

    # ── mapping (Step 3 policy from config) ──
    s3 = ROOT / "pipeline/step3_assertion_matching.py"
    cmd = [sys.executable, str(s3), "--corpus", str((out / "cases.jsonl").relative_to(ROOT)),
           "--verifier", str(Path(args.verifier).relative_to("data/outputs/step2")),
           "--out", str((out / "mapping").relative_to(ROOT))]
    if CFG["step3_assertion"].get("depicted_false_requires_case_not_shown"):
        cmd.append("--depicted-false-requires-case-not-shown")
    expansion = args.concept_expansion or CFG["step3_assertion"].get("concept_expansion", "none")
    cmd += ["--concept-expansion", expansion]
    subprocess.run(cmd, check=True, cwd=ROOT, stdout=subprocess.DEVNULL)
    rows = list(jl(out / "mapping/assignments.jsonl"))
    case_by = {c["case_id"]: c for c in kept}
    final = []
    for r in rows:
        if not r["keep"]:
            continue
        c = case_by[r["case_id"]]
        final.append({**r, "collection_category": c.get("modality"), "pmcid": c["pmcid"],
                      "publication_year": c.get("year"),
                      "article_type_tier": labels[r["case_id"]]["article_type_tier"],
                      "verifier_finding": labels[r["case_id"]]["verifier_finding"],
                      "verifier_diagnosis_in_figure": labels[r["case_id"]]["verifier_diagnosis_in_figure"]})
    with (out / "assignments.jsonl").open("w") as f:
        for r in final:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # ── Table 2 format ──
    topics = [t for t in json.loads((out / "mapping/v1_rule/curriculum_mapping/apdr_schedule_coverage.json").read_text())["topics"]
              if t["status"] != "excluded"]
    n_by = Counter(r["schedule_entry_id"] for r in final)
    table = []
    for d in DIVISIONS:
        ts = [t for t in topics if t["division"] == d]
        ns = [n_by.get(t["schedule_entry_id"], 0) for t in ts]
        table.append({"division": DIV_NAMES[d], "eligible_topics": len(ts), "topics_with_case": sum(n > 0 for n in ns),
                      "median_cases": statistics.median(ns) if ns else 0, "min": min(ns) if ns else 0,
                      "max": max(ns) if ns else 0,
                      "zero_case_topics": "; ".join(t["keyword"] for t in ts if n_by.get(t["schedule_entry_id"], 0) == 0)})
    alln = [n_by.get(t["schedule_entry_id"], 0) for t in topics]
    table.append({"division": "Total", "eligible_topics": len(topics), "topics_with_case": sum(n > 0 for n in alln),
                  "median_cases": statistics.median(alln), "min": min(alln), "max": max(alln), "zero_case_topics": ""})
    with (out / "topic_coverage_table2.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(table[0]))
        w.writeheader()
        w.writerows(table)

    # ── Figure 2 flow (v1 chain + revision nodes) ──
    qc = json.loads((ROOT / "data/outputs/step5/qc_ledger/qc_ledger_summary.json").read_text())
    s1 = json.loads((ROOT / "data/outputs/step1/step1_summary.json").read_text())
    gapfill_summaries = [json.loads((ROOT / p).read_text()) for p in args.gapfill_summary or []]
    gapfill_flow = None
    if len(gapfill_summaries) == 1:
        gapfill_flow = gapfill_summaries[0]
    elif len(gapfill_summaries) > 1:
        gapfill_flow = {"stages": [
            {"source": path, "cases_added": summary["gapfill_cases_after_article_type"], "summary": summary}
            for path, summary in zip(args.gapfill_summary, gapfill_summaries)
        ], "total_cases_added": sum(s["gapfill_cases_after_article_type"] for s in gapfill_summaries)}
    fig2 = {
        "v1_run_summed": qc["A_figure2_as_submitted"],
        "repeat_extractions_across_runs": qc["B_case_level"]["run_summed_extraction_success_minus_unique"],
        "unique_extracted_cases": qc["B_case_level"]["unique_extracted_cases_23_strata"],
        "qc_removed_by_reason": qc["C_removed_by_reason"],
        "primary_corpus_v1": qc["B_case_level"]["v2_primary_cases"],
        "supplementary_retrieval_cases": 221, "v1_final_corpus": 18823,
        "article_type_excluded_cases": s1["selected_view"]["excluded_cases"],
        "article_type_excluded_by_tier": {k: v for k, v in s1["distribution"]["cases_by_tier"].items()
                                          if k not in CFG["step1_article_type"]["include_tiers"]},
        "after_article_type": n_step1,
        "gapfill": gapfill_flow,
        "verifier_excluded_cases": len(excluded),
        "v2_corpus_cases": len(kept), "v2_corpus_articles": len({c["pmcid"] for c in kept}),
        "v2_assignments": len(final), "v2_cases_with_assignment": len({r["case_id"] for r in final}),
    }
    (out / "figure2_flow.json").write_text(json.dumps(fig2, indent=2))

    # ── provenance with verifier columns ──
    prov_in = ROOT / "data/outputs/step5/repro_package/case_provenance_v1.csv"
    with prov_in.open() as fi, (out / "case_provenance_v2.csv").open("w", newline="") as fo:
        rd = csv.DictReader(fi)
        w = csv.DictWriter(fo, fieldnames=rd.fieldnames + ["in_v2_corpus", "pipeline_version_v2"])
        w.writeheader()
        kept_ids = {c["case_id"] for c in kept}
        for r in rd:
            lab = labels.get(r["case_id"])
            if lab:
                for k in ("verifier_model", "verifier_prompt_version", "verifier_classification", "verifier_finding",
                          "verifier_diagnosis_article", "verifier_diagnosis_in_figure"):
                    r[k] = lab[k]
            r["in_v2_corpus"] = r["case_id"] in kept_ids
            r["pipeline_version_v2"] = "v2 (revision-ryai)" if lab else "excluded at step1"
            w.writerow(r)
        # cases that are not in the v1 provenance table (v2.1 gap-fill) get a minimal row
        seen = {r["case_id"] for r in csv.DictReader(open(prov_in))}
        for c in step1:
            if c["case_id"] not in seen:
                lab = labels[c["case_id"]]
                row = {k: "" for k in rd.fieldnames}
                row.update({k: c.get(k, "") for k in ("case_id", "pmcid") if k in row})
                row.update({k: lab[k] for k in ("verifier_model", "verifier_prompt_version", "verifier_classification",
                                                 "verifier_finding", "verifier_diagnosis_article",
                                                 "verifier_diagnosis_in_figure") if k in row})
                row["in_v2_corpus"] = c["case_id"] in kept_ids
                row["pipeline_version_v2"] = f"{args.version} gap-fill (revision-ryai)"
                w.writerow(row)

    # ── sampling readiness ──
    need = ["division", "modality", "collection_category", "match_method", "final_status", "final_depicted",
            "schedule_entry_id", "keyword"]
    readiness = {k: sum(1 for r in final if r.get(k) in (None, "")) for k in need}
    blocking = []
    if any(v for v in readiness.values()):
        blocking.append("assignment metadata incomplete")
    if missing:
        blocking.append(f"{len(missing)} Step 1 cases without a verifier result (built with --allow-partial)")
    (out / "sampling_readiness.json").write_text(json.dumps({
        "assignments": len(final), "missing_values_by_field": readiness,
        "verifier_missing_cases": len(missing),
        # metadata completeness only; does not certify the final policy or the evaluation design
        "metadata_complete": all(v == 0 for v in readiness.values()),
        "ready": not blocking, "blocking_reasons": blocking,
        "by_division": dict(Counter(r["division"] for r in final)),
        "by_status": dict(Counter(r["final_status"] for r in final)),
        "by_depicted": dict(Counter(r["final_depicted"] for r in final))}, indent=2))
    print(json.dumps({"fig2": fig2, "exclusion_alternatives": alt, "table2_total": table[-1],
                      "sampling_ready": not blocking, "blocking_reasons": blocking}, indent=2, default=dict))


if __name__ == "__main__":
    main()
