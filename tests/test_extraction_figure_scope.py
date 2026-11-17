"""Tests for ExtractionSubagent pass 2 (figure-scope finding). The LLM is a fake function."""
import json

import pytest

from openredu.agents.curation.subagents import extraction as ex
from openredu.agents.curation.subagents.extraction import (
    ExtractionSubagent,
    FIGURE_SCOPE_PROMPT_VERSION,
    SCOPE_FALLBACK_EMPTY,
    SCOPE_FALLBACK_ERROR,
    SCOPE_FALLBACK_LOW_SUPPORT,
    SCOPE_FIGURE,
    valid_extraction_output,
)
from openredu.core import llm
from openredu.core.state import CaseState

ARTICLE_FINDING = (
    "Contrast CT showed a 4 cm hypodense hepatic mass; follow-up MRI after chemotherapy showed "
    "regression, and biopsy confirmed hepatocellular carcinoma."
)


def _state():
    return CaseState(
        case_id="PMC1_F2",
        pmcid="PMC1",
        modality="CT_ABDOMEN",
        figure_label="Figure 2",
        figure_caption="Axial contrast-enhanced CT shows a hypodense mass in the right hepatic lobe.",
        results_text=(
            "The patient was admitted. Axial CT (Figure 2) demonstrated a hypodense hepatic mass with "
            "arterial enhancement. Follow-up MRI (Figure 3) showed regression."
        ),
        finding=ARTICLE_FINDING,
        diagnosis="Hepatocellular carcinoma",
        diagnosis_normalized="Hepatocellular carcinoma",
        laterality="right",
        title_match_quality="high",
    )


def _fake(responses):
    """Fake pass-2 LLM. Each response is a raw string, a dict (JSON-encoded) or an Exception."""
    seen = []

    def call(user_msg):
        seen.append(user_msg)
        r = responses[min(len(seen) - 1, len(responses) - 1)]
        if isinstance(r, Exception):
            raise r
        raw = r if isinstance(r, str) else json.dumps(r)
        return raw, 100, 20

    call.seen = seen
    return call


def _sub(responses):
    fake = _fake(responses)
    return ExtractionSubagent(scope_llm=fake, throttle_sleep=lambda attempt: 0), fake


def _last_log(state):
    return [e for e in state.agent_log if e.get("step") == "figure_scope_finding"][-1]


def test_normal_rewrite_replaces_finding():
    rewrite = "Hypodense mass in the right hepatic lobe with arterial enhancement on axial contrast-enhanced CT."
    sub, fake = _sub([{"finding": rewrite, "removed": "Removed follow-up MRI and biopsy."}])
    s = sub.scope_finding_to_figure(_state())
    assert s.finding == rewrite
    assert s.finding_scope == SCOPE_FIGURE
    assert s.finding_article_level == ARTICLE_FINDING
    log = _last_log(s)
    assert log["prompt_version"] == FIGURE_SCOPE_PROMPT_VERSION
    assert log["removed"] == "Removed follow-up MRI and biopsy."
    assert log["input_tokens"] == 100 and log["output_tokens"] == 20
    # prompt = rendered figure evidence + the original finding; the other figure's sentence is not sent
    msg = fake.seen[0]
    assert "[FIGURE CAPTION — Figure 2]" in msg
    assert msg.endswith("[ORIGINAL FINDING]\n" + ARTICLE_FINDING)
    assert "Figure 3" not in msg


def test_empty_rewrite_keeps_article_finding():
    sub, _ = _sub([{"finding": "", "removed": "No imaging finding for this figure."}])
    s = sub.scope_finding_to_figure(_state())
    assert s.finding == ARTICLE_FINDING
    assert s.finding_scope == SCOPE_FALLBACK_EMPTY
    assert s.finding_article_level == ARTICLE_FINDING
    assert valid_extraction_output(s)  # never N/A, so the case is not dropped


def test_low_support_rewrite_keeps_article_finding():
    # words not in caption/cited sentences -> support < 0.5
    sub, _ = _sub([{"finding": "Pericardial effusion and pleural thickening bilaterally", "removed": ""}])
    s = sub.scope_finding_to_figure(_state())
    assert s.finding == ARTICLE_FINDING
    assert s.finding_scope == SCOPE_FALLBACK_LOW_SUPPORT
    assert _last_log(s)["support_new"] < 0.5


def test_call_failure_keeps_article_finding():
    sub, _ = _sub([RuntimeError("boom")])
    s = sub.scope_finding_to_figure(_state())
    assert s.finding == ARTICLE_FINDING
    assert s.finding_scope == SCOPE_FALLBACK_ERROR
    assert _last_log(s)["calls"][0]["outcome"] == "error"


def test_format_failure_retries_twice_then_falls_back():
    sub, fake = _sub(["not json at all"])
    s = sub.scope_finding_to_figure(_state())
    assert len(fake.seen) == 3  # 1 + 2 retries
    assert s.finding_scope == SCOPE_FALLBACK_ERROR
    assert s.finding == ARTICLE_FINDING


def test_format_failure_then_success():
    rewrite = "Axial contrast-enhanced CT shows a hypodense mass in the right hepatic lobe."
    sub, fake = _sub(["oops", {"finding": rewrite, "removed": "x"}])
    s = sub.scope_finding_to_figure(_state())
    assert len(fake.seen) == 2
    assert s.finding == rewrite and s.finding_scope == SCOPE_FIGURE


def test_throttling_waits_and_retries():
    class ThrottlingException(Exception):
        pass

    rewrite = "Axial contrast-enhanced CT shows a hypodense mass in the right hepatic lobe."
    sub, fake = _sub([ThrottlingException("rate"), ThrottlingException("rate"), {"finding": rewrite, "removed": ""}])
    s = sub.scope_finding_to_figure(_state())
    assert len(fake.seen) == 3
    assert s.finding_scope == SCOPE_FIGURE
    assert [c["outcome"] for c in _last_log(s)["calls"]] == ["throttled", "throttled", "ok"]


def test_article_level_preserved_and_other_fields_untouched():
    rewrite = "Axial contrast-enhanced CT shows a hypodense mass in the right hepatic lobe."
    for resp in ([{"finding": rewrite}], [{"finding": ""}], [RuntimeError("x")]):
        sub, _ = _sub(resp)
        before = _state()
        s = sub.scope_finding_to_figure(_state())
        assert s.finding_article_level == ARTICLE_FINDING
        for f in ("diagnosis", "diagnosis_normalized", "laterality", "title_match_quality", "case_id"):
            assert getattr(s, f) == getattr(before, f)


def test_no_article_finding_skips_call():
    sub, fake = _sub([{"finding": "x"}])
    st = _state()
    st.finding = ""
    s = sub.scope_finding_to_figure(st)
    assert fake.seen == []
    assert s.finding_scope == ""


def test_new_fields_round_trip():
    sub, _ = _sub([{"finding": "Axial contrast-enhanced CT shows a hypodense mass in the right hepatic lobe."}])
    s = sub.scope_finding_to_figure(_state())
    d = json.loads(s.to_jsonl_line())
    assert d["finding_article_level"] == ARTICLE_FINDING and d["finding_scope"] == SCOPE_FIGURE
    back = CaseState.from_dict(d)
    assert back.finding_article_level == ARTICLE_FINDING and back.finding_scope == SCOPE_FIGURE
    # old records without the fields still load
    old = CaseState.from_dict({"case_id": "PMC2_F1", "finding": "f"})
    assert old.finding_article_level == "" and old.finding_scope == ""


def test_run_escalated_failure_keeps_previous_pass2(monkeypatch):
    """If escalation fails, pass 2 must not be re-run on an already-scoped finding."""
    rewrite = "Axial contrast-enhanced CT shows a hypodense mass in the right hepatic lobe."
    sub, fake = _sub([{"finding": rewrite}])
    s = sub.scope_finding_to_figure(_state())

    def boom(**kw):
        raise RuntimeError("escalation down")

    monkeypatch.setattr(llm, "_call_bedrock_anthropic", boom)
    s = sub.run_escalated(s)
    assert len(fake.seen) == 1
    assert s.finding == rewrite
    assert s.finding_article_level == ARTICLE_FINDING
    assert s.finding_scope == SCOPE_FIGURE


def test_run_escalated_success_rescopes_new_finding(monkeypatch):
    sub, fake = _sub([{"finding": "Axial contrast-enhanced CT shows a hypodense mass in the right hepatic lobe."}])
    s = sub.scope_finding_to_figure(_state())
    escalated = "Hypodense hepatic mass with arterial enhancement on CT."
    monkeypatch.setattr(llm, "_call_bedrock_anthropic", lambda **kw: (
        {"finding": escalated, "diagnosis": "Hepatocellular carcinoma", "laterality": "right"}))
    monkeypatch.setattr(ExtractionSubagent, "_self_check", lambda self, st: True)
    s = sub.run_escalated(s)
    assert len(fake.seen) == 2
    assert s.finding_article_level == escalated  # pass 2 ran on the new pass-1 finding


# ── Pass 1 unchanged ──────────────────────────────────────────────────────────

def test_pass1_request_body_unchanged():
    """Without temperature the request body is exactly the pre-revision one (no temperature key)."""
    body = llm._anthropic_body("u", "s", 400, None)
    assert body == json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 400,
        "system": "s",
        "messages": [{"role": "user", "content": "u"}],
    })
    assert json.loads(llm._anthropic_body("u", "s", 600, 0))["temperature"] == 0


def test_pass1_prompts_unchanged():
    sub = ExtractionSubagent()
    st = _state()
    assert sub._build_prompt(st, "").startswith("Paper title: ")
    assert ex._COMMON_FIGURE_SCOPE_RULE in sub._get_system_prompt("MRI_MSK")
    assert ex._COMMON_FIGURE_SCOPE_RULE not in sub._get_system_prompt("CT_CHEST")


def test_run_calls_pass2_and_keeps_diagnosis(monkeypatch):
    rewrite = "Axial contrast-enhanced CT shows a hypodense mass in the right hepatic lobe."
    sub, fake = _sub([{"finding": rewrite}])
    monkeypatch.setattr(ex, "llm_with_escalation", lambda **kw: (
        {"finding": ARTICLE_FINDING, "diagnosis": "Hepatocellular carcinoma", "laterality": "right"},
        "haiku", 1))
    monkeypatch.setattr(ExtractionSubagent, "_self_check", lambda self, st: True)
    monkeypatch.setattr(ex.time, "sleep", lambda s: None)
    st = _state()
    st.finding = ""
    s = sub.run(st)
    assert s.diagnosis == "Hepatocellular carcinoma" and s.laterality == "right"
    assert s.finding == rewrite and s.finding_article_level == ARTICLE_FINDING
    assert s.finding_scope == SCOPE_FIGURE
