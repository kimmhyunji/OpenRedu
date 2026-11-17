"""
ClassificationSubagent: rule-based modality classification + LLM adjudication
+ multipanel detection.

Rule layer (deterministic):
  - exclude_keywords checked first (quality control #1 — exclude wins)
  - include_keywords checked second
  - else: UNCERTAIN → LLM adjudication

Multipanel detection (deterministic):
  - Regex patterns detect panel markers like (A), Fig 1a-c, panels A–D
  - Sets is_multipanel and panel_count (no caption splitting this build)

LLM adjudication (only for UNCERTAIN captions):
  - Uses is_non_clinical_figure() pattern from phase3_enrich.py
  - Model: MODELS["classification_adjudicate"] (Sonnet)
  - is_llm = True because this path exists

Copied and adapted from:
  - earlier prototype classify_legend()
  - earlier prototype is_non_clinical_figure()
"""
import json
import re
import logging
import time
from typing import Optional

from openredu.core.base import Subagent
from openredu.core.state import CaseState
from openredu.config import MODALITY_CONFIG, GAP_FILL_MODALITY_CONFIG, MODELS, NON_RADIOLOGY_EXCLUDE

_ALL_MODALITY_CONFIG = {**MODALITY_CONFIG, **GAP_FILL_MODALITY_CONFIG}

log = logging.getLogger(__name__)

# Panel marker patterns for multipanel detection
PANEL_PATTERNS = [
    re.compile(r'\([A-F]\)',                   re.IGNORECASE),  # (A), (B), ..., (F)
    re.compile(r'\b[Ff]ig(?:ure)?\s+\d+[a-f]',re.IGNORECASE),  # Fig 1a, Figure 2b
    re.compile(r'panels?\s+[A-F][-–][A-F]',re.IGNORECASE), # panel A-D, panels A–F
    re.compile(r'\b[A-F]\s+and\s+[A-F]\b',    re.IGNORECASE),  # A and B
    re.compile(r',\s*[A-F]\)',                 re.IGNORECASE),  # , B), , C)
]

_CLINICAL_CHECK_SYSTEM_PROMPT = """You are a medical imaging data curator.
Your job is to decide whether a figure from a medical paper represents a real patient case image
(i.e., it shows actual patient imaging with clinical findings) or a non-clinical figure
(e.g., a methodology illustration, image processing example, algorithm diagram, or technical demo).

Respond with valid JSON only:
{"is_clinical": true/false, "reason": "one sentence explanation"}"""


class ClassificationSubagent(Subagent):
    """
    Classifies whether a figure caption represents a radiologic patient case
    for a specific modality. Three routes:

      rule_include  — include keyword matched
      rule_exclude  — exclude keyword matched (takes priority)
      llm_adjudicated — UNCERTAIN captions resolved via Sonnet
    """
    name = "ClassificationSubagent"
    is_llm = True  # LLM branch exists for UNCERTAIN captions

    def run(self, state: CaseState, bypass_modality_exclude: bool = False) -> CaseState:
        """
        Run rule layer + multipanel detection.

        bypass_modality_exclude: if True, skip modality-specific other-imaging
          exclude keywords (e.g. "chest ct" when processing CT_ABDOMEN).
          Only NON_RADIOLOGY_EXCLUDE (histopath, diagram, etc.) are still applied.
          Used in gap-fill mode to allow cross-modality figures.
        """
        self._classify_rule(state, bypass_modality_exclude=bypass_modality_exclude)
        self._detect_multipanel(state)
        return state

    def run_llm_adjudication(self, state: CaseState) -> CaseState:
        """
        Called by CurationMasterAgent for UNCERTAIN cases only.
        Uses Sonnet to decide is_clinical vs non-clinical.
        """
        result = self._is_non_clinical_figure(
            legend=state.figure_caption,
            results_text=state.results_text,
            case_text=state.case_text,
            title=state.article_title,
        )
        is_clinical = result.get("is_clinical", True)
        state.is_radiologic_case = is_clinical
        state.classification_route = "llm_adjudicated"
        state.models_used["adjudication"] = MODELS["classification_adjudicate"]
        log.info(
            f"[{state.case_id}] LLM adjudication: is_clinical={is_clinical} "
            f"— {result.get('reason', '')}"
        )
        return state

    # ── Rule layer ────────────────────────────────────────────────────────────

    def _classify_rule(self, state: CaseState, bypass_modality_exclude: bool = False) -> None:
        """
        Applies modality-specific include/exclude keyword rules to figure_caption.
        EXCLUDE wins over include (quality control priority).

        bypass_modality_exclude: skip modality-specific other-imaging excludes,
          only apply NON_RADIOLOGY_EXCLUDE. Used for gap-fill queries.
        """
        if state.modality not in _ALL_MODALITY_CONFIG:
            state.classification_route = "uncertain_pending"
            return

        cfg   = _ALL_MODALITY_CONFIG[state.modality]
        lower = state.figure_caption.lower()

        if bypass_modality_exclude:
            # Only apply non-radiology excludes (histopath, diagram, surgical photo)
            if any(kw in lower for kw in NON_RADIOLOGY_EXCLUDE):
                state.classification_route = "rule_exclude"
                state.is_radiologic_case   = False
                return
            # Skip include_keywords check — any non-excluded figure passes
            state.classification_route = "rule_include"
            state.is_radiologic_case   = True
            return
        else:
            # Apply full modality-specific exclude list
            if any(kw in lower for kw in cfg["exclude_keywords"]):
                state.classification_route = "rule_exclude"
                state.is_radiologic_case   = False
                return

        if any(kw in lower for kw in cfg["include_keywords"]):
            state.classification_route = "rule_include"
            state.is_radiologic_case   = True
            return

        state.classification_route = "uncertain_pending"
        state.is_radiologic_case   = None

    # ── Multipanel detection ──────────────────────────────────────────────────

    def _detect_multipanel(self, state: CaseState) -> None:
        """
        Detect panel markers in caption. Sets is_multipanel and panel_count.
        No caption splitting in this build — flag only.
        """
        caption = state.figure_caption
        panel_markers = set()

        # Pattern 0: (A), (B), ... — extract the letter inside parens
        for m in PANEL_PATTERNS[0].finditer(caption):
            letter = re.search(r'[A-F]', m.group(), re.IGNORECASE)
            if letter:
                panel_markers.add(letter.group().upper())

        # Pattern 1: Fig 1a, Fig 1b — extract the trailing letter only
        for m in PANEL_PATTERNS[1].finditer(caption):
            letter = re.search(r'[a-f]$', m.group(), re.IGNORECASE)
            if letter:
                panel_markers.add(letter.group().upper())

        # Pattern 2: panels A-D or panels A–D — expand range
        # Extract only the two single uppercase letters flanking the dash
        for m in PANEL_PATTERNS[2].finditer(caption):
            # Match the two boundary letters: e.g. "panels A-D" → A, D
            bounds = re.findall(r'\b([A-F])\b', m.group(), re.IGNORECASE)
            if len(bounds) >= 2:
                start = ord(bounds[0].upper()) - ord('A')
                end   = ord(bounds[-1].upper()) - ord('A')
                for i in range(start, end + 1):
                    panel_markers.add(chr(ord('A') + i))

        # Pattern 3: A and B
        for m in PANEL_PATTERNS[3].finditer(caption):
            for letter in re.findall(r'[A-F]', m.group(), re.IGNORECASE):
                panel_markers.add(letter.upper())

        # Pattern 4: , B), , C)
        for m in PANEL_PATTERNS[4].finditer(caption):
            letter = re.search(r'[A-F]', m.group(), re.IGNORECASE)
            if letter:
                panel_markers.add(letter.group().upper())

        if len(panel_markers) >= 2:
            state.is_multipanel = True
            state.panel_count   = len(panel_markers)
        else:
            state.is_multipanel = False
            state.panel_count   = 1

    # ── LLM helpers ───────────────────────────────────────────────────────────

    def _is_non_clinical_figure(
        self,
        legend: str,
        results_text: str,
        case_text: str,
        title: str = "",
    ) -> dict:
        """
        Ask Sonnet whether this is a clinical patient case image or non-clinical.
        Returns {"is_clinical": bool, "reason": str}.
        Defaults to is_clinical=True on failure (keep by default).
        """
        from openredu.core.llm import _call_bedrock_anthropic, valid_clinical_check_schema

        user_msg = (
            f"Paper title: {title}\n\n"
            f"Figure legend: {legend}\n\n"
            f"Results/context text: {results_text or '(not available)'}\n\n"
            f"Case presentation: {case_text[:500] or '(not available)'}\n\n"
            "Is this figure a real patient case image with clinical findings, "
            "or a non-clinical illustration (methodology, image processing demo, "
            "algorithm output, etc.)?"
        )
        for attempt in range(3):
            try:
                time.sleep(1)
                result = _call_bedrock_anthropic(
                    model=MODELS["classification_adjudicate"],
                    user_msg=user_msg,
                    system_prompt=_CLINICAL_CHECK_SYSTEM_PROMPT,
                    max_tokens=150,
                )
                if valid_clinical_check_schema(result):
                    return result
            except Exception as e:
                log.warning(f"Clinical check attempt {attempt+1}/3 error: {e}")
                time.sleep(3)
        # Default: keep figure
        return {"is_clinical": True, "reason": "clinical check failed — defaulting to keep"}
