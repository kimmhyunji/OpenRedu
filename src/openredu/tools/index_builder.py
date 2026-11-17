"""
Index builder for MappingMasterAgent.

Builds final_synonym_index.json from scratch — fully self-contained within src/openredu/.
No dependency on educational_material/.

Two outputs:
  1. data/guidelines/final_synonym_index.json
     — APDR guideline keywords → CUI + synonyms
     — Built by: Layer1(MeSH) → Layer2(SNOMED) → Layer3(LLM+UMLS)
     — Used by: MatchingSubagent (Path 2 synonym, Path 3 CUI)

  2. data/guidelines/mesh_mappings.json      (Layer 1 intermediate)
     data/guidelines/snomed_mappings.json    (Layer 2 intermediate)
     data/guidelines/llm_kw_mappings.json    (Layer 3 intermediate)
     — Saved separately so each layer can resume without re-running previous layers

Copied and adapted from:
  educational_material/keyword_normalization/legacy/layer1_mesh.py
  educational_material/keyword_normalization/legacy/layer2_snomed.py
  educational_material/keyword_normalization/layer3_llm.py
  educational_material/keyword_normalization/pipeline.py
"""

import csv
import json
import logging
import re
import time
from pathlib import Path
from typing import Optional, Tuple

from Bio import Entrez

from openredu.config import (
    PATHS, ENTREZ_EMAIL, ENTREZ_API_KEY, UMLS_API_KEY,
    ABBR_MAP, STOP_WORDS, TRUSTED_UMLS_SOURCES, MODELS,
)
from openredu.tools.mesh_lookup import content_tokens, expand_abbr, query_variants
from openredu.tools.umls_client import umls_search, best_cui, UMLSClient, snomed_lookup
from openredu.tools.umls_client import call_concept_llm

log = logging.getLogger(__name__)

if ENTREZ_EMAIL:
    Entrez.email = ENTREZ_EMAIL
if ENTREZ_API_KEY:
    Entrez.api_key = ENTREZ_API_KEY

# ── Intermediate output paths ─────────────────────────────────────────────────
def _out(name: str) -> Path:
    return PATHS["guidelines"] / name


# ── Keyword loading from APDR CSV ─────────────────────────────────────────────

def load_guideline_keywords(guideline_csv: Optional[Path] = None) -> list:
    """
    Load keywords from a guideline CSV.

    Accepts:
      - Standard 4-column CSV from GuidelineIngestionSubagent
        (canonical_name, category, specialty, source_type)
      - Raw APDR CSV as fallback (canonical_keyword, source_type, division)

    If guideline_csv is None, looks for pre-ingested structured_apdr.csv first,
    then falls back to raw APDR CSV.
    """
    from openredu.agents.mapping.subagents.matching import clean_keyword, build_guideline_index

    # Use build_guideline_index to resolve CSV and load topics (handles both formats)
    topics, _, _ = build_guideline_index(guideline_csv)
    keywords = list({t['keyword'] for t in topics if t.get('keyword')})
    log.info(f"Loaded {len(keywords)} unique keywords from guideline CSV")
    return keywords


# ── Layer 1: MeSH ─────────────────────────────────────────────────────────────

def run_layer1_mesh(keywords: list) -> dict:
    """
    Look up each keyword in MeSH via NCBI esearch/esummary.
    Returns {keyword: {status, mesh_preferred, all_synonyms}}.
    Saves intermediate result to mesh_mappings.json (checkpoint).
    """
    out_path = _out("mesh_mappings.json")

    # Resume from checkpoint
    results = {}
    if out_path.exists():
        results = json.loads(out_path.read_text())
        log.info(f"Layer 1: resuming from checkpoint ({len(results)} done)")

    remaining = [kw for kw in keywords if kw not in results]
    log.info(f"Layer 1 (MeSH): processing {len(remaining)} keywords")

    from openredu.tools.mesh_lookup import mesh_lookup as _mesh_lookup
    mapped = sum(1 for v in results.values() if v.get("status") == "mapped")

    for i, kw in enumerate(remaining, 1):
        result = _mesh_lookup(kw)
        if result:
            results[kw] = {
                "status": "mapped",
                "mesh_preferred": result["mesh_preferred"],
                "all_synonyms": result["all_synonyms"],
            }
            mapped += 1
        else:
            results[kw] = {"status": "miss", "mesh_preferred": None, "all_synonyms": [kw]}

        if i % 50 == 0:
            out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False))
            log.info(f"  Layer 1: [{i}/{len(remaining)}] mapped={mapped}")

    out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    log.info(f"Layer 1 done: {mapped}/{len(keywords)} mapped → {out_path}")
    return results


# ── Layer 2: SNOMED CT ────────────────────────────────────────────────────────

def run_layer2_snomed(keywords: list, layer1: dict) -> dict:
    """
    For Layer 1 misses, look up via SNOMED CT through UMLS TGT auth.
    Returns {keyword: {status, snomed_preferred, all_synonyms}}.
    """
    out_path = _out("snomed_mappings.json")

    results = {}
    if out_path.exists():
        results = json.loads(out_path.read_text())
        log.info(f"Layer 2: resuming from checkpoint ({len(results)} done)")

    # Only process Layer 1 misses
    misses = [kw for kw in keywords
              if layer1.get(kw, {}).get("status") != "mapped"
              and kw not in results]
    log.info(f"Layer 2 (SNOMED): processing {len(misses)} Layer-1 misses")

    if not misses:
        return results

    if not UMLS_API_KEY:
        log.warning("UMLS_API_KEY not set — skipping Layer 2")
        return results

    try:
        client = UMLSClient()
        mapped = sum(1 for v in results.values() if v.get("status") == "mapped")

        for i, kw in enumerate(misses, 1):
            result = snomed_lookup(client, kw)
            if result:
                results[kw] = {
                    "status": "mapped",
                    "snomed_preferred": result["snomed_preferred"],
                    "all_synonyms": result["all_synonyms"],
                }
                mapped += 1
            else:
                results[kw] = {"status": "miss", "snomed_preferred": None, "all_synonyms": [kw]}

            if i % 50 == 0:
                out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False))
                log.info(f"  Layer 2: [{i}/{len(misses)}] mapped={mapped}")

        out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False))
        log.info(f"Layer 2 done: {mapped} additional → {out_path}")
    except Exception as e:
        log.warning(f"Layer 2 failed: {e}")

    return results


# ── Layer 3: LLM + UMLS ───────────────────────────────────────────────────────

def run_layer3_llm(keywords: list, layer1: dict, layer2: dict) -> dict:
    """
    For Layer 1+2 misses, use LLM to decompose concept then UMLS for CUI.
    Returns {keyword: {status, llm_core_concepts, all_synonyms, cui, umls_preferred}}.
    """
    out_path = _out("llm_kw_mappings.json")

    results = {}
    if out_path.exists():
        results = json.loads(out_path.read_text())
        log.info(f"Layer 3: resuming from checkpoint ({len(results)} done)")

    misses = [kw for kw in keywords
              if layer1.get(kw, {}).get("status") != "mapped"
              and layer2.get(kw, {}).get("status") != "mapped"
              and kw not in results]
    log.info(f"Layer 3 (LLM+UMLS): processing {len(misses)} remaining misses")

    if not misses:
        return results

    mapped = sum(1 for v in results.values() if v.get("status") == "mapped")

    for i, kw in enumerate(misses, 1):
        parsed = call_concept_llm(kw)
        if not parsed or not parsed.get("mappable", True):
            results[kw] = {"status": "miss", "llm_core_concepts": [], "all_synonyms": [kw]}
        else:
            concepts = [c.lower().strip() for c in parsed.get("concepts", []) if c]
            cui, name = best_cui(concepts)
            if cui:
                results[kw] = {
                    "status": "mapped",
                    "llm_core_concepts": concepts,
                    "cui": cui,
                    "umls_preferred": name,
                    "all_synonyms": sorted(set([kw] + concepts)),
                }
                mapped += 1
            else:
                results[kw] = {
                    "status": "miss",
                    "llm_core_concepts": concepts,
                    "all_synonyms": sorted(set([kw] + concepts)),
                }

        if i % 100 == 0:
            out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False))
            log.info(f"  Layer 3: [{i}/{len(misses)}] mapped={mapped}")

    out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    log.info(f"Layer 3 done: {mapped} additional → {out_path}")
    return results


# ── Merge ─────────────────────────────────────────────────────────────────────

def merge_layers(keywords: list, layer1: dict, layer2: dict, layer3: dict) -> dict:
    """
    Merge Layer 1→2→3 results into final_synonym_index.json.
    Layer 2 overwrites Layer 1 misses, Layer 3 overwrites remaining misses.
    """
    final = {}

    for kw in keywords:
        if layer1.get(kw, {}).get("status") == "mapped":
            final[kw] = {
                "layer": 1,
                "source": "MeSH",
                "preferred": layer1[kw]["mesh_preferred"],
                "all_synonyms": layer1[kw]["all_synonyms"],
            }
        elif layer2.get(kw, {}).get("status") == "mapped":
            final[kw] = {
                "layer": 2,
                "source": "SNOMED CT",
                "preferred": layer2[kw]["snomed_preferred"],
                "all_synonyms": layer2[kw]["all_synonyms"],
            }
        elif layer3.get(kw, {}).get("status") == "mapped":
            final[kw] = {
                "layer": 3,
                "source": "LLM+UMLS",
                "preferred": layer3[kw].get("umls_preferred") or layer3[kw]["llm_core_concepts"][0] if layer3[kw].get("llm_core_concepts") else None,
                "all_synonyms": layer3[kw]["all_synonyms"],
                "cui": layer3[kw].get("cui"),
            }
        else:
            final[kw] = {
                "layer": None,
                "source": "none",
                "preferred": None,
                "all_synonyms": [kw],
            }

    out_path = _out("final_synonym_index.json")
    out_path.write_text(json.dumps(final, indent=2, ensure_ascii=False))

    by_layer = {1: 0, 2: 0, 3: 0, None: 0}
    for v in final.values():
        by_layer[v["layer"]] = by_layer.get(v["layer"], 0) + 1

    total_mapped = by_layer[1] + by_layer[2] + by_layer[3]
    log.info(f"── final_synonym_index.json ──────────────────────")
    log.info(f"  MeSH:     {by_layer[1]}")
    log.info(f"  SNOMED:   {by_layer[2]}")
    log.info(f"  LLM+UMLS: {by_layer[3]}")
    log.info(f"  Unmapped: {by_layer[None]}")
    log.info(f"  Total:    {total_mapped}/{len(keywords)} ({100*total_mapped//len(keywords)}%)")
    log.info(f"  Saved → {out_path}")

    return final


# ── Entry point ───────────────────────────────────────────────────────────────

def build_index(guideline_csv: Optional[Path] = None) -> dict:
    """
    Full pipeline: load guideline keywords → Layer1 → Layer2 → Layer3 → merge.
    Idempotent: resumes from per-layer checkpoints if interrupted.

    guideline_csv: path to standard 4-column CSV (from GuidelineIngestionSubagent)
                   or raw APDR CSV. If None, auto-detects structured_apdr.csv or
                   falls back to raw APDR CSV.
    """
    log.info("=== Building guideline synonym index ===")
    keywords = load_guideline_keywords(guideline_csv)

    log.info("── Layer 1: MeSH ──────────────────────────────────")
    layer1 = run_layer1_mesh(keywords)

    log.info("── Layer 2: SNOMED CT ─────────────────────────────")
    layer2 = run_layer2_snomed(keywords, layer1)

    log.info("── Layer 3: LLM + UMLS ────────────────────────────")
    layer3 = run_layer3_llm(keywords, layer1, layer2)

    log.info("── Merging layers ─────────────────────────────────")
    final = merge_layers(keywords, layer1, layer2, layer3)

    return final
