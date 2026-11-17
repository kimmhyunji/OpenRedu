"""
Shared NCBI/Entrez helpers: delay management and retry logic.
"""
import os
import time
import logging
from Bio import Entrez

log = logging.getLogger(__name__)


def setup_entrez():
    """Configure Entrez with credentials from environment."""
    email = os.getenv("ENTREZ_EMAIL", "")
    api_key = os.getenv("ENTREZ_API_KEY", "")
    if email:
        Entrez.email = email
    if api_key:
        Entrez.api_key = api_key
    return bool(api_key)


def get_delay() -> float:
    """Return appropriate delay: 0.11s with API key, 0.34s without."""
    return 0.11 if os.getenv("ENTREZ_API_KEY") else 0.34


def entrez_with_retry(fn, *args, max_retries: int = 5, **kwargs):
    """
    Call an Entrez function with exponential backoff on failure.
    Returns the parsed result or raises on exhausted retries.
    """
    delay = get_delay()
    for attempt in range(1, max_retries + 1):
        try:
            time.sleep(delay)
            handle = fn(*args, **kwargs)
            result = Entrez.read(handle)
            handle.close()
            return result
        except Exception as e:
            wait = 2 ** attempt
            log.warning(f"Entrez error attempt {attempt}/{max_retries}: {e} — waiting {wait}s")
            if attempt == max_retries:
                raise
            time.sleep(wait)
