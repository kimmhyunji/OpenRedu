"""Mask UMLS credentials in every log record (Python logging) emitted while a revision script runs.

openredu.tools.umls_client logs request exceptions whose text contains the full request URL with
`apiKey=` or a CAS `ticket=`. Importing this module installs a log-record factory that replaces those
values before any handler formats the record. Import it before using UMLS helpers.
"""
from __future__ import annotations

import logging
import re

_PAT = re.compile(r"(apiKey=|ticket=|api_key=)[^&\s\"']+", re.I)


def redact(text: str) -> str:
    return _PAT.sub(r"\1REDACTED", text)


_base_factory = logging.getLogRecordFactory()


def _factory(*args, **kwargs):
    rec = _base_factory(*args, **kwargs)
    try:
        msg = rec.getMessage()
    except Exception:
        return rec
    clean = redact(msg)
    if clean != msg:
        rec.msg, rec.args = clean, None
    return rec


logging.setLogRecordFactory(_factory)
