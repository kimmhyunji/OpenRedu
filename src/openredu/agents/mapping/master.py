"""
MappingMasterAgent: coordinates standardization → matching
with 4 explicit branch points, each logged to state.agent_log.
"""
import logging
from openredu.core.base import MasterAgent
from openredu.core.state import CaseState
from openredu.config import MODELS
from openredu.agents.mapping.subagents.standardization import StandardizationSubagent
from openredu.agents.mapping.subagents.matching import MatchingSubagent
from openredu.agents.mapping.subagents.guideline_ingestion import GuidelineIngestionSubagent

log = logging.getLogger(__name__)


class MappingMasterAgent(MasterAgent):
    """
    Resolves case diagnoses to UMLS CUIs and maps them to APDR curriculum topics.
    4 branch points, all logged.
    """
    name = "MappingMasterAgent"
    model = MODELS["mapping_adjudicate"]   # Sonnet

    def __init__(self, apdr_topics: list, kw_to_synonyms: dict, kw_to_cui: dict):
        self.subagents = {
            "guideline_ingestion": GuidelineIngestionSubagent(),
            "standardization": StandardizationSubagent(),
            "matching": MatchingSubagent(
                apdr_topics=apdr_topics,
                kw_to_synonyms=kw_to_synonyms,
                kw_to_cui=kw_to_cui,
            ),
        }

    def run(self, state: CaseState) -> CaseState:
        """
        Control flow with 4 branch points.
        """

        # ── Standardize (3-layer CUI resolution) ─────────────────────────────
        state = self.subagents["standardization"].run(state)

        # ── Branch 1: CUI resolution outcome ─────────────────────────────────
        if not state.diagnosis_cuis:
            self._log(state, "route",
                      "no CUI after MeSH+SNOMED+LLM; proceeding with text-only matching")
        else:
            self._log(state, "accept",
                      f"CUI resolved: {state.diagnosis_cuis[0]} = {state.diagnosis_umls_preferred}",
                      model=state.models_used.get("standardization"))

        # Set dedup group by first CUI
        if state.diagnosis_cuis:
            state.dedup_group_id = state.diagnosis_cuis[0]

        # ── Match to APDR topics ──────────────────────────────────────────────
        state = self.subagents["matching"].run(state)

        # ── Branch 2: No match → retry with broader synonyms ─────────────────
        if not state.curriculum_topics:
            self._log(state, "retry",
                      "no APDR topics matched; retrying with broad synonym matching")
            state = self.subagents["matching"].run_with_broader_synonyms(state)

        # ── Branch 3: Still no match → route to unmapped ──────────────────────
        if not state.curriculum_topics:
            self._log(state, "route",
                      "no APDR topics matched after synonym broadening; status=unmapped")
            state.status = "unmapped"
            return state

        # ── Branch 4: High match count → flag for ambiguity ──────────────────
        if len(state.curriculum_topics) > 10:
            self._log(state, "escalate",
                      f"high match count ({len(state.curriculum_topics)}): "
                      "flagged for ambiguity review",
                      model=None)

        self._log(state, "accept",
                  f"mapped to {len(state.curriculum_topics)} APDR topics "
                  f"via {state.mapping_paths}")
        state.status = "mapped"
        return state
