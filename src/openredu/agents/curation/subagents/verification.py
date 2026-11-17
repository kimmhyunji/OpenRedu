"""
VerificationSubagent: independent text-only verifier (Amazon Nova Pro).

Packaging of the verifier that produced the corpus verdicts. The corpus itself was verified by
pipeline/step2_verifier.py; this class reuses the same prompt file
(prompts/verifier/verifier_v3.md), the same user-message construction, the same inference
settings (temperature 0, one re-ask when the JSON is unusable) and the same validity check, so
a case gets the same request either way. tests/test_verification.py compares the two.

It checks stored text only (classification, finding, laterality, diagnosis, per-condition
status and depiction). It never inspects image pixels.
"""
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from openredu.config import MODELS
from openredu.core.base import Subagent
from openredu.core.figure_evidence import build_evidence, render_evidence
from openredu.core.state import CaseState

REPO_ROOT = Path(__file__).resolve().parents[5]
PROMPT_PATH = REPO_ROOT / "prompts" / "verifier" / "verifier_v3.md"
PROMPT_VERSION = "v3"
REGION = "us-east-1"
INFERENCE = {"temperature": 0, "max_tokens": 3000}
ABSTRACT_MAX_CHARS = 2500
VERDICTS = {"supported", "unclear", "not_supported"}

CATEGORY_TEXT = {
    "BREAST_MRI": "MRI, breast", "BREAST_ULTRASOUND": "ultrasound, breast",
    "CARDIOVASCULAR_MRI": "MRI, heart/cardiovascular", "CT_ABDOMEN": "CT, abdomen/pelvis",
    "CT_BRAIN": "CT, brain/head", "CT_CHEST": "CT, chest", "CT_CHEST_VASC": "CT angiography, chest vessels",
    "CXR": "radiograph, chest", "GI_FLUOROSCOPY": "fluoroscopy, gastrointestinal",
    "GU_FLUOROSCOPY": "fluoroscopy, genitourinary", "MAMMOGRAM": "mammography, breast",
    "MRI_ABDOMEN": "MRI, abdomen", "MRI_BRAIN": "MRI, brain", "MRI_MSK": "MRI, musculoskeletal",
    "MRI_NEURO_SPINE": "MRI, spine/spinal cord (neuro)", "MRI_PELVIS": "MRI, pelvis",
    "MRI_SPINE": "MRI, spine", "MSK_CT": "CT, musculoskeletal", "MSK_ULTRASOUND": "ultrasound, musculoskeletal",
    "MSK_XRAY": "radiograph, musculoskeletal", "NM_NUCLEAR": "nuclear medicine (PET/SPECT/scintigraphy)",
    "US_ABDOMEN": "ultrasound, abdomen", "US_GYN_TRANS": "ultrasound, gynecologic/obstetric (transvaginal)",
    "US_PELVIS": "ultrasound, pelvis", "US_SUPERFICIAL": "ultrasound, neck/superficial/chest wall",
    "US_VASCULAR": "ultrasound, vascular",
}


def load_prompt(path: Path = PROMPT_PATH) -> tuple:
    txt = Path(path).read_text()
    system = txt.split("<<<SYSTEM>>>")[1].split("<<<USER_TEMPLATE>>>")[0].strip()
    user = txt.split("<<<USER_TEMPLATE>>>")[1].split("<<<END>>>")[0].strip()
    return system, user


def classification_text(c: dict) -> str:
    base = CATEGORY_TEXT.get(c.get("modality", ""), c.get("modality", ""))
    anat = (c.get("anatomy") or "").strip()
    return f"{base}" + (f" (anatomy: {anat})" if anat else "")


def build_user(c: dict, template: str) -> tuple:
    ev = build_evidence(c)
    msg = template.format(
        evidence=render_evidence(ev),
        classification=classification_text(c),
        finding=c.get("finding") or "(empty)",
        diagnosis=c.get("diagnosis") or "(empty)",
        laterality=c.get("laterality") or "(empty)",
        normalized=c.get("diagnosis_normalized") or "(empty)",
        umls_name=c.get("diagnosis_umls_preferred") or c.get("diagnosis_umls_pref") or "(none)",
        title=c.get("article_title") or c.get("title") or "(none)",
        keywords=", ".join(c.get("author_keywords") or c.get("keywords") or []) or "(none)",
        abstract=re.sub(r"\s+", " ", c.get("abstract") or "(none)")[:ABSTRACT_MAX_CHARS],
    )
    return msg, ev


def parse_json(text: str):
    text = re.sub(r"<reasoning>.*?</reasoning>", "", text, flags=re.S)
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def valid(p) -> bool:
    if not isinstance(p, dict):
        return False
    fields = ("classification", "finding", "laterality") + (
        ("diagnosis_article",) if "diagnosis_article" in p else ("diagnosis",))
    for f in fields:
        if not isinstance(p.get(f), dict) or p[f].get("verdict") not in VERDICTS:
            return False
    return isinstance(p.get("conditions", []), list)


class VerificationSubagent(Subagent):
    name = "VerificationSubagent"
    is_llm = True

    def __init__(self, client=None, model_id: str = None, prompt_path: Path = PROMPT_PATH):
        self.model_id = model_id or MODELS["verification"]
        self.system, self.template = load_prompt(prompt_path)
        self._client = client

    @property
    def client(self):
        if self._client is None:
            import boto3
            from botocore.config import Config
            self._client = boto3.client(
                "bedrock-runtime", region_name=REGION,
                config=Config(retries={"max_attempts": 8, "mode": "adaptive"}, read_timeout=180))
        return self._client

    def verify_case(self, c: dict) -> dict:
        """Call the verifier for one case dict; returns the record (same fields as step2_verifier)."""
        user, ev = build_user(c, self.template)
        rec = {"case_id": c.get("case_id"), "model_id": self.model_id, "prompt_version": PROMPT_VERSION,
               "inference": dict(INFERENCE), "region": REGION,
               "evidence_n_sentences": ev["n_sentences"], "evidence_n_mixed": ev["n_mixed_sentences"],
               "attempts": []}
        for _ in range(2):  # one re-ask if the JSON is unusable
            t0 = time.time()
            called_at = datetime.now(timezone.utc).isoformat()
            try:
                r = self.client.converse(
                    modelId=self.model_id,
                    system=[{"text": self.system}],
                    messages=[{"role": "user", "content": [{"text": user}]}],
                    inferenceConfig={"temperature": INFERENCE["temperature"],
                                     "maxTokens": INFERENCE["max_tokens"]},
                )
                text = "".join(b.get("text", "") for b in r["output"]["message"]["content"])
                parsed = parse_json(text)
                rec["attempts"].append({"called_at": called_at, "latency_s": round(time.time() - t0, 2),
                                        "usage": r.get("usage", {}), "stop_reason": r.get("stopReason"),
                                        "raw_text": text, "valid": valid(parsed)})
                if valid(parsed):
                    rec["parsed"] = parsed
                    break
            except Exception as e:  # logged, not raised
                rec["attempts"].append({"called_at": called_at, "latency_s": round(time.time() - t0, 2),
                                        "error": f"{type(e).__name__}: {str(e)[:300]}"})
        rec["ok"] = "parsed" in rec
        return rec

    def run(self, state: CaseState) -> CaseState:
        rec = self.verify_case(json.loads(state.to_jsonl_line()))
        parsed = rec.get("parsed") or {}
        state.verification = {
            "ok": rec["ok"],
            "model_id": rec["model_id"],
            "prompt_version": rec["prompt_version"],
            "classification": (parsed.get("classification") or {}).get("verdict"),
            "finding": (parsed.get("finding") or {}).get("verdict"),
            "laterality": (parsed.get("laterality") or {}).get("verdict"),
            "parsed": parsed or None,
        }
        state.models_used["verification"] = self.model_id
        return state
