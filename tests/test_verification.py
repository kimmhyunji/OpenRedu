"""Tests for VerificationSubagent. The verifier client is a fake; no AWS calls.

The key test compares the request this subagent builds with the one built by
pipeline/step2_verifier.py, the script that verified the corpus.
"""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

from openredu.agents.curation.master import CurationMasterAgent
from openredu.agents.curation.subagents import verification as vf
from openredu.core.state import CaseState

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "pipeline" / "step2_verifier.py"
CORPUS = REPO / "examples" / "synthetic_cases.jsonl"   # invented cases, not study data

needs_repo_data = pytest.mark.skipif(
    not (SCRIPT.exists() and CORPUS.exists()), reason="pipeline script or synthetic cases not present")


def _load_script():
    sys.path.insert(0, str(SCRIPT.parent))
    spec = importlib.util.spec_from_file_location("step2_verifier_under_test", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _sample_cases(n=400):
    n = min(n, 5)
    rows = [json.loads(line) for line in CORPUS.open()]
    step = max(1, len(rows) // n)
    return rows[::step][:n]


VALID = {
    "classification": {"verdict": "supported"}, "finding": {"verdict": "supported"},
    "laterality": {"verdict": "unclear"}, "diagnosis_article": {"verdict": "supported"},
    "conditions": [],
}


class FakeClient:
    def __init__(self, parsed):
        self.parsed = parsed
        self.requests = []

    def converse(self, **kw):
        self.requests.append(kw)
        text = "<reasoning>x</reasoning>" + json.dumps(self.parsed)
        return {"output": {"message": {"content": [{"text": text}]}},
                "usage": {"inputTokens": 1, "outputTokens": 1}, "stopReason": "end_turn"}


@needs_repo_data
def test_prompt_and_user_message_match_script_on_corpus_sample():
    script = _load_script()
    system, template = script.load_prompt()
    sub = vf.VerificationSubagent(client=FakeClient(VALID))
    assert sub.system == system and sub.template == template
    assert vf.CATEGORY_TEXT == script.CATEGORY_TEXT
    for c in _sample_cases():
        assert vf.build_user(c, template) == script.build_user(c, template), c["case_id"]


@needs_repo_data
def test_request_matches_script_runner(tmp_path):
    script = _load_script()
    case = _sample_cases(5)[2]
    fake_script, fake_sub = FakeClient(VALID), FakeClient(VALID)
    runner = script.Runner("nova-pro", tmp_path)
    runner.client = fake_script
    runner.call(case)
    sub = vf.VerificationSubagent(client=fake_sub)
    sub.verify_case(case)
    assert fake_sub.requests == fake_script.requests
    assert fake_sub.requests[0]["modelId"] == script.V["models"]["nova-pro"]["model_id"]
    assert fake_sub.requests[0]["inferenceConfig"] == {"temperature": 0, "maxTokens": 3000}


def test_valid_rejects_missing_or_bad_verdict():
    assert vf.valid(VALID)
    assert not vf.valid({**VALID, "finding": {"verdict": "maybe"}})
    assert not vf.valid(None)


def test_unusable_json_is_asked_once_more_then_fails():
    fake = FakeClient({"not": "valid"})
    rec = vf.VerificationSubagent(client=fake).verify_case({"case_id": "X_F1", "figure_caption": "c"})
    assert not rec["ok"] and len(fake.requests) == 2


def _state():
    return CaseState(case_id="PMC1_F1", pmcid="PMC1", modality="CT_CHEST", figure_caption="Axial CT.",
                     finding="mass", diagnosis="carcinoma", status="extracted")


class FakeVerifier:
    def __init__(self, classification="supported", finding="supported", ok=True):
        self.v = {"ok": ok, "classification": classification, "finding": finding}

    def run(self, state):
        state.verification = dict(self.v)
        state.models_used["verification"] = "fake"
        return state


def _master(verifier):
    m = CurationMasterAgent.__new__(CurationMasterAgent)
    m.subagents = {"verification": verifier}
    return m


def test_branch_excludes_classification_not_supported():
    s = _master(FakeVerifier(classification="not_supported"))._verification_branch(_state())
    assert s.status == "rejected" and s.agent_log[-1]["decision"] == "drop"


def test_branch_flags_finding_not_supported_but_keeps_case():
    s = _master(FakeVerifier(finding="not_supported"))._verification_branch(_state())
    assert s.status == "extracted" and s.verification["needs_review"] is True
    assert s.agent_log[-1]["decision"] == "route"


def test_branch_keeps_case_when_verifier_fails():
    s = _master(FakeVerifier(ok=False))._verification_branch(_state())
    assert s.status == "extracted" and not s.verification.get("needs_review")
    assert s.agent_log[-1]["decision"] == "route"


def test_branch_accepts_supported_case():
    s = _master(FakeVerifier())._verification_branch(_state())
    assert s.status == "extracted" and s.agent_log[-1]["decision"] == "accept"


def test_default_master_does_not_verify():
    assert CurationMasterAgent().verify is False
    assert "verification" not in CurationMasterAgent().subagents
