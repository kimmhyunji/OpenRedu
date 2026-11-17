"""
CurationMasterAgent: orchestrates retrieval → classification → extraction
with 8 explicit branch points, each logged to state.agent_log.

This is the central agentic component of the curation pipeline. Every
decision it makes (accept/drop/retry/escalate/route) is logged, satisfying
the paper's agentic requirements §11 (②③④).
"""
import logging
from openredu.core.base import MasterAgent
from openredu.core.state import CaseState
from openredu.config import ALLOWED_LICENSES, MODELS
from openredu.agents.curation.subagents.retrieval import RetrievalSubagent
from openredu.agents.curation.subagents.classification import ClassificationSubagent
from openredu.agents.curation.subagents.extraction import (
    ExtractionSubagent, valid_extraction_output
)

log = logging.getLogger(__name__)


class CurationMasterAgent(MasterAgent):
    """
    Coordinates curation subagents with branching control flow.
    Every branch taken is logged for auditability and paper reproducibility.
    """
    name = "CurationMasterAgent"
    model = MODELS["classification_adjudicate"]   # Sonnet for adjudication

    def __init__(self, pmcid_counts=None, bypass_modality_exclude: bool = False,
                 verify: bool = False, verifier=None):
        self.subagents = {
            "retrieval":      RetrievalSubagent(),
            "classification": ClassificationSubagent(),
            "extraction":     ExtractionSubagent(pmcid_counts=pmcid_counts),
        }
        self.bypass_modality_exclude = bypass_modality_exclude
        # Opt-in Branch 9. Default False keeps run_pipeline() behaviour unchanged.
        self.verify = verify
        if verify:
            from openredu.agents.curation.subagents.verification import VerificationSubagent
            self.subagents["verification"] = verifier or VerificationSubagent()

    def run(self, state: CaseState) -> CaseState:
        """
        Main control flow with 8 branch points.
        Each branch appends a decision record to state.agent_log.
        """

        # ── Branch 1: License check ─────────────────────────────────────────
        if state.license not in ALLOWED_LICENSES:
            self._log(state, "drop",
                      f"license='{state.license}' not in allowed list")
            state.status = "rejected"
            return state

        # ── Branch 2: Figure caption present ────────────────────────────────
        if not state.figure_caption:
            self._log(state, "drop", "figure_caption is empty — no extractable figure")
            state.status = "rejected"
            return state

        # ── Classify ─────────────────────────────────────────────────────────
        state = self.subagents["classification"].run(
            state, bypass_modality_exclude=self.bypass_modality_exclude
        )

        # ── Branch 3: Rule exclude ───────────────────────────────────────────
        if state.classification_route == "rule_exclude":
            self._log(state, "drop",
                      f"exclude keyword matched in caption (modality={state.modality})")
            state.status = "rejected"
            return state

        # ── Branch 4: UNCERTAIN → reject ──────────────────────────────────────
        # A caption without an explicit modality keyword is rejected, so that
        # non-radiologic images (EEG, surgical photographs, fundus images) are kept out.
        # (LLM adjudication is used only when extraction fails after rule_include)
        if state.classification_route == "uncertain_pending":
            self._log(state, "drop",
                      f"UNCERTAIN: no {state.modality} keyword in caption — rejected "
                      "to prevent non-radiologic images entering curriculum mapping")
            state.status = "rejected"
            return state

        # rule_include confirmed
        self._log(state, "accept",
                  f"classification_route={state.classification_route}")

        # ── Branch 5: Multipanel flag ────────────────────────────────────────
        if state.is_multipanel:
            self._log(state, "route",
                      f"multipanel detected: panel_count={state.panel_count}; "
                      "flagged (no caption splitting this build)")
            # Continue with full caption

        # ── Extract ───────────────────────────────────────────────────────────
        state = self.subagents["extraction"].run(state)

        # ── Branch 6: Extraction invalid → retry with escalation ─────────────
        if not valid_extraction_output(state):
            self._log(state, "retry",
                      "extraction output invalid; escalating to Sonnet",
                      model=MODELS["extraction_escalate"])
            state = self.subagents["extraction"].run_escalated(state)

        # ── Branch 7: Still invalid after escalation → fail ──────────────────
        if not valid_extraction_output(state):
            self._log(state, "drop",
                      "extraction failed after all LLM tiers")
            state.status = "failed"
            return state

        # ── Branch 8: Self-check inconsistency → one more escalation ─────────
        if state.extraction_self_check_passed is False:
            self._log(state, "escalate",
                      "self-check failed: diagnosis inconsistent with caption; "
                      "forced re-extraction with Sonnet",
                      model=MODELS["extraction_escalate"])
            state = self.subagents["extraction"].run_escalated(state)

        # ── Accept ───────────────────────────────────────────────────────────
        self._log(state, "accept",
                  f"extraction ok; model={state.models_used.get('extraction', 'unknown')}",
                  model=state.models_used.get("extraction"))
        state.status = "extracted"

        if self.verify:
            state = self._verification_branch(state)
        return state

    def _verification_branch(self, state: CaseState) -> CaseState:
        """
        Branch 9 (opt-in): independent text-only verification.
        Same disposition as the corpus: classification not_supported → excluded;
        finding not_supported → kept with a Needs review flag.
        """
        state = self.subagents["verification"].run(state)
        v = state.verification
        model = state.models_used.get("verification")
        if not v.get("ok"):
            self._log(state, "route",
                      "verifier returned no valid verdict; case kept without verification", model=model)
        elif v.get("classification") == "not_supported":
            self._log(state, "drop", "verifier: category not supported by figure text", model=model)
            state.status = "rejected"
        elif v.get("finding") == "not_supported":
            v["needs_review"] = True
            self._log(state, "route",
                      "verifier: finding not supported by figure text; kept with Needs review flag",
                      model=model)
        else:
            self._log(state, "accept", "verifier: no unsupported category or finding", model=model)
        return state
