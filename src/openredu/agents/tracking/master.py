"""
TrackingMasterAgent: coordinates coverage tracking, gap prioritization,
and flashcard assessment.

Operates at serve-time, per-learner. Central paper claim:
"a learner's completed vs missing curriculum topics become visible."

4 branch points (all logged):
  1. Zero-coverage threshold check → route to gap emphasis
  2. Full coverage achieved → accept (done)
  3. Practice requested → route to AssessmentSubagent
  4. Topic has no flashcards → escalate (cases-only fallback)

Demonstrated on synthetic/example learners — no real user data.
"""
import json
import logging
from pathlib import Path
from typing import Optional

from openredu.core.base import MasterAgent
from openredu.core.state import LearnerState
from openredu.config import MODELS, PATHS
from openredu.agents.tracking.coverage import CoverageSubagent
from openredu.agents.tracking.gap_prioritization import GapPrioritizationSubagent
from openredu.agents.tracking.assessment import AssessmentSubagent

log = logging.getLogger(__name__)

# A learner with > this fraction of topics at zero → flag as "needs more exposure"
GAP_ALERT_THRESHOLD = 0.5


class TrackingMasterAgent(MasterAgent):
    """
    Coordinates CoverageSubagent → GapPrioritizationSubagent → AssessmentSubagent.
    All decisions logged to learner_state-level agent_log.
    """
    name = "TrackingMasterAgent"
    model = MODELS["gap_prioritization"]  # Sonnet — for gap ordering judgment

    def __init__(
        self,
        apdr_topics: list,
        corpus_cases: list,
    ):
        coverage_sub = CoverageSubagent(apdr_topics)
        self.subagents = {
            "coverage":     coverage_sub,
            "gap":          GapPrioritizationSubagent(apdr_topics, coverage_sub),
            "assessment":   AssessmentSubagent(corpus_cases),
        }
        self.apdr_topics = apdr_topics

    def run(
        self,
        learner_state: LearnerState,
        event_case_id: str,
        event_topic_ids: list,
        practice_topic_id: Optional[str] = None,
        event_ts: Optional[str] = None,
    ) -> dict:
        """
        Process one learner interaction.

        Args:
            learner_state:      current LearnerState (mutated in-place)
            event_case_id:      case_id the learner just viewed
            event_topic_ids:    APDR topic_ids of that case
            practice_topic_id:  if set, generate flashcards for this topic
            event_ts:           ISO timestamp (defaults to now)

        Returns dict with:
            learner_state:      updated LearnerState
            coverage_summary:   {total, completed, missing, coverage_pct, ...}
            specialty_breakdown:{specialty: {completed, missing, total, pct}}
            prioritized_gaps:   [{topic_id, topic_name, reason}, ...]
            flashcards:         assessment result if practice_topic_id was set
            agent_log:          decisions taken this turn
        """
        turn_log = []

        def _log(decision: str, reason: str, model: str = None):
            from datetime import datetime, timezone
            entry = {
                "agent":    self.name,
                "decision": decision,
                "reason":   reason,
                "model":    model,
                "ts":       datetime.now(timezone.utc).isoformat(),
            }
            turn_log.append(entry)
            log.info(f"[{learner_state.learner_id}] {decision}: {reason}")

        # ── Step 1: Coverage update (deterministic) ───────────────────────────
        learner_state = self.subagents["coverage"].update_from_event(
            learner_state, event_case_id, event_topic_ids, event_ts
        )
        coverage_summary = self.subagents["coverage"].get_summary(learner_state)
        specialty_breakdown = self.subagents["coverage"].get_specialty_breakdown(
            learner_state, self.apdr_topics
        )

        # ── Branch 1: Zero-coverage alert ─────────────────────────────────────
        missing_frac = (
            len(learner_state.missing_topics) / coverage_summary["total_topics"]
            if coverage_summary["total_topics"] > 0 else 0.0
        )
        if missing_frac > GAP_ALERT_THRESHOLD:
            _log("route",
                 f"{len(learner_state.missing_topics)}/{coverage_summary['total_topics']} "
                 f"topics ({missing_frac*100:.0f}%) never seen — gap emphasis active")
        else:
            _log("accept",
                 f"coverage update: {coverage_summary['coverage_pct']}% complete "
                 f"({coverage_summary['completed']}/{coverage_summary['total_topics']} topics)")

        # ── Branch 2: Full coverage check ─────────────────────────────────────
        if learner_state.coverage_pct >= 1.0:
            _log("accept", "full coverage achieved — all APDR topics encountered")
            return {
                "learner_state":      learner_state,
                "coverage_summary":   coverage_summary,
                "specialty_breakdown": specialty_breakdown,
                "prioritized_gaps":   [],
                "flashcards":         None,
                "agent_log":          turn_log,
            }

        # ── Step 2: Gap prioritization (LLM) ─────────────────────────────────
        prioritized_gaps = self.subagents["gap"].run(learner_state)
        if prioritized_gaps:
            _log("accept",
                 f"gap prioritization: top gap = {prioritized_gaps[0].get('topic_name','')}",
                 model=self.model)
        else:
            _log("accept", "no actionable gaps found", model=self.model)

        # ── Branch 3: Practice requested ──────────────────────────────────────
        flashcards = None
        if practice_topic_id:
            stats = self.subagents["assessment"].get_topic_stats(practice_topic_id)

            # ── Branch 4: Topic has no flashcards → escalate ──────────────────
            if stats["n_cases"] == 0:
                _log("escalate",
                     f"topic {practice_topic_id} has no cases in corpus — "
                     "flashcards unavailable; returning gap list only")
            else:
                flashcards = self.subagents["assessment"].run(practice_topic_id)
                _log("route",
                     f"assessment: {len(flashcards['cards'])} flashcards for "
                     f"topic {practice_topic_id} ({stats['n_cases']} total cases)")

        return {
            "learner_state":       learner_state,
            "coverage_summary":    coverage_summary,
            "specialty_breakdown": specialty_breakdown,
            "prioritized_gaps":    prioritized_gaps,
            "flashcards":          flashcards,
            "agent_log":           turn_log,
        }

    def initialize_learner(self, learner_id: str) -> LearnerState:
        """Create a fresh LearnerState for a new learner."""
        return LearnerState(learner_id=learner_id)

    def load_learner(self, learner_id: str) -> Optional[LearnerState]:
        """
        Load persisted LearnerState from JSONL checkpoint.
        Returns None if no saved state exists.
        """
        path = PATHS["data"] / "learners" / f"{learner_id}.json"
        if not path.exists():
            return None
        try:
            d = json.loads(path.read_text())
            return LearnerState(**{
                k: v for k, v in d.items()
                if k in LearnerState.__dataclass_fields__
            })
        except Exception as e:
            log.warning(f"Failed to load learner {learner_id}: {e}")
            return None

    def save_learner(self, learner_state: LearnerState) -> None:
        """Persist LearnerState to JSON file."""
        import dataclasses
        path = PATHS["data"] / "learners"
        path.mkdir(parents=True, exist_ok=True)
        out = path / f"{learner_state.learner_id}.json"
        out.write_text(json.dumps(dataclasses.asdict(learner_state), ensure_ascii=False))
