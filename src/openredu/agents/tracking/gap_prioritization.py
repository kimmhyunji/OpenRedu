"""
GapPrioritizationSubagent: LLM-based gap ordering.

Input:  LearnerState (coverage, missing_topics) + APDR topic metadata
Output: Ordered list of topics to study next, with reasoning

The counting (which topics are missing/under-covered) is deterministic
and computed by CoverageSubagent. Only the *ordering judgment* — which
gaps matter most clinically — uses the language model.

Adapted from RadPathway gap_priority logic (required_for_mvp → high,
required_for_final → medium), extended with LLM clinical judgment.
"""
import json
import logging
import time
from typing import Optional

from openredu.core.base import Subagent
from openredu.core.state import LearnerState
from openredu.config import MODELS
from openredu.core.llm import _call_bedrock_anthropic

log = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are a radiology education expert helping a resident prioritize their learning.

Given a learner's coverage data and a list of uncovered APDR curriculum topics,
return an ordered list of the most important topics to study next.

Prioritization criteria:
1. High-yield / must-see diagnoses that every radiologist must recognize
2. Topics with clinical urgency (life-threatening conditions, common presentations)
3. Topics that build foundation for other topics (basics before complex)
4. Balance across subspecialties — avoid clustering all in one area

Return JSON only:
{
  "prioritized_topics": [
    {"topic_id": "...", "topic_name": "...", "reason": "one sentence why this is high priority"},
    ...
  ],
  "summary": "one sentence overall learning recommendation"
}

Return at most 10 topics. Focus on quality of reasoning, not quantity."""


def _build_prompt(
    learner_state: LearnerState,
    missing_topics: list,
    under_covered_topics: list,
    apdr_topic_map: dict,
    coverage_summary: dict,
) -> str:
    """Build user prompt with learner context and gap list."""
    total   = coverage_summary.get("total_topics", 0)
    done    = coverage_summary.get("completed", 0)
    pct     = coverage_summary.get("coverage_pct", 0.0)
    events  = coverage_summary.get("total_events", 0)

    lines = [
        f"Learner has viewed {events} cases covering {done}/{total} topics ({pct}%).",
        "",
        "MISSING topics (never encountered):",
    ]
    for tid in missing_topics[:30]:  # cap at 30 for prompt length
        name = apdr_topic_map.get(tid, {}).get("keyword", tid)
        spec = apdr_topic_map.get(tid, {}).get("specialty", "")
        lines.append(f"  - [{spec}] {name} (id: {tid})")

    if under_covered_topics:
        lines.append("")
        lines.append("UNDER-COVERED topics (seen fewer than threshold times):")
        for tid in under_covered_topics[:15]:
            name  = apdr_topic_map.get(tid, {}).get("keyword", tid)
            spec  = apdr_topic_map.get(tid, {}).get("specialty", "")
            count = learner_state.coverage.get(tid, 0)
            lines.append(f"  - [{spec}] {name} (seen {count}x, id: {tid})")

    lines.append("")
    lines.append("Which topics should this learner prioritize studying next, and why?")
    return "\n".join(lines)


class GapPrioritizationSubagent(Subagent):
    """
    LLM-based gap ordering.
    Counting stays deterministic (CoverageSubagent); ordering uses LLM judgment.
    """
    name = "GapPrioritizationSubagent"
    is_llm = True

    def __init__(self, apdr_topics: list, coverage_subagent=None):
        """
        apdr_topics:       full list of APDR topic dicts
        coverage_subagent: CoverageSubagent instance (for get_summary)
        """
        self.apdr_topic_map = {
            t["keyword_id"]: t for t in apdr_topics if t.get("keyword_id")
        }
        self.all_topic_ids = list(self.apdr_topic_map.keys())
        self.coverage_subagent = coverage_subagent
        self.all_topic_ids = list(self.apdr_topic_map.keys())

    def run(
        self,
        learner_state: LearnerState,
        max_gaps: int = 10,
    ) -> list:
        """
        Return prioritized list of gap topic dicts.

        Returns:
            [{"topic_id": str, "topic_name": str, "reason": str}, ...]
            Empty list if no gaps or LLM fails.
        """
        coverage = learner_state.coverage
        from openredu.config import COVERAGE_THRESHOLD

        missing = [tid for tid in self.all_topic_ids if coverage.get(tid, 0) == 0]
        under   = [
            tid for tid in self.all_topic_ids
            if 0 < coverage.get(tid, 0) < COVERAGE_THRESHOLD
        ]

        if not missing and not under:
            log.info(f"[{learner_state.learner_id}] No gaps — full coverage achieved")
            return []

        summary = {}
        if self.coverage_subagent:
            summary = self.coverage_subagent.get_summary(learner_state)

        prompt = _build_prompt(
            learner_state, missing, under, self.apdr_topic_map, summary
        )

        for attempt in range(3):
            try:
                time.sleep(1)
                result = _call_bedrock_anthropic(
                    model=MODELS["gap_prioritization"],
                    user_msg=prompt,
                    system_prompt=_SYSTEM_PROMPT,
                    max_tokens=800,
                )
                # Handle both {"prioritized_topics": [...]} and direct list/dict
                if isinstance(result, list):
                    topics = result
                elif isinstance(result, dict):
                    topics = result.get("prioritized_topics", [])
                    # If LLM returned a single topic dict directly
                    if not topics and "topic_id" in result:
                        topics = [result]
                else:
                    topics = []

                if isinstance(topics, list):
                    log.info(
                        f"[{learner_state.learner_id}] Gap prioritization: "
                        f"{len(topics)} topics returned"
                    )
                    return topics[:max_gaps]
                log.warning(f"Gap prioritization attempt {attempt+1}: unexpected format {type(topics)}")
            except Exception as e:
                log.warning(f"Gap prioritization attempt {attempt+1} error: {e}")
                time.sleep(3 * (attempt + 1))

        # Fallback: deterministic priority (missing first, then under-covered)
        log.warning("Gap prioritization LLM failed — using deterministic fallback")
        fallback = []
        for tid in (missing + under)[:max_gaps]:
            name = self.apdr_topic_map.get(tid, {}).get("keyword", tid)
            spec = self.apdr_topic_map.get(tid, {}).get("specialty", "")
            fallback.append({
                "topic_id":   tid,
                "topic_name": name,
                "specialty":  spec,
                "reason":     "Not yet encountered" if tid in missing else "Under-covered",
            })
        return fallback
