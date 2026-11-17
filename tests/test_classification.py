"""Tests for ClassificationSubagent."""
import pytest
from openredu.core.state import CaseState
from openredu.agents.curation.subagents.classification import ClassificationSubagent


@pytest.fixture
def sub():
    return ClassificationSubagent()


def test_exclude_priority(sub):
    """Exclude keyword wins over include keyword."""
    s = CaseState(
        modality="CT_CHEST",
        figure_caption="CT brain showing hyperdense lesion in right basal ganglia",
    )
    s = sub.run(s)
    assert s.classification_route == "rule_exclude", f"got: {s.classification_route}"
    assert s.is_radiologic_case == False


def test_rule_include(sub):
    s = CaseState(
        modality="CXR",
        figure_caption="Chest X-ray (PA view) shows right lower lobe consolidation",
    )
    s = sub.run(s)
    assert s.classification_route == "rule_include"
    assert s.is_radiologic_case == True


def test_uncertain(sub):
    s = CaseState(
        modality="CXR",
        figure_caption="A representative figure from the study showing the methodology.",
    )
    s = sub.run(s)
    assert s.classification_route == "uncertain_pending"
    assert s.is_radiologic_case is None


def test_multipanel_parentheses(sub):
    s = CaseState(
        modality="CT_CHEST",
        figure_caption="(A) axial CT chest showing consolidation, (B) coronal reconstruction",
    )
    sub._detect_multipanel(s)
    assert s.is_multipanel == True
    assert s.panel_count >= 2


def test_multipanel_fig_letters(sub):
    s = CaseState(
        modality="CT_CHEST",
        figure_caption="Fig 1a CT chest, Fig 1b CT chest with different window",
    )
    sub._detect_multipanel(s)
    assert s.is_multipanel == True


def test_multipanel_panels_range(sub):
    s = CaseState(
        modality="MRI_BRAIN",
        figure_caption="panels A-D showing MRI brain at different levels",
    )
    sub._detect_multipanel(s)
    assert s.is_multipanel == True
    assert s.panel_count >= 4


def test_single_panel(sub):
    s = CaseState(
        modality="CXR",
        figure_caption="Chest X-ray PA view showing bilateral consolidation",
    )
    sub._detect_multipanel(s)
    assert s.is_multipanel == False
    assert s.panel_count == 1


def test_mammogram_exclude_wins(sub):
    """CXR config should exclude mammogram terms."""
    s = CaseState(
        modality="CXR",
        figure_caption="Craniocaudal mammogram showing spiculated mass",
    )
    s = sub.run(s)
    assert s.classification_route == "rule_exclude"


@pytest.mark.parametrize(
    "caption",
    [
        "Esophagram demonstrates a distal esophageal stricture.",
        "Upper GI series shows malrotation with a corkscrew duodenum.",
        "Small bowel follow-through demonstrates an obstructing transition point.",
        "Contrast enema shows a transition zone in the sigmoid colon.",
    ],
)
def test_gi_fluoroscopy_rule_include(sub, caption):
    state = sub.run(CaseState(modality="GI_FLUOROSCOPY", figure_caption=caption))
    assert state.classification_route == "rule_include"
    assert state.is_radiologic_case is True


@pytest.mark.parametrize(
    "caption",
    [
        "VCUG demonstrates grade IV vesicoureteral reflux.",
        "Retrograde urethrogram shows a short bulbar urethral stricture.",
        "Cystogram demonstrates extraperitoneal contrast extravasation.",
        "Hysterosalpingography shows a unicornuate uterine cavity.",
    ],
)
def test_gu_fluoroscopy_rule_include(sub, caption):
    state = sub.run(CaseState(modality="GU_FLUOROSCOPY", figure_caption=caption))
    assert state.classification_route == "rule_include"
    assert state.is_radiologic_case is True


@pytest.mark.parametrize(
    "modality,caption",
    [
        ("GI_FLUOROSCOPY", "CT scan demonstrates an esophageal stricture."),
        ("GI_FLUOROSCOPY", "Endoscopy demonstrates a gastric ulcer."),
        ("GU_FLUOROSCOPY", "CT cystography demonstrates bladder rupture."),
        ("GU_FLUOROSCOPY", "Cystoscopy demonstrates a bladder lesion."),
    ],
)
def test_fluoroscopy_other_technique_excluded(sub, modality, caption):
    state = sub.run(CaseState(modality=modality, figure_caption=caption))
    assert state.classification_route == "rule_exclude"
    assert state.is_radiologic_case is False
