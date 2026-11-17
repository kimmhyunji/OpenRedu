"""Tests for MatchingSubagent and supporting functions."""
from pathlib import Path

import pytest
from openredu.core.state import CaseState
from openredu.agents.mapping.subagents.matching import (
    MatchingSubagent, build_apdr_index, build_search_text,
    clean_keyword, match_case_to_topics,
    _check_division_anchor, _match_composite_concepts,
)


# The curriculum topic table used in the study is not distributed. These tests
# run against a small invented topic table in the standard four-column format
# (canonical_name, category, specialty, source_type).
FAKE_DIR = Path(__file__).resolve().parents[1] / "examples" / "fake_curriculum"


@pytest.fixture
def apdr_index():
    topics, kw_to_synonyms, kw_to_cui = build_apdr_index(
        FAKE_DIR / "guideline_topics.csv", FAKE_DIR / "synonym_index.json"
    )
    return topics, kw_to_synonyms, kw_to_cui


@pytest.fixture
def sub(apdr_index):
    topics, syns, cuis = apdr_index
    return MatchingSubagent(
        apdr_topics=topics,
        kw_to_synonyms=syns,
        kw_to_cui=cuis,
    )


def test_clean_keyword_basic():
    assert clean_keyword("Pulmonary Embolism") == "pulmonary embolism"
    assert clean_keyword("MRI: brain lesion") == "mri brain lesion"
    assert clean_keyword("short") == "short"  # ≥3 chars
    assert clean_keyword("ab") is None  # too short


def test_clean_keyword_colon_modality():
    assert clean_keyword("CT: pulmonary embolism") == "ct pulmonary embolism"
    assert clean_keyword("chest: pneumonia") == "chest pneumonia"


def test_clean_keyword_preserves_clinical_qualifiers():
    assert clean_keyword("Bone Scan – metastasis") == "bone scan metastasis"
    assert (
        clean_keyword("Cardiac Stress Test (any type) - ischemia")
        == "cardiac stress test any type ischemia"
    )


def test_composite_matching_requires_two_independent_concepts():
    concepts = ["Bone scintigraphy", "Metastasis", "Skeletal metastatic disease"]

    assert _match_composite_concepts(
        concepts,
        "Tc-99m bone scintigraphy demonstrates multiple osseous metastases",
    )
    assert not _match_composite_concepts(
        concepts,
        "CT demonstrates hepatic metastasis",
    )
    assert not _match_composite_concepts(
        ["Demyelination", "Brain", "MRI"],
        "Brain MRI demonstrates an enhancing mass",
    )
    assert not _match_composite_concepts(
        ["Thyroid imaging", "Thyroid uptake", "Graves disease"],
        "Normal thyroid uptake on scintigraphic imaging",
    )
    assert _match_composite_concepts(
        ["Thyroid imaging", "Thyroid uptake", "Graves disease"],
        "Thyroid scintigraphic imaging shows diffuse uptake in Graves disease",
    )
    assert not _match_composite_concepts(
        ["Ductal carcinoma in situ", "Breast", "MRI imaging"],
        "Ultrasound of the breast shows ductal carcinoma in situ",
    )


def test_build_search_text():
    s = CaseState(
        pmcid="PMC1", case_id="PMC1_f1", modality="CT_CHEST",
        diagnosis_normalized="Pulmonary embolism",
        finding="saddle embolism",
        article_title="A case of PE",
        figure_caption="CTPA showing filling defect",
        author_keywords=["pulmonary", "embolism"],
    )
    text = build_search_text(s)
    assert "pulmonary embolism" in text
    assert "saddle embolism" in text
    assert "ctpa" in text


@pytest.mark.parametrize(
    ("text", "division"),
    [
        ("bowel wall discontinuity", "Neuro"),
        ("suspected appendicitis", "NM"),
        ("secondary aortoenteric fistula", "MSK"),
        ("adrenocortical carcinoma", "Neuro"),
    ],
)
def test_division_anchor_rejects_substring_collisions(text, division):
    assert not _check_division_anchor(text, division)


@pytest.mark.parametrize(
    ("text", "division"),
    [
        ("bronchogenic cyst", "Chest"),
        ("mediastinal fibrosis", "Chest"),
        ("pancreatic laceration", "GI"),
        ("cholecystitis", "GI"),
        ("epididymitis", "GU"),
        ("vertebral fracture", "MSK"),
        ("FDG PET demonstrates uptake", "NM"),
    ],
)
def test_division_anchor_allows_explicit_terms_and_stems(text, division):
    assert _check_division_anchor(text, division)


def test_guideline_index_loads_standard_csv(apdr_index):
    topics, _, _ = apdr_index
    assert len(topics) == 5
    raw = {t["raw_keyword"] for t in topics}
    assert {"Pulmonary embolism", "Cholecystitis", "Brain abscess"} <= raw
    assert {t["specialty"] for t in topics} == {"Chest", "GI", "Neuro", "MSK", "US"}


def test_match_pulmonary_embolism(sub):
    s = CaseState(
        pmcid="PMC3", case_id="PMC3_f1", modality="CT_CHEST",
        diagnosis_normalized="Pulmonary embolism",
        finding="saddle pulmonary embolism at main pulmonary artery",
        figure_caption="CTPA showing filling defect in main pulmonary artery",
    )
    s = sub.run(s)
    assert s.curriculum_topics, "expected the invented 'Pulmonary embolism' topic to match"
    assert s.mapping_paths


def test_no_match_returns_empty(sub):
    s = CaseState(
        pmcid="PMC4", case_id="PMC4_f1", modality="CXR",
        diagnosis_normalized="Highly specific rare diagnosis XYZ123",
    )
    s = sub.run(s)
    # Should return empty lists, not raise
    assert isinstance(s.curriculum_topics, list)
    assert isinstance(s.mapping_paths, list)
