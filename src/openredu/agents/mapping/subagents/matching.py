"""
MatchingSubagent: 3-path guideline topic matching for a single CaseState.

Path 1 — direct text: keyword phrase found in case search text
Path 2 — synonym expansion: MeSH/SNOMED synonyms matched
Path 3 — CUI: case diagnosis CUI == APDR topic CUI

Division anchor filter (mapping_quality_revision 2026-07-13):
  A match is accepted only if the search_text also contains at least one
  division-specific anchor term. This prevents cross-division false positives
  (e.g. [Breast] Papilloma matching a CT_BRAIN choroid plexus papilloma case).
  Anchor terms are derived from corpus frequency analysis per APDR division.

The inverted index is built once at pipeline startup (not per-case).
Adapted from educational_material/curriculum/generate_coverage_report.py.
"""
import csv
import json
import logging
import re
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Optional

from openredu.core.base import Subagent
from openredu.core.state import CaseState
from openredu.config import PATHS, STOP_WORDS

log = logging.getLogger(__name__)


# ── Keyword cleaning (replicates cleanKeyword from lib/curriculum.ts) ─────────

# ── Division anchor terms ─────────────────────────────────────────────────────
# Loaded from config/division_anchors.json (editable without
# code changes). See that file for term rationale and overlap assessment.

def _load_division_anchors() -> tuple[dict, dict]:
    """Load DIVISION_ANCHORS and _DIVISION_ANCHOR_STEMS from JSON config."""
    anchor_path = PATHS.get("division_anchors")
    if anchor_path is None or not Path(anchor_path).exists():
        raise FileNotFoundError(
            f"division_anchors.json not found at {anchor_path}. "
            "Add 'division_anchors' to PATHS in config.py."
        )
    data = json.loads(Path(anchor_path).read_text(encoding="utf-8"))
    anchors: dict = {}
    stems: dict = {}
    for div, entry in data.items():
        if div.startswith("_"):
            continue
        all_terms = set(entry.get("terms", [])) | set(entry.get("stem_prefix_terms", []))
        anchors[div] = all_terms
        stem_list = entry.get("stem_prefix_terms", [])
        if stem_list:
            stems[div] = set(stem_list)
    return anchors, stems


DIVISION_ANCHORS, _DIVISION_ANCHOR_STEMS = _load_division_anchors()

# Divisions with no anchor requirement (catch-all or cross-system)
_NO_ANCHOR_DIVISIONS: set = set()


def _anchor_term_matches(text: str, term: str, stem: bool = False) -> bool:
    """Match an anchor as a token/phrase, or as an explicitly allowed stem."""
    start = r"(?<![a-z0-9])" + re.escape(term)
    end = r"[a-z0-9-]*" if stem else r"(?![a-z0-9])"
    return re.search(start + end, text) is not None


def _check_division_anchor(search_text: str, division: str) -> bool:
    """
    Returns True if search_text contains at least one anchor term for the division,
    OR if the division has no anchor requirement.
    Case-insensitive substring match.
    """
    if division in _NO_ANCHOR_DIVISIONS or division not in DIVISION_ANCHORS:
        return True
    txt = search_text.lower()
    stems = _DIVISION_ANCHOR_STEMS.get(division, set())
    return any(
        _anchor_term_matches(txt, anchor, stem=anchor in stems)
        for anchor in DIVISION_ANCHORS[division]
    )


def clean_keyword(raw: str) -> Optional[str]:
    """Normalize a curriculum phrase without deleting clinical qualifiers.

    Parenthetical, comma-separated, and dash-delimited text is retained because
    APDR uses those sections to distinguish clinically different topics (for
    example, ``Bone Scan - normal`` versus ``Bone Scan - Paget disease``).
    """
    s = unicodedata.normalize("NFKC", raw).strip()
    s = re.sub(r'[\[\](){}]', ' ', s)
    s = re.sub(r'[–—−]', ' ', s)
    s = re.sub(r'\s+-\s+', ' ', s)
    s = re.sub(r'[,;:]', ' ', s)
    s = re.sub(r'["“”„]', '', s)
    s = re.sub(r'\s+', ' ', s).strip().lower()
    if len(s) < 3:
        return None
    return s


def _legacy_index_keyword(raw: str) -> Optional[str]:
    """Return the former destructive key solely for synonym-index fallback."""
    s = raw.strip()
    s = re.sub(r'\s*\[.*?\]', '', s)
    s = re.sub(r'\s*\(.*?\)', '', s)
    s = re.sub(r'\s+on\s+.*$', '', s, flags=re.IGNORECASE)
    s = re.sub(r'\s+[-–]\s+.*$', '', s)
    colon = re.match(r'^(.+?)\s*:\s*(.+)$', s.strip())
    if colon:
        before = colon.group(1).strip().lower()
        after = colon.group(2).strip()
        modality_prefixes = {
            'mri', 'ct', 'pet', 'spect', 'us', 'xr', 'cxr', 'fdg',
            'mra', 'mrv', 'spect/ct', 'pet/ct',
        }
        body_part_prefixes = {
            'hip', 'knee', 'shoulder', 'ankle', 'wrist', 'elbow', 'spine',
            'neck', 'chest', 'breast', 'pelvis', 'abdomen', 'liver', 'renal',
            'hepatic',
        }
        s = after if before in modality_prefixes | body_part_prefixes else before
    s = s.split(',')[0]
    s = re.sub(r'[)()\[\]"""""„]+', '', s).strip().lower()
    return s if len(s) >= 3 else None


def load_parser_artifact_ids() -> set[str]:
    path = PATHS.get("apdr_parser_artifacts")
    if not path or not Path(path).exists():
        return set()
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return set(data.get("excluded_keyword_ids", {}))


def load_topic_normalization() -> dict:
    path = PATHS.get("apdr_topic_normalization")
    if not path or not Path(path).exists():
        return {}
    return json.loads(Path(path).read_text(encoding="utf-8")).get("topics", {})


# ── Index builders ────────────────────────────────────────────────────────────

def build_guideline_index(
    guideline_csv: Optional[Path] = None,
    synonym_index_path: Optional[Path] = None,
) -> tuple:
    """
    Load guideline topics from a standard 4-column CSV and synonym/CUI maps.

    Guideline-agnostic: accepts any CSV with columns:
      canonical_name, category, specialty, source_type
    This is the output format of GuidelineIngestionSubagent.

    If guideline_csv is not provided, falls back to the pre-ingested APDR CSV
    at PATHS["apdr_keywords"] (run `python -m openredu.run ingest` to generate
    a structured CSV from any raw guideline file first).

    Returns:
        topics: list of {keyword_id, keyword (cleaned), raw_keyword, specialty, source_type}
        kw_to_synonyms: {normalized_keyword → set of synonym strings}
        kw_to_cui: {normalized_keyword → CUI string}
    """
    synonym_path = synonym_index_path or PATHS["final_synonym_index"]

    # Resolve guideline CSV:
    # Priority: (1) explicitly passed path, (2) pre-ingested structured CSV,
    # (3) raw APDR CSV as last-resort fallback
    if guideline_csv is None:
        structured = PATHS["guidelines"] / "structured_apdr.csv"
        if structured.exists():
            guideline_csv = structured
        else:
            guideline_csv = PATHS["apdr_keywords"]

    topics = []
    seen = set()
    legacy_by_topic_id: dict[str, str] = {}
    parser_artifact_ids = load_parser_artifact_ids()
    topic_normalization = load_topic_normalization()
    normalization_by_raw = {
        (
            row.get("division", ""),
            row.get("raw_keyword", "").casefold(),
        ): row
        for row in topic_normalization.values()
    }
    with open(guideline_csv, newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []

        # Detect format: standard 4-column vs raw APDR CSV
        is_standard = "canonical_name" in headers
        is_raw_apdr = "canonical_keyword" in headers

        for i, row in enumerate(reader):
            if is_standard:
                # Standard format from GuidelineIngestionSubagent
                raw = (row.get('canonical_name') or '').strip()
                specialty   = (row.get('specialty') or '').strip()
                source_type = (row.get('source_type') or 'condition').strip()
                keyword_id  = f"topic_{i:05d}"
            elif is_raw_apdr:
                # Raw APDR CSV fallback — filter must_see_diagnosis only
                if row.get('source_type') != 'must_see_diagnosis':
                    continue
                raw         = (row.get('canonical_keyword') or '').strip()
                specialty   = (row.get('division') or '').strip()
                source_type = row.get('source_type', '')
                keyword_id  = row.get('keyword_id', f"topic_{i:05d}")
            else:
                continue

            if keyword_id in parser_artifact_ids:
                continue
            normalization = (
                topic_normalization.get(keyword_id)
                or normalization_by_raw.get((specialty, raw.casefold()))
                or {}
            )
            if normalization.get("is_alias"):
                continue
            keyword_id = normalization.get("canonical_topic_id", keyword_id)
            kw = (
                normalization.get("normalized_key")
                or clean_keyword(raw)
            )
            if not kw:
                continue
            key = (specialty, kw)
            if key in seen:
                continue
            seen.add(key)
            legacy_by_topic_id[keyword_id] = _legacy_index_keyword(raw) or ""
            topics.append({
                'keyword_id':  keyword_id,
                'keyword':     kw,
                'raw_keyword': raw,
                'specialty':   specialty,
                'source_type': source_type,
                'canonical_label': normalization.get("canonical_label", raw),
                'target_type': normalization.get("target_type", "unclassified"),
                'core_concepts': normalization.get("core_concepts", []),
                'required_context': normalization.get("required_context", []),
            })

    # Load synonym index
    kw_to_synonyms: dict = {}
    kw_to_cui: dict = {}
    if synonym_path.exists():
        data = json.loads(synonym_path.read_text())
        for kw, v in data.items():
            synonyms = v.get("all_synonyms") or []
            if synonyms:
                kw_to_synonyms[kw] = {s.lower() for s in synonyms if s}
            cui = v.get("cui")
            if cui:
                kw_to_cui[kw] = cui

        # Topic-ID corrections are applied after the generated index so manual
        # clinical review remains reproducible without editing that artifact.
        correction_path = PATHS.get("apdr_cui_corrections")
        corrections = {}
        if correction_path and correction_path.exists():
            corrections = json.loads(correction_path.read_text()).get("corrections", {})
        for topic in topics:
            topic_id = topic["keyword_id"]
            keyword = topic["keyword"]
            legacy_keyword = legacy_by_topic_id.get(topic_id, "")
            synonym_key = (
                keyword if keyword in kw_to_synonyms
                else legacy_keyword if legacy_keyword in kw_to_synonyms
                else ""
            )
            cui_key = (
                keyword if keyword in kw_to_cui
                else legacy_keyword if legacy_keyword in kw_to_cui
                else ""
            )
            if synonym_key:
                kw_to_synonyms[topic_id] = set(kw_to_synonyms[synonym_key])
            if cui_key:
                kw_to_cui[topic_id] = kw_to_cui[cui_key]
            correction = corrections.get(topic_id)
            if correction:
                if correction.get("action") == "remove_cui":
                    kw_to_cui.pop(topic_id, None)
                elif (
                    correction.get("action") == "set_cui"
                    and correction.get("cui")
                ):
                    kw_to_cui[topic_id] = correction["cui"]

            normalization = topic_normalization.get(topic_id)
            if normalization:
                kw_to_synonyms[topic_id] = set(
                    normalization.get("safe_synonyms") or [keyword]
                )
                if (
                    normalization.get("cui_match_enabled")
                    and normalization.get("terminology_cui")
                ):
                    kw_to_cui[topic_id] = normalization["terminology_cui"]
                else:
                    kw_to_cui.pop(topic_id, None)

    source_label = guideline_csv.name
    log.info(f"Guideline index ({source_label}): {len(topics)} topics, "
             f"{len(kw_to_synonyms)} synonym entries, {len(kw_to_cui)} CUI entries")
    return topics, kw_to_synonyms, kw_to_cui


# Backward-compatible alias
def build_apdr_index(
    apdr_csv: Optional[Path] = None,
    synonym_index_path: Optional[Path] = None,
) -> tuple:
    """Alias for build_guideline_index — kept for backward compatibility."""
    return build_guideline_index(apdr_csv, synonym_index_path)


def build_inverted_index(texts: list) -> dict:
    """Build word → set-of-indices inverted index."""
    index = defaultdict(set)
    for idx, text in enumerate(texts):
        for word in re.findall(r"[a-z0-9''\-]+", text):
            index[word].add(idx)
    return dict(index)


# ── Search text builder ───────────────────────────────────────────────────────

def build_search_text(state: CaseState) -> str:
    """
    Concatenate searchable text fields for curriculum topic matching.

    Included fields (mapping_quality_revision 2026-07-13):
      diagnosis_normalized, diagnosis, finding — LLM-extracted case-specific fields
      article_title, figure_caption            — direct case description
      results_text                             — figure-referencing paragraph
      modality, imaging_modality, anatomy      — inclusion-policy-validated route
                                                 context for modality-constrained
                                                 curriculum targets

    Excluded fields (reduce false positives):
      case_text   — may contain DDx mentions unrelated to this figure's diagnosis
      abstract    — background/context text with unrelated disease mentions
      author_keywords — paper-level topics, not figure-specific

    Rationale: matching is performed only against fields that directly describe
    the individual case's diagnosis and imaging findings, not the broader clinical
    narrative, to reduce false-positive curriculum mappings.
    """
    parts = [
        state.diagnosis_normalized or "",
        state.diagnosis or "",
        state.finding or "",
        state.article_title or "",
        state.figure_caption or "",
        state.results_text or "",
        state.modality or "",
        state.imaging_modality or "",
        state.anatomy or "",
    ]
    return re.sub(r"\s+", " ", " ".join(parts)).lower()


# ── Per-case matching (single CaseState against pre-built index) ──────────────

def _check_peds_age(case_age: Optional[int], division: str) -> bool:
    """
    Peds division additional filter: only allow if age <= 18 or age is unknown.
    If age is known and > 18, reject Peds topic mapping.
    """
    if division != "Peds":
        return True
    if case_age is None:
        return True
    return case_age <= 18


def match_case_to_topics(
    search_text: str,
    apdr_topics: list,
    kw_to_synonyms: dict,
    kw_to_cui: dict,
    case_cuis: list,
    case_age: Optional[int] = None,
    corpus_index: Optional[dict] = None,
    corpus_texts: Optional[list] = None,
    corpus_case_idx: Optional[int] = None,
) -> tuple:
    """
    Match a single case to APDR topics via 3 paths.

    For per-case matching (not batch), we use a single-text index.
    Returns (matched_topic_ids, matched_paths).

    case_age: patient age in years (from demographics). Used to gate Peds
    division mapping — cases with known age > 18 are not mapped to Peds topics.
    """
    # Build single-text index for this case
    single_texts = [search_text]
    single_index = build_inverted_index(single_texts)

    # CUI → set of case indices (just index 0 for single case)
    cui_to_cases = defaultdict(set)
    for cui in case_cuis:
        if cui:
            cui_to_cases[cui].add(0)

    matched_ids  = []
    matched_paths = set()
    anchor_results = {
        division: _check_division_anchor(search_text, division)
        for division in {topic.get("specialty", "") for topic in apdr_topics}
    }

    for topic in apdr_topics:
        kw = topic['keyword']
        division = topic.get('specialty', '')

        # Division anchor filter: skip if search_text lacks division-specific terms
        if not anchor_results[division]:
            continue

        # Peds age filter: skip if patient is known adult
        if not _check_peds_age(case_age, division):
            continue

        hit = _match_keyword_single(
            kw, search_text, single_index, kw_to_synonyms, kw_to_cui,
            cui_to_cases, topic_id=topic["keyword_id"],
        )
        if not hit and topic.get("target_type") in {
            "composite_imaging_target",
            "procedural_task",
            "differential_or_multiconcept",
        }:
            if _match_composite_concepts(
                topic.get("core_concepts", []), search_text
            ):
                hit = {"composite"}
        if hit:
            matched_ids.append(topic['keyword_id'] or topic['keyword'])
            matched_paths.update(hit)

    return matched_ids, sorted(matched_paths)


_COMPOSITE_GENERIC_TOKENS = {
    "abnormal", "assessment", "diagnosis", "disease", "finding", "findings",
    "imaging", "normal", "pathology", "positive", "study", "testing",
}


def _normalize_concept_token(token: str) -> str:
    if token == "metastases":
        return "metastasis"
    if len(token) > 4 and token.endswith("ies"):
        return token[:-3] + "y"
    if (
        len(token) > 4
        and token.endswith("s")
        and not token.endswith(("ss", "sis"))
    ):
        return token[:-1]
    return token


def _match_composite_concepts(core_concepts: list[str], search_text: str) -> bool:
    """Require independent evidence for at least two concept groups.

    This supports modality-plus-diagnosis and finding-plus-anatomy targets
    without reducing them to a single broad disease CUI.
    """
    text_tokens = {
        _normalize_concept_token(token)
        for token in re.findall(r"[a-z0-9]+", search_text.lower())
    }
    groups: list[tuple[tuple[str, ...], bool]] = []
    seen_groups: set[tuple[str, ...]] = set()
    modality_words = {
        "ct", "hida", "imaging", "mri", "pet", "radiography", "scan",
        "scintigraphy", "spect", "ultrasound", "uptake",
    }
    for concept in core_concepts:
        raw_tokens = set(re.findall(r"[a-z0-9]+", concept.lower()))
        tokens = tuple(
            _normalize_concept_token(token)
            for token in re.findall(r"[a-z0-9]+", concept.lower())
            if len(token) >= 2
            and token not in STOP_WORDS
            and token not in _COMPOSITE_GENERIC_TOKENS
        )
        if not tokens or tokens in seen_groups:
            continue
        seen_groups.add(tokens)
        groups.append((tokens, bool(raw_tokens & modality_words)))
    if len(groups) < 2:
        return False

    required_indices = [0, 1]
    if groups[0][1] and groups[1][1]:
        next_clinical = next(
            (
                index
                for index, (_, is_modality) in enumerate(groups[2:], 2)
                if not is_modality
            ),
            None,
        )
        if next_clinical is not None:
            required_indices.append(next_clinical)
    elif not groups[0][1]:
        later_modality = next(
            (
                index
                for index, (_, is_modality) in enumerate(groups[2:], 2)
                if is_modality
            ),
            None,
        )
        if later_modality is not None:
            required_indices.append(later_modality)
    return all(
        set(groups[index][0]).issubset(text_tokens)
        for index in required_indices
    )


def _match_keyword_single(
    kw_norm: str,
    search_text: str,
    index: dict,
    kw_to_synonyms: dict,
    kw_to_cui: dict,
    cui_to_cases: dict,
    topic_id: Optional[str] = None,
) -> set:
    """
    Match one keyword against one case's search text. Returns set of matched paths.
    """
    matched_paths = set()

    # Path 1: direct text match
    words = re.findall(r"[a-z0-9''\-]+", kw_norm)
    content_words = [w for w in words if len(w) >= 3]
    if content_words:
        sets = sorted([index.get(w, set()) for w in content_words], key=len)
        if sets:
            candidates = sets[0].copy()
            for s in sets[1:]:
                candidates &= s
                if not candidates:
                    break
            if candidates:
                pattern = r"\b" + re.escape(kw_norm) + r"\b"
                if re.search(pattern, search_text):
                    matched_paths.add("direct")

    # Path 2: synonym expansion
    if kw_to_synonyms:
        synonyms = kw_to_synonyms.get(topic_id, kw_to_synonyms.get(kw_norm, set()))
        for syn in synonyms:
            if syn == kw_norm:
                continue
            syn_words = re.findall(r"[a-z0-9''\-]+", syn)
            syn_content = [w for w in syn_words if len(w) >= 3]
            if not syn_content:
                continue
            sets2 = sorted([index.get(w, set()) for w in syn_content], key=len)
            if not sets2:
                continue
            cands2 = sets2[0].copy()
            for s in sets2[1:]:
                cands2 &= s
                if not cands2:
                    break
            if cands2:
                pat2 = r"\b" + re.escape(syn) + r"\b"
                if re.search(pat2, search_text):
                    matched_paths.add("synonym")
                    break

    # Path 3: CUI-based match
    if kw_to_cui and cui_to_cases:
        cui = kw_to_cui.get(topic_id, kw_to_cui.get(kw_norm))
        if cui and cui_to_cases.get(cui):
            matched_paths.add("cui")

    return matched_paths


# ── MatchingSubagent class ────────────────────────────────────────────────────

class MatchingSubagent(Subagent):
    """
    Matches a CaseState to APDR guideline topics.
    Requires pre-built apdr_topics, kw_to_synonyms, kw_to_cui.
    is_llm = False: fully deterministic.
    """
    name = "MatchingSubagent"
    is_llm = False

    def __init__(
        self,
        apdr_topics: list,
        kw_to_synonyms: dict,
        kw_to_cui: dict,
    ):
        self.apdr_topics    = apdr_topics
        self.kw_to_synonyms = kw_to_synonyms
        self.kw_to_cui      = kw_to_cui

    def run(self, state: CaseState) -> CaseState:
        """Match case to APDR topics via 3 paths."""
        search_text = build_search_text(state)
        case_age = (state.demographics or {}).get("age") if state.demographics else None
        matched_ids, matched_paths = match_case_to_topics(
            search_text=search_text,
            apdr_topics=self.apdr_topics,
            kw_to_synonyms=self.kw_to_synonyms,
            kw_to_cui=self.kw_to_cui,
            case_cuis=state.diagnosis_cuis,
            case_age=case_age,
        )
        state.curriculum_topics = matched_ids
        state.mapping_paths     = matched_paths
        return state

    def run_with_broader_synonyms(self, state: CaseState) -> CaseState:
        """
        Retry matching with looser synonym matching (substring instead of word-boundary).
        Called by MappingMasterAgent on no-match cases.
        Division anchor filter is applied here too.
        """
        search_text = build_search_text(state)
        case_age = (state.demographics or {}).get("age") if state.demographics else None
        matched_ids  = []
        matched_paths = set()
        anchor_results = {
            division: _check_division_anchor(search_text, division)
            for division in {
                topic.get("specialty", "") for topic in self.apdr_topics
            }
        }

        for topic in self.apdr_topics:
            kw = topic['keyword']
            division = topic.get('specialty', '')

            # Division anchor filter applies in broad mode too
            if not anchor_results[division]:
                continue

            # Peds age filter applies in broad mode too
            if not _check_peds_age(case_age, division):
                continue

            # Looser: check if any synonym appears as a substring
            synonyms = self.kw_to_synonyms.get(
                topic["keyword_id"], self.kw_to_synonyms.get(kw, {kw})
            )
            for syn in synonyms:
                if len(syn) >= 4 and syn in search_text:
                    matched_ids.append(topic['keyword_id'] or topic['keyword'])
                    matched_paths.add("synonym_broad")
                    break

        state.curriculum_topics = matched_ids
        state.mapping_paths     = sorted(matched_paths)
        return state
