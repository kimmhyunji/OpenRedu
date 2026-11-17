# Runtime data layout

Everything below lives under `data/` (git-ignored, not distributed). Set `OPENREDU_HOME` to use a different repository root. Paths in `config/pipeline.yaml` are relative to the repository root.

## Inputs you supply

Only the NCBI and AWS credentials in `.env` are needed to build a library. The curriculum files below are needed only for topic links (`pipeline/build_library.py link`).

| Path | Content | Format |
|---|---|---|
| `data/curriculum/apdr_schedule_topics.csv` | Curriculum schedule | columns `division, year_level, week, keyword_type, keyword` (invented example: `examples/fake_curriculum/schedule_topics.csv`) |
| `data/guidelines/apdr_schedule_topic_keywords.json` | Per-topic phrase lists and eligibility | `{"entries": [{schedule_entry_id, canonical_topic_id, division, year_level, week, keyword_type, keyword, eligible, exclusion_category, exclusion_reason, requires_pediatric_evidence, phrases[], n_cases, status}]}` (example: `examples/fake_curriculum/topic_keywords.json`). `schedule_entry_id` is `apdr_sched_` plus the 1-based row number of the topic in the schedule file (`apdr_sched_0001` for the first row) |
| `data/guidelines/<guideline>.csv` | Topic table for the matching agent | four columns `canonical_name, category, specialty, source_type` (example: `examples/fake_curriculum/guideline_topics.csv`); `python -m openredu.run ingest` creates it from a raw guideline file |
| `data/guidelines/final_synonym_index.json` | Topic synonyms and concept identifiers | `{normalized_keyword: {"all_synonyms": [...], "cui": "..."}}`; built with a UMLS license by `src/openredu/tools/index_builder.py` (example: `examples/fake_curriculum/synonym_index.json`, empty) |

## Curriculum-specific technique gates

`build_library.py link` defaults to no topic-specific technique gate. Use `--technique-terms FILE` with a JSON object mapping `schedule_entry_id` to a nonempty list of technique terms. The IDs must exist in the supplied curriculum. Move the gates with their topics if you reorder the curriculum rows. Division, modality, pediatric, assertion and depiction rules still apply.

For the article's original APDR curriculum and row ordering, `step3_assertion_matching.py` retains the historical `step3_assertion.technique_terms` profile in `config/pipeline.yaml`. To explicitly select those same gates through the build command (only with that original curriculum):

```bash
python -c 'import json, yaml; print(json.dumps(yaml.safe_load(open("config/pipeline.yaml"))["step3_assertion"]["technique_terms"]))' > data/apdr_technique_terms.json
python pipeline/build_library.py link --technique-terms data/apdr_technique_terms.json
```

## Outputs written by the stages

| Path | Written by |
|---|---|
| `data/library/` (`build.out_dir`): `candidates/`, `runs/`, `cases_casereport.jsonl`, `library/` (`cases.jsonl`, `manifest.json`, `excluded.csv`), `links/` | `pipeline/build_library.py` |
| `data/processed/`, `data/failed/`, `data/unmapped/`, `data/manifests/`, `data/images/` | collection run (`openredu.run pipeline`) |
| `data/outputs/step1/` | `pipeline/step1_*` |
| `data/outputs/step2/runs/<run_id>/<model>.jsonl` | `pipeline/step2_verifier.py` (one logged record per call: model ID, timestamp, parameters, prompt version, tokens, duration, raw response) |
| `data/outputs/step3/`, `step4/` | `pipeline/step3_*`, `step4_*` |
| `data/outputs/step5/` | `pipeline/step5_*` |
| `data/outputs/step6_figure_scope/` | `pipeline/step6_figure_scope.py` |
| `data/outputs/gapfill_v21/`, `gapfill_v22/` | targeted retrieval |

Aggregate records are copied into `docs/data/`. The exception at figure level is `docs/data/retrieval/removed_case_ledger.csv`: public PMC figure identifiers and QC exclusion categories/methods, with original reason provenance. It contains no extracted case text, images or participant records. See `docs/quality_control_removals.md`.
