#!/usr/bin/env python3
"""Build a case library from PubMed Central open-access case reports.

Settings come from the `build` section of config/pipeline.yaml. Every file is written under its `out_dir`
(default data/library/); verifier calls go to data/outputs/step2/runs/<verifier_run_id>/.

  search    the 23 category queries + the date window -> candidate articles per category. NCBI only, no LLM.
  extract   Curation agent on the candidates: figure retrieval, caption classification, two-pass extraction and
            self-check (AWS Bedrock). Resumable; figure images are saved under data/images/.
  assemble  one record per figure, open licenses only, article-type screening (case reports kept). NCBI only.
  verify    independent verifier on every assembled case (AWS Bedrock). Rerun the same command for failed calls.
  finalize  drop cases whose category or finding the verifier judged not supported -> library/cases.jsonl
  synonyms  optional: UMLS synonyms of your topic phrases (UMLS license).
  link      optional: link library cases to your curriculum topics (docs/data_layout.md lists the input files).

To add newly published articles to an existing library, set a new date window and out_dir, list the earlier
library in `skip_articles_in`, and run the same commands.
"""
from __future__ import annotations

import argparse
import csv
from copy import deepcopy
import io
import json
import subprocess
import sys
import threading
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).parent))
import safe_logging  # noqa: E402,F401  (keeps API keys out of log output)

CFG = yaml.safe_load((ROOT / "config/pipeline.yaml").read_text())
B = CFG["build"]
V = CFG["step2_verifier"]
OUT = ROOT / B["out_dir"]
VERIFIER_FILE = ROOT / "data/outputs/step2/runs" / B["verifier_run_id"] / f"{V['final_model']}.jsonl"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def jl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def write_jl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT))


# ── search ────────────────────────────────────────────────────────────────────
def categories() -> dict[str, str]:
    q = json.loads((ROOT / B["queries"]).read_text())
    chosen = B.get("categories") or list(q)
    return {k: q[k]["query_without_date_clause"] for k in chosen}


def skipped_articles() -> set[str]:
    ids = set()
    for p in B.get("skip_articles_in") or []:
        ids |= {r.get("pmcid", "") for r in jl(ROOT / p)}
    ids.discard("")
    return ids


def read_candidates(cat: str) -> list[str]:
    path = OUT / "candidates" / f"{cat}.csv"
    if not path.exists():
        return []
    return [r["pmcid"] for r in csv.DictReader(path.open(encoding="utf-8-sig"))]


def cmd_search(_a) -> None:
    from openredu.tools.pmc_api import search_pmc
    from gapfill_v21 import metadata, translate
    (OUT / "candidates").mkdir(parents=True, exist_ok=True)
    skip = skipped_articles()
    man = {"run_at": now(), "date_filter": B["date_filter"], "skipped_articles": len(skip), "categories": {}}
    for cat, q in categories().items():
        full = f"{q} AND {B['date_filter']}"
        hits = None
        for attempt in range(4):
            try:
                hits, tr = search_pmc(full), translate(full)
                break
            except Exception:
                time.sleep(5 * (attempt + 1))
        if hits is None:
            raise RuntimeError(f"PMC search failed for {cat}")
        fresh = [p for p in dict.fromkeys(hits) if p not in skip]
        meta = metadata(fresh) if fresh else {}
        with (OUT / "candidates" / f"{cat}.csv").open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=["pmcid", "pubdate", "journal", "title"])
            w.writeheader()
            for p in fresh:
                m = meta.get(p, {})
                w.writerow({"pmcid": p, "pubdate": m.get("pubdate", ""), "journal": m.get("journal", ""),
                            "title": m.get("title", "")})
        man["categories"][cat] = {"query": full, "pmc_query_translation": tr, "hits": len(hits),
                                  "skipped": len(hits) - len(fresh), "candidates": len(fresh)}
        print(f"{cat:<22} hits {len(hits):>5}  skipped {len(hits) - len(fresh):>4}  candidates {len(fresh):>5}", flush=True)
        (OUT / "search_manifest.json").write_text(json.dumps(man, indent=2, ensure_ascii=False))
        time.sleep(1)


# ── extract ───────────────────────────────────────────────────────────────────
class _Recorder:
    """Pass-through Bedrock client that records model, token use and latency of every call."""

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
            u = json.loads(raw).get("usage") or {}
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


class _StandardizeOnly:
    """Used when no curriculum topic table is supplied: the Mapping agent's diagnosis standardization still runs
    (the verifier uses the standardized name), and topic links are made later with the `link` command."""

    def __init__(self):
        from openredu.agents.mapping.subagents.standardization import StandardizationSubagent
        self.standardization = StandardizationSubagent()

    def run(self, state):
        state = self.standardization.run(state)
        if state.status == "extracted":
            state.status = "unmapped"
        return state


def _topic_table_present() -> bool:
    from openredu.config import PATHS
    return (PATHS["guidelines"] / "structured_apdr.csv").exists() or PATHS["apdr_keywords"].exists()


def cmd_extract(a) -> None:
    import openredu.coordinator as coord
    import openredu.core.llm as llm
    from openredu.config import PATHS
    rec = _Recorder(llm._get_bedrock_client(), OUT / "llm_calls.jsonl")
    llm._BEDROCK_CLIENT = rec
    if not _topic_table_present():
        print("No curriculum topic table in data/guidelines/; diagnoses are standardized, topics are linked later.")
        coord._mapping_agent = _StandardizeOnly()
    mp = OUT / "extract_manifest.json"
    man = json.loads(mp.read_text()) if mp.exists() else {"runs": []}
    for cat in ([a.category] if a.category else list(categories())):
        pmcids = read_candidates(cat)[: a.limit or None]
        if not pmcids:
            continue
        base = OUT / "runs" / cat
        PATHS["data"] = base
        for k in ("processed", "checkpoint", "failed"):
            PATHS[k] = base / k
            PATHS[k].mkdir(parents=True, exist_ok=True)
        rec.category = cat
        started = now()
        stats = coord.run_pipeline_for_pmcids(pmcids=pmcids, modality=cat, dry_run=False, bypass_modality_exclude=False)
        man["runs"].append({"category": cat, "pmcids": len(pmcids), "started": started, "finished": now(),
                            "stats": dict(stats or {}), "limit": a.limit})
        mp.write_text(json.dumps(man, indent=2, ensure_ascii=False))
        print(f"{cat}: {dict(stats or {})}", flush=True)


# ── assemble ──────────────────────────────────────────────────────────────────
def cmd_assemble(_a) -> None:
    from openredu.config import ALLOWED_LICENSES
    from step1_label_article_types import label_article
    from openredu.tools.image_downloader import case_has_valid_images
    skip = skipped_articles()
    s = {"extracted": 0, "cross_category_duplicate": 0, "skipped_article": 0, "license_excluded": 0, "image_excluded": 0, "per_category": {}}
    cases, seen, image_excluded = [], set(), []
    for cat in categories():
        n = Counter()
        for f in sorted((OUT / "runs" / cat / "processed").glob("cases_*.jsonl")):
            for c in jl(f):
                if c.get("status") not in ("mapped", "unmapped", "extracted"):
                    continue
                n["extracted"] += 1
                if c["case_id"] in seen:
                    n["cross_category_duplicate"] += 1
                elif c["pmcid"] in skip:
                    n["skipped_article"] += 1
                elif c.get("license") not in ALLOWED_LICENSES:
                    n["license_excluded"] += 1
                elif not case_has_valid_images(c, ROOT):
                    n["image_excluded"] += 1
                    image_excluded.append({"case_id": c["case_id"], "pmcid": c["pmcid"],
                                           "category": cat, "reason": "missing_or_invalid_image"})
                else:
                    seen.add(c["case_id"])
                    cases.append({**c, "collection_category": cat})
        s["per_category"][cat] = dict(n)
        for k in ("extracted", "cross_category_duplicate", "skipped_article", "license_excluded", "image_excluded"):
            s[k] += n[k]
    write_jl(OUT / "assemble_image_excluded.jsonl", image_excluded)
    write_jl(OUT / "cases_all.jsonl", cases)
    meta_p = OUT / "article_meta.jsonl"
    subprocess.run([sys.executable, str(ROOT / "pipeline/step1_fetch_article_meta.py"), "--corpus",
                    rel(OUT / "cases_all.jsonl"), "--out", rel(meta_p)], check=True)
    meta = {r["pmcid"]: r for r in jl(meta_p)}
    keep_tiers = set(CFG["step1_article_type"]["include_tiers"])
    labels, kept = [], []
    for c in cases:
        r = label_article(meta[c["pmcid"]], c.get("article_title", ""), c.get("abstract", ""))
        labels.append({"case_id": c["case_id"], "pmcid": c["pmcid"], "tier": r["tier"],
                       "jats_article_type": r["jats_article_type"], "flags": r["flags"]})
        if r["tier"] in keep_tiers:
            kept.append(c)
    write_jl(OUT / "cases_casereport.jsonl", kept)
    write_jl(OUT / "case_article_labels.jsonl", labels)
    s.update(unique_cases=len(cases), after_article_type=len(kept),
             articles_after_article_type=len({c["pmcid"] for c in kept}),
             tiers=dict(Counter(r["tier"] for r in labels)), assembled_at=now())
    (OUT / "assemble_summary.json").write_text(json.dumps(s, indent=2, ensure_ascii=False))
    print(json.dumps({k: v for k, v in s.items() if k != "per_category"}, indent=2))


# ── verify ────────────────────────────────────────────────────────────────────
def cmd_verify(a) -> None:
    cmd = [sys.executable, str(ROOT / "pipeline/step2_verifier.py"), "--cases", f"corpus:{rel(OUT / 'cases_casereport.jsonl')}",
           "--models", V["final_model"], "--run-id", B["verifier_run_id"]]
    if a.limit:
        cmd += ["--limit", str(a.limit)]
    subprocess.run(cmd, check=True)


# ── finalize ──────────────────────────────────────────────────────────────────
def apply_verifier(cases: list[dict], records: list[dict], exclusion_fields: list[str]):
    """Keep cases unless the verifier judged one of `exclusion_fields` not supported.
    The last successful record per case counts. Returns (kept, excluded, missing case IDs)."""
    ver = {}
    for r in records:
        if r.get("ok"):
            ver[r["case_id"]] = r
    kept, excluded, missing = [], [], []
    for c in cases:
        r = ver.get(c["case_id"])
        if r is None:
            missing.append(c["case_id"])
            continue
        p = r["parsed"]
        verdicts = {f: (p.get(f) or {}).get("verdict", "") for f in
                    ("classification", "finding", "laterality", "diagnosis_article", "diagnosis_in_figure")}
        bad = [f for f in exclusion_fields if verdicts.get(f) == "not_supported"]
        if bad:
            excluded.append({"case_id": c["case_id"], "pmcid": c["pmcid"], "reason": "+".join(f"{f}_not_supported" for f in bad)})
        else:
            kept.append({**c, "source_url": f"https://pmc.ncbi.nlm.nih.gov/articles/{c['pmcid']}/",
                         "verifier": {"model": r.get("model_id", ""), "prompt_version": r.get("prompt_version", ""),
                                      "verdicts": verdicts, "conditions": p.get("conditions", [])}})
    return kept, excluded, missing


def cmd_finalize(a) -> None:
    from openredu.tools.image_downloader import case_has_valid_images

    cases = jl(OUT / "cases_casereport.jsonl")
    fields = V.get("corpus_exclusion_fields", ["classification", "finding"])
    valid, image_excluded = [], []
    for c in cases:
        if case_has_valid_images(c, ROOT):
            valid.append(c)
        else:
            image_excluded.append({"case_id": c["case_id"], "pmcid": c["pmcid"],
                                   "reason": "missing_or_invalid_image"})
    kept, excluded, missing = apply_verifier(valid, jl(VERIFIER_FILE), fields)
    verifier_excluded = len(excluded)
    excluded.extend(image_excluded)
    if missing and not a.allow_partial:
        sys.exit(f"verifier results missing for {len(missing)} cases; run `verify` again (or --allow-partial)")
    lib = OUT / "library"
    write_jl(lib / "cases.jsonl", kept)
    with (lib / "excluded.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["case_id", "pmcid", "reason"])
        w.writeheader()
        w.writerows(excluded)
    manifest = {"built_at": now(), "date_filter": B["date_filter"], "categories": list(categories()),
                "verifier_run": rel(VERIFIER_FILE), "exclusion_fields": fields,
                "assembled_cases": len(cases), "verifier_excluded": verifier_excluded, "image_excluded": len(image_excluded), "missing_verifier": len(missing),
                "library_cases": len(kept), "library_articles": len({c["pmcid"] for c in kept}),
                "cases_by_category": dict(Counter(c["collection_category"] for c in kept))}
    (lib / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    print(json.dumps(manifest, indent=2))


# ── link ──────────────────────────────────────────────────────────────────────
def link_cases(corpus: Path, out_dir: Path, verifier: str | None, umls: bool, root: Path = ROOT,
               technique_terms: dict | None = None) -> dict:
    """Link a custom curriculum with only its explicitly supplied technique gates."""
    import step3_assertion_matching as s3
    terms = {} if technique_terms is None else technique_terms
    if not isinstance(terms, dict) or any(
        not isinstance(sid, str) or not isinstance(words, list) or not words
        or any(not isinstance(w, str) or not w.strip() for w in words)
        for sid, words in terms.items()
    ):
        raise ValueError("technique terms must map topic IDs to nonempty lists of terms")
    old_snap, old_s3 = s3.SNAP, deepcopy(s3.S3)
    try:
        return _link_cases(corpus, out_dir, verifier, umls, root, terms)
    finally:
        s3.SNAP = old_snap
        s3.S3.clear()
        s3.S3.update(old_s3)


def _link_cases(corpus: Path, out_dir: Path, verifier: str | None, umls: bool,
                root: Path, technique_terms: dict) -> dict:
    """Topic matching with assertion and depiction rules (pipeline/step3_assertion_matching.py) on `corpus`,
    using the curriculum files of docs/data_layout.md. Writes out_dir/assignments.jsonl and summary.json."""
    import step3_assertion_matching as s3
    s3.SNAP = root                      # curriculum files are read from data/curriculum/ and data/guidelines/
    s3.S3["concept_expansion"] = "umls_synonyms" if umls else "none"
    s3.S3["topic_phrase_additions"] = {}  # phrase additions of the article's curriculum only
    out_dir.mkdir(parents=True, exist_ok=True)
    cases = {c["case_id"]: c for c in jl(corpus)}
    ver = s3.load_verifier(verifier)
    covres = s3.v1_candidates(corpus, out_dir)
    unknown = set(technique_terms) - {t["schedule_entry_id"] for t in covres["topics"]}
    if unknown:
        raise ValueError(f"Technique gates reference unknown curriculum IDs: {sorted(unknown)}")
    rows = []
    for t in (t for t in covres["topics"] if t["status"] != "excluded"):
        sid, phrases = t["schedule_entry_id"], t["match_phrases"]
        for cid in t.get("matched_case_ids", []):
            c = cases[cid]
            rs = s3.rule_status(c, phrases)
            al = s3.align(ver[cid], phrases) if cid in ver else None
            if al is not None:
                al["case_dx_in_figure"] = (ver[cid].get("diagnosis_in_figure") or {}).get("verdict")
            tech, _ = s3.technique_ok(c, sid, technique_terms)
            keep, status, depicted, why = s3.decide(rs, al, tech)
            rows.append({"case_id": cid, "schedule_entry_id": sid, "division": t["division"], "keyword": t["keyword"],
                         "matched_phrases": sorted({o["phrase"] for o in rs["occurrences"]}),
                         "match_strength": s3.match_strength(rs), "status": status, "depicted": depicted,
                         "keep": keep, "decision": why})
    write_jl(out_dir / "assignments.jsonl", rows)
    kept = [r for r in rows if r["keep"]]
    summary = {"candidate_links": len(rows), "links": len(kept), "linked_cases": len({r["case_id"] for r in kept}),
               "topics": len([t for t in covres["topics"] if t["status"] != "excluded"]),
               "topics_with_case": len({r["schedule_entry_id"] for r in kept}), "umls_synonyms": umls,
               "technique_terms": technique_terms}
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    return summary


def cmd_synonyms(_a) -> None:
    """UMLS concepts and synonyms of your topic phrases (pipeline/step4_*; UMLS_API_KEY) for `link --umls`."""
    import step4_synonyms as syn
    import step4_umls_topics as topics
    topics.SNAP = syn.SNAP = ROOT       # topic phrase file from data/guidelines/
    sys.argv = ["step4_umls_topics.py", "--relations"]
    topics.main()
    sys.argv = ["step4_synonyms.py"]
    syn.main()


def cmd_link(a) -> None:
    v = VERIFIER_FILE.relative_to(ROOT / "data/outputs/step2")
    terms = json.loads(a.technique_terms.read_text()) if a.technique_terms else None
    print(json.dumps(link_cases(OUT / "library/cases.jsonl", OUT / "links", str(v), a.umls,
                                technique_terms=terms), indent=2))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("search")
    e = sp.add_parser("extract")
    e.add_argument("--category", default=None, help="one category only")
    e.add_argument("--limit", type=int, default=0, help="at most this many articles per category")
    sp.add_parser("assemble")
    v = sp.add_parser("verify")
    v.add_argument("--limit", type=int, default=0)
    f = sp.add_parser("finalize")
    f.add_argument("--allow-partial", action="store_true", help="build even if some cases have no verifier result")
    sp.add_parser("synonyms", help="UMLS synonyms of your topic phrases (needs a UMLS license)")
    k = sp.add_parser("link")
    k.add_argument("--umls", action="store_true", help="also match the UMLS synonyms made by `synonyms`")
    k.add_argument("--technique-terms", type=Path, help="JSON topic-ID to required technique terms for this curriculum")
    a = ap.parse_args()
    {"search": cmd_search, "extract": cmd_extract, "assemble": cmd_assemble, "verify": cmd_verify,
     "finalize": cmd_finalize, "synonyms": cmd_synonyms, "link": cmd_link}[a.cmd](a)


if __name__ == "__main__":
    main()
