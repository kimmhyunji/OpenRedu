#!/usr/bin/env python3
"""Prospective update: articles published after the corpus collection, processed by the current pipeline.

Config section `update_2026q3` (config/pipeline.yaml). Everything is written to a new folder (<out_dir>) and the
final cases to a new freeze directory; the resubmission corpus (v2.2) and shared paths are never written.

  search    the 23 original category queries (query_without_date_clause) + the date window -> PMCIDs -> drop articles
            already in any existing corpus -> candidates_<category>.csv, search_manifest.json (written and PMC-translated
            queries). Free NCBI E-utilities; no LLM.
  extract   standard curation pipeline (openredu.coordinator.run_pipeline_for_pmcids, unchanged; the extraction agent runs
            the figure-scoped second pass itself) per category into <out_dir>/runs/<category>/. Bedrock calls are only
            recorded (model, tokens, latency) by a pass-through client wrapper -> <out_dir>/llm_calls.jsonl. Resumable.
  assemble  extracted cases -> one record per case_id (category order of queries.json), CC BY licences only, article
            metadata and the same article-type labelling (T1-T3 kept) -> <out_dir>/cases_casereport.jsonl, labels,
            assemble_summary.json. No LLM.
  combine   inputs for one build of v2.2 + new cases (verifier run must exist): <out_dir>/build_input/
  (then step2_verifier.py on corpus:<out_dir>/cases_casereport.jsonl and step5_build_v2.py on build_input; see
   docs/retrieval_queries_and_run_counts.md)
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).parent))
import safe_logging  # noqa: E402,F401


class _RedactingStream:
    """Second guard: every text written to stdout/stderr passes safe_logging.redact (the 2026-10-19 extract log
    still showed NCBI api_key values in efetch error URLs although the log-record factory was installed)."""

    def __init__(self, stream):
        self._s = stream

    def write(self, text):
        return self._s.write(safe_logging.redact(text))

    def __getattr__(self, name):
        return getattr(self._s, name)


sys.stdout, sys.stderr = _RedactingStream(sys.stdout), _RedactingStream(sys.stderr)

CFG = yaml.safe_load((ROOT / "config/pipeline.yaml").read_text())
U = CFG["update_2026q3"]
OUT = ROOT / U["out_dir"]


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def categories() -> dict[str, str]:
    q = json.loads((ROOT / U["queries"]).read_text())
    return {k: v["query_without_date_clause"] for k, v in q.items()}


def existing_pmcids() -> set[str]:
    import gapfill_v21 as g
    g.G = {"dedupe_corpora": U["dedupe_corpora"]}
    g.BASE_CORPUS = ROOT / U["base_corpus"]
    return g.existing_pmcids()


def cmd_search(_a) -> None:
    from openredu.tools.pmc_api import search_pmc
    from gapfill_v21 import translate, metadata
    OUT.mkdir(parents=True, exist_ok=True)
    have = existing_pmcids()
    man = {"run_at": now(), "date_filter": U["date_filter"], "existing_pmcids_checked": len(have), "categories": {}}
    for cat, q in categories().items():
        full = f"{q} AND {U['date_filter']}"
        hits, tr = None, ""
        for attempt in range(4):
            try:
                hits, tr = search_pmc(full), translate(full)
                break
            except Exception:
                time.sleep(5 * (attempt + 1))
        if hits is None:
            raise RuntimeError(f"PMC search failed for {cat}")
        fresh = [p for p in dict.fromkeys(hits) if p not in have]
        meta = metadata(fresh) if fresh else {}
        with (OUT / f"candidates_{cat}.csv").open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=["pmcid", "pubdate", "journal", "title"])
            w.writeheader()
            for p in fresh:
                m = meta.get(p, {})
                w.writerow({"pmcid": p, "pubdate": m.get("pubdate", ""), "journal": m.get("journal", ""), "title": m.get("title", "")})
        man["categories"][cat] = {"query": full, "pmc_query_translation": tr, "hits": len(hits),
                                  "already_in_corpus": len(hits) - len(fresh), "candidates": len(fresh)}
        print(f"{cat:<20} hits {len(hits):>5}  in corpus {len(hits) - len(fresh):>4}  candidates {len(fresh):>5}", flush=True)
        (OUT / "search_manifest.json").write_text(json.dumps(man, indent=2, ensure_ascii=False))
        time.sleep(1)
    allc = {p for c in man["categories"] for p in read_candidates(c)}
    man["unique_candidate_articles"] = len(allc)
    (OUT / "search_manifest.json").write_text(json.dumps(man, indent=2, ensure_ascii=False))
    print("unique candidate articles", len(allc))


def read_candidates(cat: str) -> list[str]:
    return [r["pmcid"] for r in csv.DictReader((OUT / f"candidates_{cat}.csv").open(encoding="utf-8-sig"))]


class _Recorder:
    """Pass-through Bedrock client: the response body is read once, its usage recorded, and an identical body returned."""

    def __init__(self, client, path: Path):
        self._c, self._path, self._lock = client, path, threading.Lock()
        self.category = ""

    def __getattr__(self, name):
        return getattr(self._c, name)

    def invoke_model(self, **kw):
        t0 = time.time()
        rec = {"at": now(), "category": self.category, "model": kw.get("modelId"), "ok": False}
        try:
            resp = self._c.invoke_model(**kw)
            raw = resp["body"].read()
            resp["body"] = io.BytesIO(raw)
            js = json.loads(raw)
            u = js.get("usage") or {}
            rec.update(ok=True, input_tokens=u.get("input_tokens", u.get("prompt_tokens", u.get("inputTokens", 0))),
                       output_tokens=u.get("output_tokens", u.get("completion_tokens", u.get("outputTokens", 0))))
            return resp
        except Exception as e:
            rec["error"] = type(e).__name__
            raise
        finally:
            rec["latency_s"] = round(time.time() - t0, 3)
            with self._lock, self._path.open("a") as f:
                f.write(json.dumps(rec) + "\n")


def cmd_extract(a) -> None:
    import openredu.core.llm as llm
    from openredu.config import PATHS
    from openredu.coordinator import run_pipeline_for_pmcids
    rec = _Recorder(llm._get_bedrock_client(), OUT / "llm_calls.jsonl")
    llm._BEDROCK_CLIENT = rec
    mp = OUT / "extract_manifest.json"
    man = json.loads(mp.read_text()) if mp.exists() else {"runs": []}
    cats = [a.category] if a.category else list(categories())
    for cat in cats:
        pmcids = read_candidates(cat)
        if a.limit:
            pmcids = pmcids[: a.limit]
        if not pmcids:
            continue
        base = OUT / "runs" / cat
        PATHS["data"] = base
        for k in ("processed", "checkpoint", "failed"):
            PATHS[k] = base / k
            PATHS[k].mkdir(parents=True, exist_ok=True)
        rec.category = cat
        started = now()
        stats = run_pipeline_for_pmcids(pmcids=pmcids, modality=cat, dry_run=False, bypass_modality_exclude=False)
        man["runs"].append({"category": cat, "pmcids": len(pmcids), "started": started, "finished": now(),
                            "stats": dict(stats or {}), "limit": a.limit})
        mp.write_text(json.dumps(man, indent=2, ensure_ascii=False))
        print(f"{cat}: {dict(stats or {})}", flush=True)


def cmd_assemble(_a) -> None:
    import subprocess
    from collections import Counter
    from openredu.config import ALLOWED_LICENSES
    from step1_label_article_types import label_article
    have_pmc = existing_pmcids()
    order = list(categories())
    s = {"extracted": 0, "cross_category_duplicate": 0, "already_in_corpus": 0, "license_excluded": 0, "per_category": {}}
    cases, seen = [], set()
    for cat in order:
        n = Counter()
        for f in sorted((OUT / "runs" / cat / "processed").glob("cases_*.jsonl")):
            for line in f.open():
                c = json.loads(line)
                if c.get("status") not in ("mapped", "unmapped", "extracted"):
                    continue
                n["extracted"] += 1
                if c["case_id"] in seen:
                    n["cross_category_duplicate"] += 1
                    continue
                if c["pmcid"] in have_pmc:
                    n["already_in_corpus"] += 1
                    continue
                if c.get("license") not in ALLOWED_LICENSES:
                    n["license_excluded"] += 1
                    continue
                seen.add(c["case_id"])
                cases.append({**c, "is_gap_fill": False, "corpus_source": "update_2026q3", "update_category": cat})
        s["per_category"][cat] = dict(n)
        for k in ("extracted", "cross_category_duplicate", "already_in_corpus", "license_excluded"):
            s[k] += n[k]
    allp = OUT / "cases_all.jsonl"
    with allp.open("w") as f:
        for c in cases:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    meta_p = OUT / "article_meta.jsonl"
    subprocess.run([sys.executable, str(ROOT / "pipeline/step1_fetch_article_meta.py"), "--corpus",
                    str(allp.relative_to(ROOT)), "--out", str(meta_p.relative_to(ROOT))], check=True)
    meta = {json.loads(l)["pmcid"]: json.loads(l) for l in meta_p.open()}
    keep_tiers = set(CFG["step1_article_type"]["include_tiers"])
    labels, kept = [], []
    for c in cases:
        r = label_article(meta[c["pmcid"]], c.get("article_title", ""), c.get("abstract", ""))
        labels.append({"case_id": c["case_id"], "pmcid": c["pmcid"], "tier": r["tier"], "jats_article_type": r["jats_article_type"],
                       "flags": r["flags"], "case_signals": r["case_signals"], "case_series": r["case_series"]})
        if r["tier"] in keep_tiers:
            kept.append(c)
    with (OUT / "cases_casereport.jsonl").open("w") as f:
        for c in kept:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    with (OUT / "case_article_labels.jsonl").open("w") as f:
        for r in labels:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    s.update(unique_cases=len(cases), articles=len({c["pmcid"] for c in cases}), after_article_type=len(kept),
             articles_after_article_type=len({c["pmcid"] for c in kept}), tiers=dict(Counter(r["tier"] for r in labels)),
             finding_scope=dict(Counter(c.get("finding_scope") for c in kept)), assembled_at=now())
    (OUT / "assemble_summary.json").write_text(json.dumps(s, indent=2, ensure_ascii=False))
    print(json.dumps({k: v for k, v in s.items() if k != "per_category"}, indent=2))


def cmd_combine(_a) -> None:
    """build inputs = v2.2 input + new T1-T3 cases; labels and verifier records concatenated (case IDs disjoint)."""
    bi = OUT / "build_input"
    bi.mkdir(parents=True, exist_ok=True)
    new = [json.loads(l) for l in (OUT / "cases_casereport.jsonl").open()]
    base_ids = {json.loads(l)["case_id"] for l in (ROOT / U["base_corpus"]).open()}
    assert not base_ids & {c["case_id"] for c in new}
    run = ROOT / f"data/outputs/step2/runs/{U['verifier_run_id']}/nova-pro.jsonl"
    vr = [json.loads(l) for l in run.open()]
    assert {r["case_id"] for r in vr} >= {c["case_id"] for c in new}, "verifier missing new cases"
    for name, base, extra in [("cases.jsonl", U["base_corpus"], OUT / "cases_casereport.jsonl"),
                              ("case_article_labels.jsonl", U["base_labels"], OUT / "case_article_labels.jsonl"),
                              ("nova-pro.jsonl", U["base_verifier"], run)]:
        # step5_build_v2.py requires the verifier file under data/outputs/step2 (new run folder, nothing overwritten)
        dest = ROOT / f"data/outputs/step2/runs/{U['verifier_run_id']}_combined" / name if name == "nova-pro.jsonl" else bi / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open("w") as f:
            for p in (ROOT / base, extra):
                t = p.read_text()
                f.write(t if t.endswith("\n") else t + "\n")
    print("build_input written:", {p.name: sum(1 for _ in p.open()) for p in bi.iterdir() if p.is_file()},
          "verifier:", f"data/outputs/step2/runs/{U['verifier_run_id']}_combined/nova-pro.jsonl")


def main() -> None:
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("search")
    e = sp.add_parser("extract")
    e.add_argument("--category", default=None)
    e.add_argument("--limit", type=int, default=0)
    sp.add_parser("assemble")
    sp.add_parser("combine")
    a = ap.parse_args()
    {"search": cmd_search, "extract": cmd_extract, "assemble": cmd_assemble, "combine": cmd_combine}[a.cmd](a)


if __name__ == "__main__":
    main()
