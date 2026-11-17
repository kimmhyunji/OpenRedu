#!/usr/bin/env python3
"""v2.1 gap-fill for the zero-case topics of v2, same procedure as v1's
supplementary retrieval (the v1 supplementary retrieval scripts, not included in this release).

  search   query family per topic (config `gapfill_v21`) -> PMCIDs -> drop articles already in any existing
           corpus (every freeze cases.jsonl, the Step 1 corpus, v1 supplementary processed dirs) -> PMC
           metadata (title, journal, date) -> one review sheet per topic for the human candidate review
           (column `include` = y/n, `reason`). Free NCBI E-utilities; no LLM.
  (next steps, after the review: `extract` runs the standard curation pipeline on the approved PMCIDs into
   <out_dir>/processed (isolated; LLM cost - estimate and approval first), then article type, verifier,
   Step 3, v2.1 build.)
Outputs: <out_dir>/candidates_<schedule_entry_id>.csv, <out_dir>/search_manifest.json (queries, hit counts,
         dedupe counts, run time) - the query record of the retrieval queries and counts.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).parent))
import safe_logging  # noqa: E402,F401
CFG = yaml.safe_load((ROOT / "config/pipeline.yaml").read_text())
G = CFG["gapfill_v21"]
OUT = ROOT / G["out_dir"]
BASE_CORPUS = ROOT / "data/outputs/step1/corpus_casereport_only/cases.jsonl"
BASE_LABELS = ROOT / "data/outputs/step1/case_article_labels.jsonl"
SECTION = "gapfill_v21"


def existing_pmcids() -> set[str]:
    ids = set()
    paths = list((ROOT / "data/freeze").glob("*/cases.jsonl"))
    paths += list((ROOT / "data").glob("processed*/*.jsonl"))
    paths.append(ROOT / "data/outputs/step1/corpus_casereport_only/cases.jsonl")
    paths.append(BASE_CORPUS)
    paths += [ROOT / p for p in G.get("dedupe_corpora", [])]
    for p in paths:
        try:
            with p.open() as f:
                for line in f:
                    if '"pmcid"' in line:
                        try:
                            ids.add(json.loads(line).get("pmcid") or "")
                        except json.JSONDecodeError:
                            continue
        except OSError:
            continue
    ids.discard("")
    return ids


def group_text(g) -> str:
    """("a"[tiab] OR "b"[tiab]) - a tag on each term (PMC ignores a tag on a parenthesised group)."""
    g = G["groups"][g] if isinstance(g, str) else g
    return "(" + " OR ".join(f'"{t}"[{g["field"]}]' for t in g["terms"]) + ")"


def query_text(groups: list) -> str:
    return " AND ".join([group_text(g) for g in groups] + [G["access_filter"], G["date_filter"]])


def translate(q: str) -> str:
    from Bio import Entrez
    h = Entrez.esearch(db="pmc", term=q, retmax=0)
    r = Entrez.read(h)
    h.close()
    return r.get("QueryTranslation", "")


def metadata(pmcids: list[str]) -> dict[str, dict]:
    from Bio import Entrez
    from openredu.tools.ncbi_helpers import get_delay
    out = {}
    nums = [p.replace("PMC", "") for p in pmcids]
    for i in range(0, len(nums), 200):
        time.sleep(get_delay())
        h = Entrez.esummary(db="pmc", id=",".join(nums[i:i + 200]))
        for d in Entrez.read(h):
            out["PMC" + str(d.get("Id"))] = {"title": str(d.get("Title", "")), "journal": str(d.get("FullJournalName", "")),
                                            "pubdate": str(d.get("PubDate", ""))}
        h.close()
    return out


def cmd_search(_args) -> None:
    from openredu.tools.pmc_api import search_pmc
    OUT.mkdir(parents=True, exist_ok=True)
    have = existing_pmcids()
    manifest = {"run_at": datetime.now(timezone.utc).isoformat(), "filters": [G["access_filter"], G["date_filter"]],
                "existing_pmcids_checked": len(have), "topics": {}}
    for sid, t in G["topics"].items():
        seen, rows, per_q = set(), [], {}
        for qname, q in t["queries"].items():
            full = query_text(q)
            hits, translation = None, ""
            for attempt in range(4):   # PMC search backend fails transiently
                try:
                    hits, translation = search_pmc(full), translate(full)
                    break
                except Exception:
                    time.sleep(5 * (attempt + 1))
            if hits is None:
                raise RuntimeError(f"PMC search failed for {qname}")
            new = [p for p in hits if p not in seen]
            seen.update(new)
            per_q[qname] = {"query": full, "pmc_query_translation": translation, "hits": len(hits), "new_in_family": len(new)}
            for p in new:
                rows.append({"pmcid": p, "query": qname})
            time.sleep(1)
        fresh = [r for r in rows if r["pmcid"] not in have]
        meta = metadata([r["pmcid"] for r in fresh]) if fresh else {}
        path = OUT / f"candidates_{sid}.csv"
        with path.open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=["include (y/n)", "reason", "pmcid", "query", "pubdate", "journal", "title", "pmc_link"])
            w.writeheader()
            for r in sorted(fresh, key=lambda r: meta.get(r["pmcid"], {}).get("pubdate", ""), reverse=True):
                m = meta.get(r["pmcid"], {})
                w.writerow({"include (y/n)": "", "reason": "", "pmcid": r["pmcid"], "query": r["query"],
                            "pubdate": m.get("pubdate", ""), "journal": m.get("journal", ""), "title": m.get("title", ""),
                            "pmc_link": f"https://pmc.ncbi.nlm.nih.gov/articles/{r['pmcid']}/"})
        manifest["topics"][sid] = {"label": t["label"], "modalities": t["modalities"], "queries": per_q,
                                   "unique_hits": len(rows), "already_in_corpus": len(rows) - len(fresh),
                                   "candidates": len(fresh), "sheet": str(path.relative_to(ROOT))}
        print(f"{sid} {t['label']}: unique {len(rows)}, already in corpus {len(rows) - len(fresh)}, candidates {len(fresh)}",
              flush=True)
        (OUT / "search_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))


def cmd_extract(args) -> None:
    """Standard curation pipeline (openredu.coordinator.run_pipeline_for_pmcids, unchanged) on the candidate
    PMCIDs, per topic and per configured modality key, into isolated directories
    <out_dir>/runs/<schedule_entry_id>/{processed,checkpoint,failed}. Resumable (the coordinator skips
    PMCIDs already written for that modality). LLM cost (extraction cascade) - """
    from openredu.config import PATHS
    from openredu.coordinator import run_pipeline_for_pmcids
    manifest_p = OUT / "extract_manifest.json"
    manifest = json.loads(manifest_p.read_text()) if manifest_p.exists() else {"runs": []}
    topics = [args.topic] if args.topic else list(G["topics"])
    for sid in topics:
        t = G["topics"][sid]
        rows = list(csv.DictReader(open(OUT / f"candidates_{sid}.csv", encoding="utf-8-sig")))
        pmcids = [r["pmcid"] for r in rows if (r.get("include (y/n)") or "").strip().lower() != "n"]
        if args.limit:
            pmcids = pmcids[: args.limit]
        base = OUT / "runs" / sid
        # coordinator._checkpoint_path resolves from PATHS["data"], not PATHS["checkpoint"].
        # Keep v2.1 defaults intact while isolating every v2.2 checkpoint and manifest.
        if SECTION != "gapfill_v21":
            PATHS["data"] = base
        for k in ("processed", "checkpoint", "failed"):
            PATHS[k] = base / k
            PATHS[k].mkdir(parents=True, exist_ok=True)
        for mod in t["modalities"]:
            started = datetime.now(timezone.utc).isoformat()
            stats = run_pipeline_for_pmcids(pmcids=pmcids, modality=mod, dry_run=False, bypass_modality_exclude=False)
            manifest["runs"].append({"schedule_entry_id": sid, "modality": mod, "pmcids": len(pmcids),
                                     "started": started, "finished": datetime.now(timezone.utc).isoformat(),
                                     "stats": dict(stats or {}), "limit": args.limit})
            manifest_p.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
            print(f"{sid} {mod}: {dict(stats or {})}", flush=True)


def cmd_assemble(_args) -> None:
    """Gap-fill cases -> v2.1 Step 1 view (no LLM; NCBI metadata only).
    1. collect extracted cases from every run dir; one record per case_id; licence must be one of the six
       CC BY variants (CLAUDE.md rule 2); drop anything already in the Step 1 corpus
    2. source-article metadata (step1_fetch_article_meta.py --corpus, same cache) and the same article-type
       labelling (step1_label_article_types.label_article); keep config include_tiers (T1+T3)
    3. write <out_dir>/step1_view/{cases.jsonl, case_article_labels.jsonl, manifest.json}
       = Step 1 corpus + kept gap-fill cases, and <out_dir>/gapfill_summary.json (counts per topic)
    Next: verifier on corpus:<out_dir>/gapfill_cases_casereport.jsonl, then step5_build_v2.py --version v2.1."""
    import subprocess
    from openredu.config import ALLOWED_LICENSES
    from step1_label_article_types import label_article
    step1_path = BASE_CORPUS
    step1 = [json.loads(l) for l in step1_path.open()]
    have_ids = {c["case_id"] for c in step1}
    have_pmc = {c["pmcid"] for c in step1}
    ex = json.loads((OUT / "extract_manifest.json").read_text())
    summary = {"topics": {}}
    cases, seen = [], set()
    for sid in G["topics"]:
        n = {"candidates_pmcids": sum(1 for _ in open(OUT / f"candidates_{sid}.csv", encoding="utf-8-sig")) - 1,
             "pipeline_stats": [r for r in ex["runs"] if r["schedule_entry_id"] == sid and not r.get("limit")],
             "extracted": 0, "duplicate_or_existing": 0, "license_excluded": 0}
        for f in sorted((OUT / "runs" / sid / "processed").glob("cases_*.jsonl")):
            for line in f.open():
                c = json.loads(line)
                if c.get("status") not in ("mapped", "unmapped", "extracted"):
                    continue
                n["extracted"] += 1
                if c["case_id"] in seen or c["case_id"] in have_ids or c["pmcid"] in have_pmc:
                    n["duplicate_or_existing"] += 1
                    continue
                if c.get("license") not in ALLOWED_LICENSES:
                    n["license_excluded"] += 1
                    continue
                seen.add(c["case_id"])
                source_version = "v2.1" if SECTION == "gapfill_v21" else "v2.2"
                cases.append({**c, "is_gap_fill": True, "corpus_source": f"{source_version}_gapfill:{sid}",
                              "gapfill_schedule_entry_id": sid})
        summary["topics"][sid] = n
    all_path = OUT / "gapfill_cases_all.jsonl"
    with all_path.open("w") as f:
        for c in cases:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    meta_path = ROOT / "data/outputs/step1/article_meta.jsonl"
    cmd = [sys.executable, str(ROOT / "pipeline/step1_fetch_article_meta.py"),
           "--corpus", str(all_path.relative_to(ROOT))]
    if SECTION != "gapfill_v21":
        meta_path = OUT / "article_meta.jsonl"
        cmd += ["--out", str(meta_path.relative_to(ROOT))]
    subprocess.run(cmd, check=True)
    meta = {json.loads(l)["pmcid"]: json.loads(l) for l in meta_path.open()}
    tiers_keep = set(CFG["step1_article_type"]["include_tiers"])
    labels, kept = [], []
    for c in cases:
        a = label_article(meta[c["pmcid"]], c.get("article_title", ""), c.get("abstract", ""))
        labels.append({"case_id": c["case_id"], "pmcid": c["pmcid"], "tier": a["tier"],
                       "jats_article_type": a["jats_article_type"], "flags": a["flags"],
                       "case_signals": a["case_signals"], "case_series": a["case_series"]})
        if a["tier"] in tiers_keep:
            kept.append(c)
            summary["topics"][c["gapfill_schedule_entry_id"]]["after_article_type"] = \
                summary["topics"][c["gapfill_schedule_entry_id"]].get("after_article_type", 0) + 1
    with (OUT / "gapfill_cases_casereport.jsonl").open("w") as f:
        for c in kept:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    view = OUT / "step1_view"
    view.mkdir(parents=True, exist_ok=True)
    with (view / "cases.jsonl").open("w") as f:
        for c in step1 + kept:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    base_labels = BASE_LABELS.read_text()
    with (view / "case_article_labels.jsonl").open("w") as f:
        f.write(base_labels if base_labels.endswith("\n") else base_labels + "\n")
        for r in labels:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    (view / "manifest.json").write_text(json.dumps({"view": "v2.1 step1 (step1 corpus + gap-fill T1/T3)" if SECTION == "gapfill_v21" else f"{SECTION} input corpus + gap-fill",
                                                    "cases": len(step1) + len(kept), "gapfill_cases": len(kept)}))
    summary.update(gapfill_cases_extracted_unique=len(cases), gapfill_cases_after_article_type=len(kept),
                   tiers=dict(__import__("collections").Counter(r["tier"] for r in labels)))
    (OUT / "gapfill_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(json.dumps({k: v for k, v in summary.items() if k != "topics"}, indent=2))
    for sid, n in summary["topics"].items():
        print(sid, {k: v for k, v in n.items() if k != "pipeline_stats"})


def main() -> None:
    global G, OUT, BASE_CORPUS, BASE_LABELS, SECTION
    ap = argparse.ArgumentParser()
    ap.add_argument("--config-section", default="gapfill_v21")
    ap.add_argument("--base-corpus", default="data/outputs/step1/corpus_casereport_only/cases.jsonl")
    ap.add_argument("--base-labels", default=None)
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("search")
    sp.add_parser("assemble")
    e = sp.add_parser("extract")
    e.add_argument("--topic", default=None)
    e.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    SECTION = args.config_section
    G = CFG[SECTION]
    OUT = ROOT / G["out_dir"]
    BASE_CORPUS = ROOT / args.base_corpus
    BASE_LABELS = ROOT / (args.base_labels or G.get("base_labels", "data/outputs/step1/case_article_labels.jsonl"))
    {"search": cmd_search, "extract": cmd_extract, "assemble": cmd_assemble}[args.cmd](args)


if __name__ == "__main__":
    main()
