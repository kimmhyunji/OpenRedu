"""
CaseState and LearnerState dataclasses.

CaseState flows through the full pipeline:
  RetrievalSubagent → ClassificationSubagent → ExtractionSubagent
  → StandardizationSubagent → MatchingSubagent

to_jsonl_line() outputs both internal fields AND viewer-compatible aliases
so the output JSONL can be dropped directly into final_json/ for the case viewer.
"""
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional


@dataclass
class CaseState:
    # ── Provenance (RetrievalSubagent) ────────────────────────────────────────
    pmcid: str = ""
    case_id: str = ""
    license: str = ""
    article_title: str = ""
    journal: str = ""
    pub_date: str = ""           # "YYYY-MM" or "YYYY"
    year: str = ""               # viewer compat (CaseData.year)
    month: str = ""              # viewer compat (CaseData.month)
    publication_date: str = ""   # viewer compat — same value as pub_date
    modality: str = ""
    imaging_modality: str = ""   # viewer compat — from MODALITY_CONFIG
    anatomy: str = ""            # viewer compat — from MODALITY_CONFIG

    # ── Source text (RetrievalSubagent) ───────────────────────────────────────
    author_keywords: list = field(default_factory=list)
    abstract: str = ""
    case_text: str = ""
    results_text: str = ""
    figure_label: str = ""
    figure_caption: str = ""
    image_paths: list = field(default_factory=list)
    image_size_kb: Optional[float] = None

    # ── Classification (ClassificationSubagent) ───────────────────────────────
    is_radiologic_case: Optional[bool] = None   # None = not yet decided
    is_multipanel: bool = False
    panel_count: int = 1
    # "rule_include" | "rule_exclude" | "llm_adjudicated" | "uncertain_pending"
    classification_route: str = ""

    # ── Extraction (ExtractionSubagent) ───────────────────────────────────────
    demographics: dict = field(default_factory=lambda: {"age": None, "sex": None})
    finding: str = ""
    diagnosis: str = ""
    diagnosis_normalized: str = ""
    laterality: str = ""
    title_match_quality: str = ""            # "high" | "medium" | "low"
    extraction_self_check_passed: Optional[bool] = None
    # Pass 2 (figure-scope finding, added in the revision): the pass-1 finding
    # before rewriting, and "figure" | "article_fallback_*" ("" = pass 2 not run)
    finding_article_level: str = ""
    finding_scope: str = ""

    # ── Verification (VerificationSubagent, opt-in) ───────────────────────────
    # {} = not run. Keys: ok, model_id, prompt_version, classification/finding/laterality
    # verdicts, parsed, needs_review (set by CurationMasterAgent).
    verification: dict = field(default_factory=dict)

    # ── Mapping (MappingMasterAgent subagents) ────────────────────────────────
    diagnosis_cuis: list = field(default_factory=list)
    diagnosis_umls_preferred: str = ""
    curriculum_topics: list = field(default_factory=list)
    mapping_paths: list = field(default_factory=list)  # ["direct","synonym","cui"]
    dedup_group_id: Optional[str] = None               # first CUI for grouping

    # ── Control (all agents append) ───────────────────────────────────────────
    # "retrieved"|"classified"|"extracted"|"mapped"|"rejected"|"failed"|"unmapped"
    status: str = "retrieved"
    models_used: dict = field(default_factory=dict)
    agent_log: list = field(default_factory=list)
    # Each entry: {agent, decision, reason, model, ts}
    # decision values: "accept"|"retry"|"escalate"|"route"|"drop"

    # ─────────────────────────────────────────────────────────────────────────

    def to_jsonl_line(self) -> str:
        """
        Serialize to JSONL. Includes OpenRedu internal fields AND viewer-compat
        aliases so output files work directly with the viewer API without
        any post-processing.
        """
        d = asdict(self)
        # Viewer-compatible aliases
        d["title"]              = self.article_title
        d["keywords"]           = self.author_keywords
        d["figure_legend"]      = self.figure_caption
        d["image_path"]         = self.image_paths[0] if self.image_paths else None
        d["diagnosis_cui"]      = self.diagnosis_cuis[0] if self.diagnosis_cuis else None
        d["diagnosis_umls_pref"] = self.diagnosis_umls_preferred
        return json.dumps(d, ensure_ascii=False)

    @classmethod
    def from_dict(cls, d: dict) -> "CaseState":
        """Deserialize from dict, ignoring unknown keys (viewer aliases etc.)."""
        import dataclasses
        known = {f.name for f in dataclasses.fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in known})

    @classmethod
    def from_phase2_dict(cls, raw: dict) -> "CaseState":
        """
        Load from existing phase2/phase3 JSONL record.
        Maps old field names to CaseState field names.
                """
        # Image path: single string → list
        img = raw.get("image_path")
        if img and isinstance(img, str):
            image_paths = [img]
        else:
            image_paths = []

        # CUI: single string → list
        cui = raw.get("diagnosis_cui") or raw.get("diagnosis_cuis")
        if isinstance(cui, str) and cui:
            diagnosis_cuis = [cui]
        elif isinstance(cui, list):
            diagnosis_cuis = cui
        else:
            diagnosis_cuis = []

        # pub_date / year / month
        pub_date = raw.get("publication_date", "") or raw.get("pub_date", "")
        year = raw.get("year", "")
        month = raw.get("month", "")
        if pub_date and not year:
            parts = pub_date.split("-")
            year = parts[0] if parts else ""
            month = parts[1] if len(parts) > 1 else ""

        return cls(
            pmcid               = raw.get("pmcid", ""),
            case_id             = raw.get("case_id", ""),
            license             = raw.get("license", ""),
            article_title       = raw.get("title", raw.get("article_title", "")),
            journal             = raw.get("journal", ""),
            pub_date            = pub_date,
            year                = year,
            month               = month,
            publication_date    = pub_date,
            modality            = raw.get("modality", ""),
            imaging_modality    = raw.get("imaging_modality", ""),
            anatomy             = raw.get("anatomy", ""),
            author_keywords     = raw.get("keywords", raw.get("author_keywords", [])) or [],
            abstract            = raw.get("abstract", ""),
            case_text           = raw.get("case_text", ""),
            results_text        = raw.get("results_text", ""),
            figure_label        = raw.get("figure_label", ""),
            figure_caption      = raw.get("figure_legend", raw.get("figure_caption", "")),
            image_paths         = image_paths,
            image_size_kb       = raw.get("image_size_kb"),
            diagnosis_cuis      = diagnosis_cuis,
            diagnosis_umls_preferred = raw.get("diagnosis_umls_pref",
                                               raw.get("diagnosis_umls_preferred", "")),
            status              = "retrieved",
        )


@dataclass
class LearnerState:
    """
    Per-learner state for TrackingMasterAgent.

    Core fields (raw data):
      exposure_events: ordered log of case-view events
      coverage:        per-APDR-topic encounter count (computed by CoverageSubagent)

    Derived views (recomputed by CoverageSubagent on each update):
      completed_topics: topic_ids with encounter count >= COVERAGE_THRESHOLD
      missing_topics:   topic_ids with encounter count == 0
      coverage_pct:     len(completed_topics) / total APDR topics  (0.0–1.0)

    This is the paper's central claim data structure:
    "completed vs missing curriculum topics become visible per learner."
    """
    learner_id: str

    # Raw data
    exposure_events: list = field(default_factory=list)
    # [{"case_id": str, "topic_ids": List[str], "ts": str (ISO8601)}]

    coverage: dict = field(default_factory=dict)
    # {topic_id: int}  — cumulative encounter count per APDR topic

    # Derived views (recomputed by CoverageSubagent)
    completed_topics: list = field(default_factory=list)
    # topic_ids with count >= COVERAGE_THRESHOLD
    missing_topics: list = field(default_factory=list)
    # topic_ids with count == 0
    coverage_pct: float = 0.0
    # completed_topics / total APDR topics
