"""Tests for CaseState serialization and alias mapping."""
import json
import pytest
from openredu.core.state import CaseState, LearnerState


def test_casestate_defaults():
    s = CaseState(pmcid="PMC123", case_id="PMC123_fig1", modality="CXR")
    assert s.status == "retrieved"
    assert s.image_paths == []
    assert s.demographics == {"age": None, "sex": None}
    assert s.diagnosis_cuis == []
    assert s.agent_log == []


def test_to_jsonl_viewer_aliases():
    s = CaseState(
        pmcid="PMC123", case_id="PMC123_fig1", modality="CXR",
        article_title="Test paper",
        author_keywords=["pneumonia"],
        figure_caption="Chest X-ray shows consolidation",
        image_paths=["/path/to/img.jpg"],
        diagnosis_cuis=["C0032285"],
        diagnosis_umls_preferred="Pneumonia",
    )
    d = json.loads(s.to_jsonl_line())
    assert d["title"] == "Test paper"
    assert d["keywords"] == ["pneumonia"]
    assert d["figure_legend"] == "Chest X-ray shows consolidation"
    assert d["image_path"] == "/path/to/img.jpg"
    assert d["diagnosis_cui"] == "C0032285"
    assert d["diagnosis_umls_pref"] == "Pneumonia"


def test_to_jsonl_empty_lists():
    s = CaseState(pmcid="PMC1", case_id="PMC1_f1", modality="CXR")
    d = json.loads(s.to_jsonl_line())
    assert d["image_path"] is None
    assert d["diagnosis_cui"] is None
    assert d["diagnosis_umls_pref"] == ""


def test_round_trip():
    s = CaseState(
        pmcid="PMC999", case_id="PMC999_fig2", modality="CT_CHEST",
        article_title="Some CT paper",
        author_keywords=["lung cancer", "ct chest"],
        image_paths=["/images/CT_CHEST/PMC999/fig2.jpg"],
        diagnosis_cuis=["C0024117"],
        diagnosis_umls_preferred="Lung cancer",
        finding="right upper lobe mass",
        diagnosis="Lung adenocarcinoma",
        laterality="right",
        status="extracted",
    )
    line = s.to_jsonl_line()
    d = json.loads(line)
    s2 = CaseState.from_dict(d)
    assert s2.pmcid == s.pmcid
    assert s2.case_id == s.case_id
    assert s2.diagnosis_cuis == s.diagnosis_cuis
    assert s2.author_keywords == s.author_keywords
    assert s2.status == s.status


def test_from_dict_ignores_unknown_keys():
    d = {
        "pmcid": "PMC1", "case_id": "PMC1_f1", "modality": "CXR",
        # viewer aliases — should be silently ignored
        "title": "Some paper",
        "keywords": ["test"],
        "image_path": "/path/img.jpg",
        "diagnosis_cui": "C0001",
        "diagnosis_umls_pref": "Test",
        "unknown_future_field": "should_be_ignored",
    }
    s = CaseState.from_dict(d)
    assert s.pmcid == "PMC1"
    assert not hasattr(s, "title")  # not a CaseState field
    assert not hasattr(s, "unknown_future_field")


def test_from_phase2_dict_alias_mapping():
    raw = {
        "case_id": "PMC999_fig1", "pmcid": "PMC999", "modality": "CXR",
        "title": "Some paper",
        "publication_date": "2024-03",
        "keywords": ["tb"],
        "figure_legend": "Chest X-ray shows bilateral infiltrates",
        "image_path": "data/images/CXR/PMC999/img.jpg",
        "license": "CC BY", "year": "2024", "month": "3",
        "imaging_modality": "XR", "anatomy": "chest",
        "journal": "Medicine", "abstract": "abstract text",
        "case_text": "case text", "results_text": "results",
        "figure_label": "Figure 1", "image_size_kb": 120.0,
    }
    s = CaseState.from_phase2_dict(raw)
    assert s.article_title == "Some paper"
    assert s.author_keywords == ["tb"]
    assert s.figure_caption == "Chest X-ray shows bilateral infiltrates"
    assert len(s.image_paths) == 1
    assert s.image_paths == ["data/images/CXR/PMC999/img.jpg"]
    assert s.publication_date == "2024-03"
    assert s.year == "2024"
    assert s.anatomy == "chest"
    assert s.imaging_modality == "XR"
    assert s.status == "retrieved"


def test_from_phase2_dict_cui_normalization():
    raw = {
        "case_id": "PMC1_f1", "pmcid": "PMC1", "modality": "CXR",
        "diagnosis_cui": "C0032285",
        "publication_date": "2024-01",
    }
    s = CaseState.from_phase2_dict(raw)
    assert s.diagnosis_cuis == ["C0032285"]


def test_learner_state_stub():
    ls = LearnerState(learner_id="user1")
    assert ls.exposure_events == []
    assert ls.coverage == {}
