# Quality-control removals before article-type screening

Between structured extraction and the primary corpus, 1,138 unique figure-level cases were removed by quality control.
Supplementary Table S2 groups them into five reasons; this file lists the recorded reasons within each group and how
each was identified. The 1,138 individual exclusions are released in
[`removed_case_ledger.csv`](data/retrieval/removed_case_ledger.csv). Counts by reason and method are in
`docs/data/retrieval/qc_ledger_summary.json`. The historical compilation script is `pipeline/step5_qc_ledger.py`;
the public replay and validation command is `pipeline/replay_qc_exclusions.py`.

| Table S2 reason | Recorded reason | Cases | How the cases were identified |
|---|---|---:|---|
| Not a radiologic still image or wrong modality (859) | Wrong modality or non-imaging material | 666 | Manual review in the curation gallery; figures whose modality did not match the collection category or that were not imaging (for example, pathology, graphs or clinical photographs) were excluded. |
| | Not a radiologic image or unsuitable figure (mostly charts, diagrams, photographs and histology) | 172 | Manual exclusion during corpus review (135) and figures reported through the viewer's exclusion button (37). |
| | Video or other non-still media | 21 | Image-file audit of the source files. |
| Modality or category outside the collection category (82) | Figure modality differs from collection category | 80 | Corpus-builder rule: the modality stated for the figure did not match the modality of the collection category. |
| | Reassigned to an excluded vascular category | 2 | Category-level rule: the figure was reassigned to a vascular category that is not part of the library. |
| Nonhuman subject (157) | Animal case | 150 | Rule-based scans: animal terms in author keywords (for example, canine, feline, equine, porcine, murine, rabbit; 70 in a first scan and 5 in a second), articles from veterinary journals (36; list below), articles from the Journal of Feline Medicine and Surgery under its journal-title variants (36), and animal subjects named in titles, abstracts or figure captions (3). |
| | Animal research | 7 | Automated animal-keyword filter followed by manual confirmation that the figure came from an animal experiment. |
| Original image file unavailable (19) | Original figure file unavailable | 19 | Image-file audit: the figure graphic named in the article XML could not be retrieved. |
| Unusable extraction (21) | Uninformative or not a case figure | 8 | Audit of extractions whose fields were returned as not applicable. |
| | Missing or unclear diagnosis | 8 | Automated diagnosis-quality filter on the extracted diagnosis. |
| | Failed musculoskeletal ultrasound caption re-screen | 5 | Extraction check not passed (one also had a missing image file) during the caption re-screen of musculoskeletal ultrasound figures. |
| Total | | 1,138 | |

Veterinary journals covered by the journal filter: Frontiers in Veterinary Science; Journal of Veterinary Internal
Medicine; Case Reports in Veterinary Medicine; Animals (MDPI); Open Veterinary Journal; Veterinary Sciences; Veterinary
Medicine and Science; Veterinary Radiology & Ultrasound; Australian Veterinary Journal; BMC Veterinary Research; The
Journal of Small Animal Practice; Acta Veterinaria Scandinavica.

Repeat extractions of the same figure in another collection run (1,429) are removed before this step and are not
quality-control removals.


## Inspect or replay the recorded decisions

The CSV contains one row per excluded figure: `case_id`, `pmcid`, collection `stratum`, extraction `source`,
`exclusion_step`, published `reason_code`, recorded `method`, `original_reason_code`, `reason_provenance`,
and `table_s2_group`. A PMCID opens the source article at `https://pmc.ncbi.nlm.nih.gov/articles/<PMCID>/`;
the case-ID suffix is the figure identifier from that article. The ledger contains no article text, images,
extracted clinical descriptions, reviewer identities or participant records.

For the 135 `manual_exclusion_list_pre_ledger` cases, the historical compiled ledger stored
`reason_not_recorded`. The public aggregate summary subsequently categorized that group as
`manual_corpus_review_non_radiologic_figure`. Both values are retained here and marked
`retrospective_group_category`. No finer per-figure subtype (for example, chart versus histology) is claimed.
The 37 viewer-button exclusions likewise retain their recorded button-report reason; they do not carry
individual narrative adjudications. Empty `method` cells mean that a separate method field was not recorded;
the exclusion step and the table above describe the process. These limits do not change the excluded IDs or counts.
Artifact hashes and the recoding provenance are in `removed_case_ledger_provenance.json` in the same directory.

Validate identifiers, unique figures, reason grouping, and all previously released reason/method counts:

```bash
python pipeline/replay_qc_exclusions.py
# 1,138 removals: 859 + 82 + 157 + 19 + 21 (Table S2)
```

Apply the decisions to a deduplicated extraction universe that you supply:

```bash
python pipeline/replay_qc_exclusions.py --input path/to/unique_extracted_cases.jsonl --out data/qc_replay
```

The command writes retained cases, applied exclusion rows, and a count summary to a new directory.
The reported historical stage contains 19,740 unique extraction outputs and retains 18,602 after these 1,138
exclusions. The input library itself is not distributed. By default, an input missing any ledger IDs is rejected;
use `--allow-partial` to inspect a subset, with all absent exclusion IDs reported explicitly. Duplicate input
figure IDs and mismatched PMCIDs are rejected. This step excludes the recorded IDs and reproduces the counts;
it does not independently repeat manual image review, article-type screening or later verifier filtering.
