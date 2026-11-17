"""
PMC API tools: Entrez search, NXML fetch, and structured text extraction.

All functions here are deterministic (no LLM). They are called by agents,
not inlined as flat scripts, satisfying the agentic requirement ①.

Adapted from the earlier prototype collection scripts (phase 1 and
phase 2; no import from those files).
"""
import os
import re
import time
import logging
import requests
from pathlib import Path
from typing import Optional
from xml.etree import ElementTree as ET

from Bio import Entrez

from openredu.tools.ncbi_helpers import setup_entrez, get_delay, entrez_with_retry
from openredu.config import (
    PMC_EFETCH_URL, ENTREZ_EMAIL, ENTREZ_API_KEY,
    MODALITY_CONFIG, GAP_FILL_MODALITY_CONFIG, BATCH_SIZE
)

log = logging.getLogger(__name__)

# Configure Entrez at module load
if ENTREZ_EMAIL:
    Entrez.email = ENTREZ_EMAIL
if ENTREZ_API_KEY:
    Entrez.api_key = ENTREZ_API_KEY

CASE_SECTION_KEYWORDS = ["case", "patient", "history", "presentation", "clinical", "report"]


# ── Phase 1: Search ───────────────────────────────────────────────────────────

def build_query(
    modality: str,
    year_start: Optional[int] = None,
    year_end: Optional[int] = None,
    year: Optional[int] = None,
    month: Optional[int] = None,
) -> str:
    """
    Build a PMC search query for a given modality with optional date filter.

    For reproducibility, use year_start/year_end to define the corpus range.
    Specific year/month can be used for incremental updates.
    """
    all_configs = {**MODALITY_CONFIG, **GAP_FILL_MODALITY_CONFIG}
    if modality not in all_configs:
        raise ValueError(f"Unknown modality: {modality}. Available: {list(all_configs.keys())}")

    cfg = all_configs[modality]

    # Gap-fill modalities use diagnosis_terms + modality_terms for AND-combined query.
    # Original 10 modalities use search_keywords with OR-only clause.
    if "diagnosis_terms" in cfg and "modality_terms" in cfg:
        diag_clause = " OR ".join(f'"{t}"[tiab]' for t in cfg["diagnosis_terms"])
        mod_clause  = " OR ".join(f'"{t}"[tiab]' for t in cfg["modality_terms"])
        query = (
            f"({diag_clause})"
            f' AND ({mod_clause})'
            ' AND "case report"[pt]'
            ' AND "open access"[filter]'
        )
    else:
        keywords = cfg["search_keywords"]
        keyword_clause = " OR ".join(f'"{kw}"[tiab]' for kw in keywords)
        query = (
            f"({keyword_clause})"
            ' AND "case report"[pt]'
            ' AND "open access"[filter]'
        )

    if year_start and year_end:
        query += f' AND {year_start}:{year_end}[PDAT]'
    elif year and month:
        query += f' AND {year}/{month:02d}[PDAT]'
    elif year:
        query += f' AND {year}[PDAT]'

    return query


def search_pmc(query: str) -> list:
    """
    Execute a PMC esearch and return list of PMCIDs (e.g. ["PMC123456", ...]).
    Uses server-side history for efficient batched retrieval.
    """
    delay = get_delay()

    time.sleep(delay)
    handle = Entrez.esearch(db="pmc", term=query, usehistory="y", retmax=0)
    result = Entrez.read(handle)
    handle.close()

    total = int(result["Count"])
    webenv, query_key = result["WebEnv"], result["QueryKey"]
    log.info(f"PMC search hits: {total:,}")

    pmcids = []
    for start in range(0, total, BATCH_SIZE):
        time.sleep(delay)
        handle = Entrez.esearch(
            db="pmc", term=query,
            webenv=webenv, query_key=query_key,
            retstart=start, retmax=BATCH_SIZE,
        )
        batch = Entrez.read(handle)
        handle.close()
        pmcids.extend(f"PMC{i}" for i in batch["IdList"])
        log.info(f"  collected {len(pmcids):,}/{total:,}")

    return pmcids


# ── Phase 2: NXML fetch ───────────────────────────────────────────────────────

def fetch_article_nxml(pmcid: str) -> Optional[ET.Element]:
    """Fetch full NXML for a PMC article. Returns parsed ElementTree root or None."""
    delay = get_delay()
    time.sleep(delay)
    params = {
        "db": "pmc",
        "id": pmcid.replace("PMC", ""),
        "rettype": "xml",
        "retmode": "xml",
    }
    if ENTREZ_EMAIL:
        params["email"] = ENTREZ_EMAIL
    if ENTREZ_API_KEY:
        params["api_key"] = ENTREZ_API_KEY

    try:
        resp = requests.get(PMC_EFETCH_URL, params=params, timeout=30)
        resp.raise_for_status()
        return ET.fromstring(resp.content)
    except Exception as e:
        log.warning(f"NXML fetch failed for {pmcid}: {e}")
        return None


# ── NXML extractors ───────────────────────────────────────────────────────────

def _all_text(el: Optional[ET.Element]) -> str:
    """Join all text content within an element."""
    return " ".join(el.itertext()).strip() if el is not None else ""


def extract_license(root: ET.Element) -> str:
    """Read only this article's license metadata; references are not permissions.

    Multiple different CC licenses are ambiguous and require review rather than
    choosing whichever URL happens to appear first in the XML.
    """
    from urllib.parse import urlsplit

    def local(el):
        return el.tag.rsplit("}", 1)[-1]

    def children(el, name):
        return [child for child in el if local(child) == name]

    articles = [root] if local(root) == "article" else children(root, "article")
    if len(articles) != 1:
        return "UNKNOWN"
    licenses = set()
    for front in children(articles[0], "front"):
        for meta in children(front, "article-meta"):
            scopes = [el for permissions in children(meta, "permissions")
                      for el in permissions if local(el) in ("license", "license_ref", "license-ref")]
            scopes += [el for el in meta if local(el) in ("license_ref", "license-ref")]
            for scope in scopes:
                for el in scope.iter():
                    urls = [el.get("{http://www.w3.org/1999/xlink}href", "")]
                    if local(el) in ("license_ref", "license-ref"):
                        urls.append((el.text or "").strip())
                    for url in urls:
                        try:
                            parsed = urlsplit(url)
                        except ValueError:
                            continue
                        if parsed.scheme not in ("http", "https") or parsed.netloc.lower() not in (
                            "creativecommons.org", "www.creativecommons.org"
                        ):
                            continue
                        match = re.fullmatch(
                            r"/licenses/(by|by-sa|by-nd|by-nc|by-nc-sa|by-nc-nd)/"
                            r"\d+(?:\.\d+)*(?:/(?:deed\.[a-zA-Z_-]+|legalcode))?/?",
                            parsed.path, re.I,
                        )
                        if match:
                            licenses.add("CC " + match[1].upper())
    return next(iter(licenses)) if len(licenses) == 1 else "UNKNOWN"


def extract_citation(root: ET.Element) -> dict:
    """Extract structured citation metadata from NXML."""
    pub_date = root.find(".//pub-date[@pub-type='epub']") or root.find(".//pub-date")
    year  = _all_text(pub_date.find("year"))  if pub_date is not None else ""
    month = _all_text(pub_date.find("month")) if pub_date is not None else ""
    publication_date = f"{year}-{month.zfill(2)}" if year and month else year
    return {
        "title":            _all_text(root.find(".//article-title")),
        "journal":          _all_text(root.find(".//journal-title")),
        "year":             year,
        "month":            month,
        "publication_date": publication_date,
    }


def extract_abstract(root: ET.Element) -> str:
    """Extract full abstract text."""
    abstract = root.find(".//abstract")
    return _all_text(abstract) if abstract is not None else ""


def extract_keywords(root: ET.Element) -> list:
    """Extract author keywords from <kwd-group>."""
    keywords = []
    for kwd_group in root.findall(".//kwd-group"):
        for kwd in kwd_group.findall(".//kwd"):
            text = _all_text(kwd)
            if text:
                keywords.append(text)
    return keywords


def extract_case_text(root: ET.Element, title: str = "", keywords: list = None) -> str:
    """
    Extract text from case presentation sections.
    Returns empty string for review articles to prevent demographic confusion.
    """
    title_lower = title.lower()
    kw_lower = [k.lower() for k in (keywords or [])]
    review_indicators = ["review", " cases", "case series", "teaching", "pearls", "atlas"]
    if any(ind in title_lower for ind in review_indicators):
        return ""
    if any(any(ind in kw for ind in review_indicators) for kw in kw_lower):
        return ""

    sections = []
    for sec in root.findall(".//body//sec"):
        sec_title = _all_text(sec.find("title")).lower()
        if any(kw in sec_title for kw in CASE_SECTION_KEYWORDS):
            sections.append(_all_text(sec))
    return " ".join(sections)


def extract_results_sentences(root: ET.Element, fig_label: str) -> str:
    """Return body paragraphs that mention this figure label."""
    num = re.search(r"\d+", fig_label)
    if not num:
        return ""
    pattern = re.compile(rf"\bFig(?:ure)?\.?\s*{num.group()}\b", re.IGNORECASE)
    paragraphs = [
        _all_text(p)
        for p in root.findall(".//body//p")
        if pattern.search(_all_text(p))
    ]
    return " ".join(paragraphs)
