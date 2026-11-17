"""Offline walk-through of the rule, verification and matching stages.

Runs on five invented cases (examples/synthetic_cases.jsonl) and an invented
four-column topic table (examples/fake_curriculum/). No network, no API keys,
no study data. The verifier is replaced by a stub that returns "supported", so
this example shows how records move through the stages, not model behaviour.

    python examples/run_offline_example.py
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))

from openredu.agents.curation.subagents.classification import ClassificationSubagent  # noqa: E402
from openredu.agents.curation.subagents.verification import VerificationSubagent  # noqa: E402
from openredu.agents.mapping.subagents.matching import MatchingSubagent, build_guideline_index  # noqa: E402
from openredu.core.state import CaseState  # noqa: E402


class StubVerifierClient:
    """Stands in for the Bedrock client; always answers 'supported'."""

    def converse(self, **kwargs):
        verdict = {"verdict": "supported"}
        parsed = {"classification": verdict, "finding": verdict, "laterality": verdict,
                  "diagnosis_article": verdict, "conditions": []}
        text = "<reasoning>stub</reasoning>" + json.dumps(parsed)
        return {"output": {"message": {"content": [{"text": text}]}},
                "usage": {"inputTokens": 0, "outputTokens": 0}, "stopReason": "end_turn"}


def main() -> None:
    topics, synonyms, cuis = build_guideline_index(
        HERE / "fake_curriculum" / "guideline_topics.csv", HERE / "fake_curriculum" / "synonym_index.json")
    names = {t["keyword_id"]: t["raw_keyword"] for t in topics}
    classifier = ClassificationSubagent()
    verifier = VerificationSubagent(client=StubVerifierClient())
    matcher = MatchingSubagent(apdr_topics=topics, kw_to_synonyms=synonyms, kw_to_cui=cuis)

    # "uncertain_pending" = the caption matched neither dictionary; the full pipeline
    # sends such captions to the LLM adjudication step (needs credentials, not run here).
    print(f"{'case_id':12} {'caption rule':18} {'verifier':10} linked topics")
    for line in (HERE / "synthetic_cases.jsonl").read_text().splitlines():
        raw = json.loads(line)
        state = CaseState(
            pmcid=raw["pmcid"], case_id=raw["case_id"], modality=raw["modality"],
            figure_caption=raw["figure_caption"], finding=raw["finding"], diagnosis=raw["diagnosis"],
            diagnosis_normalized=raw["diagnosis_normalized"], article_title=raw["article_title"],
            author_keywords=raw["author_keywords"], status="retrieved")
        state = classifier.run(state)
        state = verifier.run(state)
        state = matcher.run(state)
        topics_linked = ", ".join(names.get(t, str(t)) for t in state.curriculum_topics) or "-"
        print(f"{state.case_id:12} {str(state.classification_route):18} "
              f"{state.verification.get('classification', '?'):10} {topics_linked}")


if __name__ == "__main__":
    main()
