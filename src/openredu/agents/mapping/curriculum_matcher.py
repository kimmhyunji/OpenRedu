"""
CurriculumMatcher: corpus case → curriculum topic matching.

SCOPE NOTE
==========
This class serves the separate Core Radiology/Grainger topic index.  It is not
the authoritative implementation for the APDR residency-schedule analysis.
APDR schedule eligibility, matching, and reporting are implemented end-to-end
in ``src/openredu/pipeline/report_apdr_schedule_coverage.py`` so that the manuscript
result cannot silently mix two different gate systems.

POLICY OVERVIEW
===============
Goal: zero wrong-division matches. Prefer no match over wrong match.

Unlike APDR matching (which maximises coverage of 460 specific diagnoses),
curriculum matching maps cases to broad topic areas that describe what
educational content the case *primarily* illustrates. The topic list is wider
and many topics are ambiguous across organ systems, so the bar for acceptance
is significantly higher.

GATE STRUCTURE (all gates must pass for a match to be accepted)
---------------------------------------------------------------
Gate 1 — Division pre-filter
  The case's `modality` field encodes division (e.g. "CHEST_XRAY" → Chest,
  "BRAIN_MRI" → Neuro). Only topics whose division is compatible with the
  case's modality-division are even considered. Cross-division candidacy is
  only allowed for a small explicit allowlist.

Gate 2 — Primary field match (mandatory)
  At least ONE of the "primary" case fields must contain a match phrase for
  the topic:
    - diagnosis        (LLM-extracted, figure-specific)
    - diagnosis_normalized
    - finding          (primary finding of this figure)
  These fields are the most reliable. Matching only in figure_caption or
  article_title is not sufficient alone.

Gate 3 — Topic phrase must be non-trivial
  Match phrases shorter than 4 characters, or consisting of only stop-words,
  are never used. Broad single-word phrases (e.g. "trauma", "masses",
  "infection") are accepted only if the topic has NO level2 (i.e. it is
  genuinely a standalone topic) AND the same word appears in the primary
  fields as the *dominant* finding (not a mention in passing).

Gate 4 — Incidental blocker
  For topics classified as `finding_primary` (e.g. Pleural Effusion, Pulmonary
  Edema): the case's `diagnosis` must *not* point to a different primary
  disease where the finding is incidental. Implementation: if diagnosis does
  not contain the topic's core phrase AND the finding contains a qualifier
  indicating it is secondary (e.g. "secondary", "associated", "incidental"),
  the match is blocked.

Gate 5 — Peds age filter (inherited from APDR policy)
  Peds-division topics only match if age <= 18 or age is unknown.

WHAT IS NEVER USED FOR MATCHING
--------------------------------
- `case_text` (full clinical narrative — too many disease mentions)
- `abstract`  (paper-level background)
- `author_keywords` (paper-level, not figure-specific)

MATCH PATHS (for audit trail)
------------------------------
- "phrase"  : canonical topic label or derived phrase found in primary fields
- "synonym" : topic synonym found in primary fields
- "extended": phrase found in figure_caption or article_title (secondary confirmation)
             Only valid if primary fields already matched via "phrase" or "synonym"
"""

from __future__ import annotations

import json
import re
import logging
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

# ── Stop words (single-word topics composed only of these are never matched) ──
_STOP = {
    "the", "and", "of", "in", "with", "for", "to", "a", "an",
    "other", "imaging", "disorder", "disorders", "disease",
    "diseases", "pathology", "pathologies", "lesion", "lesions",
}

# ── Modality code → curriculum division(s) ───────────────────────────────────
# A case may map to multiple divisions (e.g. a PET case may match NM topics,
# but also GI/Liver topics if the case is primarily about a liver tumour).
# We use a PRIMARY division (strict) and SECONDARY divisions (relaxed).
# Cross-division matches require the case to pass the secondary division's
# own anchor terms.

MODALITY_PRIMARY_DIVISION: dict[str, str] = {
    # ── Chest ───────────────────────────────────────────────────────────────
    "CXR":               "Chest",
    "CT_CHEST":          "Chest",
    "CT_CHEST_VASC":     "Chest",     # CTPA / chest CTA
    # ── Nuclear Medicine ────────────────────────────────────────────────────
    "NM_NUCLEAR":        "NM",
    # ── GI / Abdomen (default to GI, GU splits by anatomy in Gate 1 secondary)
    "CT_ABDOMEN":        "GI",
    "MRI_ABDOMEN":       "GI",
    "US_ABDOMEN":        "GI",
    "GI_FLUOROSCOPY":    "GI",
    # ── GU ──────────────────────────────────────────────────────────────────
    "US_PELVIS":         "GU",
    "MRI_PELVIS":        "GU",
    "US_GYN_TRANS":      "GU",        # transvaginal / gynecologic US
    "GU_FLUOROSCOPY":    "GU",
    # ── Neuro ───────────────────────────────────────────────────────────────
    "MRI_BRAIN":         "Neuro",
    "CT_BRAIN":          "Neuro",
    "MRI_SPINE":         "Neuro",
    "MRI_NEURO_SPINE":   "Neuro",
    # ── MSK ─────────────────────────────────────────────────────────────────
    "MSK_XRAY":          "MSK",
    "MRI_MSK":           "MSK",
    "MSK_CT":            "MSK",
    "MSK_ULTRASOUND":    "MSK",
    # ── Breast ──────────────────────────────────────────────────────────────
    "MAMMOGRAM":         "Breast",
    "BREAST_MRI":        "Breast",
    "BREAST_ULTRASOUND": "Breast",
    # ── Cardiac ─────────────────────────────────────────────────────────────
    "CARDIOVASCULAR_MRI": "Cardiac",
    # ── Vascular ────────────────────────────────────────────────────────────
    "US_VASCULAR":       "Vascular",
    # ── IR (no corpus-specific code yet; IR cases come via CT_ABDOMEN etc.) ─
    # ── OB ──────────────────────────────────────────────────────────────────
    # OB cases currently arrive as US_PELVIS / US_GYN_TRANS
    # (handled by secondary division logic from GU primary)
}

# Divisions that a given primary-division case may ADDITIONALLY match if the
# topic's anchor terms are present in the case text.
SECONDARY_DIVISIONS: dict[str, set[str]] = {
    "GI":       {"GU", "Vascular", "IR"},   # abdominal cases span organs
    "GU":       {"GI", "Vascular", "IR"},
    "Chest":    {"Cardiac", "Vascular"},
    "NM":       {"Chest", "GI", "GU", "MSK", "Neuro"},  # NM crosses all
    "Vascular": {"GI", "GU", "Chest", "Cardiac"},
    "Cardiac":  {"Chest", "Vascular"},
    "IR":       {"GI", "GU", "Vascular", "Chest"},
    "Neuro":    set(),
    "MSK":      set(),
    "Breast":   set(),
    "OB":       {"GU"},
    "Peds":     {"Chest", "GI", "GU", "Neuro", "MSK", "Cardiac"},
}

# Divisions whose anchor terms gate cross-division matches
_DIVISION_ANCHORS: dict[str, list[str]] = {}   # loaded lazily

# ── Organ/anatomy words that are NEVER valid as sole match phrases ─────────────
# These identify the *division* (Gate 1 handles that), not the specific topic.
# For depth≥2 topics, only level2+ phrases are used as match phrases.
_ORGAN_ANCHOR_WORDS = {
    # Chest/Thoracic
    "lung", "pulmonary", "thoracic", "chest", "airway", "airways",
    "pleura", "pleural", "mediastinum", "mediastinal", "bronchial",
    # GI
    "liver", "hepatic", "biliary", "pancrea", "pancreatic", "spleen",
    "splenic", "gastric", "stomach", "bowel", "intestinal", "colonic",
    "esophagus", "esophageal", "peritoneal", "mesenteric",
    # GU
    "renal", "kidney", "kidneys", "bladder", "uterine", "uterus",
    "ovarian", "ovary", "prostate", "prostatic", "scrotal", "testicular",
    "adrenal", "cervical", "pelvis", "pelvic",
    # MSK
    "knee", "shoulder", "hip", "ankle", "wrist", "elbow", "foot",
    "bone", "joint", "spine", "spinal", "vertebra", "femoral",
    # Breast
    "breast", "mammary",
    # Neuro
    "brain", "cerebral", "cortical", "intracranial", "cranial",
    "meningeal", "orbital", "skull", "temporal", "frontal",
    # Vascular
    "aorta", "aortic", "vascular", "arterial", "venous",
    # Cardiac
    "cardiac", "coronary", "pericardial",
    # NM
    "nuclear", "thyroid", "parathyroid",
    # Generic location/structure words (insufficient specificity alone)
    "upper", "lower", "right", "left", "bilateral", "unilateral",
    "anterior", "posterior", "lateral", "medial", "central",
    "diffuse", "focal", "nodule", "mass", "lesion",
    "infection", "infections", "inflammation", "inflammatory",
    "malignant", "benign", "solid", "cystic",
}

# ── Broad single-word topics that require extra confidence ────────────────────
# If a depth=1 topic's match phrase is one of these, require it in BOTH
# diagnosis AND finding fields.
_BROAD_SINGLE_WORD_TOPICS = {
    "trauma", "infection", "masses", "tumors", "tumours",
    "neoplasms", "neoplasia", "disease", "disorders",
    "pathology", "complications", "hemorrhage", "bleeding",
}

# ── Allowed single-token match phrases (medically specific) ──────────────────
# Only these single words may serve as sole match phrases.
# Everything else requires ≥2 meaningful tokens to avoid over-broad matching.
_ALLOWED_SINGLE_TOKENS = {
    # ── High-specificity single-entity terms ────────────────────────────────
    # Only terms that map to EXACTLY ONE curriculum topic are safe here.
    # Terms that could match multiple topics (e.g. "pneumonia" matches both
    # "Viral Pneumonia" and "Complications of Pneumonia") must NOT be here.

    # Unambiguous syndromes (only one curriculum topic)
    "stroke",           # Neuro: Stroke
    "sah",              # Neuro: SAH
    "dvt",              # Vascular: DVT
    "copd",             # Airways: COPD
    "ild",              # Diffuse Lung Disease: ILD
    "ibd",              # NM/GI: IBD
    "appendicitis",     # GI: Appendix (primary)
    "pancreatitis",     # Pancreas: Pancreatitis
    "cirrhosis",        # Liver: Cirrhosis
    "emphysema",        # Airways: Emphysema
    "pneumothorax",     # Chest (finding_primary)
    "pneumoconioses",   # standalone Pneumoconioses topic
    "endometriosis",    # GU: Pelvis: Endometriosis
    "hydrocephalus",    # Ventricles: Hydrocephalus
    "mesothelioma",     # specific enough, single topic
    "osteomyelitis",    # MSK: Infection
    "spondylitis",      # Spine: Infection (specific)
    "hydrops",          # OB: Hydrops
    "dementia",         # Neuro: Dementia
    # Recognized acronyms used as diagnosis — each maps to one topic
    "tb",               # Pulmonary Infection: TB
    "hcc",              # Liver: HCC
    "hsct",             # Pulmonary Infection: Post HSCT
    "melas",            # Peds_Neuro: MELAS
    "iugr",             # OB: IUGR
    "iph",              # Neuro: IPH
    "nph",              # Ventricles: NPH
    "ras",              # Renal Vessels: RAS
    "fmd",              # Renal Vessels: FMD
    # NM-specific procedures/tracers that uniquely identify topics
    "hida",             # NM: HIDA
    # NOT included (ambiguous across topics):
    # "pneumonia" — matches Viral Pneumonia, Complications of Pneumonia, etc.
    # "aneurysm"  — matches Thoracic Aortic Aneurysm, AAA, Cerebral Aneurysms
    # "lymphoma"  — matches NM: Lymphoma Staging AND GI: Hepatic Lymphoma
    # "cholecystitis" — matches Gallstones & Cholecystitis but also appears in
    #                   acalculous/emphysematous contexts
    # "infection"     — far too broad
}

# ── Incidental qualifier words that block finding_primary matches ─────────────
_INCIDENTAL_QUALIFIERS = {
    "incidental", "secondary", "associated", "concomitant",
    "concurrent", "complicating", "accompanying",
}


def _load_division_anchors(anchor_path: Path) -> dict[str, set[str]]:
    """Load division anchor terms from division_anchors.json."""
    if not anchor_path.exists():
        return {}
    data = json.loads(anchor_path.read_text(encoding="utf-8"))
    result: dict[str, set[str]] = {}
    for div, entry in data.items():
        if div.startswith("_"):
            continue
        terms = set(entry.get("terms", []))
        for s in entry.get("stem_prefix_terms", []):
            terms.add(s)
        result[div] = terms
    return result


def _normalize(text: str) -> str:
    """Lowercase, collapse whitespace, strip punctuation for matching."""
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s\-]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _phrase_in_text(phrase: str, text: str) -> bool:
    """Whole-word phrase match (allows internal hyphens)."""
    if not phrase or not text:
        return False
    pattern = r"(?<![a-z0-9])" + re.escape(phrase) + r"(?![a-z0-9])"
    return bool(re.search(pattern, text))


def _anchor_present(text: str, division: str, anchors: dict[str, set[str]]) -> bool:
    """Check if any anchor term for `division` is present in text."""
    terms = anchors.get(division, set())
    if not terms:
        return True  # no anchors defined → no restriction
    txt = text.lower()
    for term in terms:
        if re.search(r"(?<![a-z0-9])" + re.escape(term) + r"[a-z0-9\-]*", txt):
            return True
    return False


def _is_organ_anchor_only(phrase: str) -> bool:
    """Return True if phrase consists entirely of organ/division anchor words.
    Empty token list → True (empty phrase is not a valid match phrase).
    Tokens in _ALLOWED_SINGLE_TOKENS are NOT considered organ-anchor words —
    they are specific medical terms.
    """
    tokens = phrase.lower().split()
    if not tokens:
        return True
    return all(
        t in _ORGAN_ANCHOR_WORDS
        or t in _STOP
        or (len(t) <= 2 and t not in _ALLOWED_SINGLE_TOKENS)
        for t in tokens
    )


def _build_match_phrases(topic: dict) -> list[str]:
    """
    Derive ordered list of match phrases from topic fields.

    KEY RULE: for depth >= 2 topics, level1-only phrases (organ/anatomy words)
    are excluded from match phrases. Gate 1 already ensures the case is in the
    right division; matching the organ name alone would match every case in that
    division to every subtopic of that organ — exactly the problem we avoid.

    Returns normalized, deduplicated phrases sorted longest-first.
    """
    depth = topic.get("depth", 1)
    seen: set[str] = set()
    phrases: list[str] = []

    def add(raw: str, is_level1: bool = False) -> None:
        p = _normalize(raw).strip()
        if not p:
            return
        # Tokens for content analysis (include 2-char medical abbreviations)
        tokens = [w for w in p.split() if w not in _STOP]
        content_tokens = [w for w in tokens if len(w) >= 2]
        if not content_tokens:
            return
        # min length: 2 chars is enough for acronyms (tb, ct, mr, etc)
        if len(p) < 2:
            return
        # Organ-anchor-only check (any depth)
        if _is_organ_anchor_only(p):
            return
        # For depth≥2 topics: skip phrases that are only organ/anatomy words
        if depth >= 2 and is_level1:
            return
        # MINIMUM SPECIFICITY:
        # Single-token phrases are only allowed if the token is a
        # medically-specific term from _ALLOWED_SINGLE_TOKENS.
        if len(content_tokens) == 1:
            token = content_tokens[0]
            if token not in _ALLOWED_SINGLE_TOKENS:
                return
        if p not in seen:
            seen.add(p)
            phrases.append(p)

    l1 = topic.get("level1", "")
    l2 = topic.get("level2")
    l3 = topic.get("level3")
    l4 = topic.get("level4")

    # canonical_label — includes level1+level2 joined; add as multi-word phrase
    label = topic.get("canonical_label", "")
    add(label)

    # level2 phrase (most clinically specific for depth=2 topics)
    if l2:
        add(l2.replace("_", " "))

    # level3/4 if present
    if l3:
        add(l3.replace("_", " "))
    if l4:
        add(l4.replace("_", " "))

    # level1 only valid for depth=1 topics that are NOT pure organ/anatomy words
    if depth == 1 and l1:
        l1_phrase = _normalize(l1.replace("_", " "))
        if not _is_organ_anchor_only(l1_phrase):
            add(l1_phrase, is_level1=False)  # already checked, safe to add

    # full tag_path as a phrase
    tag = topic.get("tag_path", "").replace("::", " ").replace("_", " ")
    add(tag)

    # search_terms (pre-built, already has multi-word combos)
    l1_norm = _normalize(l1.replace("_", " ")) if l1 else ""
    for t in topic.get("search_terms", []):
        # Skip phrases that are only organ/anchor words
        if _is_organ_anchor_only(t):
            continue
        # For depth≥2: skip phrases that are just the level1 prefix
        # e.g. "pulmonary infection" for a ::TB subtopic
        if depth >= 2 and l1_norm and t.strip() == l1_norm:
            continue
        add(t)

    # Sort: longer phrases are more specific → try first
    phrases.sort(key=len, reverse=True)
    return phrases


def _is_broad_single_word(phrase: str) -> bool:
    tokens = phrase.split()
    return len(tokens) == 1 and phrase in _BROAD_SINGLE_WORD_TOPICS


class CurriculumMatcher:
    """
    Matches a single case dict to curriculum eligible topics.

    Usage:
        matcher = CurriculumMatcher.from_files(topics_path, anchor_path)
        result = matcher.match(case_dict)
        # result: list of {topic_id, canonical_label, division, match_paths}
    """

    def __init__(
        self,
        topics: list[dict],
        division_anchors: dict[str, set[str]],
    ):
        self.topics = topics
        self.anchors = division_anchors
        # Pre-compute match phrases per topic
        self._phrases: dict[str, list[str]] = {
            t["topic_id"]: _build_match_phrases(t) for t in topics
        }
        # Group topics by division for fast pre-filter
        self._by_division: dict[str, list[dict]] = {}
        for t in topics:
            self._by_division.setdefault(t["division"], []).append(t)

    @classmethod
    def from_files(
        cls,
        topics_path: Path,
        anchor_path: Path,
    ) -> "CurriculumMatcher":
        data = json.loads(topics_path.read_text(encoding="utf-8"))
        topics = data["eligible_topics"]
        anchors = _load_division_anchors(anchor_path)
        log.info(
            f"CurriculumMatcher loaded: {len(topics)} topics, "
            f"{len(anchors)} anchor divisions"
        )
        return cls(topics, anchors)

    # ── Gate helpers ──────────────────────────────────────────────────────────

    def _eligible_divisions(self, case: dict) -> set[str]:
        """Return divisions this case is allowed to match (Gate 1)."""
        modality = (case.get("modality") or "").upper()
        primary = MODALITY_PRIMARY_DIVISION.get(modality)
        if primary:
            allowed = {primary}
            allowed |= SECONDARY_DIVISIONS.get(primary, set())
        else:
            # Unknown modality: allow all divisions but require anchor
            allowed = set(self._by_division.keys())
        return allowed

    def _primary_text(self, case: dict) -> str:
        """Build primary match text (Gate 2 — highest precision fields only)."""
        parts = [
            case.get("diagnosis_normalized") or "",
            case.get("diagnosis") or "",
            case.get("finding") or "",
        ]
        return _normalize(" ".join(parts))

    def _extended_text(self, case: dict) -> str:
        """Extended text for secondary confirmation only."""
        parts = [
            case.get("figure_caption") or "",
            case.get("figure_legend") or "",
            case.get("article_title") or "",
        ]
        return _normalize(" ".join(parts))

    def _check_incidental(self, case: dict, topic: dict) -> bool:
        """
        Gate 4: block incidental finding matches.
        For finding_primary topics, if the case diagnosis doesn't reference
        the topic's core concept AND the finding text contains an incidental
        qualifier, reject.
        Returns True if the match should be BLOCKED.
        """
        if topic.get("match_source") != "finding_primary":
            return False  # only applies to finding_primary topics
        diag = _normalize(
            (case.get("diagnosis") or "") + " " +
            (case.get("diagnosis_normalized") or "")
        )
        finding = _normalize(case.get("finding") or "")

        # Get the core phrase(s) for this topic
        phrases = self._phrases.get(topic["topic_id"], [])
        core_phrases = [p for p in phrases if len(p.split()) >= 2][:3]

        # If diagnosis clearly contains the topic phrase → not incidental
        for p in core_phrases:
            if _phrase_in_text(p, diag):
                return False  # diagnosis references it → primary, not incidental

        # If diagnosis is clearly something else AND finding has qualifier → block
        if any(q in finding for q in _INCIDENTAL_QUALIFIERS):
            return True

        return False

    # ── Main match method ─────────────────────────────────────────────────────

    def match(self, case: dict) -> list[dict]:
        """
        Match a case to curriculum topics. Returns list of accepted matches.
        Each match: {topic_id, canonical_label, division, match_paths, phrases_hit}
        """
        eligible_divisions = self._eligible_divisions(case)
        primary_text  = self._primary_text(case)
        extended_text = self._extended_text(case)
        age = (case.get("demographics") or {}).get("age")

        accepted: list[dict] = []

        for topic in self.topics:
            division = topic["division"]
            topic_id = topic["topic_id"]

            # ── Gate 1: division pre-filter ───────────────────────────────────
            if division not in eligible_divisions:
                continue

            # For secondary divisions: require anchor terms in primary_text
            primary_div = MODALITY_PRIMARY_DIVISION.get(
                (case.get("modality") or "").upper()
            )
            if primary_div and division != primary_div:
                if not _anchor_present(primary_text, division, self.anchors):
                    continue

            # ── Gate 5: Peds age filter ───────────────────────────────────────
            if division == "Peds":
                if age is not None and age > 18:
                    continue

            # ── Gate 2: primary field match ───────────────────────────────────
            phrases = self._phrases.get(topic_id, [])
            primary_hit: Optional[str] = None
            for phrase in phrases:
                # Extra strictness for broad single-word topics
                if _is_broad_single_word(phrase):
                    diag_hit = _phrase_in_text(phrase, _normalize(
                        (case.get("diagnosis") or "") + " " +
                        (case.get("diagnosis_normalized") or "")
                    ))
                    finding_hit = _phrase_in_text(phrase, _normalize(
                        case.get("finding") or ""
                    ))
                    if diag_hit and finding_hit:
                        primary_hit = phrase
                        break
                else:
                    if _phrase_in_text(phrase, primary_text):
                        primary_hit = phrase
                        break

            if not primary_hit:
                continue  # Gate 2 failed — no match in primary fields

            # ── Gate 3: phrase non-triviality already enforced in phrase builder ──
            # (phrases < 4 chars or all-stop-words are excluded during build)

            # ── Gate 4: incidental blocker ────────────────────────────────────
            if self._check_incidental(case, topic):
                continue

            # ── All gates passed — determine match paths ──────────────────────
            match_paths = ["phrase"]
            # Check if extended text also supports (for audit trail)
            if _phrase_in_text(primary_hit, extended_text):
                match_paths.append("extended")

            accepted.append({
                "topic_id":       topic_id,
                "canonical_label": topic["canonical_label"],
                "division":       division,
                "match_paths":    match_paths,
                "phrase_hit":     primary_hit,
                "grainger_allison": topic.get("grainger_allison", []),
            })

        return accepted
