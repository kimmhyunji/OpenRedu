"""
CoverageSubagent: deterministic exposure tracking.

On each case-view event:
  1. Append to LearnerState.exposure_events
  2. Update LearnerState.coverage (per-APDR-topic encounter counts)
  3. Recompute derived views:
       completed_topics  (count >= COVERAGE_THRESHOLD)
       missing_topics    (count == 0)
       coverage_pct      (completed / total APDR topics)

This is the paper's central claim data:
"a learner's completed vs missing curriculum topics become visible."

Logic adapted from RadPathway users.py mastery aggregation pattern,
reimplemented without Neo4j — uses JSONL + Python dicts.
"""
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from openredu.core.base import Subagent
from openredu.core.state import LearnerState, CaseState
from openredu.config import COVERAGE_THRESHOLD, PATHS

log = logging.getLogger(__name__)


class CoverageSubagent(Subagent):
    """
    Deterministic coverage tracker.
    Maintains LearnerState against the APDR topic list.
    """
    name = "CoverageSubagent"
    is_llm = False

    def __init__(self, apdr_topics: list):
        """
        apdr_topics: list of topic dicts from build_apdr_index()
                     [{keyword_id, keyword, specialty, ...}, ...]
        """
        self.all_topic_ids = [t["keyword_id"] for t in apdr_topics if t.get("keyword_id")]
        self.total_topics = len(self.all_topic_ids)
        log.debug(f"CoverageSubagent: {self.total_topics} APDR topics loaded")

    def update(self, learner_state: LearnerState, case: CaseState) -> LearnerState:
        """
        Process one case-view event.
        Updates exposure_events, coverage, and derived views in-place.

        Args:
            learner_state: current learner state (mutated in-place)
            case:          CaseState of the viewed case
        Returns:
            updated LearnerState
        """
        topic_ids = case.curriculum_topics or []

        # 1. Append exposure event
        learner_state.exposure_events.append({
            "case_id":   case.case_id,
            "topic_ids": topic_ids,
            "ts":        datetime.now(timezone.utc).isoformat(),
        })

        # 2. Update per-topic encounter counts
        for tid in topic_ids:
            learner_state.coverage[tid] = learner_state.coverage.get(tid, 0) + 1

        # 3. Recompute derived views
        learner_state = self._recompute(learner_state)
        return learner_state

    def update_from_event(
        self,
        learner_state: LearnerState,
        case_id: str,
        topic_ids: list,
        ts: Optional[str] = None,
    ) -> LearnerState:
        """
        Process one case-view event from raw data (without a CaseState object).
        Used for serve-time integration where only case_id + topic_ids are available.
        """
        learner_state.exposure_events.append({
            "case_id":   case_id,
            "topic_ids": topic_ids,
            "ts":        ts or datetime.now(timezone.utc).isoformat(),
        })
        for tid in topic_ids:
            learner_state.coverage[tid] = learner_state.coverage.get(tid, 0) + 1

        learner_state = self._recompute(learner_state)
        return learner_state

    def _recompute(self, learner_state: LearnerState) -> LearnerState:
        """Recompute completed_topics, missing_topics, coverage_pct."""
        coverage = learner_state.coverage

        learner_state.completed_topics = [
            tid for tid in self.all_topic_ids
            if coverage.get(tid, 0) >= COVERAGE_THRESHOLD
        ]
        learner_state.missing_topics = [
            tid for tid in self.all_topic_ids
            if coverage.get(tid, 0) == 0
        ]
        learner_state.coverage_pct = (
            len(learner_state.completed_topics) / self.total_topics
            if self.total_topics > 0 else 0.0
        )
        return learner_state

    def get_summary(self, learner_state: LearnerState) -> dict:
        """Return a human-readable coverage summary dict."""
        coverage = learner_state.coverage
        under_covered = [
            tid for tid in self.all_topic_ids
            if 0 < coverage.get(tid, 0) < COVERAGE_THRESHOLD
        ]
        return {
            "learner_id":       learner_state.learner_id,
            "total_topics":     self.total_topics,
            "completed":        len(learner_state.completed_topics),
            "under_covered":    len(under_covered),
            "missing":          len(learner_state.missing_topics),
            "coverage_pct":     round(learner_state.coverage_pct * 100, 1),
            "total_events":     len(learner_state.exposure_events),
            "threshold":        COVERAGE_THRESHOLD,
        }

    def get_specialty_breakdown(self, learner_state: LearnerState, apdr_topics: list) -> dict:
        """
        Coverage breakdown by specialty (APDR division).
        Returns {specialty: {completed, missing, total, coverage_pct}}
        Adapted from RadPathway mastery_by_rotation pattern.
        """
        # Build specialty → topic_ids map
        specialty_map: dict = {}
        for t in apdr_topics:
            spec = t.get("specialty", "Unknown")
            tid  = t.get("keyword_id", "")
            if tid:
                specialty_map.setdefault(spec, []).append(tid)

        breakdown = {}
        coverage = learner_state.coverage
        for spec, tids in sorted(specialty_map.items()):
            completed = sum(1 for tid in tids if coverage.get(tid, 0) >= COVERAGE_THRESHOLD)
            missing   = sum(1 for tid in tids if coverage.get(tid, 0) == 0)
            total     = len(tids)
            breakdown[spec] = {
                "completed":    completed,
                "missing":      missing,
                "total":        total,
                "coverage_pct": round(completed / total * 100, 1) if total else 0.0,
            }
        return breakdown
