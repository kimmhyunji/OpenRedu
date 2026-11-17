"""Offline regression coverage for the final public-code review."""
import copy
import io
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))
from openredu.tools.pmc_api import extract_license
from openredu.tools import image_downloader as images
from openredu import coordinator as coord
from openredu.core.state import CaseState
import build_library as bl


def xml_license(metadata, extra=""):
    return ET.fromstring(f'<article xmlns:xlink="http://www.w3.org/1999/xlink">'
                         f'<front><article-meta>{metadata}</article-meta></front>{extra}</article>')


@pytest.mark.parametrize("kind", ["by", "by-sa", "by-nd", "by-nc", "by-nc-sa", "by-nc-nd"])
def test_article_permissions_six_cc_licenses(kind):
    node = xml_license(f'<permissions><license><ext-link xlink:href="https://creativecommons.org/licenses/{kind}/4.0/"/></license></permissions>')
    assert extract_license(node) == "CC " + kind.upper()


@pytest.mark.parametrize("extra", [
    '<body><ext-link xlink:href="https://creativecommons.org/licenses/by/4.0/"/></body>',
    '<back><ref-list><ref><ext-link xlink:href="https://creativecommons.org/licenses/by/4.0/"/></ref></ref-list></back>',
    '<sub-article><front><article-meta><permissions><license xlink:href="https://creativecommons.org/licenses/by/4.0/"/></permissions></article-meta></front></sub-article>',
])
def test_unrelated_cc_links_are_not_article_licenses(extra):
    assert extract_license(xml_license('<permissions>All rights reserved.</permissions>', extra)) == "UNKNOWN"


@pytest.mark.parametrize("url", ["https://creativecommons.org.evil.test/licenses/by/4.0/", "https://evil.test/creativecommons.org/licenses/by/4.0/", "https://creativecommons.org/licenses/not-by/4.0/"])
def test_license_url_host_and_path(url):
    assert extract_license(xml_license(f'<permissions><license xlink:href="{url}"/></permissions>')) == "UNKNOWN"


def test_namespaced_license_ref_and_conflicting_metadata():
    assert extract_license(xml_license('<ali:license_ref xmlns:ali="http://www.niso.org/schemas/ali/1.0/">https://creativecommons.org/licenses/by/4.0/</ali:license_ref>')) == "CC BY"
    assert extract_license(xml_license('<permissions><license xlink:href="https://creativecommons.org/licenses/by/4.0/"/><license xlink:href="https://creativecommons.org/licenses/by-nc/4.0/"/></permissions>')) == "UNKNOWN"
    assert extract_license(xml_license('<permissions><copyright-statement><ext-link xlink:href="https://creativecommons.org/licenses/by/4.0/"/></copyright-statement></permissions>')) == "UNKNOWN"


def picture(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 8), "white").save(path)
    return str(path)


class Response:
    def __init__(self, data, fail=False):
        self.data, self.fail = data, fail
    def raise_for_status(self):
        pass
    def iter_content(self, _size):
        yield self.data
        if self.fail:
            raise OSError("interrupted stream")
    def close(self):
        pass


def test_webp_and_query_url_discovery(monkeypatch):
    url = "https://cdn.ncbi.nlm.nih.gov/pmc/blobs/aa/bb/fig1.webp?download=1"
    monkeypatch.setattr(images.requests, "get", lambda *a, **kw: SimpleNamespace(text=url, raise_for_status=lambda: None))
    assert images.get_cdn_map("PMC1") == {"fig1": url}


def test_failed_download_is_cleaned_and_corrupt_existing_file_retried(tmp_path, monkeypatch):
    payload = io.BytesIO()
    Image.new("RGB", (8, 8)).save(payload, format="WEBP")
    calls = []
    def get(*a, **kw):
        calls.append(1)
        return Response(payload.getvalue(), fail=len(calls) == 1)
    monkeypatch.setattr(images.requests, "get", get)
    (tmp_path / "PMC1_fig1.webp").write_bytes(b"truncated")
    urls = {"fig1": "https://cdn.ncbi.nlm.nih.gov/pmc/blobs/a/b/fig1.webp"}
    assert images.download_image("PMC1", "fig1", urls, tmp_path) is None
    assert not list(tmp_path.glob("*.part"))
    result = images.download_image("PMC1", "fig1", urls, tmp_path)
    assert images.is_valid_image(Path(result))
    assert images.download_image("PMC1", "fig1", urls, tmp_path) == result
    assert len(calls) == 2


def test_html_response_is_not_published(tmp_path, monkeypatch):
    monkeypatch.setattr(images.requests, "get", lambda *a, **kw: Response(b"<html>error</html>"))
    assert images.download_image("PMC1", "fig1", {"fig1": "https://example.test/fig1.png"}, tmp_path) is None
    assert not list(tmp_path.iterdir())


@pytest.fixture
def pipeline(tmp_path, monkeypatch):
    from openredu.agents.curation.subagents import retrieval
    paths = {"data": tmp_path, "processed": tmp_path / "processed", "failed": tmp_path / "failed"}
    monkeypatch.setattr(coord, "PATHS", paths)
    monkeypatch.setattr(coord, "write_manifest", lambda *a: None)
    monkeypatch.setattr(coord.time, "sleep", lambda *a: None)
    image = picture(tmp_path / "figure.png")
    states = [CaseState(case_id=f"PMC1_F{i}", pmcid="PMC1", modality="CXR", image_paths=[image], license="CC BY") for i in (1, 2)]
    fetched, curated = [], []
    def scratch(pmcids, *a):
        fetched.extend(pmcids)
        yield from (copy.deepcopy(s) for s in states if s.pmcid in pmcids)
    class Curator:
        def __init__(self, **kw):
            pass
        def run(self, state):
            curated.append(state.case_id)
            state.status = "extracted"
            return state
    class Mapper:
        def run(self, state):
            state.status = "unmapped"
            return state
    monkeypatch.setattr(coord, "_iter_scratch", scratch)
    monkeypatch.setattr(coord, "CurationMasterAgent", Curator)
    monkeypatch.setattr(coord, "_get_mapping_agent", Mapper)
    monkeypatch.setattr(retrieval, "RetrievalSubagent", lambda: None)
    return SimpleNamespace(states=states, curated=curated, fetched=fetched, paths=paths)


@pytest.mark.parametrize("interrupt_at", ["retrieved", "extracted", "persisted"])
def test_restart_restores_incomplete_figure_and_discovers_sibling(pipeline, monkeypatch, interrupt_at):
    save, persist = coord._save_checkpoint, coord._persist_state
    def interrupted_save(state, modality, stage):
        save(state, modality, stage)
        if stage == interrupt_at:
            raise KeyboardInterrupt()
    def interrupted_persist(state, modality):
        persist(state, modality)
        if interrupt_at == "persisted":
            raise KeyboardInterrupt()
    monkeypatch.setattr(coord, "_save_checkpoint", interrupted_save)
    monkeypatch.setattr(coord, "_persist_state", interrupted_persist)
    with pytest.raises(KeyboardInterrupt):
        coord.run_pipeline_for_pmcids(["PMC1"], "CXR")
    monkeypatch.setattr(coord, "_save_checkpoint", save)
    monkeypatch.setattr(coord, "_persist_state", persist)
    coord.run_pipeline_for_pmcids(["PMC1"], "CXR")
    coord.run_pipeline_for_pmcids(["PMC1"], "CXR")
    result = bl.jl(pipeline.paths["processed"] / "cases_cxr.jsonl")
    assert [r["case_id"] for r in result] == ["PMC1_F1", "PMC1_F2"]
    assert pipeline.curated == ["PMC1_F1", "PMC1_F2"]


def test_failed_cases_retry_and_checkpoints_respect_requested_articles(pipeline):
    failed = copy.deepcopy(pipeline.states[0])
    failed.status = "failed"
    coord._persist_state(failed, "CXR")
    foreign = copy.deepcopy(failed)
    foreign.pmcid, foreign.case_id = "PMC2", "PMC2_F1"
    coord._save_checkpoint(foreign, "CXR", "retrieved")
    assert not coord._load_already_done("CXR")
    coord.run_pipeline_for_pmcids(["PMC1", "PMC1"], "CXR")
    assert pipeline.curated == ["PMC1_F1", "PMC1_F2"]
    assert pipeline.fetched == ["PMC1"]


def test_missing_checkpoint_image_retrieves_fresh_state(pipeline):
    old = copy.deepcopy(pipeline.states[0])
    old.image_paths = []
    coord._save_checkpoint(old, "CXR", "retrieved")
    result = list(coord._iter_scratch_with_resume(["PMC1"], "CXR", None,
                  retrieved_checkpoint=coord._load_checkpoint("CXR", "retrieved")))
    assert len(result) == 2 and all(s.image_paths for s in result)


def test_finalize_rechecks_actual_images(tmp_path, monkeypatch):
    monkeypatch.setattr(bl, "categories", lambda: ["CXR"])
    monkeypatch.setattr(bl, "ROOT", tmp_path)
    monkeypatch.setattr(bl, "OUT", tmp_path / "build")
    monkeypatch.setattr(bl, "VERIFIER_FILE", tmp_path / "verifier.jsonl")
    good = picture(tmp_path / "valid.png")
    corrupt = tmp_path / "corrupt.png"
    corrupt.write_bytes(b"bad image")
    paths = [[good], [], [str(corrupt)], [str(tmp_path / "absent.png")]]
    cases = [{"case_id": f"PMC1_F{i}", "pmcid": "PMC1", "image_paths": p, "collection_category": "CXR"} for i, p in enumerate(paths)]
    bl.write_jl(bl.OUT / "cases_casereport.jsonl", cases)
    bl.write_jl(bl.VERIFIER_FILE, [{"case_id": c["case_id"], "ok": True, "parsed": {"finding": {"verdict": "supported"}}} for c in cases])
    bl.cmd_finalize(SimpleNamespace(allow_partial=False))
    kept = bl.jl(bl.OUT / "library/cases.jsonl")
    assert [c["case_id"] for c in kept] == ["PMC1_F0"]
    manifest = json.loads((bl.OUT / "library/manifest.json").read_text())
    assert manifest["image_excluded"] == 3 and manifest["verifier_excluded"] == 0
    assert (bl.OUT / "library/excluded.csv").read_text().count("missing_or_invalid_image") == 3


@pytest.mark.parametrize("row_number", [44, 45])
def test_custom_curriculum_row_position_does_not_inherit_apdr_gate(tmp_path, monkeypatch, row_number):
    import csv
    import step3_assertion_matching as s3
    import openredu.pipeline.report_apdr_schedule_coverage as cov
    from copy import deepcopy

    template = json.loads((ROOT / "examples/fake_curriculum/topic_keywords.json").read_text())["entries"][0]
    entries = []
    for n in range(1, 47):
        entry = deepcopy(template)
        entry["schedule_entry_id"] = f"apdr_sched_{n:04d}"
        entry["canonical_topic_id"] = f"invented_{n}"
        if n != row_number:
            entry["keyword"] = f"Invented topic {n}"
            entry["phrases"] = [f"invented topic {n}"]
        entries.append(entry)
    curriculum = tmp_path / "data/curriculum/apdr_schedule_topics.csv"
    curriculum.parent.mkdir(parents=True)
    with curriculum.open("w", newline="") as f:
        fields = ["division", "year_level", "week", "keyword_type", "keyword"]
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(entries)
    keywords = tmp_path / "data/guidelines/apdr_schedule_topic_keywords.json"
    keywords.parent.mkdir(parents=True)
    keywords.write_text(json.dumps({"entries": entries}))
    corpus = tmp_path / "data/library/library/cases.jsonl"
    case = bl.jl(ROOT / "examples/synthetic_cases.jsonl")[0]
    bl.write_jl(corpus, [case])
    (corpus.parent / "manifest.json").write_text("{}")
    monkeypatch.setattr(s3, "ROOT", tmp_path)
    monkeypatch.setattr(cov, "ROOT", tmp_path)
    original = deepcopy(s3.S3)
    sid = f"apdr_sched_{row_number:04d}"
    normal = bl.link_cases(corpus, tmp_path / "links", None, False, root=tmp_path)
    assert normal["links"] == 1
    assert s3.S3 == original  # custom settings do not mutate the historical APDR profile
    gated = bl.link_cases(corpus, tmp_path / "gated", None, False, root=tmp_path, technique_terms={sid: ["PET", "FDG", "SUV"]})
    assert gated["links"] == 0
    ct = bl.link_cases(corpus, tmp_path / "ct", None, False, root=tmp_path, technique_terms={sid: ["CT"]})
    assert ct["links"] == 1
    with pytest.raises(ValueError, match="unknown curriculum"):
        bl.link_cases(corpus, tmp_path / "invalid", None, False, root=tmp_path, technique_terms={"missing_topic": ["CT"]})


def test_assemble_excludes_invalid_images_before_article_screening(tmp_path, monkeypatch):
    import step1_label_article_types as labels
    monkeypatch.setattr(bl, "ROOT", tmp_path)
    monkeypatch.setattr(bl, "OUT", tmp_path / "build")
    monkeypatch.setattr(bl, "categories", lambda: ["CXR"])
    monkeypatch.setattr(bl, "skipped_articles", lambda: set())
    monkeypatch.setattr(labels, "label_article", lambda *a: {"tier": bl.CFG["step1_article_type"]["include_tiers"][0], "jats_article_type": "case-report", "flags": []})
    cases = [{"case_id": f"PMC1_F{n}", "pmcid": "PMC1", "status": "extracted", "license": "CC BY", "image_paths": paths}
             for n, paths in enumerate(([picture(tmp_path / "image.png")], [], [str(tmp_path / "missing.png")]))]
    bl.write_jl(bl.OUT / "runs/CXR/processed/cases_cxr.jsonl", cases)
    def metadata(*a, **kw):
        assert len(bl.jl(bl.OUT / "cases_all.jsonl")) == 1
        bl.write_jl(bl.OUT / "article_meta.jsonl", [{"pmcid": "PMC1"}])
    monkeypatch.setattr(bl.subprocess, "run", metadata)
    bl.cmd_assemble(None)
    assert len(bl.jl(bl.OUT / "cases_casereport.jsonl")) == 1
    assert len(bl.jl(bl.OUT / "assemble_image_excluded.jsonl")) == 2
    assert json.loads((bl.OUT / "assemble_summary.json").read_text())["image_excluded"] == 2


def test_public_qc_ledger_matches_counts_and_preserves_original_reasons():
    import hashlib
    import replay_qc_exclusions as qc
    rows, summary = qc.validate_ledger()
    assert summary["removed_cases"] == 1138
    assert summary["table_s2"] == qc.EXPECTED
    retrospective = [r for r in rows if r["original_reason_code"] == "reason_not_recorded"]
    assert len(retrospective) == 135
    assert {r["reason_provenance"] for r in retrospective} == {"retrospective_group_category"}
    provenance = json.loads((qc.LEDGER.parent / "removed_case_ledger_provenance.json").read_text())
    assert hashlib.sha256(qc.LEDGER.read_bytes()).hexdigest() == provenance["released_sha256"]


def test_qc_replay_applies_each_decision_and_rejects_duplicates_and_partial_input():
    import replay_qc_exclusions as qc
    rows, _ = qc.validate_ledger()
    cases = [{"case_id": r["case_id"], "pmcid": r["pmcid"]} for r in rows]
    retained = {"case_id": "SYNTHETIC_KEEP_F1", "pmcid": "SYNTHETIC_KEEP"}
    kept, removed, missing = qc.replay(cases + [retained], rows)
    assert kept == [retained] and len(removed) == 1138 and not missing
    with pytest.raises(ValueError, match="duplicate"):
        qc.replay(cases + cases[:1], rows)
    with pytest.raises(ValueError, match="Input lacks"):
        qc.replay(cases[:1], rows)
    assert len(qc.replay(cases[:1], rows, allow_partial=True)[2]) == 1137
    cases[0]["pmcid"] = "PMC0"
    with pytest.raises(ValueError, match="PMCID disagrees"):
        qc.replay(cases, rows)
