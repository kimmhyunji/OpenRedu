"""
Figure-scoped evidence for a case: the target figure's caption plus the
body-text sentences that cite the target figure number.

Sentences that cite only other figures are dropped. Sentences citing the target
and another figure are kept and marked. Title, abstract, keywords and case
narrative are not used. No LLM.

Moved from pipeline/step2_evidence.py (2026-10-08) so the
extraction agent can use it; that file now re-exports this module. Used by the
verifier and by ExtractionSubagent.scope_finding_to_figure. Behaviour must stay
identical for dict input.
"""
from __future__ import annotations

import re

_FIG_REF = re.compile(
    r"\b(?:fig(?:ure)?s?|images?)\.?\s*\(?\s*"
    r"((?:\d+(?:\s*[A-Za-z](?![A-Za-z]))?(?:\s*(?:,|and|&|to|[-–—])\s*)?)+)",
    re.IGNORECASE,
)
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z(\[])")


def figure_number(label: str) -> int | None:
    m = re.search(r"(\d+)", label or "")
    return int(m.group(1)) if m else None


def cited_figures(sentence: str) -> set[int]:
    """Figure numbers cited in a sentence, expanding ranges (Figures 2-4)."""
    nums: set[int] = set()
    for grp in _FIG_REF.findall(sentence):
        tokens = re.findall(r"\d+|[-–—]|to", grp)
        prev = None
        pending_range = False
        for t in tokens:
            if t.isdigit():
                n = int(t)
                if pending_range and prev is not None and 0 < n - prev <= 20:
                    nums.update(range(prev, n + 1))
                else:
                    nums.add(n)
                prev, pending_range = n, False
            else:
                pending_range = True
    return nums


def split_sentences(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text or "").strip()
    return [s.strip() for s in _SENT_SPLIT.split(text) if s.strip()] if text else []


def case_to_evidence_dict(case) -> dict:
    """Accept a case dict or a CaseState; return the dict build_evidence reads."""
    if isinstance(case, dict):
        return case
    return {
        "figure_caption": getattr(case, "figure_caption", ""),
        "figure_label": getattr(case, "figure_label", ""),
        "results_text": getattr(case, "results_text", ""),
    }


def build_evidence(case) -> dict:
    case = case_to_evidence_dict(case)
    caption = re.sub(r"\s+", " ", case.get("figure_caption") or case.get("figure_legend") or "").strip()
    num = figure_number(case.get("figure_label", ""))
    sentences: list[dict] = []
    if num is not None:
        for s in split_sentences(case.get("results_text", "")):
            cited = cited_figures(s)
            if num in cited:
                sentences.append({"text": s, "also_cites_other_figures": len(cited - {num}) > 0})
    return {
        "figure_label": case.get("figure_label", ""),
        "figure_number": num,
        "caption": caption,
        "sentences": sentences,
        "n_sentences": len(sentences),
        "n_mixed_sentences": sum(s["also_cites_other_figures"] for s in sentences),
    }


def render_evidence(ev: dict) -> str:
    lines = [f"[FIGURE CAPTION — {ev['figure_label'] or 'target figure'}]", ev["caption"] or "(no caption)"]
    lines.append("")
    lines.append("[BODY-TEXT SENTENCES THAT CITE THIS FIGURE]")
    if not ev["sentences"]:
        lines.append("(none)")
    for i, s in enumerate(ev["sentences"], 1):
        tag = " [also cites other figures — use only what refers to the target figure]" \
            if s["also_cites_other_figures"] else ""
        lines.append(f"S{i}.{tag} {s['text']}")
    return "\n".join(lines)


def evidence_text(ev: dict) -> str:
    """Caption + cited sentences as one string (for word-support checks)."""
    return ev["caption"] + " " + " ".join(s["text"] for s in ev["sentences"])


# Word-support check: same as in the 120-case development pilot.
_SUPPORT_STOP = set(
    "with without from that this were was are the and for into over under between within also both then than their "
    "there have has had been being which while after before during shows showed show seen noted".split()
)


def support_words(t: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", (t or "").lower()) if len(w) > 3 and w not in _SUPPORT_STOP}


def support_ratio(finding: str, evidence: str) -> float | None:
    """Share of the finding's content words that appear in the evidence; None if no content words."""
    w = support_words(finding)
    return None if not w else len(w & support_words(evidence)) / len(w)
