# Tracking and finding-flashcard implementation

## Method resources

- The topic-suggestion system prompt and exact dynamic input builder are in [prompt_texts.md](prompt_texts.md).
- Model identifiers and inference settings are in [models_and_inference_settings.md](models_and_inference_settings.md).
- Topic-state and recommendation code in this release: `src/openredu/agents/tracking/coverage.py`, `src/openredu/agents/tracking/gap_prioritization.py`, and `src/openredu/config.py` (`COVERAGE_THRESHOLD`).
- The web viewer and its backend (event recording, flashcard policy, self-assessment storage) are not part of this release. Their interaction rules are specified in the sections below.

## Viewing records and topic suggestions

Opening a case detail view or displaying a finding card sends a case-view event containing the case identifier and interaction context. The backend attaches the case's curriculum-topic identifiers. The learner state replays the latest snapshot for each distinct case; a topic is marked viewed once at least one linked case has been viewed (`COVERAGE_THRESHOLD = 1`).

The topic-suggestion input contains the viewing summary and topic names, divisions, and identifiers. The current input builder supplies up to 30 not-yet-viewed topics. The prompt asks for an ordered list of up to 10 topics with short reasons, emphasizing high-yield diagnoses, clinical urgency, foundational topics, and balance across subspecialties. The model configuration is Claude Haiku 4.5 on AWS Bedrock, with up to 800 output tokens and provider-default sampling parameters. The catalog caches recommendations for 24 hours using the viewing-history signature and curriculum version. After unsuccessful model attempts, the implementation supplies a deterministic topic ordering.

## Optional finding-flashcard workflow

Cards reuse the stored image, finding, and article diagnosis from cases saved in user-selected collections. Eligibility requires a figure-specific, nonempty finding, an available image path, and an eligible case under the viewer policy. The exact eligibility predicate is `isFindingCardEligible` and collection-based selection is `selectFindingCards` in the viewer code (not distributed).

The front shows the image and asks “What finding do you see?” The learner describes the finding and flips the card to compare with the stored source finding and article diagnosis. Know it/Still learning buttons submit a self-assessment choice for that case. The statistics endpoint records the number of responses, the number marked Know it, and the last response date; My Stats displays these case-level review records.

Topic suggestions consume the viewing history and topic metadata. Card self-assessment choices populate the case-level review statistics. This separation is implemented by the view-event and statistics endpoints listed above.

## Caption-based marker filter

The viewer function `captionMentionsMarker` identifies caption mentions of arrows, arrowheads, asterisks, circles, and dashed/dotted outlines. The optional gallery/card filter uses this flag.
