"""
UMLS client: REST API search + SNOMED CT TGT auth + LLM concept decomposition.

Combines logic from:
  - educational_material/keyword_normalization/legacy/layer2_snomed.py (UMLSClient)
  - educational_material/keyword_normalization/layer3_llm.py (umls_search, best_cui, call_llm)

Used by StandardizationSubagent (Layers 2 and 3).
"""
import json
import logging
import re
import time
from typing import Optional, Tuple

import requests

from openredu.config import UMLS_API_KEY, UMLS_BASE, TRUSTED_UMLS_SOURCES, STOP_WORDS, MODELS

log = logging.getLogger(__name__)

UMLS_DELAY = 0.25


# ── Content token helpers ─────────────────────────────────────────────────────

def content_tokens(text: str) -> set:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower())
            if len(w) >= 3 and w not in STOP_WORDS}


def is_valid_match(query: str, name: str) -> bool:
    qt = content_tokens(query)
    nt = content_tokens(name)
    if len(qt) <= 1:
        return True
    return bool(qt & nt)


# ── UMLS API (Layer 3 style — api_key based) ─────────────────────────────────

def umls_search(text: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Search UMLS REST API with api_key authentication.
    Returns (CUI, preferred_name) or (None, None).
    Prefers trusted sources: MTH, SNOMEDCT_US, MSH, ICD10CM, NCI, HPO.
    """
    if not UMLS_API_KEY:
        log.warning("UMLS_API_KEY not set — skipping UMLS search")
        return None, None

    for attempt in range(3):
        try:
            time.sleep(UMLS_DELAY)
            r = requests.get(
                f"{UMLS_BASE}/search/current",
                params={
                    "string": text,
                    "apiKey": UMLS_API_KEY,
                    "searchType": "words",
                    "pageSize": 5,
                },
                timeout=15,
            )
            r.raise_for_status()
            results = r.json().get("result", {}).get("results", [])
            trusted = next(
                (h for h in results
                 if h.get("ui", "") != "NONE" and h.get("rootSource") in TRUSTED_UMLS_SOURCES),
                None,
            )
            first = next((h for h in results if h.get("ui", "") != "NONE"), None)
            best = trusted or first
            if best:
                return best["ui"], best["name"]
            return None, None
        except Exception as e:
            if attempt == 2:
                log.warning(f"UMLS error for {text!r}: {e}")
            time.sleep(2 ** attempt)
    return None, None


def best_cui(concepts: list) -> Tuple[Optional[str], Optional[str]]:
    """Try each concept string; return first valid UMLS CUI."""
    for concept in concepts:
        cui, name = umls_search(concept)
        if cui and name and is_valid_match(concept, name):
            return cui, name
    return None, None


# ── UMLS TGT auth client (Layer 2 — SNOMED CT) ───────────────────────────────

class UMLSClient:
    """
    UMLS client with TGT (Ticket Granting Ticket) auth.
    TGT is cached for ~7 hours.
    Used for SNOMED CT lookups (Layer 2).
    """
    def __init__(self):
        self.api_key = UMLS_API_KEY
        self._tgt = None
        self._tgt_expires = 0

    def _get_tgt(self) -> str:
        if self._tgt and time.time() < self._tgt_expires:
            return self._tgt
        r = requests.post(
            "https://utslogin.nlm.nih.gov/cas/v1/api-key",
            data={"apikey": self.api_key},
            timeout=10,
        )
        r.raise_for_status()
        self._tgt = re.search(r'action="([^"]+)"', r.text).group(1)
        self._tgt_expires = time.time() + 7 * 3600
        return self._tgt

    def _get_st(self) -> str:
        tgt = self._get_tgt()
        r = requests.post(tgt, data={"service": "http://umlsks.nlm.nih.gov"}, timeout=10)
        r.raise_for_status()
        return r.text.strip()

    def search(self, query: str, sabs: str = "SNOMEDCT_US") -> list:
        time.sleep(UMLS_DELAY)
        st = self._get_st()
        r = requests.get(
            f"{UMLS_BASE}/search/current",
            params={"string": query, "sabs": sabs, "searchType": "words",
                    "pageSize": 5, "ticket": st},
            timeout=15,
        )
        r.raise_for_status()
        return r.json().get("result", {}).get("results", [])

    def get_atoms(self, cui: str, sabs: str = "SNOMEDCT_US") -> list:
        time.sleep(UMLS_DELAY)
        st = self._get_st()
        r = requests.get(
            f"{UMLS_BASE}/content/current/CUI/{cui}/atoms",
            params={"sabs": sabs, "pageSize": 50, "ticket": st},
            timeout=15,
        )
        r.raise_for_status()
        atoms = r.json().get("result", [])
        return [a.get("name", "").lower() for a in atoms if a.get("name")]


def snomed_lookup(client: UMLSClient, keyword: str) -> Optional[dict]:
    """
    Look up keyword via SNOMED CT through UMLS.
    Returns {cui, snomed_preferred, all_synonyms} or None.
    """
    from openredu.tools.mesh_lookup import content_tokens as mesh_content_tokens, expand_abbr, query_variants
    kw_tokens = mesh_content_tokens(keyword) | mesh_content_tokens(expand_abbr(keyword))

    for query in query_variants(keyword):
        try:
            results = client.search(query, sabs="SNOMEDCT_US")
            for hit in results:
                cui  = hit.get("ui", "")
                name = hit.get("name", "")
                if not cui or cui == "NONE":
                    continue
                pref_tokens = mesh_content_tokens(name)
                if kw_tokens & pref_tokens:
                    atoms = client.get_atoms(cui)
                    return {
                        "cui":              cui,
                        "snomed_preferred": name,
                        "all_synonyms":     sorted(set([keyword.lower(), name.lower()] + atoms)),
                    }
        except Exception as e:
            log.warning(f"SNOMED lookup error for {query!r}: {e}")
    return None


# ── LLM concept decomposition (Layer 3) ──────────────────────────────────────

_CONCEPT_SYSTEM_PROMPT = """You are a medical terminology expert specializing in radiology.
Extract the core clinical concept(s) from the given medical term or phrase.
Return only well-established clinical terms that appear in medical literature.
Never invent terms. If a phrase contains multiple concepts, list the most specific one first."""

_CONCEPT_USER_TEMPLATE = (
    'Extract the core clinical concept(s) from this medical term:\n"{text}"\n\n'
    "Return JSON only:\n"
    '{{"concepts": ["most specific clinical term", "broader term if needed"], "mappable": true/false}}\n\n'
    "- concepts: 1-3 standard medical terms (diagnosis names, no adjectives like 'acute/chronic')\n"
    "- mappable: false only if this is pure educational framing with no clinical concept"
)


def call_concept_llm(text: str) -> Optional[dict]:
    """
    Use Haiku (standardization_llm) to extract core clinical concepts.
    Returns {"concepts": [...], "mappable": bool} or None.
    """
    from openredu.core.llm import _call_bedrock_anthropic, valid_concept_extraction_schema

    user_msg = _CONCEPT_USER_TEMPLATE.format(text=text)
    for attempt in range(6):
        try:
            time.sleep(3)
            result = _call_bedrock_anthropic(
                model=MODELS["standardization_llm"],
                user_msg=user_msg,
                system_prompt=_CONCEPT_SYSTEM_PROMPT,
                max_tokens=200,
            )
            if valid_concept_extraction_schema(result):
                return result
        except Exception as e:
            if "ThrottlingException" in str(e):
                wait = 2 ** (attempt + 2)
                log.warning(f"Throttled at Layer 3 LLM, waiting {wait}s")
                time.sleep(wait)
            else:
                log.warning(f"Layer 3 LLM error: {e}")
                return None
    return None
