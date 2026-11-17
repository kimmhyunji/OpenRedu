"""Tests for ExtractionSubagent (deterministic parts only — no LLM calls)."""
import pytest
from openredu.agents.curation.subagents.extraction import (
    ExtractionSubagent,
    _MODALITIES_REQUIRING_FIGURE_SCOPE_RULE,
)


@pytest.fixture
def sub():
    return ExtractionSubagent()


# ── Demographics ──────────────────────────────────────────────────────────────

def test_demographics_legend_priority(sub):
    demo = sub.extract_demographics(
        figure_legend="A 45-year-old male patient.",
        results_text="A 30-year-old female.",
        case_text="A 60-year-old man.",
    )
    assert demo["age"] == 45
    assert demo["sex"] == "M"


def test_demographics_results_fallback(sub):
    demo = sub.extract_demographics(
        figure_legend="CT scan showing consolidation.",
        results_text="A 38-year-old woman presented with cough.",
        case_text="A 60-year-old man.",
    )
    assert demo["age"] == 38
    assert demo["sex"] == "F"


def test_demographics_case_text_fallback(sub):
    demo = sub.extract_demographics(
        figure_legend="Chest X-ray findings.",
        results_text="Findings were noted.",
        case_text="A 55-year-old boy presented.",
    )
    assert demo["age"] == 55
    assert demo["sex"] == "M"


def test_demographics_none(sub):
    demo = sub.extract_demographics(
        figure_legend="PA chest radiograph.",
        results_text="Bilateral infiltrates noted.",
        case_text="The patient was treated with antibiotics.",
    )
    assert demo["age"] is None
    assert demo["sex"] is None


def test_demographics_age_patterns(sub):
    for text, expected_age in [
        ("A 5-year-old girl", 5),
        ("A 100-year-old male", 100),
        ("A 2 year old boy", 2),
    ]:
        demo = sub.extract_demographics(figure_legend=text, results_text="", case_text="")
        assert demo["age"] == expected_age, f"Failed for: {text}"


# ── Normalization ──────────────────────────────────────────────────────────────

def test_normalize_author_keyword_priority(sub):
    result = sub.normalize_diagnosis("glioblastoma multiforme", ["Glioblastoma"], "MRI_BRAIN")
    assert result == "Glioblastoma"


def test_normalize_modality_map(sub):
    result = sub.normalize_diagnosis("pulmonary embolism found on imaging", [], "CT_CHEST")
    assert result == "Pulmonary embolism"


def test_normalize_capitalize_fallback(sub):
    result = sub.normalize_diagnosis("unknown finding", [], "CXR")
    assert result == "Unknown finding"


def test_normalize_extraction_failed(sub):
    result = sub.normalize_diagnosis("extraction failed", [], "CXR")
    assert result == "extraction failed"


def test_normalize_empty(sub):
    result = sub.normalize_diagnosis("", [], "CXR")
    assert result == ""


# ── Prompt scope ──────────────────────────────────────────────────────────────

def test_common_figure_scope_rule_targets_expected_10_modalities(sub):
    assert len(_MODALITIES_REQUIRING_FIGURE_SCOPE_RULE) == 10
    for modality in _MODALITIES_REQUIRING_FIGURE_SCOPE_RULE:
        prompt = sub._get_system_prompt(modality)
        assert "STRICT TARGET-FIGURE SCOPE" in prompt
        assert "different time points" in prompt


@pytest.mark.parametrize(
    "modality",
    [
        "CT_ABDOMEN",
        "CT_BRAIN",
        "CT_CHEST",
        "MRI_BRAIN",
        "MRI_PELVIS",
        "US_ABDOMEN",
    ],
)
def test_reviewed_modalities_are_excluded_from_new_scope_rule(sub, modality):
    assert "STRICT TARGET-FIGURE SCOPE" not in sub._get_system_prompt(modality)


def test_us_pelvis_existing_and_common_scope_rules_are_both_applied(sub):
    prompt = sub._get_system_prompt("US_PELVIS")
    assert "STRICT SCOPE RULE" in prompt
    assert "STRICT TARGET-FIGURE SCOPE" in prompt


# ── Title match quality ───────────────────────────────────────────────────────

def test_title_match_high(sub):
    q = sub.calc_title_match_quality(
        title="Pulmonary embolism presenting as chest pain in a young patient",
        diagnosis="Pulmonary embolism",
    )
    assert q == "high"


def test_title_match_low(sub):
    q = sub.calc_title_match_quality(
        title="A rare case of endocrine disorder",
        diagnosis="Pulmonary embolism",
    )
    assert q == "low"


def test_title_match_empty(sub):
    q = sub.calc_title_match_quality(title="", diagnosis="Pneumonia")
    assert q == "low"
