# OpenRedu: Open Radiology Education through AI-Native Curation of Open-Access Case Reports into a Source-Traceable, Curriculum-Indexed Case Library

OpenRedu searches PubMed Central (PMC) for open-access radiology case reports, takes each radiologic figure as one case, extracts the finding and diagnosis that the article states for that figure, checks them with an independent verifier, and writes a case library in which every case links back to its source article. Cases can then be linked to the topics of a curriculum you supply.

This is the code of the article *OpenRedu: Open Radiology Education through AI-Native Curation of Open-Access Case Reports into a Source-Traceable, Curriculum-Indexed Case Library*. The repository does not distribute article text, figure images or the assembled case library; you build the library yourself from PMC. It includes figure identifiers and recorded QC exclusion decisions for the article’s 1,138 removals (`docs/quality_control_removals.md`).

## What you get

`data/library/library/cases.jsonl`, one JSON record per figure, with:

- `case_id` (PMCID + figure), `pmcid`, `source_url`, `article_title`, `journal`, `pub_date`, `license`
- `figure_label`, `figure_caption`, `image_paths` (figure files downloaded to `data/images/`)
- `modality`, `anatomy`, `finding`, `diagnosis`, `diagnosis_normalized`, `laterality`, `demographics`
- `verifier`: the independent verifier's judgments of category, finding, laterality and diagnosis

`manifest.json` in the same folder gives the counts, and `excluded.csv` lists the cases removed by the verifier or by the final image check. With a curriculum, `data/library/links/assignments.jsonl` holds the case–topic links (`keep: true`).

Only articles under the six Creative Commons licenses listed in `src/openredu/config.py` (`ALLOWED_LICENSES`) are kept. Each figure keeps its article's license; follow it, including attribution, if you share cases.

## Setup

Python 3.10 or later.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt && pip install -e .
cp .env.example .env        # then fill in the values
python -m pytest -q         # offline tests; no network, no keys
```

`.env` needs:

- `ENTREZ_EMAIL` and `ENTREZ_API_KEY` for the NCBI E-utilities (free)
- AWS credentials with Amazon Bedrock access in `AWS_REGION` (default `us-east-1`) to the models listed in `docs/models_and_inference_settings.md` (Claude Haiku 4.5, Mistral Large 3, Claude Sonnet 4.6, Amazon Nova Pro)
- `UMLS_API_KEY` for the UMLS step of diagnosis standardization and for UMLS synonyms (needs a UMLS license; without it that step is skipped)

## Build a library

Settings are in the `build` section of `config/pipeline.yaml`: the publication-date window, the categories to search (all 23 by default; queries in `docs/data/retrieval/queries.json`), and the output folder.

```bash
python pipeline/build_library.py search      # PMC search per category -> candidate articles
python pipeline/build_library.py extract     # figures, caption classification, finding/diagnosis extraction (Bedrock)
python pipeline/build_library.py assemble    # one record per figure, open licenses, case reports only
python pipeline/build_library.py verify      # independent verifier (Bedrock); rerun to retry failed calls
python pipeline/build_library.py finalize    # remove cases whose category or finding is not supported
```

`extract` and `verify` can be stopped and restarted. Extraction skips terminal figure IDs, resumes unfinished checkpoints and revisits the requested articles to discover remaining figures; failed cases remain retryable. An extracted checkpoint resumes at mapping without repeating extraction. Verification skips cases with successful results. To try a small run first, use `extract --category CXR --limit 20`. As a guide, an update run of 1,431 candidate articles (891 cases in the end) took about 7.3 hours and about US$9 in model calls.

`assemble` excludes missing or undecodable images and records them in `assemble_image_excluded.jsonl`; `finalize` checks the image files again and records exclusions in `library/excluded.csv`. Restore or re-download excluded images and rerun these stages before including them. Downloads support WebP and are published only after the complete image can be decoded.

## Add newly published articles

Use the same commands with a new window. In the `build` section, set `date_filter` (for example `2026/10/20:2027/03/31[PDAT]`) and a new `out_dir` and `verifier_run_id`, and list the earlier library in `skip_articles_in` (for example `data/library/library/cases.jsonl`) so that articles already in it are skipped. Then run `search`, `extract`, `assemble`, `verify` and `finalize` again. The earlier library is not changed.

## Link cases to a curriculum (optional)

Put your curriculum topic table and topic phrase lists where `docs/data_layout.md` describes; `examples/fake_curriculum/` shows the formats with invented topics. Then:

```bash
python pipeline/build_library.py link          # phrase matching with negation, differential, suspected and history rules
python pipeline/build_library.py synonyms     # optional: UMLS synonyms of your topic phrases (UMLS_API_KEY)
python pipeline/build_library.py link --umls   # also match those synonyms
```

Custom curricula do not inherit the paper’s APDR row-specific technique gates. To require a technique for a topic, supply a JSON file mapping your topic IDs to allowed terms, e.g. `{"apdr_sched_0045": ["PET", "FDG", "SUV"]}`, and run `link --technique-terms path/to/terms.json`. At least one listed term must occur in the figure evidence. See `docs/data_layout.md` for using the paper’s APDR profile with its original curriculum.

A link is kept when the condition is stated as present for that figure; conditions the article rules out, lists only as a differential or mentions only as history are not linked.

## Where things are

```
pipeline/build_library.py   build a library (commands above)
src/openredu/               agents: curation (retrieval, classification, extraction, verification),
                            mapping (standardization, topic matching), tracking
prompts/                    extraction prompts (one per category), self-check, figure-scope rule, verifier
config/                     pipeline.yaml, model settings, caption dictionaries, normalization maps
docs/                       model settings, prompt texts, retrieval queries and counts, data layout
examples/, tests/           invented inputs, an offline example and offline tests
```

`python examples/run_offline_example.py` runs five invented cases through the caption rules, a stub verifier and topic matching without keys.

To check how the library in the article was built (its stage scripts, retrieval records, quality-control removals and the prospective update), see `docs/paper_reproducibility.md`.

To validate all 1,138 QC decisions and reproduce the five Table S2 counts without private inputs or model calls:

```bash
python pipeline/replay_qc_exclusions.py
```

The case ledger preserves both the original reason codes and retrospective group categorization where detailed reasons were not retained. The command can also apply the recorded exclusions to a supplied extraction universe; see `docs/quality_control_removals.md`.

## License

Code: MIT (`LICENSE`). Articles and figures retrieved from PMC remain under their own licenses.
