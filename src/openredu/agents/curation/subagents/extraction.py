"""
ExtractionSubagent: demographics regex + LLM extraction + self-check
+ diagnosis normalization + title_match_quality
+ figure-scope finding pass (pass 2, added in the revision, 2026-10-08).

Adapted from the earlier prototype enrichment script.
"""
import re
import logging
import time
from collections import Counter
from datetime import datetime, timezone
from typing import Optional

from openredu.core.base import Subagent
from openredu.core.state import CaseState
from openredu.config import MODALITY_CONFIG, GAP_FILL_MODALITY_CONFIG, MODELS

_ALL_MODALITY_CONFIG = {**MODALITY_CONFIG, **GAP_FILL_MODALITY_CONFIG}
from openredu.core.llm import llm_with_escalation, valid_extraction_schema, valid_self_check_schema
from openredu.core.figure_evidence import build_evidence, render_evidence, evidence_text, support_ratio

log = logging.getLogger(__name__)

AGE_PATTERN = re.compile(r"\b(\d{1,3})[\s-]*year[\s-]*old\b", re.IGNORECASE)
SEX_PATTERN = re.compile(r"\b(male|female|man|woman|boy|girl)\b", re.IGNORECASE)
SEX_MAP = {"male": "M", "man": "M", "boy": "M", "female": "F", "woman": "F", "girl": "F"}

TITLE_STOP_WORDS = {
    "a", "an", "the", "and", "or", "of", "in", "on", "at", "to", "for",
    "with", "by", "from", "as", "is", "was", "are", "were", "be", "been",
    "case", "report", "patient", "unusual", "rare",
}

_SELF_CHECK_SYSTEM_PROMPT = """You are a medical image annotation quality checker.
Check whether the extracted diagnosis is consistent with what the figure caption describes.
Return JSON only: {"consistent": true/false, "reason": "one sentence"}"""

# These legacy modality prompts do not contain an explicit target-figure scope
# rule. Append one centrally so the safety rule cannot drift across separate
# configuration blocks.
_MODALITIES_REQUIRING_FIGURE_SCOPE_RULE = frozenset({
    "CT_CHEST_VASC",
    "GI_FLUOROSCOPY",
    "GU_FLUOROSCOPY",
    "MRI_ABDOMEN",
    "MRI_MSK",
    "MRI_NEURO_SPINE",
    "MSK_XRAY",
    "NM_NUCLEAR",
    "US_GYN_TRANS",
    "US_PELVIS",
})

_COMMON_FIGURE_SCOPE_RULE = """

STRICT TARGET-FIGURE SCOPE:
- Extract the finding ONLY for the specific target figure identified in the Figure legend.
- Treat the Figure legend as the highest-authority source for the finding. Use Results text
  only when it clearly describes that same figure.
- Do NOT import or combine findings from other figure numbers, other examinations, or
  different time points (pre-treatment, post-treatment, or follow-up).
- If the target figure itself contains panels from multiple time points, keep the time
  points explicitly separated; do not merge them into one contemporaneous finding.
- Abstract, title, keywords, and case presentation may clarify the final diagnosis, but
  must not add imaging findings that are not shown or described for the target figure.
"""


# ── Pass 2: figure-scope finding (added after the first submission) ───────
# Pass 1 (above) reads the whole article and may mix in other figures, other
# examinations or time points. Pass 2 rewrites ONLY the finding from the target
# figure's caption + the body-text sentences that cite it. Diagnosis and
# laterality stay as pass 1 produced them. The prompt text is the one used in
# the 120-case development pilot — do not edit.
FIGURE_SCOPE_PROMPT_VERSION = "figure_scope_v1"

_FIGURE_SCOPE_FINDING_PROMPT = """You rewrite the "finding" field of a radiology teaching case so that it describes ONLY the target figure.

You get (1) the figure caption and the body-text sentences that cite this figure, and (2) the original finding, which was
written from the whole article and may contain content from other figures, other examinations, other time points, or
clinical information.

Rules:
1. Keep only imaging findings that the caption or the cited sentences state for THIS figure. Reuse their wording as closely as possible.
2. Remove: findings of other figures, other examinations or modalities, other time points (if this figure itself shows several
   time points or panels, keep them separate and label them as the caption does), clinical history, laboratory, pathology or
   treatment details, causes or interpretations not stated for this figure, and measurements that the caption/cited sentences do not give.
3. Do not add anything that is not in the caption or the cited sentences. Do not use outside knowledge.
4. If the caption and sentences give no imaging finding for this figure, return the shortest imaging statement they do give; if there is none, return an empty string.
Return JSON only: {"finding": "...", "removed": "one short sentence on what was removed"}"""

FIGURE_SCOPE_MAX_TOKENS = 600
FIGURE_SCOPE_TEMPERATURE = 0
FIGURE_SCOPE_MIN_SUPPORT = 0.5      # below this the rewrite is not grounded in the figure evidence
FIGURE_SCOPE_FORMAT_RETRIES = 2     # extra attempts after a JSON/format failure
FIGURE_SCOPE_THROTTLE_RETRIES = 14  # same as the pilot

# finding_scope values
SCOPE_FIGURE = "figure"
SCOPE_FALLBACK_EMPTY = "article_fallback_no_figure_finding"
SCOPE_FALLBACK_LOW_SUPPORT = "article_fallback_low_support"
SCOPE_FALLBACK_ERROR = "article_fallback_error"


def _default_scope_llm(user_msg: str) -> tuple:
    """One pass-2 call: returns (raw_text, input_tokens, output_tokens)."""
    from openredu.core.llm import call_bedrock_anthropic_raw
    return call_bedrock_anthropic_raw(
        model=MODELS["extraction_primary"],
        user_msg=user_msg,
        system_prompt=_FIGURE_SCOPE_FINDING_PROMPT,
        max_tokens=FIGURE_SCOPE_MAX_TOKENS,
        temperature=FIGURE_SCOPE_TEMPERATURE,
    )


def _is_throttling(e: Exception) -> bool:
    return "Throttl" in type(e).__name__ or "Throttl" in str(e)


def valid_extraction_output(state: CaseState) -> bool:
    """True if extraction produced non-empty, non-failed finding and diagnosis."""
    return (
        bool(state.finding) and state.finding not in ("extraction failed", "N/A")
        and bool(state.diagnosis) and state.diagnosis not in ("extraction failed", "N/A")
        and bool(state.laterality)
    )


class ExtractionSubagent(Subagent):
    """
    Extracts demographics, finding, diagnosis, laterality from CaseState text fields.
    Also runs self-check and diagnosis normalization.
    """
    name = "ExtractionSubagent"
    is_llm = True

    def __init__(self, pmcid_counts: Optional[Counter] = None, scope_llm=None, throttle_sleep=None):
        """
        pmcid_counts: Counter of figures per PMCID in the current batch.
        If a PMCID has >1 figure, case_text is excluded from LLM input to
        prevent demographic confusion across figures.
        scope_llm: pass-2 caller (user_msg -> (raw_text, in_tok, out_tok));
        tests inject a fake. throttle_sleep: seconds to wait on throttling, by attempt.
        """
        self.pmcid_counts = pmcid_counts or Counter()
        self.scope_llm = scope_llm or _default_scope_llm
        self.throttle_sleep = throttle_sleep or (lambda attempt: min(3 * (attempt + 1), 40))

    def run(self, state: CaseState) -> CaseState:
        """Full extraction: demographics → LLM → self-check → normalization."""
        state.demographics = self.extract_demographics(
            figure_legend=state.figure_caption,
            results_text=state.results_text,
            case_text=state.case_text,
        )

        # Exclude case_text for multi-figure articles (avoid demographic confusion)
        case_text_for_llm = (
            "" if self.pmcid_counts.get(state.pmcid, 1) > 1
            else state.case_text
        )

        llm_result, model_used, attempts = llm_with_escalation(
            prompt=self._build_prompt(state, case_text_for_llm),
            system_prompt=self._get_system_prompt(state.modality),
            primary=MODELS["extraction_primary"],
            escalate=MODELS["extraction_escalate"],
            validate_fn=valid_extraction_schema,
            middle=MODELS["extraction_middle"],
            max_retries=3,
            sleep_s=3.0,
        )
        state.models_used["extraction"] = model_used

        if llm_result:
            state.finding   = llm_result.get("finding", "")
            state.diagnosis = llm_result.get("diagnosis", "")
            state.laterality = llm_result.get("laterality", "")

            time.sleep(0.5)  # avoid throttling (between extraction and self-check)
            # Self-check: verify extracted diagnosis is consistent with caption
            state.extraction_self_check_passed = self._self_check(state)

        state.diagnosis_normalized = self.normalize_diagnosis(
            state.diagnosis, state.author_keywords, state.modality
        )
        state.title_match_quality = self.calc_title_match_quality(
            state.article_title, state.diagnosis_normalized or state.diagnosis
        )
        self.scope_finding_to_figure(state)
        return state

    def run_escalated(self, state: CaseState) -> CaseState:
        """Force re-extraction using only the escalate (Sonnet) model."""
        from openredu.core.llm import _call_bedrock_anthropic

        # If pass 2 already ran (from run()), put the article-level finding back
        # so a failed escalation never feeds an already-scoped finding to pass 2.
        prev_scope = (state.finding, state.finding_article_level, state.finding_scope)
        if state.finding_scope:
            state.finding = state.finding_article_level
        updated = False

        prompt = self._build_prompt(state, "")
        system_prompt = self._get_system_prompt(state.modality)
        try:
            result = _call_bedrock_anthropic(
                model=MODELS["extraction_escalate"],
                user_msg=prompt,
                system_prompt=system_prompt,
                max_tokens=400,
            )
            if valid_extraction_schema(result):
                state.finding    = result.get("finding", "")
                state.diagnosis  = result.get("diagnosis", "")
                state.laterality = result.get("laterality", "")
                state.models_used["extraction"] = MODELS["extraction_escalate"]
                state.extraction_self_check_passed = self._self_check(state)
                updated = True
        except Exception as e:
            log.warning(f"Escalated extraction failed: {e}")

        state.diagnosis_normalized = self.normalize_diagnosis(
            state.diagnosis, state.author_keywords, state.modality
        )
        state.title_match_quality = self.calc_title_match_quality(
            state.article_title, state.diagnosis_normalized or state.diagnosis
        )
        if updated or not prev_scope[2]:
            self.scope_finding_to_figure(state)
        else:
            # Escalation did not change the finding: keep the earlier pass-2 result.
            state.finding, state.finding_article_level, state.finding_scope = prev_scope
        return state

    # ── Pass 2: figure-scope finding ──────────────────────────────────────────

    def _call_scope_llm(self, user_msg: str, calls: list) -> Optional[dict]:
        """
        Call pass 2 with throttling waits and up to FIGURE_SCOPE_FORMAT_RETRIES
        extra attempts on JSON/format failure. Appends one record per call to
        `calls`. Returns the parsed dict, or None on failure.
        """
        from openredu.core.llm import _parse_json_response

        format_failures = 0
        throttles = 0
        while True:
            t0 = time.time()
            try:
                raw, tin, tout = self.scope_llm(user_msg)
            except Exception as e:
                if _is_throttling(e) and throttles < FIGURE_SCOPE_THROTTLE_RETRIES:
                    calls.append({"outcome": "throttled", "input_tokens": 0, "output_tokens": 0,
                                  "latency_s": round(time.time() - t0, 3)})
                    time.sleep(self.throttle_sleep(throttles))
                    throttles += 1
                    continue
                calls.append({"outcome": "error", "error": f"{type(e).__name__}: {str(e)[:200]}",
                              "input_tokens": 0, "output_tokens": 0, "latency_s": round(time.time() - t0, 3)})
                return None
            rec = {"input_tokens": tin, "output_tokens": tout, "latency_s": round(time.time() - t0, 3)}
            try:
                parsed = _parse_json_response(raw)
                if not isinstance(parsed.get("finding", ""), str):
                    raise ValueError("finding is not a string")
            except Exception as e:
                rec.update(outcome="format_error", error=str(e)[:200])
                calls.append(rec)
                format_failures += 1
                if format_failures > FIGURE_SCOPE_FORMAT_RETRIES:
                    return None
                continue
            rec["outcome"] = "ok"
            calls.append(rec)
            return parsed

    def scope_finding_to_figure(self, state: CaseState) -> CaseState:
        """
        Pass 2: rewrite state.finding from the target figure's evidence only.

        Deterministic handling of the result (no LLM):
          empty rewrite              -> keep article-level finding, SCOPE_FALLBACK_EMPTY
          word support < 0.5         -> keep article-level finding, SCOPE_FALLBACK_LOW_SUPPORT
          call/format failure        -> keep article-level finding, SCOPE_FALLBACK_ERROR
          otherwise                  -> state.finding = rewrite,   SCOPE_FIGURE
        Never writes "N/A" (valid_extraction_output would drop the case).
        Diagnosis, laterality, normalization and title match are not touched.
        """
        original = state.finding or ""
        if original.strip().lower() in ("", "extraction failed", "n/a"):
            state.agent_log.append({
                "agent": self.name, "decision": "route", "step": "figure_scope_finding",
                "reason": "pass 2 skipped: no article-level finding", "model": None,
                "prompt_version": FIGURE_SCOPE_PROMPT_VERSION,
                "ts": datetime.now(timezone.utc).isoformat(),
            })
            return state

        ev = build_evidence(state)
        user_msg = render_evidence(ev) + f"\n\n[ORIGINAL FINDING]\n{original}"
        calls: list = []
        result = self._call_scope_llm(user_msg, calls)

        new = ""
        removed = ""
        support_new = None
        if result is None:
            scope = SCOPE_FALLBACK_ERROR
        else:
            new = (result.get("finding") or "").strip()
            removed = result.get("removed", "") or ""
            support_new = support_ratio(new, evidence_text(ev))
            if not new:
                scope = SCOPE_FALLBACK_EMPTY
            elif support_new is not None and support_new < FIGURE_SCOPE_MIN_SUPPORT:
                scope = SCOPE_FALLBACK_LOW_SUPPORT
            else:
                scope = SCOPE_FIGURE

        state.finding_article_level = original
        state.finding_scope = scope
        if scope == SCOPE_FIGURE:
            state.finding = new
        state.models_used["figure_scope_finding"] = MODELS["extraction_primary"]
        state.agent_log.append({
            "agent": self.name,
            "decision": "accept" if scope == SCOPE_FIGURE else "route",
            "step": "figure_scope_finding",
            "reason": f"finding_scope={scope}",
            "model": MODELS["extraction_primary"],
            "prompt_version": FIGURE_SCOPE_PROMPT_VERSION,
            "temperature": FIGURE_SCOPE_TEMPERATURE,
            "finding_scope": scope,
            "removed": removed,
            "rewrite": new,
            "support_new": support_new,
            "support_article_level": support_ratio(original, evidence_text(ev)),
            "n_citing_sentences": ev["n_sentences"],
            "calls": calls,
            "input_tokens": sum(c["input_tokens"] for c in calls),
            "output_tokens": sum(c["output_tokens"] for c in calls),
            "ts": datetime.now(timezone.utc).isoformat(),
        })
        return state

    # ── Demographics ──────────────────────────────────────────────────────────

    def extract_demographics(
        self,
        figure_legend: str,
        results_text: str,
        case_text: str,
    ) -> dict:
        """
        Extract age and sex with priority: figure_legend > results_text > case_text.
        """
        def _extract(text: str) -> dict:
            age_m = AGE_PATTERN.search(text)
            sex_m = SEX_PATTERN.search(text)
            return {
                "age": int(age_m.group(1)) if age_m else None,
                "sex": SEX_MAP.get(sex_m.group(1).lower()) if sex_m else None,
            }

        demo = _extract(figure_legend)
        if demo["age"] is not None and demo["sex"] is not None:
            return demo

        demo2 = _extract(results_text)
        if demo["age"] is None:
            demo["age"] = demo2["age"]
        if demo["sex"] is None:
            demo["sex"] = demo2["sex"]
        if demo["age"] is not None and demo["sex"] is not None:
            return demo

        demo3 = _extract(case_text)
        if demo["age"] is None:
            demo["age"] = demo3["age"]
        if demo["sex"] is None:
            demo["sex"] = demo3["sex"]
        return demo

    # ── LLM helpers ───────────────────────────────────────────────────────────

    def _get_system_prompt(self, modality: str) -> str:
        cfg = _ALL_MODALITY_CONFIG.get(modality, {})
        prompt = cfg.get("llm_system_prompt", (
            'You are a radiology data curator. Extract structured information.\n'
            'Return ONLY valid JSON: {"finding": "...", "diagnosis": "...", "laterality": "..."}'
        ))
        if modality in _MODALITIES_REQUIRING_FIGURE_SCOPE_RULE:
            prompt += _COMMON_FIGURE_SCOPE_RULE
        return prompt

    def _build_prompt(self, state: CaseState, case_text_for_llm: str) -> str:
        kw_str = ", ".join(state.author_keywords) if state.author_keywords else "(not available)"
        return (
            f"Paper title: {state.article_title}\n\n"
            f"Author keywords: {kw_str}\n\n"
            f"Abstract: {state.abstract[:1000] or '(not available)'}\n\n"
            f"Case presentation: {case_text_for_llm[:2000] or '(not available)'}\n\n"
            f"Figure legend: {state.figure_caption}\n\n"
            f"Results text: {state.results_text or '(not available)'}"
        )

    def _self_check(self, state: CaseState) -> Optional[bool]:
        """
        Cheap self-check: ask LLM if extracted diagnosis matches caption.
        Returns True if consistent, False if not, None if check unavailable.
        """
        if not state.diagnosis or not state.figure_caption:
            return None
        from openredu.core.llm import _call_bedrock_anthropic

        user_msg = (
            f'Does the extracted diagnosis "{state.diagnosis}" match what the '
            f'figure caption describes?\n'
            f'Caption: {state.figure_caption[:500]}\n'
            f'Answer JSON only: {{"consistent": true/false, "reason": "one sentence"}}'
        )
        try:
            time.sleep(0.5)
            result = _call_bedrock_anthropic(
                model=MODELS["extraction_primary"],
                user_msg=user_msg,
                system_prompt=_SELF_CHECK_SYSTEM_PROMPT,
                max_tokens=100,
            )
            if valid_self_check_schema(result):
                return result.get("consistent")
        except Exception as e:
            log.debug(f"Self-check error: {e}")
        return None

    # ── Normalization ─────────────────────────────────────────────────────────

    def normalize_diagnosis(
        self,
        diagnosis: str,
        keywords: list,
        modality: str,
    ) -> str:
        """
        Normalize diagnosis:
        1. Author keyword match (exact substring, case-insensitive)
        2. Modality-specific normalization map
        3. Fallback: capitalize first letter
        """
        if not diagnosis or diagnosis in ("extraction failed", "N/A", "unclear"):
            return diagnosis

        diag_lower = diagnosis.lower()

        # 1. Author keyword match
        for kw in (keywords or []):
            if kw and kw.lower() in diag_lower:
                return kw

        # 2. Modality normalization map
        cfg = _ALL_MODALITY_CONFIG.get(modality, {})
        norm_map = cfg.get("diagnosis_normalization", {})
        for pattern, standard in norm_map.items():
            if pattern in diag_lower:
                return standard

        # 3. Capitalize first letter
        return diagnosis[0].upper() + diagnosis[1:] if len(diagnosis) > 1 else diagnosis.upper()

    def calc_title_match_quality(self, title: str, diagnosis: str) -> str:
        """
        Compute word overlap between article title and diagnosis.
        Returns "high" (≥2), "medium" (1), or "low" (0).
        """
        if not title or not diagnosis:
            return "low"
        title_words    = set(w.lower() for w in re.findall(r"\w+", title))
        diagnosis_words = set(w.lower() for w in re.findall(r"\w+", diagnosis))
        overlap = len((title_words & diagnosis_words) - TITLE_STOP_WORDS)
        if overlap >= 2:
            return "high"
        if overlap == 1:
            return "medium"
        return "low"
