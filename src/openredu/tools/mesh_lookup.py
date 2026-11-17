"""
MeSH lookup tool via NCBI esearch/esummary.

Copied and adapted from educational_material/keyword_normalization/legacy/layer1_mesh.py.
Used by StandardizationSubagent (Layer 1).
"""
import re
import time
import logging
from typing import Optional, Tuple
from Bio import Entrez

from openredu.config import ENTREZ_EMAIL, ENTREZ_API_KEY, ABBR_MAP, STOP_WORDS

log = logging.getLogger(__name__)

if ENTREZ_EMAIL:
    Entrez.email = ENTREZ_EMAIL
if ENTREZ_API_KEY:
    Entrez.api_key = ENTREZ_API_KEY

DELAY = 0.11 if ENTREZ_API_KEY else 0.35


def content_tokens(text: str) -> set:
    words = re.sub(r"[-/,().]", " ", text.lower()).split()
    return {w for w in words if len(w) >= 3 and w not in STOP_WORDS}


def expand_abbr(text: str) -> str:
    words = re.sub(r"[-/]", " ", text.lower()).split()
    return " ".join(ABBR_MAP.get(w, w) for w in words)


def query_variants(keyword: str) -> list:
    """Return up to 3 MeSH query strings for a keyword, best-first."""
    kw = keyword.lower()
    variants = []
    expanded = expand_abbr(kw.split("/")[0].strip())
    variants.append(expanded)
    if "/" in kw:
        for part in kw.split("/"):
            v = expand_abbr(part.strip())
            if v and v not in variants:
                variants.append(v)
    if kw not in variants:
        variants.append(kw)
    return variants[:3]


def _entrez_call(fn, *args, **kwargs):
    """Call Entrez function with exponential backoff."""
    for attempt in range(5):
        try:
            time.sleep(DELAY)
            return fn(*args, **kwargs)
        except Exception as e:
            if attempt == 4:
                raise
            time.sleep(2 ** (attempt + 1))


def mesh_lookup(keyword: str) -> Optional[dict]:
    """
    Look up a keyword in MeSH via NCBI.

    Returns dict with:
      {mesh_preferred: str, all_synonyms: [str]}
    or None if no valid mapping found.
    """
    kw_tokens = content_tokens(keyword) | content_tokens(expand_abbr(keyword))

    for query in query_variants(keyword):
        try:
            h = _entrez_call(Entrez.esearch, db="mesh", term=query, retmax=3)
            r = Entrez.read(h); h.close()
            if not r["IdList"]:
                continue

            for uid in r["IdList"]:
                h = _entrez_call(Entrez.esummary, db="mesh", id=uid)
                s = Entrez.read(h); h.close()
                if not s:
                    continue
                mesh_terms = list(s[0].get("DS_MeshTerms", []))
                if not mesh_terms:
                    continue
                preferred = mesh_terms[0]
                pref_tokens = content_tokens(preferred)
                if kw_tokens & pref_tokens:
                    return {
                        "mesh_preferred": preferred,
                        "all_synonyms": sorted(set([keyword.lower()] + [t.lower() for t in mesh_terms])),
                    }
        except Exception as e:
            log.warning(f"MeSH lookup error for {query!r}: {e}")

    return None
