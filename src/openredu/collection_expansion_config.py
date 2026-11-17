"""Production-ready configurations for the remaining ABR retrieval routes.

These configurations are additive and are not executed automatically. They are
loaded by ``openredu.config`` so each route can be selected explicitly with the
pipeline CLI after the current four-route collection finishes.
"""

from __future__ import annotations


COMMON_EXCLUDES = [
    "histopath", "h&e", "hematoxylin", "microscop", "gross specimen",
    "flowchart", "flow chart", "diagram", "schematic", "algorithm",
    " table ", "intraoperative", "surgical photograph", "endoscopy",
]


def _config(name, anatomy, modality, search, include, exclude, focus):
    return {
        "name": name,
        "anatomy": anatomy,
        "imaging_modality": modality,
        "search_keywords": search,
        "include_keywords": include,
        "exclude_keywords": exclude + COMMON_EXCLUDES,
        "diagnosis_normalization": {},
        "llm_system_prompt": (
            f"You are a radiology data curator specializing in {focus}. "
            "Extract structured information only from the target imaging figure.\n"
            "Return ONLY valid JSON with these exact fields:\n"
            "{\n"
            '  "finding": "primary imaging finding visible in the figure",\n'
            '  "diagnosis": "final clinical diagnosis",\n'
            '  "laterality": "right | left | bilateral | central | midline | N/A"\n'
            "}\n\n"
            "Use the figure legend and results text as primary sources. Describe "
            "modality-specific imaging features and do not infer pathology findings "
            "that are not visible on the target image. If uncertain, use 'unclear' "
            "or 'N/A'. Never return null."
        ),
    }


COLLECTION_EXPANSION_MODALITY_CONFIG = {
    "BREAST_ULTRASOUND": _config(
        "Breast Ultrasound", "breast", "Ultrasound",
        ["breast ultrasound", "breast ultrasonography", "breast sonography", "ultrasound of the breast"],
        ["breast ultrasound", "breast ultrasonography", "breast sonography", "ultrasound of the breast", "breast doppler"],
        ["mammogram", "mammography", "breast mri", "magnetic resonance", "breast ct"],
        "breast ultrasound",
    ),
    "BREAST_MRI": _config(
        "Breast MRI", "breast", "MRI",
        ["breast MRI", "MRI of the breast", "breast magnetic resonance imaging", "dynamic contrast-enhanced breast MRI"],
        ["breast mri", "mri of the breast", "breast magnetic resonance", "dynamic contrast-enhanced breast", "dce-mri breast"],
        ["mammogram", "mammography", "breast ultrasound", "breast sonography", "breast ct"],
        "breast MRI",
    ),
    "CARDIOVASCULAR_MRI": _config(
        "Cardiovascular MRI", "heart/cardiovascular system", "MRI",
        ["cardiac MRI", "cardiac magnetic resonance", "cardiovascular magnetic resonance", "cardiac MR imaging", "CMR imaging"],
        ["cardiac mri", "cardiac magnetic resonance", "cardiovascular magnetic resonance", "cardiac mr imaging", "cmr imaging", "late gadolinium enhancement"],
        ["cardiac ct", "coronary ct", "echocardiograph", "spect", "pet/ct", "scintigraph"],
        "cardiac and cardiovascular MRI",
    ),
    "MSK_CT": _config(
        "Musculoskeletal CT", "bone/joint", "CT",
        ["musculoskeletal CT", "bone CT", "CT knee", "CT shoulder", "CT hip", "CT ankle", "CT wrist", "CT elbow", "CT foot", "CT hand"],
        ["musculoskeletal ct", "bone ct", "ct knee", "ct shoulder", "ct hip", "ct ankle", "ct wrist", "ct elbow", "ct foot", "ct hand", "ct of the joint"],
        ["mri", "magnetic resonance", "ultrasound", "sonograph", "radiograph", "x-ray", "pet/ct"],
        "musculoskeletal CT",
    ),
    "MSK_ULTRASOUND": _config(
        "Musculoskeletal Ultrasound", "muscle/tendon/joint", "Ultrasound",
        [
            "musculoskeletal ultrasound", "musculoskeletal ultrasonography",
            "tendon ultrasound", "tendon ultrasonography", "joint ultrasound",
            "joint ultrasonography", "muscle ultrasound", "muscle ultrasonography",
            "shoulder ultrasound", "peripheral nerve ultrasound",
            "peripheral nerve sonography", "power Doppler synovitis",
            "dynamic ultrasound",
        ],
        [
            "musculoskeletal ultrasound", "musculoskeletal ultrasonography",
            "tendon ultrasound", "tendon ultrasonography", "joint ultrasound",
            "joint ultrasonography", "muscle ultrasound", "muscle ultrasonography",
            "shoulder ultrasound", "peripheral nerve ultrasound",
            "peripheral nerve sonography", "dynamic ultrasound",
            "ultrasound image", "ultrasonographic", "sonographic", "sonogram",
            "power doppler", "color doppler", "colour doppler", "us scan",
            "ultrasound-guided", "ultrasound guided",
        ],
        ["mri", "magnetic resonance", "ct scan", "computed tomography", "radiograph", "x-ray"],
        "musculoskeletal ultrasound",
    ),
    "OBSTETRIC_ULTRASOUND": _config(
        "Obstetric Ultrasound", "pregnancy/fetus/placenta", "Ultrasound",
        ["obstetric ultrasound", "fetal ultrasound", "prenatal ultrasound", "pregnancy ultrasound", "placental ultrasound", "antenatal sonography"],
        ["obstetric ultrasound", "fetal ultrasound", "prenatal ultrasound", "pregnancy ultrasound", "placental ultrasound", "antenatal sonography", "fetal sonography"],
        ["fetal mri", "placental mri", "computed tomography", "ct scan", "radiograph", "x-ray"],
        "obstetric and fetal ultrasound",
    ),
    # ── US_SUPERFICIAL: thyroid / neck / pleural ultrasound ───────────────────
    # Replaces the removed US_VASCULAR bucket for the APDR US division topic
    # "Neck and chest ultrasound" (apdr_sched_0131).
    # Tighter than US_VASCULAR: include_keywords require an explicit anatomy +
    # ultrasound term pair; single-word anatomy or single-word "ultrasound"
    # alone does NOT pass the gate.
    "US_SUPERFICIAL": _config(
        "Superficial / Neck / Pleural Ultrasound",
        "neck/thyroid/pleural",
        "Ultrasound",
        # search_keywords — PMC query terms
        [
            "thyroid ultrasound", "thyroid sonography",
            "neck ultrasound", "neck sonography",
            "pleural ultrasound", "pleural sonography",
            "salivary gland ultrasound", "parotid ultrasound",
        ],
        # include_keywords — curation gate (at least one required in figure text)
        # Deliberately anatomy+modality compound terms only
        [
            "thyroid ultrasound", "thyroid sonography", "thyroid us",
            "ultrasound thyroid", "sonography thyroid",
            "neck ultrasound", "neck sonography",
            "cervical ultrasound", "cervical sonography",
            "pleural ultrasound", "pleural sonography",
            "salivary gland ultrasound", "salivary gland sonography",
            "parotid ultrasound", "parotid sonography",
            "superficial ultrasound", "superficial sonography",
            "point-of-care neck",
        ],
        # exclude_keywords — hard excludes
        [
            "ct neck", "mri neck", "ct chest", "mri chest",
            "carotid doppler", "carotid ultrasound",   # vascular — not superficial
            "abdominal ultrasound", "pelvic ultrasound",
            "echocardiograph", "cardiac ultrasound",
            "obstetric ultrasound", "fetal ultrasound",
            "musculoskeletal ultrasound",
        ],
        "thyroid, neck, and pleural ultrasound",
    ),
}
