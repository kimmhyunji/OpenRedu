import json

from openredu import coordinator


def _write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))


def test_load_coverage_cases_deduplicates_in_directory_order(tmp_path, monkeypatch):
    monkeypatch.setitem(coordinator.PATHS, "data", tmp_path)
    _write_jsonl(
        tmp_path / "final" / "cases_a.jsonl",
        [{"case_id": "same", "curriculum_topics": ["from_final"]}],
    )
    _write_jsonl(
        tmp_path / "processed" / "cases_b.jsonl",
        [
            {"case_id": "same", "curriculum_topics": ["from_processed"]},
            {"case_id": "new", "curriculum_topics": ["new_topic"]},
        ],
    )

    cases, stats = coordinator._load_coverage_cases(["final", "processed"])

    assert {case["case_id"] for case in cases} == {"same", "new"}
    assert next(case for case in cases if case["case_id"] == "same")[
        "curriculum_topics"
    ] == ["from_final"]
    assert stats["total_rows"] == 3
    assert stats["unique_cases"] == 2
    assert stats["duplicate_rows"] == 1


def test_load_coverage_cases_applies_exclusions_and_optional_scope(tmp_path, monkeypatch):
    monkeypatch.setitem(coordinator.PATHS, "data", tmp_path)
    _write_jsonl(tmp_path / "final" / "cases_a.jsonl", [{"case_id": "base"}])
    _write_jsonl(
        tmp_path / "gap_fill_bypass" / "cases_b.jsonl",
        [{"case_id": "bypass"}, {"case_id": "excluded"}],
    )
    (tmp_path / "excluded_cases.json").write_text(json.dumps(["excluded"]))

    base_cases, base_stats = coordinator._load_coverage_cases(["final"])
    all_cases, all_stats = coordinator._load_coverage_cases(
        ["final", "gap_fill_bypass"]
    )

    assert [case["case_id"] for case in base_cases] == ["base"]
    assert base_stats["active_cases"] == 1
    assert {case["case_id"] for case in all_cases} == {"base", "bypass"}
    assert all_stats["unique_cases"] == 3
    assert all_stats["excluded_cases"] == 1
    assert all_stats["active_cases"] == 2
