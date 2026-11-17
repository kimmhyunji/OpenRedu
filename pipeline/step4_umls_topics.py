#!/usr/bin/env python3
"""Step 4a: map APDR topic clinical phrases to UMLS CUIs with the same resolver used for
case diagnoses (openredu StandardizationSubagent order), and fetch hierarchy relations.

Resolver order (identical to agents/mapping/subagents/standardization.py):
  L1 MeSH (NCBI) -> UMLS CUI of the MeSH preferred term
  L2 SNOMED CT via UTS
  L3 LLM concept decomposition (Claude Haiku) + UTS search  -- OFF unless --allow-llm
Phrases unresolved by L1/L2 are listed. Hierarchy: UTS relations PAR/CHD (+RB/RN) for the
topic CUIs, cached. UMLS release is recorded (UTS "current" endpoint). Free APIs, no LLM
by default. Resumable via cache.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).parent))
import safe_logging  # noqa: E402,F401  (masks UMLS apiKey/ticket in log records)
CFG = yaml.safe_load((ROOT / "config/pipeline.yaml").read_text())
SNAP = ROOT / CFG["snapshot_dir"]
OUT = ROOT / "data/outputs/step4"


def umls_release() -> dict:
    r = requests.get("https://uts-ws.nlm.nih.gov/releases",
                     params={"releaseType": "umls-full-release", "current": "true"}, timeout=30)
    rel = r.json()[0]
    return {"releaseVersion": rel["releaseVersion"], "releaseDate": rel["releaseDate"],
            "queried_at": datetime.now(timezone.utc).isoformat()}


def resolve(phrase: str, allow_llm: bool) -> dict:
    from openredu.agents.mapping.subagents.standardization import StandardizationSubagent, _get_umls_client
    from openredu.tools.umls_client import snomed_lookup, call_concept_llm, best_cui
    sub = StandardizationSubagent()
    try:
        r = sub._layer1_mesh(phrase)
        if r and r.get("cui"):
            return {"cui": r["cui"], "name": r.get("umls_preferred", ""), "layer": "L1_MeSH"}
    except Exception as e:  # network errors are recorded, not fatal
        pass
    try:
        r = snomed_lookup(_get_umls_client(), phrase)
        if r and r.get("cui"):
            return {"cui": r["cui"], "name": r.get("snomed_preferred", ""), "layer": "L2_SNOMED"}
    except Exception as e:
        return {"cui": None, "layer": "error", "error": str(e)[:200]}
    if allow_llm:
        parsed = call_concept_llm(phrase)
        if parsed and parsed.get("mappable", True):
            cui, name = best_cui([c.lower().strip() for c in parsed.get("concepts", []) if c])
            if cui:
                return {"cui": cui, "name": name or "", "layer": "L3_LLM"}
    return {"cui": None, "layer": "unresolved_L1_L2" if not allow_llm else "unresolved"}


def relations(cui: str, api_key: str) -> list[dict]:
    out, page = [], 1
    while True:
        r = None
        for attempt in range(5):  # retry transient 5xx; never surface the URL (it carries the key)
            try:
                r = requests.get(f"https://uts-ws.nlm.nih.gov/rest/content/current/CUI/{cui}/relations",
                                 params={"apiKey": api_key, "includeRelationLabels": "PAR,CHD,RB,RN",
                                         "pageNumber": page, "pageSize": 200}, timeout=60)
                if r.status_code < 500:
                    break
            except requests.RequestException:
                r = None
            time.sleep(2 ** attempt)
        if r is None or r.status_code >= 500:
            return out + [{"label": "_fetch_error", "related_cui": "", "related_name": f"HTTP {getattr(r, 'status_code', 'n/a')}", "source": ""}]
        if r.status_code == 404:
            break
        if r.status_code != 200:
            return out + [{"label": "_fetch_error", "related_cui": "", "related_name": f"HTTP {r.status_code}", "source": ""}]
        js = r.json()
        for rel in js.get("result", []):
            rid = rel.get("relatedId", "")
            out.append({"label": rel.get("relationLabel"), "related_cui": rid.rsplit("/", 1)[-1],
                        "related_name": rel.get("relatedIdName"), "source": rel.get("rootSource")})
        if page >= js.get("pageCount", 1):
            break
        page += 1
        time.sleep(0.1)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--allow-llm", action="store_true", help="enable L3 (Claude Haiku); off by default")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--relations", action="store_true", help="also fetch PAR/CHD/RB/RN for topic CUIs")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    from openredu.config import UMLS_API_KEY

    phrases_by_entry = {e["schedule_entry_id"]: e["phrases"] for e in
                        json.loads((SNAP / CFG["v1"]["topic_phrases"]).read_text())["entries"]}
    uniq = sorted({p.lower().strip() for ps in phrases_by_entry.values() for p in ps})
    if args.limit:
        uniq = uniq[: args.limit]
    cache_path = OUT / "topic_phrase_cuis.json"
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {"phrases": {}}
    cache["umls_release"] = umls_release()
    for i, p in enumerate(uniq, 1):
        prev = cache["phrases"].get(p, {}).get("layer")
        # cached results are kept, except errors and (with --allow-llm) L1/L2-unresolved phrases,
        # which are retried through L3
        if prev and prev != "error" and not (args.allow_llm and prev in ("unresolved_L1_L2", "unresolved")):
            continue
        cache["phrases"][p] = {**resolve(p, args.allow_llm), "resolved_at": datetime.now(timezone.utc).isoformat()}
        if i % 25 == 0:
            cache_path.write_text(json.dumps(cache, indent=1, ensure_ascii=False))
            print(f"  {i}/{len(uniq)}", flush=True)
    cache_path.write_text(json.dumps(cache, indent=1, ensure_ascii=False))

    if args.relations:
        rel_path = OUT / "topic_cui_relations.json"
        rels = json.loads(rel_path.read_text()) if rel_path.exists() else {}
        todo = [c for c in sorted({v["cui"] for v in cache["phrases"].values() if v.get("cui")})
                if c not in rels or any(x["label"] == "_fetch_error" for x in rels[c])]
        for i, cui in enumerate(todo, 1):
            rels[cui] = relations(cui, UMLS_API_KEY)
            if i % 50 == 0:
                rel_path.write_text(json.dumps(rels, indent=1, ensure_ascii=False))
                print(f"  relations {i}/{len(todo)}", flush=True)
        rel_path.write_text(json.dumps(rels, indent=1, ensure_ascii=False))

    from collections import Counter
    layers = Counter(v["layer"] for p, v in cache["phrases"].items() if p in set(uniq))
    unresolved = [p for p in uniq if not cache["phrases"][p].get("cui")]
    (OUT / "topic_phrases_unresolved.txt").write_text("\n".join(unresolved) + "\n")
    print(json.dumps({"umls_release": cache["umls_release"], "phrases": len(uniq), "by_layer": layers,
                      "unresolved": len(unresolved)}, indent=2))


if __name__ == "__main__":
    main()
