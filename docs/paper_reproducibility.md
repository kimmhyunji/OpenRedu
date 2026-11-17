# Tracing the article to the code

This file is for readers who want to check how the library described in the article was built. To build your own library, follow the README instead.

The article's library was built in stages, and some stage scripts read intermediate files of that build that are not distributed (`docs/data_layout.md`). They are kept here as the record of what was run. `pipeline/build_library.py` runs the same agents, prompts, rules and settings in one sequence.

## What is and is not released

| Released here | Not released |
|---|---|
| QC exclusion figure identifiers, reasons and methods (1,138 cases) | Raw internal review logs |
| Agent code (curation, mapping, tracking) | The assembled case library |
| Stage scripts used to build and check the library | Figure images |
| Prompt texts, model identifiers, call settings, retry rules | Case-level extractions, case–topic links, full extraction provenance |
| Caption dictionaries and diagnosis normalization maps | Participant-level evaluation data |
| PMC query strings, execution windows, per-category flow counts | Curriculum documents and curriculum topic tables (third-party material) |
| Targeted-retrieval queries, dates, and per-topic counts | UMLS Metathesaurus files and derived synonym indexes (license) |
| LLM-free tests and a small offline example (invented data) | Web viewer, backend, accounts, evaluation screens |

## Article sections and the files that implement them

| Article section | Where it is implemented or documented |
|---|---|
| Source retrieval, license filter, case definition (Methods: Study Design and Data; Supplementary Methods S1) | `src/openredu/tools/pmc_api.py`, `src/openredu/agents/curation/subagents/retrieval.py`, `ALLOWED_LICENSES` in `src/openredu/config.py`; queries and per-category flow counts in `docs/retrieval_queries_and_run_counts.md` and `docs/data/retrieval/`; execution date and counts of every run in `docs/data/retrieval/run_manifest_funnel.csv` |
| Agent architecture; logged accept/retry/escalate/route/drop decisions | `src/openredu/core/base.py`, `src/openredu/agents/curation/master.py` |
| Caption classification (inclusion/exclusion dictionaries) | `src/openredu/agents/curation/subagents/classification.py`; dictionaries in `docs/caption_dictionaries_and_normalization_maps.md` and `config/keyword_dictionaries_and_normalization_maps.json` |
| First-pass extraction, model fallback, self-check | `src/openredu/agents/curation/subagents/extraction.py`, `src/openredu/core/llm.py`; prompts in `prompts/extraction/`, `prompts/self_check.txt`, `prompts/common_figure_scope_rule.txt` and `docs/prompt_texts.md` |
| Figure-scoped finding rewrite (second pass) | `extraction.py` (`scope_finding_to_figure`), `src/openredu/core/figure_evidence.py`, `pipeline/step6_figure_scope.py` |
| Independent verifier | `src/openredu/agents/curation/subagents/verification.py`, `pipeline/step2_verifier.py`, `pipeline/step2_salvage.py`, `pipeline/step6_merge_verifier.py`; prompt `prompts/verifier/verifier_v3.md`; every call is logged with model identifier, timestamp, settings, prompt version, token use and raw response (`step2_verifier.py`) |
| Article-type screening | `pipeline/step1_fetch_article_meta.py`, `pipeline/step1_label_article_types.py` |
| Diagnosis standardization to UMLS | `src/openredu/agents/mapping/subagents/standardization.py`, `src/openredu/tools/umls_client.py`, `src/openredu/tools/mesh_lookup.py` |
| Topic matching, division/modality gates, pediatric rule, technique gate | `src/openredu/agents/mapping/subagents/matching.py`, `src/openredu/pipeline/report_apdr_schedule_coverage.py`, `pipeline/step3_assertion_matching.py`; `step3_assertion` in `config/pipeline.yaml` |
| Negation, differential, suspected, historical handling | `pipeline/step3_assertion_matching.py` |
| UMLS synonym expansion (release 2026AA) | `pipeline/step4_umls_topics.py`, `pipeline/step4_synonyms.py` (scripts only; the synonym tables are not distributed) |
| Corpus build and quality-control flow | `pipeline/step5_build_v2.py`, `pipeline/step5_qc_ledger.py`, `pipeline/step5_query_disclosure.py`, `pipeline/step5_repro_package.py`; removal reasons and how each was identified in `docs/quality_control_removals.md` |
| Targeted retrieval (three rounds) | Rounds 2 and 3: `pipeline/gapfill_v21.py`, `pipeline/merge_gapfill_v22.py`, `config/pipeline.yaml` (`gapfill_v21`, `gapfill_v22`); the round 1 scripts are not included. Queries, dates, and per-topic counts of all three rounds in `docs/retrieval_queries_and_run_counts.md` and `docs/data/targeted_retrieval/` |
| Prospective update | `pipeline/update_prospective.py`, `pipeline/update_prospective_report.py`, `pipeline/update_cluster_bootstrap.py`, `pipeline/temporal_stability.py`; `update_2026q3` in `config/pipeline.yaml`; steps under "Prospective update" below; details in `docs/retrieval_queries_and_run_counts.md` |
| Tracking agent, topic suggestion, finding flashcards (Supplementary Methods S3) | `src/openredu/agents/tracking/`; prompt and settings in `docs/prompt_texts.md`, `docs/models_and_inference_settings.md`; viewer rules in `docs/tracking_and_flashcard_methods.md` |
| Model identifiers, settings, retry and fallback rules, missing provenance | `docs/models_and_inference_settings.md`, `config/models_and_parameters.json`; text supplied to each model (context handling) in `docs/classification_extraction_verification.md` and `docs/prompt_texts.md`; AWS Bedrock region and credentials in `.env.example` |

Clinical evaluation and analysis scripts (Methods: Clinical Evaluation and Analysis; Supplementary Methods S4) are not part of this release because they read participant-level data.

## Stage order of the article's build

1. Collection: `python -m openredu.run pipeline ...` (retrieve → classify → extract → self-check → map).
2. `pipeline/step1_*` article-type labels.
3. `pipeline/step2_verifier.py` (then `step2_salvage.py`) independent verification.
4. `pipeline/step4_umls_topics.py`, `step4_synonyms.py` UMLS topic phrases and synonyms.
5. `pipeline/step3_assertion_matching.py` assertion- and depiction-aware matching.
6. `pipeline/step6_figure_scope.py`, `step6_merge_verifier.py` (`step6_verifier_chain.sh`) second-pass finding and verifier merge.
7. `pipeline/step5_build_v2.py` build; `step5_qc_ledger.py`, `step5_query_disclosure.py`, `step5_repro_package.py` flow tables and package.
8. `pipeline/gapfill_v21.py`, `merge_gapfill_v22.py` targeted retrieval rounds 2 and 3 and merge.

The final library rule excludes a case whose category or finding the verifier judged not supported (421 and 167 cases). The article's build applied the category rule in step 7 and the finding rule as a last step; `corpus_exclusion_fields` in `config/pipeline.yaml` now applies both together.

## The prospective update reported in the response to reviewers

The update reported in the response to reviewers (publication dates July 1 to October 19, 2026) used the `update_2026q3` section of `config/pipeline.yaml`;
change `date_filter`, `out_dir`, `verifier_run_id` and `freeze_dir` there for a new window. Existing cases and links are
not changed; everything is written to new folders.

```bash
python pipeline/update_prospective.py search      # category queries + date window; drops articles already in the library
python pipeline/update_prospective.py extract     # curation agent on the new articles (AWS Bedrock; resumable)
python pipeline/update_prospective.py assemble    # one record per figure, license filter, article-type labels
python pipeline/step2_verifier.py --cases corpus:data/outputs/update_2026q3_v1/cases_casereport.jsonl \
    --models nova-pro --run-id update_2026q3_v1    # independent verifier; rerun the same command for failed calls
python pipeline/update_prospective.py combine     # library + new cases as one build input
python pipeline/step5_build_v2.py --version update_2026q3 --out data/outputs/update_2026q3_v1/build \
    --step1-corpus data/outputs/update_2026q3_v1/build_input/cases.jsonl \
    --labels data/outputs/update_2026q3_v1/build_input/case_article_labels.jsonl \
    --gapfill-summary data/outputs/gapfill_v21/gapfill_summary.json \
    --gapfill-summary data/outputs/gapfill_v22/gapfill_summary.json \
    --verifier data/outputs/step2/runs/update_2026q3_v1_combined/nova-pro.jsonl
python pipeline/temporal_stability.py             # quality indicators of library cases by publication period
python pipeline/update_prospective_report.py      # counts, new links and topics, processing time, model cost
python pipeline/update_cluster_bootstrap.py       # update vs library indicators with article-level bootstrap intervals
```

Scripts read their inputs from `data/` (not distributed) and settings from `config/pipeline.yaml`; see `docs/data_layout.md`. Counts quoted in script docstrings come from intermediate builds; the final counts are those in the article.

## Known gaps and limits

- The first extraction pass did not set temperature or top-p (provider defaults), and per-case attempt counts, token use, and latency were not retained for that pass.
- The originally executed query strings were not stored in the run manifests. The category queries listed here are reconstructed from the stored configuration; run manifests record whether each run's configuration hash matched the configuration used for reconstruction (`docs/data/retrieval/per_category_queries_and_flow.csv`).
- Dated model snapshots are available only for the identifiers listed in `docs/models_and_inference_settings.md`.
- The curriculum topic tables, topic phrase lists, and UMLS-derived files are inputs you must supply. The matching code runs on any topic table in the documented format; `examples/fake_curriculum/` shows the formats with invented entries, so the study's exact topic counts cannot be reproduced from this repository alone.
- `pipeline/step5_qc_ledger.py` is the historical compilation script and reads internal audit files that are not distributed. Its figure-level exclusion output is now released in `docs/data/retrieval/removed_case_ledger.csv`. `pipeline/replay_qc_exclusions.py` validates that public output, reproduces Table S2 and replays the recorded decisions without those internal files. For 135 pre-ledger exclusions, the original fine-grained reason was not retained; both the original `reason_not_recorded` value and the retrospective group category are disclosed. This allows replay of the decisions, not independent re-creation of the original manual judgments. See `docs/quality_control_removals.md`.
- The package is named `openredu`; earlier prototype code used other names.
