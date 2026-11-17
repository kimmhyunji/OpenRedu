"""Offline checks of pipeline/build_library.py: verifier filtering and topic linking on invented data."""
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))
sys.path.insert(0, str(ROOT / "src"))

import build_library as bl  # noqa: E402

EXAMPLES = ROOT / "examples"


def _cases():
    return [json.loads(l) for l in (EXAMPLES / "synthetic_cases.jsonl").read_text().splitlines() if l.strip()]


def _record(case_id, classification="supported", finding="supported", ok=True):
    v = lambda x: {"verdict": x}  # noqa: E731
    return {"case_id": case_id, "ok": ok, "model_id": "stub", "prompt_version": "v3",
            "parsed": {"classification": v(classification), "finding": v(finding), "laterality": v("supported"),
                       "diagnosis_article": v("supported"), "conditions": []}}


def test_apply_verifier_excludes_unsupported_category_or_finding():
    cases = _cases()
    ids = [c["case_id"] for c in cases]
    records = [_record(ids[0]), _record(ids[1], classification="not_supported"),
               _record(ids[2], finding="not_supported"), _record(ids[3], finding="unclear"),
               _record(ids[4], ok=False)]
    kept, excluded, missing = bl.apply_verifier(cases, records, ["classification", "finding"])
    assert [c["case_id"] for c in kept] == [ids[0], ids[3]]
    assert {e["case_id"]: e["reason"] for e in excluded} == {
        ids[1]: "classification_not_supported", ids[2]: "finding_not_supported"}
    assert missing == [ids[4]]
    assert kept[0]["source_url"] == f"https://pmc.ncbi.nlm.nih.gov/articles/{cases[0]['pmcid']}/"


def test_later_successful_record_supersedes_earlier():
    case = _cases()[:1]
    cid = case[0]["case_id"]
    kept, excluded, _ = bl.apply_verifier(case, [_record(cid, finding="not_supported"), _record(cid)], ["finding"])
    assert len(kept) == 1 and not excluded


def test_link_with_invented_curriculum(tmp_path, monkeypatch):
    import step3_assertion_matching as s3
    import openredu.pipeline.report_apdr_schedule_coverage as cov
    (tmp_path / "data/curriculum").mkdir(parents=True)
    (tmp_path / "data/guidelines").mkdir(parents=True)
    shutil.copy(EXAMPLES / "fake_curriculum/schedule_topics.csv", tmp_path / "data/curriculum/apdr_schedule_topics.csv")
    shutil.copy(EXAMPLES / "fake_curriculum/topic_keywords.json",
                tmp_path / "data/guidelines/apdr_schedule_topic_keywords.json")
    lib = tmp_path / "data/library/library"
    lib.mkdir(parents=True)
    (lib / "cases.jsonl").write_text((EXAMPLES / "synthetic_cases.jsonl").read_text())
    (lib / "manifest.json").write_text("{}")
    monkeypatch.setattr(s3, "ROOT", tmp_path)
    monkeypatch.setattr(cov, "ROOT", tmp_path)
    summary = bl.link_cases(lib / "cases.jsonl", tmp_path / "data/library/links", None, False, root=tmp_path)
    rows = [json.loads(l) for l in (tmp_path / "data/library/links/assignments.jsonl").read_text().splitlines()]
    assert summary["links"] == sum(r["keep"] for r in rows) == 5
    assert {(r["case_id"], r["keyword"]) for r in rows if r["keep"]} == {
        ("SYN0001_F1", "Pulmonary embolism"), ("SYN0002_F2", "Brain abscess"), ("SYN0003_F1", "Cholecystitis"),
        ("SYN0004_F1", "Scaphoid fracture"), ("SYN0005_F1", "Ovarian torsion")}
