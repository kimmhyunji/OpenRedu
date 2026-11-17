"""
RetrievalSubagent: deterministic PMC search + NXML parse + image download.

Two modes:
  cache mode  — loads from existing phase2 JSONL (dev shortcut, no PMC API call)
  scratch mode — full Phase 1 → Phase 2 flow via PMC Entrez + NXML + CDN download

is_llm = False: no LLM involved.
"""
import json
import logging
from pathlib import Path
from typing import Optional
from xml.etree import ElementTree as ET

from openredu.core.base import Subagent
from openredu.core.state import CaseState
from openredu.config import MODALITY_CONFIG, ALLOWED_LICENSES, PATHS
from openredu.tools.pmc_api import (
    fetch_article_nxml, extract_license, extract_citation,
    extract_abstract, extract_keywords, extract_case_text,
    extract_results_sentences,
)
from openredu.tools.image_downloader import get_cdn_map, download_image

log = logging.getLogger(__name__)


class RetrievalSubagent(Subagent):
    """
    Populates all provenance and source-text fields of CaseState.
    In cache mode: reads from existing phase2 JSONL — no PMC API calls.
    In scratch mode: full PMC NXML fetch + image download.
    """
    name = "RetrievalSubagent"
    is_llm = False

    def run(self, state: CaseState) -> CaseState:
        """Entry point used by CurationMasterAgent (scratch mode)."""
        return self._run_scratch(state)

    def run_from_cache(self, raw: dict) -> CaseState:
        """Load a CaseState from a phase2 JSONL record (cache mode)."""
        state = CaseState.from_phase2_dict(raw)
        cfg = MODALITY_CONFIG.get(state.modality, {})
        if not state.imaging_modality:
            state.imaging_modality = cfg.get("imaging_modality", "")
        if not state.anatomy:
            state.anatomy = cfg.get("anatomy", "")
        state.status = "retrieved"
        return state

    def should_skip(self, case_id: str, already_done: set) -> bool:
        """Idempotency check: skip case_id if already in output JSONL."""
        return case_id in already_done

    # ── Scratch mode ──────────────────────────────────────────────────────────

    def _run_scratch(self, state: CaseState) -> CaseState:
        """
        Full pipeline for one PMCID: NXML fetch → parse → figure extraction
        → image download. Populates all source-text fields.
        """
        pmcid = state.pmcid
        root = fetch_article_nxml(pmcid)
        if root is None:
            state.status = "failed"
            return state

        state.license = extract_license(root)
        citation = extract_citation(root)
        state.article_title     = citation["title"]
        state.journal           = citation["journal"]
        state.year              = citation["year"]
        state.month             = citation["month"]
        state.publication_date  = citation["publication_date"]
        state.pub_date          = citation["publication_date"]
        state.author_keywords   = extract_keywords(root)
        state.abstract          = extract_abstract(root)
        state.case_text         = extract_case_text(root, citation["title"], state.author_keywords)

        cfg = MODALITY_CONFIG.get(state.modality, {})
        state.imaging_modality = cfg.get("imaging_modality", "")
        state.anatomy          = cfg.get("anatomy", "")

        # Find figures matching this modality (first match only in scratch mode)
        # Full multi-figure logic is handled at the coordinator level
        cdn_map: Optional[dict] = None

        for fig in root.findall(".//fig"):
            from openredu.tools.pmc_api import _all_text
            label   = _all_text(fig.find("label"))
            caption = _all_text(fig.find("caption"))
            graphic = fig.find("graphic")
            href = (
                graphic.get("{http://www.w3.org/1999/xlink}href", "")
                if graphic is not None else ""
            )
            if not (label and caption):
                continue

            state.figure_label   = label
            state.figure_caption = caption
            state.results_text   = extract_results_sentences(root, label)

            if href:
                if cdn_map is None:
                    cdn_map = get_cdn_map(pmcid)
                out_dir = PATHS["images"] / state.modality / pmcid
                img_path = download_image(pmcid, href, cdn_map, out_dir) if cdn_map else None
                if img_path:
                    state.image_paths   = [img_path]
                    state.image_size_kb = round(Path(img_path).stat().st_size / 1024, 1)

            # Return first figure found; CurationMasterAgent handles multi-figure
            break

        state.status = "retrieved"
        return state

    # ── Batch scratch mode ────────────────────────────────────────────────────

    def iter_from_scratch(self, pmcids: list, modality: str) -> "Iterator[CaseState]":
        """
        Yield one CaseState per figure per PMCID (scratch mode).
        Handles multi-figure articles by yielding one state per <fig>.
        """
        cfg = MODALITY_CONFIG.get(modality, {})
        from openredu.tools.pmc_api import (
            fetch_article_nxml, extract_license, extract_citation,
            extract_abstract, extract_keywords, extract_case_text,
            extract_results_sentences, _all_text,
        )

        for pmcid in pmcids:
            root = fetch_article_nxml(pmcid)
            if root is None:
                continue

            lic = extract_license(root)
            if lic not in ALLOWED_LICENSES:
                continue

            citation    = extract_citation(root)
            author_kws  = extract_keywords(root)
            abstract    = extract_abstract(root)
            case_text   = extract_case_text(root, citation["title"], author_kws)
            cdn_map     = None

            for fig in root.findall(".//fig"):
                label   = _all_text(fig.find("label"))
                caption = _all_text(fig.find("caption"))
                graphic = fig.find("graphic")
                href = (
                    graphic.get("{http://www.w3.org/1999/xlink}href", "")
                    if graphic is not None else ""
                )
                if not (label and caption):
                    continue

                fig_id   = fig.get("id", "fig")
                case_id  = f"{pmcid}_{fig_id}"
                results  = extract_results_sentences(root, label)

                image_paths   = []
                image_size_kb = None
                if href:
                    if cdn_map is None:
                        cdn_map = get_cdn_map(pmcid)
                    out_dir  = PATHS["images"] / modality / pmcid
                    img_path = download_image(pmcid, href, cdn_map, out_dir) if cdn_map else None
                    if img_path:
                        image_paths   = [img_path]
                        image_size_kb = round(Path(img_path).stat().st_size / 1024, 1)

                pub_date = citation["publication_date"]
                yield CaseState(
                    pmcid            = pmcid,
                    case_id          = case_id,
                    license          = lic,
                    article_title    = citation["title"],
                    journal          = citation["journal"],
                    year             = citation["year"],
                    month            = citation["month"],
                    publication_date = pub_date,
                    pub_date         = pub_date,
                    modality         = modality,
                    imaging_modality = cfg.get("imaging_modality", ""),
                    anatomy          = cfg.get("anatomy", ""),
                    author_keywords  = author_kws,
                    abstract         = abstract,
                    case_text        = case_text,
                    results_text     = results,
                    figure_label     = label,
                    figure_caption   = caption,
                    image_paths      = image_paths,
                    image_size_kb    = image_size_kb,
                    status           = "retrieved",
                )
