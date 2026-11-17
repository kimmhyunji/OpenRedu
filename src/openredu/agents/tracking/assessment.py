"""
AssessmentSubagent: deterministic flashcard generation — NO LLM.

Builds flashcards directly from already-extracted CaseState fields:
  front = finding (or image path), back = diagnosis
  reverse = front: diagnosis, back: finding

No language-model generation: items are composed from validated extracted
content, avoiding risk of generating incorrect quiz content.
Cases missing finding or diagnosis are skipped.

Schema adapted from RadPathway QuizItem/Flashcard pattern.
"""
import logging
import random
from collections import defaultdict
from pathlib import Path
from typing import Optional

from openredu.core.base import Subagent
from openredu.core.state import LearnerState

log = logging.getLogger(__name__)


class AssessmentSubagent(Subagent):
    """
    Deterministic flashcard builder from extracted case fields.
    is_llm = False: no language model involved.
    """
    name = "AssessmentSubagent"
    is_llm = False

    def __init__(self, corpus_cases: list):
        """
        corpus_cases: list of CaseState dicts (or CaseState objects) from processed JSONL.
                      Pre-loaded once at startup.
        """
        # Build topic → cases index
        self.topic_to_cases: dict = defaultdict(list)
        self.all_cases: list = []

        for c in corpus_cases:
            # Accept both dict and CaseState-like objects
            if hasattr(c, '__dict__'):
                d = vars(c)
            else:
                d = c

            finding  = (d.get("finding") or "").strip()
            diagnosis = (d.get("diagnosis_normalized") or d.get("diagnosis") or "").strip()
            if not finding or not diagnosis:
                continue  # skip incomplete cases

            self.all_cases.append(d)

            for tid in (d.get("curriculum_topics") or []):
                self.topic_to_cases[tid].append(d)

        log.debug(
            f"AssessmentSubagent: {len(self.all_cases)} usable cases, "
            f"{len(self.topic_to_cases)} topics indexed"
        )

    def run(self, topic_id: str, n_cards: int = 10, seed: int = 42) -> dict:
        """
        Generate flashcards for a given APDR topic.

        Returns:
            {
              "topic_id": str,
              "cards": [
                {
                  "case_id": str,
                  "front": str,         # finding
                  "back": str,          # diagnosis
                  "image_path": str,    # first image if available
                  "modality": str,
                  "demographics": dict,
                  "reverse_card": {"front": str, "back": str},  # diagnosis → finding
                },
                ...
              ],
              "total_cases_for_topic": int,
            }
        """
        cases = self.topic_to_cases.get(topic_id, [])
        if not cases:
            log.warning(f"No cases found for topic {topic_id}")
            return {"topic_id": topic_id, "cards": [], "total_cases_for_topic": 0}

        rng = random.Random(seed)
        selected = rng.sample(cases, min(n_cards, len(cases)))

        cards = []
        for c in selected:
            finding   = (c.get("finding") or "").strip()
            diagnosis = (c.get("diagnosis_normalized") or c.get("diagnosis") or "").strip()
            modality  = c.get("modality", "")

            card = {
                "case_id":      c.get("case_id", ""),
                "front":        finding,
                "back":         diagnosis,
                "image_path":   (c.get("image_paths") or [None])[0] or c.get("image_path"),
                "modality":     modality,
                "demographics": c.get("demographics", {}),
                "reverse_card": {
                    "front": diagnosis,
                    "back":  finding,
                },
            }

            cards.append(card)

        return {
            "topic_id":               topic_id,
            "cards":                  cards,
            "total_cases_for_topic":  len(cases),
        }

    def get_topic_stats(self, topic_id: str) -> dict:
        """Return how many cases are available for a topic."""
        cases = self.topic_to_cases.get(topic_id, [])
        modalities = list({c.get("modality") for c in cases if c.get("modality")})
        return {
            "topic_id":  topic_id,
            "n_cases":   len(cases),
            "modalities": modalities,
            "has_images": sum(
                1 for c in cases
                if (c.get("image_paths") or []) or c.get("image_path")
            ),
        }
