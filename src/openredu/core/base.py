"""
Base classes for all OpenRedu agents.

MasterAgent: coordinates subagents with branching decisions. Every decision
is logged to state.agent_log so the pipeline is fully auditable.

Subagent: executes one focused task. is_llm must be declared explicitly.
"""
from datetime import datetime, timezone
from openredu.core.state import CaseState


class Subagent:
    """Base class for all subagents."""
    name: str = "Subagent"
    is_llm: bool = False   # MUST be overridden: True = LLM, False = deterministic

    def run(self, state: CaseState) -> CaseState:
        raise NotImplementedError(f"{self.name}.run() not implemented")


class MasterAgent:
    """
    Base class for master agents.

    Master agents coordinate subagents with ≥2 logged branching decisions
    among {accept, retry, escalate, route, drop}. This is required for the
    paper's agentic claim (§11).
    """
    name: str = "MasterAgent"
    model: str = ""        # higher-capacity model used for adjudication
    subagents: dict = {}

    def run(self, state: CaseState) -> CaseState:
        raise NotImplementedError(f"{self.name}.run() not implemented")

    def _log(
        self,
        state: CaseState,
        decision: str,
        reason: str,
        model: str = None,
    ) -> None:
        """
        Append a decision record to state.agent_log.

        decision must be one of: accept | retry | escalate | route | drop
        """
        valid = {"accept", "retry", "escalate", "route", "drop"}
        if decision not in valid:
            raise ValueError(f"Invalid decision '{decision}'. Must be one of {valid}")
        state.agent_log.append({
            "agent":    self.name,
            "decision": decision,
            "reason":   reason,
            "model":    model,
            "ts":       datetime.now(timezone.utc).isoformat(),
        })
