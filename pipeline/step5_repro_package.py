#!/usr/bin/env python3
"""Step 5: reproducibility package and per-case provenance manifest.

Exports (from the repository at the submitted-version tag):
  - extraction system prompts per collection category, the self-check prompt, the common
    figure-scope rule, model IDs, call parameters, retry/fallback logic description
  - inclusion/exclusion/search keyword dictionaries and diagnosis normalization maps
  - per-case provenance for the v1 corpus: extraction model, fallback tier, self-check
    (initial failure logged + final value), classification route, standardization layer,
    whether the normalized diagnosis came from an author keyword, Step 1 article-type tier
No LLM, no network.
"""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
CFG = yaml.safe_load((ROOT / "config/pipeline.yaml").read_text())
SNAP = ROOT / CFG["snapshot_dir"]
OUT = ROOT / "data/outputs/step5/repro_package"


def main() -> None:
    from openredu.config import MODELS, MODALITY_CONFIG, GAP_FILL_MODALITY_CONFIG
    import openredu.agents.curation.subagents.extraction as ex
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "prompts").mkdir(exist_ok=True)
    allcfg = {**MODALITY_CONFIG, **GAP_FILL_MODALITY_CONFIG}

    dictionaries = {}
    for m, cfg in sorted(allcfg.items()):
        sp = cfg.get("llm_system_prompt") or cfg.get("system_prompt") or ""
        if sp:
            extra = ex._COMMON_FIGURE_SCOPE_RULE if m in ex._MODALITIES_REQUIRING_FIGURE_SCOPE_RULE else ""
            (OUT / "prompts" / f"extraction_{m}.txt").write_text(sp + extra)
        dictionaries[m] = {k: cfg.get(k) for k in ("search_keywords", "diagnosis_terms", "modality_terms",
                                                     "include_keywords", "exclude_keywords",
                                                     "diagnosis_normalization") if cfg.get(k)}
    (OUT / "prompts" / "self_check.txt").write_text(ex._SELF_CHECK_SYSTEM_PROMPT)
    (OUT / "prompts" / "common_figure_scope_rule.txt").write_text(ex._COMMON_FIGURE_SCOPE_RULE)
    (OUT / "keyword_dictionaries_and_normalization_maps.json").write_text(
        json.dumps(dictionaries, indent=2, ensure_ascii=False))
    (OUT / "models_and_parameters.json").write_text(json.dumps({
        "models": MODELS,
        "call_parameters": {"provider": "AWS Bedrock invoke_model", "max_tokens": 400,
                            "temperature": "not set (provider default)", "top_p": "not set (provider default)"},
        "retry_and_fallback": [
            "Primary model (Claude Haiku 4.5) up to 3 attempts with exponential backoff on error or schema-invalid output",
            "then middle tier (Mistral Large 3) once, then escalate (Claude Sonnet 4.6) once; else extraction failure",
            "Master branch 6: invalid extraction after cascade -> forced Sonnet re-extraction; still invalid -> drop",
            "Master branch 8: self-check (Haiku, diagnosis vs first 500 caption chars) explicit mismatch -> one forced "
            "Sonnet re-extraction; the case is accepted regardless of the second self-check result",
        ],
        "code_refs": ["src/openredu/core/llm.py llm_with_escalation", "src/openredu/agents/curation/master.py",
                      "src/openredu/agents/curation/subagents/extraction.py"],
        "not_recorded_per_case": ["number of attempts", "token usage", "latency"],
    }, indent=2))

    # ── per-case provenance ──
    tiers = {}
    tl = ROOT / "data/outputs/step1/case_article_labels.jsonl"
    if tl.exists():
        tiers = {json.loads(l)["case_id"]: json.loads(l)["tier"] for l in tl.open()}
    rows, stats = [], Counter()
    for line in (SNAP / CFG["v1"]["corpus"]).open():
        c = json.loads(line)
        log = c.get("agent_log") or []
        model = (c.get("models_used") or {}).get("extraction", "")
        tier = ("primary_haiku" if "haiku" in model else "middle_mistral" if "mistral" in model
                else "escalate_sonnet" if "sonnet" in model else "unknown")
        sc_fail_logged = any("self-check failed" in (x.get("reason") or "") for x in log)
        invalid_logged = any("extraction output invalid" in (x.get("reason") or "") for x in log)
        kw = [k.lower() for k in (c.get("author_keywords") or []) if k]
        norm_from_kw = bool(c.get("diagnosis_normalized")) and c["diagnosis_normalized"].lower() in kw
        rows.append({
            "case_id": c["case_id"], "pmcid": c["pmcid"], "collection_category": c.get("modality"),
            "corpus_source": c.get("corpus_source"), "classification_route": c.get("classification_route"),
            "extraction_model": model, "extraction_tier": tier,
            "escalated_after_invalid_output": invalid_logged, "self_check_initial_failure_logged": sc_fail_logged,
            "self_check_final": c.get("extraction_self_check_passed"),
            "standardization_layer": (c.get("models_used") or {}).get("standardization", ""),
            "normalized_diagnosis_from_author_keyword": norm_from_kw,
            "article_type_tier_step1": tiers.get(c["case_id"], ""),
            "pipeline_version": "v1 (tag v1-submitted)",
            "verifier_model": "", "verifier_prompt_version": "", "verifier_classification": "",
            "verifier_finding": "", "verifier_diagnosis_article": "", "verifier_diagnosis_in_figure": "",
        })
        stats[tier] += 1
        stats["self_check_initial_failure_logged"] += sc_fail_logged
        stats["escalated_after_invalid_output"] += invalid_logged
        stats["normalized_diagnosis_from_author_keyword"] += norm_from_kw
        stats[f"self_check_final={c.get('extraction_self_check_passed')}"] += 1
    with (OUT / "case_provenance_v1.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    stats["cases"] = len(rows)
    (OUT / "provenance_summary.json").write_text(json.dumps(dict(stats), indent=2))
    print(json.dumps(dict(stats), indent=2))


if __name__ == "__main__":
    main()
