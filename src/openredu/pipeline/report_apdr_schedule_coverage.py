#!/usr/bin/env python3
"""
report_apdr_schedule_coverage.py

Compute APDR residency schedule topic coverage against the OpenRedu corpus.

MATCHING POLICY (v2 — strict AND)
===================================
A corpus case matches a schedule topic if and only if ALL of the following hold:

  Gate 1 — Division:  case.modality maps to the topic's subspecialty division
  Gate 2 — Keyword:   case.diagnosis OR case.finding contains ≥1 topic keyword
  Gate 3 — Pediatric topics: patient age ≤ 18 years, or age not reported
            with an explicit pediatric descriptor

A topic is "covered" if ≥1 corpus case satisfies all applicable gates.

Eligibility is determined independently of observed coverage. An entry is excluded
only when its educational objective cannot be represented by a patient-level
diagnostic imaging case: foundational normal anatomy, physics/regulation, pure
image-acquisition technique, procedure-performance competency, or an undefined
catch-all review topic. Diagnostic signs, devices/lines, interpretive frameworks,
and mixed technique-plus-findings topics remain eligible.

OUTPUT
======
  data/curriculum_mapping/apdr_schedule_coverage.json
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "data"
CURRICULUM = ROOT / "data/curriculum"
SCHEDULE_CSV = CURRICULUM / "apdr_schedule_topics.csv"

# ── Gate 1: modality → set of ALLOWED divisions ──────────────────────────────
# ── Division gate: modality → set of ALLOWED divisions ───────────────────────
# Each modality maps to one or more divisions it is anatomically compatible with.
# A case passes the division gate if its modality is in the allowed set for
# the topic's division.
#
# Design principles:
#   - Unambiguous modalities (MAMMOGRAM, MRI_BRAIN) → single division only
#   - Ambiguous modalities (CT_ABDOMEN) → multiple compatible divisions
#     (GI + GU + IR), relying on the keyword gate to prevent cross-division errors
#   - This prevents e.g. a MAMMOGRAM case matching a GU "bladder papilloma" topic,
#     while still allowing CT_ABDOMEN cases to match both GI and GU topics
#   - Peds uses age gate (not modality), handled separately in code

MODALITY_ALLOWED_DIVISIONS: dict[str, set[str]] = {
    # Chest — unambiguous
    "CXR":                {"Chest"},
    "CT_CHEST":           {"Chest"},
    "CT_CHEST_VASC":      {"Chest"},

    # Neuro — unambiguous
    "MRI_BRAIN":          {"Neuro"},
    "CT_BRAIN":           {"Neuro"},
    "MRI_SPINE":          {"Neuro"},
    "MRI_NEURO_SPINE":    {"Neuro"},

    # MSK — unambiguous
    "MSK_XRAY":           {"MSK"},
    "MRI_MSK":            {"MSK"},
    "MSK_CT":             {"MSK"},
    "MSK_ULTRASOUND":     {"MSK"},

    # Breast — unambiguous
    "MAMMOGRAM":          {"Breast"},
    "BREAST_MRI":         {"Breast"},
    "BREAST_ULTRASOUND":  {"Breast"},

    # NM — unambiguous
    "NM_NUCLEAR":         {"NM"},

    # Cardiovascular — Cardiac (Peds cardiac also handled via age gate)
    "CARDIOVASCULAR_MRI": {"Cardiac"},

    # Abdominal CT/MRI — ambiguous: GI, GU, or IR depending on content
    "CT_ABDOMEN":         {"GI", "GU", "IR"},
    "MRI_ABDOMEN":        {"GI", "GU", "IR"},

    # Abdominal US — GI or US depending on context
    "US_ABDOMEN":         {"GI", "US"},

    # Pelvic — GU or US
    "US_PELVIS":          {"GU", "US"},
    "MRI_PELVIS":         {"GU"},
    "US_GYN_TRANS":       {"GU", "US"},

    # Fluoroscopy — GI/GU procedures
    "GI_FLUOROSCOPY":     {"GI", "IR"},
    "GU_FLUOROSCOPY":     {"GU", "IR"},

    # Vascular US — US division
    "US_VASCULAR":        {"US", "IR"},

    # Superficial / neck / pleural US — US division
    "US_SUPERFICIAL":     {"US"},
}

# ── Gate 2: topic keyword sets ────────────────────────────────────────────────
# Loaded from apdr_schedule_topic_keywords.json (edit that file to update phrases).
# Each topic entry: list of lowercase phrases; a case matches if ≥1 found in
# case.diagnosis + case.finding (word-boundary match).
#
# TECHNIQUE = []      → excluded from coverage analysis
# Non-empty list     → clinical topic, both gates required

_TOPIC_KEYWORDS_PATH = DATA / "guidelines/apdr_schedule_topic_keywords.json"

def _load_topic_keywords(path: Path) -> dict[str, dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    # Schedule-entry IDs, rather than labels, are the lookup key. Labels recur at
    # different year/week positions and "Liver" occurs in both GI and US; a
    # label-keyed dict silently overwrote those distinct entries.
    result: dict[str, dict] = {}
    for entry in data["entries"]:
        entry_id = entry["schedule_entry_id"]
        if entry_id in result:
            raise ValueError(f"Duplicate APDR schedule_entry_id: {entry_id}")
        result[entry_id] = {
            "phrases": entry["phrases"],
            "requires_pediatric_evidence": bool(
                entry.get("requires_pediatric_evidence", False)
            ),
            "allowed_modalities": entry.get("allowed_modalities", []),
        }
    return result

# The topic phrase file is not distributed (see docs/data_layout.md for its format and
# examples/fake_curriculum/topic_keywords.json for an invented example). Without it the
# module still imports, with an empty table.
TOPIC_KEYWORDS: dict[str, dict] = (
    _load_topic_keywords(_TOPIC_KEYWORDS_PATH) if _TOPIC_KEYWORDS_PATH.exists() else {}
)

# (A legacy inline copy of the topic phrase lists was removed from this release;
#  the topic phrase file is curriculum-derived data and is not distributed.)


# Eligibility is deliberately separate from TOPIC_KEYWORDS.  A topic must not
# enter or leave the denominator merely because a synonym list is empty or
# because no matching case happened to be found.
#
# Policy version: APDR_SCHEDULE_ELIGIBILITY_V1 (2026-07-22)
TOPIC_EXCLUSIONS: dict[str, tuple[str, str]] = {
    # Foundational normal anatomy / physics / regulatory material
    "the normal chest x-ray": ("foundational_non_case", "Normal-reference teaching objective, not a patient-level abnormal imaging case."),
    "lobar anatomy": ("foundational_non_case", "Normal anatomy teaching objective."),
    "nm physics (radioactivity, instrumentation, spect/pet)": ("foundational_non_case", "Physics and instrumentation competency."),
    "radiation safety / authorized user": ("foundational_non_case", "Regulatory and radiation-safety competency."),
    "practical physics / doppler ultrasound": ("foundational_non_case", "Physics and acquisition competency."),

    # Pure acquisition/examination technique without a defined finding/disease
    "techniques in neuroimaging": ("pure_technique", "Image-acquisition technique without a defined case entity."),
    "the radiographic examination": ("pure_technique", "Examination technique without a defined case entity."),
    "cross-sectional imaging techniques": ("pure_technique", "Image-acquisition technique without a defined case entity."),
    "chest ct": ("pure_technique", "Modality/technique topic without a defined case entity."),
    "fundamentals of high-resolution ct (ch. 1–2)": ("pure_technique", "Foundational acquisition/technical content."),
    "fundamentals of high-resolution ct (ch. 3–5)": ("pure_technique", "Foundational acquisition/technical content."),
    "thoracic mri: techniques and approach": ("pure_technique", "Acquisition/approach topic without a defined case entity."),
    "introduction: abdominal ct approach": ("pure_technique", "General interpretive approach without a defined case entity."),
    "introduction/basic approach, intraperitoneal and retroperitoneal spaces and body wall": ("pure_technique", "General interpretive approach without a defined case entity."),
    "contrast-enhanced ultrasound / elastography": ("pure_technique", "Technique topic without a defined disease or finding."),
    "msk mri: pulse sequences and fundamentals": ("pure_technique", "Pulse-sequence and acquisition competency."),

    # Procedure-performance objectives are not inferred from a diagnostic case
    "interventional techniques": ("procedure_performance", "Procedure-performance competency."),
    "gu interventions and advanced topics": ("procedure_performance", "Intervention-focused competency; the label does not define a diagnostic entity."),
    "fundamentals of angiography": ("procedure_performance", "Procedure-performance competency."),
    "image-guided percutaneous biopsy": ("procedure_performance", "Procedure-performance competency."),
    "percutaneous abscess and fluid drainage": ("procedure_performance", "Procedure-performance competency."),
    "central venous access (picc, tunneled line, port)": ("procedure_performance", "Procedure-performance competency."),
    "fundamentals of angiography / vascular interventions": ("procedure_performance", "Procedure-performance competency."),
    "biliary intervention": ("procedure_performance", "Procedure-performance competency."),
    "gastrointestinal tract intervention": ("procedure_performance", "Procedure-performance competency."),
    "percutaneous genitourinary tract intervention": ("procedure_performance", "Procedure-performance competency."),
    "advanced arterial interventions (embolization, ufe)": ("procedure_performance", "Procedure-performance competency."),
    "lower extremity arteries / venous intervention": ("procedure_performance", "Procedure-performance competency."),
    "chemoembolization / radioembolization": ("procedure_performance", "Procedure-performance competency."),
    "image-guided tumor ablation": ("procedure_performance", "Procedure-performance competency."),
    # IR disease/vascular topics: despite being anchored to clinical conditions,
    # the educational objective in the IR curriculum is procedural/interventional.
    # Consistent with the IR-division procedure_performance policy.
    "ivc and tributaries / ivc filter placement": ("procedure_performance", "IR division topic; educational objective is procedural, not diagnostic case-based."),
    "abdominal aorta and pelvic arteries": ("procedure_performance", "IR division topic; educational objective is procedural, not diagnostic case-based."),
    "visceral arteries": ("procedure_performance", "IR division topic; educational objective is procedural, not diagnostic case-based."),
    "portal and hepatic veins / tips": ("procedure_performance", "IR division topic; educational objective is procedural, not diagnostic case-based."),

    # Undefined catch-all/review labels cannot be tested reproducibly
    "advanced msk mri topics": ("undefined_catch_all", "No bounded educational concept is specified."),
    "review of r1/r2 weak areas": ("undefined_catch_all", "Learner-dependent review label without a fixed topic."),
    "msk requisites comprehensive review": ("undefined_catch_all", "Comprehensive review label without a bounded topic."),
    "board prep and advanced topics": ("undefined_catch_all", "Unbounded review label."),
    "advanced pediatric topics": ("undefined_catch_all", "No bounded educational concept is specified."),
}

PEDS_TEXT_ANCHORS = (
    "pediatric", "paediatric", "child", "children", "infant", "neonate",
    "neonatal", "newborn", "adolescent", "teenager",
)


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", text.lower())).strip()


def phrase_in_text(phrase: str, text: str) -> bool:
    if not phrase or not text:
        return False
    return bool(re.search(
        r"(?<![a-z0-9])" + re.escape(normalize(phrase)) + r"(?![a-z0-9])", text
    ))


def case_primary_text(c: dict) -> str:
    return normalize(" ".join(filter(None, [
        c.get("diagnosis_normalized", ""),
        c.get("diagnosis", ""),
        c.get("finding", ""),
    ])))


def case_peds_evidence_text(c: dict) -> str:
    """Fields allowed to rescue an age-unreported case for Peds matching."""
    return normalize(" ".join(filter(None, [
        c.get("diagnosis_normalized", ""),
        c.get("diagnosis", ""),
        c.get("finding", ""),
        c.get("figure_caption", ""),
        c.get("caption", ""),
    ])))


def age_as_years(c: dict) -> float | None:
    a = (c.get("demographics") or {}).get("age")
    if a is None or a == "":
        return None
    try:
        return float(a)
    except (TypeError, ValueError):
        return None


def peds_evidence(c: dict) -> str | None:
    """Return the auditable evidence path for a pediatric case, else None."""
    a = age_as_years(c)
    if a is not None:
        return "age_le_18" if a <= 18 else None
    txt = case_peds_evidence_text(c)
    if any(phrase_in_text(anchor, txt) for anchor in PEDS_TEXT_ANCHORS):
        return "age_unreported_with_pediatric_text_anchor"
    return None


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def source_documents_by_division_year() -> dict[tuple[str, str], set[str]]:
    """Resolve APDR raw checklist provenance from the prior verbatim extract."""
    source_csv = ROOT / "data/curriculum/apdr_pmc_keywords.csv"
    resolved: dict[tuple[str, str], set[str]] = defaultdict(set)
    if not source_csv.exists():  # provenance record of the article's curriculum only; not needed for matching
        return resolved
    with source_csv.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            resolved[(row["division"], row["year"])].add(row["source_file"])
    return resolved


def schedule_row_sources(row: dict, registry: dict[tuple[str, str], set[str]]) -> list[str]:
    years = sorted(set(re.findall(r"R[1-4]", row["year_level"])))
    return sorted({doc for year in years for doc in registry.get((row["division"], year), set())})


def raw_source_manifest(schedule: list[dict], registry: dict[tuple[str, str], set[str]]) -> list[dict]:
    raw_root = ROOT / "radpathway/ARPD_processing/ARPD_Raw_Data"
    names = sorted({doc for row in schedule for doc in schedule_row_sources(row, registry)})
    manifest = []
    for name in names:
        path = raw_root / name
        manifest.append({
            "source_document": name,
            "path": str(path.relative_to(ROOT)),
            "exists": path.is_file(),
            "sha256": sha256_file(path) if path.is_file() else None,
        })
    return manifest


def main():
    schedule: list[dict] = []
    with open(SCHEDULE_CSV, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            schedule.append(row)
    print(f"Schedule topics: {len(schedule)}")

    corpus_path = ROOT / os.environ.get(
        "OPENREDU_APDR_CORPUS",
        "data/freeze/openredu_manuscript_2017_2026_scope_v2_extended/cases.jsonl",  # 18,617 + IBD 104 + MRU 89 = 18,810
    )
    corpus_manifest_path = corpus_path.parent / "manifest.json"
    cases = [json.loads(l) for l in corpus_path.open(encoding="utf-8") if l.strip()]
    print(f"Corpus: {len(cases)} cases")
    print("Building index...", flush=True)

    # Pre-index: division → set of case indices (via modality allowed-divisions)
    division_cases: dict[str, set[int]] = defaultdict(set)
    modality_cases: dict[str, set[int]] = defaultdict(set)   # for extra_modalities
    peds_cases: set[int] = set()
    peds_evidence_by_index: dict[int, str] = {}
    for i, c in enumerate(cases):
        mod = c.get("modality", "").upper()
        allowed_divs = MODALITY_ALLOWED_DIVISIONS.get(mod, set())
        for div in allowed_divs:
            division_cases[div].add(i)
        modality_cases[mod].add(i)
        evidence = peds_evidence(c)
        if evidence:
            peds_cases.add(i)
            peds_evidence_by_index[i] = evidence

    for div, s in division_cases.items():
        print(f"  {div:8s}: {len(s):6d} candidate cases")

    # Pre-compute primary text per case
    texts = [case_primary_text(c) for c in cases]
    source_registry = source_documents_by_division_year()

    print("Running coverage analysis...\n")

    results = []
    covered_total = 0
    excluded_total = 0
    current_div = None
    div_covered: Counter = Counter()
    div_total: Counter = Counter()

    print(f"{'Div':>6}  {'Type':>16}  {'n_cases':>8}  {'Status':<12}  Keyword")
    print("-" * 100)

    for entry_number, row in enumerate(schedule, start=1):
        div   = row["division"]
        ktype = row["keyword_type"]
        kw    = row["keyword"]
        kw_key = kw.lower().strip()

        if div != current_div:
            if current_div:
                print(f"  ── {current_div}: {div_covered[current_div]}/{div_total[current_div]} covered ──\n")
            current_div = div

        div_total[div] += 1

        schedule_entry_id = f"apdr_sched_{entry_number:04d}"
        canonical_topic_id = "apdr_sched_topic_" + hashlib.sha1(
            f"{div}|{kw_key}".encode("utf-8")
        ).hexdigest()[:12]
        source_documents = schedule_row_sources(row, source_registry)

        # Eligibility is set by the prespecified policy, never by match outcome.
        exclusion = TOPIC_EXCLUSIONS.get(kw_key)
        if exclusion:
            exclusion_category, exclusion_reason = exclusion
            status = "excluded"
            excluded_total += 1
            div_total[div] -= 1
            results.append({
                "schedule_entry_id": schedule_entry_id,
                "canonical_topic_id": canonical_topic_id,
                "division": div,
                "year_level": row["year_level"],
                "week": row["week"],
                "keyword_type": ktype,
                "keyword": kw,
                "eligible": False,
                "exclusion_category": exclusion_category,
                "exclusion_reason": exclusion_reason,
                "source_documents": source_documents,
                "n_cases": 0,
                "status": status,
            })
            print(f"{div:>6}  {ktype:>16}  {'—':>8}  {status:<12}  {kw[:55]}")
            continue

        # Look up keyword set
        topic_config = TOPIC_KEYWORDS.get(schedule_entry_id)
        keywords = topic_config["phrases"] if topic_config else None
        matched_indices: list[int] = []
        n_cases = 0
        if keywords is None:
            keywords = []
            status = "MISSING_KEY"
        elif keywords == []:
            # An eligible topic with no phrases is a policy/configuration error,
            # not an exclusion and not a coverage gap.
            status = "MISSING_KEYWORDS"
        else:
            # Gate 1: division filter
            if div == "Peds":
                # Peds gate: age ≤18, or unknown with an explicit pediatric
                # descriptor (across all modalities).
                div_case_indices = peds_cases
            elif topic_config.get("requires_pediatric_evidence", False):
                # A pediatric topic can occur outside the Peds division (for
                # example NM — Pediatric nuclear medicine). It must satisfy
                # both the division and pediatric-evidence gates.
                div_case_indices = division_cases.get(div, set()) & peds_cases
            else:
                # allowed_modalities: if set, use ONLY these modalities as the
                # candidate pool (overrides the standard division mapping).
                # Use this for MRI-titled topics that must exclude CT/US cases
                # but need modalities outside the normal division set.
                allowed = topic_config.get("allowed_modalities", [])
                if allowed:
                    div_case_indices = set()
                    for mod in allowed:
                        div_case_indices |= modality_cases.get(mod.upper(), set())
                else:
                    div_case_indices = division_cases.get(div, set())
                    # extra_modalities: append additional modalities on top of
                    # the standard division mapping (e.g. IBD MRI extraintestinal
                    # manifestations on CARDIOVASCULAR_MRI / MRI_BRAIN).
                    for extra_mod in topic_config.get("extra_modalities", []):
                        div_case_indices = div_case_indices | modality_cases.get(
                            extra_mod.upper(), set()
                        )

            # Gate 2: keyword match within division-filtered cases
            norm_keywords = [normalize(k) for k in keywords]
            matched_indices = []
            for idx in div_case_indices:
                txt = texts[idx]
                if any(phrase_in_text(k, txt) for k in norm_keywords):
                    matched_indices.append(idx)

            n_cases = len(matched_indices)

            status = "covered" if n_cases > 0 else "GAP"

        if status == "covered":
            covered_total += 1
            div_covered[div] += 1

        flag = "  <<<" if status == "GAP" else ""
        print(f"{div:>6}  {ktype:>16}  {n_cases:>8}  {status:<12}  {kw[:55]}{flag}")
        result = {
            "schedule_entry_id": schedule_entry_id,
            "canonical_topic_id": canonical_topic_id,
            "division": div,
            "year_level": row["year_level"],
            "week": row["week"],
            "keyword_type": ktype,
            "keyword": kw,
            "eligible": True,
            "source_documents": source_documents,
            "match_phrases": keywords,
            "requires_pediatric_evidence": bool(
                topic_config.get("requires_pediatric_evidence", False)
            ),
            "n_cases": n_cases,
            "status": status,
        }
        if status in {"covered", "GAP"}:
            result["matched_case_ids"] = [cases[i].get("case_id") for i in matched_indices]
            if div == "Peds" or topic_config.get(
                "requires_pediatric_evidence", False
            ):
                result["peds_evidence_counts"] = dict(Counter(
                    peds_evidence_by_index[i] for i in matched_indices
                ))
        results.append(result)

    if current_div:
        print(f"  ── {current_div}: {div_covered[current_div]}/{div_total[current_div]} covered ──\n")

    matchable = sum(div_total.values())
    print("=" * 80)
    print("Policy: Gate1(division/modality) AND Gate2(keyword) AND "
          "Gate3(pediatric topics: age≤18 OR explicit pediatric anchor "
          "when age is unreported)")
    print(f"Total topics:           {len(schedule)}")
    print(f"Policy exclusions:      {excluded_total}  (excluded from denominator)")
    print(f"Matchable topics:       {matchable}")
    print(f"Covered (matchable):    {covered_total}/{matchable} "
          f"({100*covered_total/matchable:.1f}%)")
    print()
    print("By division:")
    for div in ["Neuro","Chest","GI","GU","MSK","Breast","US","IR","NM","Peds"]:
        tot = div_total[div]
        cov = div_covered[div]
        bar = "█" * cov + "░" * (tot - cov)
        print(f"  {div:>6}: {cov:3d}/{tot:3d}  {bar}")

    out = {
        "analysis_name": "APDR residency schedule entry representation",
        "analysis_cohort": os.environ.get(
            "OPENREDU_APDR_ANALYSIS_COHORT",
            "2017-2026 corpus after category-level exclusion of CT_CHEST_VASC "
            "and US_VASCULAR, plus the single APDR schedule-guided "
            "gastric-emptying supplementary retrieval",
        ),
        "policy_version": "APDR_SCHEDULE_MATCHING_V3_20260722",
        "eligibility_policy_version": "APDR_SCHEDULE_ELIGIBILITY_V1_20260722",
        "policy": "Gate1(division) AND Gate2(primary-field keyword) AND Gate3(Peds: age<=18 OR age-unreported with explicit pediatric text anchor)",
        "unit_of_analysis": "schedule_entry",
        "unique_topic_definition": "division + normalized topic label",
        "source_note": "Schedule labels are normalized entries derived from the listed APDR September 2024 checklists; source_documents records document-level provenance. They are not asserted to be verbatim quotations.",
        "input_files": {
            "schedule_csv": str(SCHEDULE_CSV.relative_to(ROOT)),
            "schedule_csv_sha256": sha256_file(SCHEDULE_CSV),
            "corpus_jsonl": str(corpus_path.relative_to(ROOT)),
            "corpus_jsonl_sha256": sha256_file(corpus_path),
            "corpus_manifest": str(corpus_manifest_path.relative_to(ROOT)),
            "corpus_manifest_sha256": sha256_file(corpus_manifest_path),
            "verbatim_extract_csv": "data/curriculum/apdr_pmc_keywords.csv",
        },
        "raw_apdr_source_documents": raw_source_manifest(schedule, source_registry),
        "total": len(schedule),
        "corpus_cases": len(cases),
        "policy_excluded": excluded_total,
        "matchable": matchable,
        "covered": covered_total,
        "pct": round(100 * covered_total / matchable, 1),
        "unique_total": len({(r["division"], normalize(r["keyword"])) for r in schedule}),
        "unique_eligible": len({
            (r["division"], normalize(r["keyword"])) for r in schedule
            if r["keyword"].lower().strip() not in TOPIC_EXCLUSIONS
        }),
        "unique_covered": len({
            (r["division"], normalize(r["keyword"])) for r in results
            if r["status"] == "covered"
        }),
        "by_division": {
            div: {"covered": div_covered[div], "total": div_total[div]}
            for div in div_total
        },
        "topics": results,
    }
    output_stem = os.environ.get("OPENREDU_APDR_OUTPUT_STEM", "apdr_schedule")
    # Write to both locations: production and audit
    for out_dir in [
        DATA / "curriculum_mapping",
        DATA / "audits/scope_v2_final_schedule/curriculum_mapping",
    ]:
        out_dir.mkdir(parents=True, exist_ok=True)

        out_path = out_dir / f"{output_stem}_coverage.json"
        out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False))
        print(f"\nSaved: {out_path}")

        table_fields = [
            "schedule_entry_id", "canonical_topic_id", "division", "year_level",
            "week", "keyword", "eligible", "exclusion_category",
            "exclusion_reason", "status", "n_cases",
        ]
        table_path = out_dir / f"{output_stem}_topic_results.csv"
        with table_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=table_fields, extrasaction="ignore")
            writer.writeheader()
            for result in results:
                writer.writerow(result)
        print(f"Saved: {table_path}")

        exclusions_path = out_dir / f"{output_stem}_exclusions.csv"
        exclusion_fields = [
            "schedule_entry_id", "division", "year_level", "week", "keyword",
            "exclusion_category", "exclusion_reason",
        ]
        with exclusions_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=exclusion_fields, extrasaction="ignore")
            writer.writeheader()
            for result in results:
                if not result["eligible"]:
                    writer.writerow(result)
        print(f"Saved: {exclusions_path}")


if __name__ == "__main__":
    main()
