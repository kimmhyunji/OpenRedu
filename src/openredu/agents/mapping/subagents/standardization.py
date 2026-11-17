"""
StandardizationSubagent: 3-layer concept resolution.

Layer 1 — MeSH (NCBI esearch/esummary, deterministic)
Layer 2 — SNOMED CT via UMLS TGT auth (deterministic)
Layer 3 — LLM concept decomposition + UMLS api_key search (LLM)

Each layer only runs if the previous layer missed.
Output: state.diagnosis_cuis, state.diagnosis_umls_preferred
"""
import logging
from openredu.core.base import Subagent
from openredu.core.state import CaseState
from openredu.config import MODELS
from openredu.tools.mesh_lookup import mesh_lookup
from openredu.tools.umls_client import (
    UMLSClient, snomed_lookup, call_concept_llm, best_cui, umls_search
)

log = logging.getLogger(__name__)

_umls_client: UMLSClient = None


def _get_umls_client() -> UMLSClient:
    global _umls_client
    if _umls_client is None:
        _umls_client = UMLSClient()
    return _umls_client


class StandardizationSubagent(Subagent):
    """
    Resolves a case diagnosis to UMLS CUI via 3-layer cascade.
    is_llm = True because Layer 3 uses LLM.
    """
    name = "StandardizationSubagent"
    is_llm = True

    def run(self, state: CaseState) -> CaseState:
        """
        Try Layer 1 → Layer 2 → Layer 3 in sequence.
        Stops at first successful CUI resolution.
        Skips entirely if CUIs are already populated (e.g. from backup).
        """
        if state.diagnosis_cuis:
            return state

        diagnosis = (state.diagnosis_normalized or state.diagnosis or "").strip()
        if not diagnosis or diagnosis in ("extraction failed", "N/A", "unclear", ""):
            return state

        # ── Layer 1: MeSH ─────────────────────────────────────────────────────
        result = self._layer1_mesh(diagnosis)
        if result:
            state.diagnosis_cuis          = [result["cui"]] if result.get("cui") else []
            state.diagnosis_umls_preferred = result.get("umls_preferred", "")
            if result.get("cui"):
                state.models_used["standardization"] = "MeSH"
                log.debug(f"[{state.case_id}] Layer1 CUI: {result['cui']}")
                return state

        # ── Layer 2: SNOMED CT ────────────────────────────────────────────────
        try:
            client = _get_umls_client()
            result = snomed_lookup(client, diagnosis)
            if result:
                state.diagnosis_cuis          = [result["cui"]]
                state.diagnosis_umls_preferred = result.get("snomed_preferred", "")
                state.models_used["standardization"] = "SNOMED"
                log.debug(f"[{state.case_id}] Layer2 CUI: {result['cui']}")
                return state
        except Exception as e:
            log.warning(f"Layer 2 SNOMED failed for {diagnosis!r}: {e}")

        # ── Layer 3: LLM + UMLS ───────────────────────────────────────────────
        try:
            parsed = call_concept_llm(diagnosis)
            if parsed and parsed.get("mappable", True):
                concepts = [c.lower().strip() for c in parsed.get("concepts", []) if c]
                cui, name = best_cui(concepts)
                if cui:
                    state.diagnosis_cuis          = [cui]
                    state.diagnosis_umls_preferred = name or ""
                    state.models_used["standardization"] = f"LLM+UMLS/{MODELS['standardization_llm']}"
                    log.debug(f"[{state.case_id}] Layer3 CUI: {cui}")
                    return state
        except Exception as e:
            log.warning(f"Layer 3 LLM+UMLS failed for {diagnosis!r}: {e}")

        # No CUI found — gracefully return with empty lists
        log.debug(f"[{state.case_id}] No CUI found for {diagnosis!r}")
        return state

    def _layer1_mesh(self, diagnosis: str) -> dict:
        """
        Try MeSH lookup. If a preferred term is found, also look up its CUI via UMLS.
        """
        result = mesh_lookup(diagnosis)
        if not result:
            return {}

        preferred = result["mesh_preferred"]
        # Get CUI for the MeSH preferred term via UMLS api_key search
        try:
            cui, name = umls_search(preferred)
            if cui:
                return {"cui": cui, "umls_preferred": name or preferred}
        except Exception as e:
            log.debug(f"UMLS CUI lookup for MeSH term failed: {e}")

        # Return without CUI — indicates Layer 1 partially matched
        return {"cui": None, "umls_preferred": preferred}
