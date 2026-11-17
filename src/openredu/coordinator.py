"""
Coordinator: thin orchestration harness. NOT an agent.

Responsibilities:
  - Sequences CurationMasterAgent → MappingMasterAgent
  - Handles idempotency (skip already-processed case_ids)
  - Writes to queue JSONL files (processed / failed / rejected / unmapped)
  - Writes run manifests

process_case_from_cache(): single-case entry point for cache mode (dev shortcut)
run_pipeline(): batch entry point for all modalities
"""
import hashlib
import json
import logging
import time
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from openredu.config import (
    PATHS, MODELS, TARGET_MODALITIES, MODALITY_CONFIG,
    GAP_FILL_MODALITIES, GAP_FILL_MODALITY_CONFIG, NORMAL_STUDY_EXCLUSIONS,
)
from openredu.core.state import CaseState
from openredu.agents.curation.master import CurationMasterAgent
from openredu.agents.mapping.master import MappingMasterAgent
from openredu.agents.mapping.subagents.matching import build_apdr_index

log = logging.getLogger(__name__)

# Mapping index: built once at first use
_mapping_agent: MappingMasterAgent = None


def _get_mapping_agent() -> MappingMasterAgent:
    """Build MappingMasterAgent with APDR index (lazy, built once per process)."""
    global _mapping_agent
    if _mapping_agent is None:
        log.info("Building APDR matching index...")
        apdr_topics, kw_to_synonyms, kw_to_cui = build_apdr_index(PATHS["apdr_keywords"])
        _mapping_agent = MappingMasterAgent(
            apdr_topics=apdr_topics,
            kw_to_synonyms=kw_to_synonyms,
            kw_to_cui=kw_to_cui,
        )
        log.info(f"APDR index ready: {len(apdr_topics)} topics")
    return _mapping_agent


# ── Persistence helpers ───────────────────────────────────────────────────────

# Checkpoint files by stage:
#   checkpoint/{modality}/retrieved.jsonl   — NXML parsed (scratch only)
#   checkpoint/{modality}/classified.jsonl  — passed classification
#   checkpoint/{modality}/extracted.jsonl   — LLM extraction done
#   cases_{modality}.jsonl                  — final mapped/unmapped results
#   failed/rejected_{modality}.jsonl        — rejected
#   failed/failed_{modality}.jsonl          — errors


def _checkpoint_path(modality: str, stage: str) -> Path:
    p = PATHS["data"] / "checkpoint" / modality.lower()
    p.mkdir(parents=True, exist_ok=True)
    return p / f"{stage}.jsonl"


def _load_checkpoint(modality: str, stage: str) -> dict:
    """Load checkpoint as {case_id: CaseState dict}."""
    path = _checkpoint_path(modality, stage)
    if not path.exists():
        return {}
    result = {}
    for line in path.read_text().splitlines():
        if line.strip():
            try:
                d = json.loads(line)
                result[d["case_id"]] = d
            except Exception:
                pass
    return result


def _save_checkpoint(state: CaseState, modality: str, stage: str) -> None:
    """Append state to stage checkpoint file."""
    path = _checkpoint_path(modality, stage)
    with open(path, "a") as f:
        f.write(state.to_jsonl_line() + "\n")


def _load_already_done(modality: str) -> set:
    """Return terminal figure IDs, never article IDs or unfinished checkpoints.

    Failed cases remain retryable. A single completed figure does not establish
    that every figure of its article has been discovered or processed.
    """
    done = set()
    for path in (PATHS["processed"] / f"cases_{modality.lower()}.jsonl",
                 PATHS["failed"] / f"rejected_{modality.lower()}.jsonl"):
        if not path.exists():
            continue
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            raw = json.loads(line)
            if raw.get("status") in ("mapped", "unmapped", "extracted", "rejected"):
                if raw.get("case_id"):
                    done.add(raw["case_id"])
    return done


def _persist_state(state: CaseState, modality: str) -> None:
    """Append CaseState to the appropriate final queue JSONL."""
    if state.status in ("mapped", "unmapped"):
        out = PATHS["processed"] / f"cases_{modality.lower()}.jsonl"
    elif state.status == "extracted":
        # cases extracted but not mapped are also kept in the final results
        out = PATHS["processed"] / f"cases_{modality.lower()}.jsonl"
    elif state.status == "failed":
        out = PATHS["failed"] / f"failed_{modality.lower()}.jsonl"
    elif state.status == "rejected":
        out = PATHS["failed"] / f"rejected_{modality.lower()}.jsonl"
    else:
        out = PATHS["processed"] / f"cases_{modality.lower()}.jsonl"

    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "a") as f:
        f.write(state.to_jsonl_line() + "\n")


# ── Single-case entry points ──────────────────────────────────────────────────

def remap_from_checkpoint(modality: str, dry_run: bool = False) -> dict:
    """
    Re-run MappingMasterAgent only on already-extracted cases (from checkpoint).
    Uses the current final_synonym_index.json (Path 2 synonym + Path 3 CUI active).

    Does NOT re-run Curation — reads extracted.jsonl checkpoint directly.
    Idempotent: skips case_ids already in processed/cases_{modality}.jsonl.
    """
    checkpoint = _checkpoint_path(modality, "extracted")
    if not checkpoint.exists():
        log.warning(f"[{modality}] No extracted checkpoint found: {checkpoint}")
        return {}

    # For remap: only skip case_ids already in FINAL output (not checkpoints)
    done_in_output = set()
    for fname in [f"cases_{modality.lower()}.jsonl"]:
        p = PATHS["processed"] / fname
        if p.exists():
            for line in p.read_text().splitlines():
                if line.strip():
                    try: done_in_output.add(json.loads(line)["case_id"])
                    except: pass

    mapping_agent = _get_mapping_agent()
    stats = Counter()

    cases = []
    for line in checkpoint.read_text().splitlines():
        if not line.strip(): continue
        try:
            d = json.loads(line)
            if d.get("case_id") not in done_in_output:
                cases.append(d)
        except: pass

    log.info(f"[{modality}] Re-mapping {len(cases)} cases from checkpoint "
             f"(skipping {len(done_in_output)} already in output)")

    # Load CUIs from backup if available (avoids redundant UMLS API calls)
    backup_cuis: dict = {}
    backup_path = PATHS["data"].parent / "processed_backup" / f"cases_{modality.lower()}.jsonl"
    if not backup_path.exists():
        backup_path = Path("data/processed_backup") / f"cases_{modality.lower()}.jsonl"
    if backup_path.exists():
        for line in backup_path.read_text().splitlines():
            if not line.strip(): continue
            try:
                d2 = json.loads(line)
                cid = d2.get("case_id", "")
                cuis = d2.get("diagnosis_cuis", [])
                pref = d2.get("diagnosis_umls_preferred", "")
                if cid and cuis:
                    backup_cuis[cid] = {"cuis": cuis, "preferred": pref}
            except: pass
        if backup_cuis:
            log.info(f"[{modality}] Loaded {len(backup_cuis)} CUIs from backup")

    for d in cases:
        state = CaseState.from_dict(d)
        state.status = "extracted"

        # Reuse CUIs from backup if available (skip UMLS API call)
        if state.case_id in backup_cuis:
            state.diagnosis_cuis = backup_cuis[state.case_id]["cuis"]
            state.diagnosis_umls_preferred = backup_cuis[state.case_id]["preferred"]
            state.models_used["standardization"] = "backup"

        # Reset only matching fields for fresh run with new index
        state.curriculum_topics = []
        state.mapping_paths = []
        state.dedup_group_id = None

        stats["extracted"] += 1
        try:
            state = mapping_agent.run(state)
        except Exception as e:
            log.error(f"Mapping error for {state.case_id}: {e}")
            state.status = "failed"

        if state.status == "mapped":
            stats["mapped"] += 1
        elif state.status == "unmapped":
            stats["unmapped"] += 1
        else:
            stats["failed"] += 1

        if not dry_run:
            _persist_state(state, modality)

        if stats["extracted"] % 500 == 0:
            log.info(f"[{modality}] progress: {stats['extracted']} / {len(cases)}")

    if not dry_run:
        write_manifest(modality, {"cache_mode": "remap_from_checkpoint"}, stats)

    log.info(f"[{modality}] Re-mapping done: {dict(stats)}")
    return dict(stats)


def process_case_from_cache(raw: dict, modality: str) -> CaseState:
    """
    Process one phase2 JSONL record through CurationMasterAgent → MappingMasterAgent.
    Used in --from-cache mode (dev shortcut).
    Does NOT write to output files — caller decides.
    """
    curation_agent = CurationMasterAgent(pmcid_counts=Counter({raw.get("pmcid", ""): 1}))

    state = curation_agent.subagents["retrieval"].run_from_cache(raw)
    state.modality = modality
    state = curation_agent.run(state)

    if state.status in ("rejected", "failed"):
        return state

    mapping_agent = _get_mapping_agent()
    state = mapping_agent.run(state)
    return state


# ── Batch pipeline ────────────────────────────────────────────────────────────

def run_pipeline(
    modality: str,
    limit: Optional[int] = None,
    from_cache: bool = True,
    dry_run: bool = False,
    year_start: Optional[int] = None,
    year_end: Optional[int] = None,
) -> dict:
    """
    Run full curation pipeline for one modality.

    Returns stats dict:
      {retrieved, rejected, failed, extracted, mapped, unmapped}

    from_cache=True: reads phase2 JSONL (dev shortcut)
    from_cache=False: runs full PMC scratch pipeline
    dry_run=True: processes but does not write output files
    """
    # ── Stage-level funnel counters (flow counts) ────────────────────────────
    # pmc_query_hits      : articles returned by PMC esearch
    # nxml_fetched        : articles whose NXML was fetched
    # license_passed      : articles with an allowed (CC) license
    # figures_with_caption: figures with a label and caption
    # rule_include        : figures with a modality keyword (ClassificationSubagent)
    # rule_exclude        : figures rejected by an exclusion keyword
    # uncertain_rejected  : figures rejected because no keyword matched
    # extraction_success  : cases with successful LLM extraction
    # extraction_failed   : cases with failed LLM extraction
    # self_check_escalated: cases re-extracted after a failed self-check
    # mapped              : cases matched to a curriculum topic
    # unmapped            : cases not matched to a curriculum topic
    stats = Counter()
    already_done = _load_already_done(modality)
    if already_done:
        log.info(f"[{modality}] Skipping {len(already_done)} already-processed cases")

    if from_cache:
        records = _load_phase2_cache(modality, limit, already_done)
        # Count figures per PMCID for multi-figure handling (cache mode)
        pmcid_counts = Counter(r.get("pmcid", "") for r in records)
        stats["pmc_query_hits"] = 0      # not applicable in cache mode
        stats["nxml_fetched"] = 0
        stats["license_passed"] = 0
    else:
        records = _collect_scratch(modality, limit, already_done, year_start, year_end, stats)
        pmcid_counts = Counter()  # scratch: counted per-PMCID at retrieval time

    mapping_agent = _get_mapping_agent()

    if from_cache:
        curation_agent = CurationMasterAgent(pmcid_counts=pmcid_counts)
        case_iter = _iter_cache(records, modality, curation_agent)
    else:
        pmcids = [r["pmcid"] for r in records]
        from openredu.agents.curation.subagents.retrieval import RetrievalSubagent
        retrieval = RetrievalSubagent()

        # Restore unfinished figures and revisit articles to discover remaining figures.
        retrieved_checkpoint = _load_checkpoint(modality, "retrieved")
        if retrieved_checkpoint:
            log.info(f"[{modality}] Resuming {len(retrieved_checkpoint)} states "
                     f"from retrieved checkpoint")
        case_iter = _iter_scratch_with_resume(
            pmcids, modality, retrieval, stats, retrieved_checkpoint
        )

    for state in case_iter:
        # ── Step 1: Retrieved ─────────────────────────────────────────────────
        stats["figures_with_caption"] += 1
        if not dry_run and not from_cache and state.status != "extracted":
            # scratch mode: save the parsed NXML to the retrieved checkpoint
            _save_checkpoint(state, modality, "retrieved")

        # ── Step 2-4: Curation (Classification + Extraction) ─────────────────
        try:
            curation_agent = CurationMasterAgent(pmcid_counts=Counter({state.pmcid: 1}))
            if state.status != "extracted":
                state = curation_agent.run(state)
        except Exception as e:
            log.error(f"Curation error for {state.case_id}: {e}")
            stats["extraction_failed"] += 1
            continue

        # count classification results
        route = state.classification_route
        if route == "rule_include":
            stats["rule_include"] += 1
        elif route == "rule_exclude":
            stats["rule_exclude"] += 1
        elif route == "uncertain_pending":
            stats["uncertain_rejected"] += 1

        if state.status == "rejected":
            if not dry_run:
                _persist_state(state, modality)
            continue

        if state.status == "failed":
            stats["extraction_failed"] += 1
            if not dry_run:
                _persist_state(state, modality)
            continue

        # ── Step 5: Extraction checkpoint ───────────────────────────────
        if state.extraction_self_check_passed is False:
            stats["self_check_escalated"] += 1
        stats["extraction_success"] += 1

        if not dry_run:
            # saved right after extraction so a run interrupted before mapping can resume
            _save_checkpoint(state, modality, "extracted")

        # ── Step 6: Mapping ───────────────────────────────────────────────────
        try:
            state = mapping_agent.run(state)
        except Exception as e:
            log.error(f"Mapping error for {state.case_id}: {e}")
            state.status = "failed"

        if state.status == "mapped":
            stats["mapped"] += 1
        elif state.status == "unmapped":
            stats["unmapped"] += 1
        else:
            stats["extraction_failed"] += 1

        if not dry_run:
            # save final results
            _persist_state(state, modality)

        log.info(f"[{modality}] {state.case_id} → {state.status} "
                 f"(diagnosis={state.diagnosis_normalized or state.diagnosis})")
        time.sleep(0.1)  # avoid throttling between cases

    if not dry_run:
        write_manifest(modality, {
            "cache_mode": from_cache,
            "limit": limit,
            "year_start": year_start,
            "year_end": year_end,
            "run_date": datetime.now(timezone.utc).isoformat(),
        }, stats)

    # funnel summary log
    log.info(f"[{modality}] ── Funnel summary ──────────────────────────")
    if stats.get("pmc_query_hits"):
        log.info(f"[{modality}]  PMC query hits:       {stats['pmc_query_hits']}")
        log.info(f"[{modality}]  NXML fetched:         {stats['nxml_fetched']}")
        log.info(f"[{modality}]  License passed:       {stats['license_passed']}")
    log.info(f"[{modality}]  Figures w/ caption:   {stats['figures_with_caption']}")
    log.info(f"[{modality}]  → rule_include:        {stats['rule_include']}")
    log.info(f"[{modality}]  → rule_exclude:        {stats['rule_exclude']}")
    log.info(f"[{modality}]  → uncertain_rejected:  {stats['uncertain_rejected']}")
    log.info(f"[{modality}]  Extraction success:    {stats['extraction_success']}")
    log.info(f"[{modality}]  Extraction failed:     {stats['extraction_failed']}")
    log.info(f"[{modality}]  Self-check escalated:  {stats['self_check_escalated']}")
    log.info(f"[{modality}]  Mapped to APDR:        {stats['mapped']}")
    log.info(f"[{modality}]  Unmapped:              {stats['unmapped']}")
    log.info(f"[{modality}] ────────────────────────────────────────────")
    return dict(stats)


def _iter_cache(records: list, modality: str, curation_agent) -> "Iterator[CaseState]":
    """Yield CaseState from pre-parsed phase2 cache records."""
    for raw in records:
        state = curation_agent.subagents["retrieval"].run_from_cache(raw)
        state.modality = modality
        yield state


def _iter_scratch_with_resume(
    pmcids: list,
    modality: str,
    retrieval,
    stats: Optional[Counter] = None,
    retrieved_checkpoint: dict = None,
) -> "Iterator[CaseState]":
    """Restore unfinished figures in the requested articles, then find siblings.

    Re-read every requested article: a checkpoint is not an article-completion
    marker. Deduplicate by figure ID, and prefer extracted states so a mapping
    retry does not repeat paid extraction calls.
    """
    from openredu.tools.image_downloader import case_has_valid_images

    requested = set(pmcids)
    done = _load_already_done(modality)
    checkpoint = dict(retrieved_checkpoint or {})
    checkpoint.update(_load_checkpoint(modality, "extracted"))
    yielded = set(done)
    for case_id, raw in checkpoint.items():
        if raw.get("pmcid") not in requested or case_id in yielded:
            continue
        # Let retrieval retry missing/corrupt images instead of restoring them.
        if not case_has_valid_images(raw):
            continue
        state = CaseState.from_dict(raw)
        if state.status != "extracted":
            state.status = "retrieved"
        yielded.add(case_id)
        yield state

    for state in _iter_scratch(list(dict.fromkeys(pmcids)), modality, retrieval, stats):
        if state.case_id not in yielded:
            yielded.add(state.case_id)
            yield state


def _iter_scratch(
    pmcids: list,
    modality: str,
    retrieval,
    stats: Optional[Counter] = None,
) -> "Iterator[CaseState]":
    """
    Fetch NXML for each PMCID and yield one CaseState per figure.
    Also updates funnel stats: nxml_fetched, license_passed.
    """
    from openredu.tools.pmc_api import fetch_article_nxml, extract_license
    from openredu.config import ALLOWED_LICENSES

    for pmcid in pmcids:
        try:
            root = fetch_article_nxml(pmcid)
            if root is None:
                continue
            if stats is not None:
                stats["nxml_fetched"] += 1

            lic = extract_license(root)
            if lic not in ALLOWED_LICENSES:
                continue
            if stats is not None:
                stats["license_passed"] += 1

            for state in retrieval.iter_from_scratch([pmcid], modality):
                yield state
        except Exception as e:
            log.warning(f"Scratch retrieval error for {pmcid}: {e}")
            continue


def _load_phase2_cache(modality: str, limit: Optional[int], already_done: set) -> list:
    """Load records from existing phase2 JSONL, skipping already-done cases."""
    path = PATHS["cache_phase2_dir"] / f"phase2_cases_{modality.lower()}.jsonl"
    if not path.exists():
        log.warning(f"Phase2 cache not found: {path}")
        return []

    records = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
            case_id = raw.get("case_id", "")
            if case_id and case_id in already_done:
                continue
            records.append(raw)
            if limit and len(records) >= limit:
                break
        except Exception:
            pass
    log.info(f"[{modality}] Loaded {len(records)} cache records to process")
    return records


def run_pipeline_for_pmcids(
    pmcids: list,
    modality: str,
    dry_run: bool = False,
    bypass_modality_exclude: bool = False,
) -> dict:
    """
    Run full curation+mapping pipeline for a specific list of PMCIDs.

    Used by topic_per_query.py (Phase 3) to process only the PMCIDs
    returned by a targeted per-topic PMC query, rather than re-running
    the full modality pipeline. Terminal figures are skipped; articles are
    revisited so interrupted retrieval cannot hide their remaining figures.

    Args:
        pmcids:   list of PMC IDs to process (e.g. ["PMC1234567", ...])
        modality: modality key for classification + extraction config
        dry_run:  if True, process but do not write output files

    Returns stats dict matching run_pipeline format.
    """
    from openredu.agents.curation.subagents.retrieval import RetrievalSubagent

    stats = Counter()
    already_done = _load_already_done(modality)

    requested_pmcids = list(dict.fromkeys(pmcids))
    if not requested_pmcids:
        return {}
    stats["pmc_query_hits"] = len(requested_pmcids)
    log.info(f"[{modality}] Revisiting {len(requested_pmcids)} articles; "
             f"skipping {len(already_done)} terminal figure IDs")
    mapping_agent = _get_mapping_agent()
    retrieval = RetrievalSubagent()
    case_iter = _iter_scratch_with_resume(
        requested_pmcids, modality, retrieval, stats,
        _load_checkpoint(modality, "retrieved"),
    )

    for state in case_iter:
        stats["figures_with_caption"] += 1
        if not dry_run and state.status != "extracted":
            _save_checkpoint(state, modality, "retrieved")

        try:
            curation_agent = CurationMasterAgent(
                pmcid_counts=Counter({state.pmcid: 1}),
                bypass_modality_exclude=bypass_modality_exclude,
            )
            if state.status != "extracted":
                state = curation_agent.run(state)
        except Exception as e:
            log.error(f"Curation error for {state.case_id}: {e}")
            stats["extraction_failed"] += 1
            continue

        route = state.classification_route
        if route == "rule_include":
            stats["rule_include"] += 1
        elif route == "rule_exclude":
            stats["rule_exclude"] += 1
        elif route == "uncertain_pending":
            stats["uncertain_rejected"] += 1

        if state.status == "rejected":
            if not dry_run:
                _persist_state(state, modality)
            continue

        if state.status == "failed":
            stats["extraction_failed"] += 1
            if not dry_run:
                _persist_state(state, modality)
            continue

        if state.status in ("extracted",):
            stats["extraction_success"] += 1
            if state.models_used.get("self_check_escalated"):
                stats["self_check_escalated"] += 1
            if not dry_run:
                _save_checkpoint(state, modality, "extracted")

            try:
                state = mapping_agent.run(state)
            except Exception as e:
                log.error(f"Mapping error for {state.case_id}: {e}")
                state.status = "failed"

            if state.status == "mapped":
                stats["mapped"] += 1
                log.info(f"[{modality}] {state.case_id} → mapped (diagnosis={state.diagnosis})")
            elif state.status == "unmapped":
                stats["unmapped"] += 1
                log.info(f"[{modality}] {state.case_id} → unmapped (diagnosis={state.diagnosis})")
            else:
                stats["extraction_failed"] += 1

            if not dry_run:
                _persist_state(state, modality)

    if not dry_run:
        write_manifest(modality, {"cache_mode": "topic_per_query"}, stats)

    log.info(f"[{modality}] topic_per_query done: {dict(stats)}")
    return dict(stats)


def _collect_scratch(
    modality: str,
    limit: Optional[int],
    already_done: set,
    year_start: Optional[int],
    year_end: Optional[int],
    stats: Optional[Counter] = None,
) -> list:
    """Collect PMCIDs from PMC API and return list of {pmcid, modality} dicts."""
    from openredu.tools.pmc_api import build_query, search_pmc

    query = build_query(modality, year_start=year_start, year_end=year_end)
    log.info(f"[{modality}] PMC query: {query[:120]}...")
    pmcids = search_pmc(query)

    # Funnel Step 0: record PMC query hits
    if stats is not None:
        stats["pmc_query_hits"] = len(pmcids)
        log.info(f"[{modality}] pmc_query_hits={len(pmcids)}")

    if limit:
        pmcids = pmcids[:limit]
    log.info(f"[{modality}] {len(pmcids)} PMCIDs to process")

    return [{"pmcid": p, "modality": modality} for p in pmcids
            if p not in already_done]


# ── Manifest ──────────────────────────────────────────────────────────────────

def _get_modality_config(modality: str) -> dict:
    """Return config for any modality — original or gap-fill."""
    return MODALITY_CONFIG.get(modality) or GAP_FILL_MODALITY_CONFIG.get(modality, {})


def write_manifest(modality: str, run_config: dict, stats: Counter) -> Path:
    """Write a run-level JSON manifest for reproducibility."""
    cfg_str = json.dumps(_get_modality_config(modality), sort_keys=True)
    manifest = {
        "run_id":         uuid.uuid4().hex[:8],
        "timestamp":      datetime.now(timezone.utc).isoformat(),
        "modality":       modality,
        "cache_mode":     run_config.get("cache_mode", True),
        "config_hash":    hashlib.md5(cfg_str.encode()).hexdigest(),
        "model_versions": MODELS,
        "apdr_csv_version": _file_hash(PATHS["apdr_keywords"]),
        # ── Stage-level funnel ──────────────────────────────
        # scratch mode: pmc_query_hits → nxml_fetched → license_passed
        #               → figures_with_caption → rule_include / rule_exclude
        #               / uncertain_rejected → extraction_success
        #               / extraction_failed → mapped / unmapped
        # cache mode:  pmc_query_hits=0 (N/A), counts start at figures_with_caption
        "funnel": {
            "pmc_query_hits":       stats.get("pmc_query_hits", 0),
            "nxml_fetched":         stats.get("nxml_fetched", 0),
            "license_passed":       stats.get("license_passed", 0),
            "figures_with_caption": stats.get("figures_with_caption", 0),
            "rule_include":         stats.get("rule_include", 0),
            "rule_exclude":         stats.get("rule_exclude", 0),
            "uncertain_rejected":   stats.get("uncertain_rejected", 0),
            "extraction_success":   stats.get("extraction_success", 0),
            "extraction_failed":    stats.get("extraction_failed", 0),
            "self_check_escalated": stats.get("self_check_escalated", 0),
            "mapped":               stats.get("mapped", 0),
            "unmapped":             stats.get("unmapped", 0),
        },
        # summary kept for compatibility
        "counts": {
            "figures_with_caption": stats.get("figures_with_caption", 0),
            "rule_include":         stats.get("rule_include", 0),
            "extraction_success":   stats.get("extraction_success", 0),
            "extraction_failed":    stats.get("extraction_failed", 0),
            "mapped":               stats.get("mapped", 0),
            "unmapped":             stats.get("unmapped", 0),
        },
        "query_strings":  run_config.get("queries", {}),
        "harvest_date":   run_config.get("run_date", ""),
        "year_start":     run_config.get("year_start"),
        "year_end":       run_config.get("year_end"),
    }
    out = PATHS["manifests"] / f"manifest_{modality.lower()}_{manifest['run_id']}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, indent=2))
    log.info(f"Manifest written: {out}")
    return out


def _file_hash(path: Path) -> str:
    """MD5 hash of a file (for manifest provenance)."""
    if not path.exists():
        return "missing"
    return hashlib.md5(path.read_bytes()).hexdigest()[:8]


# ── Coverage gap analysis & gap-fill pipeline ─────────────────────────────────
# mapping_coverage_revision Phase 2: curriculum-driven supplemental retrieval.
# After initial 10-modality corpus construction, MappingMasterAgent coverage
# analysis identifies APDR topics with zero mapped cases. These trigger a
# targeted retrieval pass through the identical curation pipeline — only the
# PMC search keywords differ.

def _load_coverage_cases(corpus_dirs: list[str]) -> tuple[list[dict], dict]:
    """Load and de-duplicate cases for a coverage analysis.

    Directory order defines precedence when the same case_id occurs more than
    once.  This keeps the manuscript corpus in ``final`` authoritative when a
    later supplemental directory contains another copy of the same case.
    """
    cases_by_id: dict[str, dict] = {}
    rows_by_dir: dict[str, int] = {}
    duplicate_rows = 0
    invalid_rows = 0

    for directory_name in corpus_dirs:
        directory = PATHS["data"] / directory_name
        rows_by_dir[directory_name] = 0
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.jsonl")):
            for line in path.read_text().splitlines():
                if not line.strip():
                    continue
                rows_by_dir[directory_name] += 1
                try:
                    case = json.loads(line)
                except json.JSONDecodeError:
                    invalid_rows += 1
                    continue
                case_id = case.get("case_id", "")
                if not case_id:
                    invalid_rows += 1
                    continue
                if case_id in cases_by_id:
                    duplicate_rows += 1
                    continue
                cases_by_id[case_id] = case

    excluded_path = PATHS["data"] / "excluded_cases.json"
    excluded_ids: set = set()
    if excluded_path.exists():
        excluded_ids = set(json.loads(excluded_path.read_text()))

    active_cases = [
        case for case_id, case in cases_by_id.items()
        if case_id not in excluded_ids
    ]
    stats = {
        "corpus_dirs": list(corpus_dirs),
        "rows_by_dir": rows_by_dir,
        "total_rows": sum(rows_by_dir.values()),
        "unique_cases": len(cases_by_id),
        "duplicate_rows": duplicate_rows,
        "invalid_rows": invalid_rows,
        "excluded_cases": len(cases_by_id) - len(active_cases),
        "active_cases": len(active_cases),
    }
    return active_cases, stats


def compute_coverage_gaps(corpus_dirs: Optional[list[str]] = None) -> dict:
    """
    Analyse APDR must_see_diagnosis coverage across an explicit corpus scope.

    By default, use the reviewed pipeline outputs in ``final`` and
    ``processed``.  Pass ``["final", "processed", "gap_fill_bypass"]`` to
    include the provisional bypass candidate set.

    Returns a dict with:
      covered_topics:   list of keyword_ids with >= 1 mapped case
      uncovered_topics: list of {keyword_id, raw_keyword, specialty, keyword}
      excluded_normal:  topics excluded as normal-study (no case reports exist)
      coverage_pct:     float 0–1 (of collectible topics)
    """
    from collections import defaultdict
    from openredu.agents.mapping.subagents.matching import build_guideline_index

    topics, _, _ = build_guideline_index(
        PATHS["apdr_keywords"],
        PATHS["final_synonym_index"],
    )

    selected_dirs = corpus_dirs or ["final", "processed"]
    cases, corpus_stats = _load_coverage_cases(selected_dirs)

    topic_counts: dict = defaultdict(int)
    for c in cases:
        for t in (c.get("curriculum_topics") or []):
            topic_counts[t] += 1

    # Separate normal-study exclusions
    normal_raw = {kw.lower() for kw in NORMAL_STUDY_EXCLUSIONS}
    excluded_normal = [t for t in topics if t["raw_keyword"].lower() in normal_raw]
    excluded_normal_ids = {t["keyword_id"] for t in excluded_normal}

    collectible = [t for t in topics if t["keyword_id"] not in excluded_normal_ids]
    covered = [t for t in collectible if topic_counts[t["keyword_id"]] > 0]
    uncovered = [t for t in collectible if topic_counts[t["keyword_id"]] == 0]

    coverage_pct = len(covered) / len(collectible) if collectible else 0.0

    log.info(
        f"Coverage: {len(covered)}/{len(collectible)} collectible topics "
        f"({coverage_pct:.1%}); {len(uncovered)} gaps; "
        f"{len(excluded_normal)} normal-study exclusions"
    )

    return {
        "total_topics":    len(topics),
        "collectible":     len(collectible),
        "covered_topics":  [t["keyword_id"] for t in covered],
        "uncovered_topics": uncovered,
        "excluded_normal": excluded_normal,
        "coverage_pct":    coverage_pct,
        "topic_counts":    dict(topic_counts),
        "corpus_stats":    corpus_stats,
    }


def run_gap_fill_pipeline(
    modalities: Optional[list] = None,
    year_start: Optional[int] = 2020,
    year_end:   Optional[int] = 2026,
    limit: Optional[int] = None,
    dry_run: bool = False,
) -> dict:
    """
    Phase 2 curriculum-driven retrieval pass.

    For each gap-fill modality, runs the identical curation + mapping pipeline
    as run_pipeline() — only the PMC search keywords differ (GAP_FILL_MODALITY_CONFIG).

    This function is the implementation of the feedback loop described in Methods:
      MappingMasterAgent coverage analysis → uncovered topics →
      RetrievalSubagent targeted query → same ClassificationSubagent +
      ExtractionSubagent → same MappingMasterAgent → merged corpus.

    Args:
        modalities: subset of GAP_FILL_MODALITIES to run (default: all 6)
        year_start / year_end: PMC date range (default 2020–2026 matching Phase 1)
        limit: cap per modality (dev/smoke-test)
        dry_run: log what would run, skip API calls
    """
    targets = modalities or GAP_FILL_MODALITIES
    unknown = [m for m in targets if m not in GAP_FILL_MODALITY_CONFIG]
    if unknown:
        raise ValueError(f"Unknown gap-fill modalities: {unknown}. "
                         f"Available: {GAP_FILL_MODALITIES}")

    # Log current coverage before starting
    gaps = compute_coverage_gaps()
    log.info(
        f"Gap-fill starting. Pre-run coverage: "
        f"{gaps['coverage_pct']:.1%} ({len(gaps['covered_topics'])}/{gaps['collectible']} topics). "
        f"Uncovered: {len(gaps['uncovered_topics'])} topics."
    )

    all_stats: dict = {}

    for modality in targets:
        log.info(f"=== Gap-fill [{modality}] ===")

        if dry_run:
            log.info(f"[{modality}] DRY RUN — skipping pipeline")
            all_stats[modality] = {"dry_run": True}
            continue

        stats = run_pipeline(
            modality=modality,
            year_start=year_start,
            year_end=year_end,
            limit=limit,
            from_cache=False,
        )
        all_stats[modality] = stats
        log.info(f"[{modality}] done: {stats}")

    # Log coverage after all gap-fill modalities
    gaps_after = compute_coverage_gaps()
    all_stats["_coverage_before"] = gaps["coverage_pct"]
    all_stats["_coverage_after"]  = gaps_after["coverage_pct"]
    all_stats["_uncovered_before"] = len(gaps["uncovered_topics"])
    all_stats["_uncovered_after"]  = len(gaps_after["uncovered_topics"])
    log.info(
        f"Gap-fill complete. Coverage: "
        f"{gaps['coverage_pct']:.1%} → {gaps_after['coverage_pct']:.1%}. "
        f"Uncovered: {gaps['uncovered_topics'].__len__()} → "
        f"{gaps_after['uncovered_topics'].__len__()}"
    )

    return all_stats
