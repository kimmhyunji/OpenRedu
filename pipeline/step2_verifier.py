#!/usr/bin/env python3
"""Step 2: run the independent verifier (non-Claude, non-Mistral) on a case set.

Each call sends figure-scoped evidence (caption + sentences citing the figure) and the
v1 extracted fields; the model returns per-field verdicts, diagnostic status, and the
status/depiction of each condition named in the extraction (reused by Step 3).

Every call is logged with model ID, timestamp, inference parameters, prompt version,
token usage, latency and the raw response. Runs are resumable per (model, case).

Usage:
  python3 pipeline/step2_verifier.py --cases dev230 --models all --run-id dev_v1
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import boto3
import yaml
from botocore.config import Config
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).parent))
from step2_evidence import build_evidence, render_evidence  # noqa: E402

CFG = yaml.safe_load((ROOT / "config/pipeline.yaml").read_text())
V = CFG["step2_verifier"]
SNAP = ROOT / CFG["snapshot_dir"]
load_dotenv(ROOT / ".env")

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


def load_prompt() -> tuple[str, str]:
    txt = (ROOT / V["prompt_file"]).read_text()
    system = txt.split("<<<SYSTEM>>>")[1].split("<<<USER_TEMPLATE>>>")[0].strip()
    user = txt.split("<<<USER_TEMPLATE>>>")[1].split("<<<END>>>")[0].strip()
    return system, user


def classification_text(c: dict) -> str:
    base = CATEGORY_TEXT.get(c.get("modality", ""), c.get("modality", ""))
    anat = (c.get("anatomy") or "").strip()
    return f"{base}" + (f" (anatomy: {anat})" if anat else "")


def build_user(c: dict, template: str) -> tuple[str, dict]:
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
    ) if "{abstract}" in template else template.format(
        evidence=render_evidence(ev), classification=classification_text(c),
        finding=c.get("finding") or "(empty)", diagnosis=c.get("diagnosis") or "(empty)",
        laterality=c.get("laterality") or "(empty)", normalized=c.get("diagnosis_normalized") or "(empty)",
        umls_name=c.get("diagnosis_umls_preferred") or c.get("diagnosis_umls_pref") or "(none)",
    )
    return msg, ev


def parse_json(text: str) -> dict | None:
    text = re.sub(r"<reasoning>.*?</reasoning>", "", text, flags=re.S)
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


VERDICTS = {"supported", "unclear", "not_supported"}
ABSTRACT_MAX_CHARS = 2500


def valid(p: dict | None) -> bool:
    if not isinstance(p, dict):
        return False
    fields = ("classification", "finding", "laterality") + (
        ("diagnosis_article",) if "diagnosis_article" in p else ("diagnosis",))
    for f in fields:
        if not isinstance(p.get(f), dict) or p[f].get("verdict") not in VERDICTS:
            return False
    return isinstance(p.get("conditions", []), list)


def load_cases(spec: str) -> list[dict]:
    corpus = SNAP / CFG["v1"]["corpus"]
    if spec == "dev230":
        rows = csv.DictReader(open(ROOT / "data/dev_labels/extraction_labels.csv"))
        ids = {r["case_id"] for r in rows if r["in_paper_230"] == "True"}
    elif spec == "step1":
        corpus = ROOT / "data/outputs/step1/corpus_casereport_only/cases.jsonl"
        ids = None
    elif spec.startswith("corpus:"):          # every case of another corpus file (e.g. v2.1 gap-fill cases)
        corpus = ROOT / spec.split(":", 1)[1]
        ids = None
    else:
        ids = {l.strip() for l in open(spec) if l.strip()}
    out = []
    for line in corpus.open():
        c = json.loads(line)
        if ids is None or c["case_id"] in ids:
            out.append(c)
    return out


class Runner:
    def __init__(self, short: str, run_dir: Path):
        m = V["models"][short]
        self.short, self.model_id = short, m["model_id"]
        self.extra = m.get("extra") or {}
        self.client = boto3.client("bedrock-runtime", region_name=V["region"],
                                   config=Config(retries={"max_attempts": 8, "mode": "adaptive"},
                                                 read_timeout=180))
        self.system, self.template = load_prompt()
        self.out = run_dir / f"{short}.jsonl"
        self.lock = threading.Lock()

    def done(self) -> set[str]:
        if not self.out.exists():
            return set()
        # Only successful records count as done; failed cases are retried and the newer
        # record supersedes the older one (readers keep the last record per case).
        return {r["case_id"] for r in map(json.loads, filter(str.strip, self.out.open())) if r["ok"]}

    def call(self, c: dict) -> dict:
        user, ev = build_user(c, self.template)
        rec = {"case_id": c["case_id"], "model_short": self.short, "model_id": self.model_id,
               "prompt_version": V["prompt_version"], "inference": {**V["inference"], **self.extra},
               "region": V["region"], "evidence_n_sentences": ev["n_sentences"],
               "evidence_n_mixed": ev["n_mixed_sentences"], "attempts": []}
        for attempt in range(2):  # one re-ask if the JSON is unusable
            t0 = time.time()
            called_at = datetime.now(timezone.utc).isoformat()
            try:
                kwargs = {"additionalModelRequestFields": self.extra} if self.extra else {}
                r = self.client.converse(
                    **kwargs,
                    modelId=self.model_id,
                    system=[{"text": self.system}],
                    messages=[{"role": "user", "content": [{"text": user}]}],
                    inferenceConfig={"temperature": V["inference"]["temperature"],
                                     "maxTokens": V["inference"]["max_tokens"]},
                )
                text = "".join(b.get("text", "") for b in r["output"]["message"]["content"])
                usage = r.get("usage", {})
                parsed = parse_json(text)
                rec["attempts"].append({"called_at": called_at, "latency_s": round(time.time() - t0, 2),
                                        "usage": usage, "stop_reason": r.get("stopReason"),
                                        "raw_text": text, "valid": valid(parsed)})
                if valid(parsed):
                    rec["parsed"] = parsed
                    break
            except Exception as e:  # logged, not raised
                rec["attempts"].append({"called_at": called_at, "latency_s": round(time.time() - t0, 2),
                                        "error": f"{type(e).__name__}: {str(e)[:300]}"})
        rec["ok"] = "parsed" in rec
        rec["input_tokens"] = sum(a.get("usage", {}).get("inputTokens", 0) for a in rec["attempts"])
        rec["output_tokens"] = sum(a.get("usage", {}).get("outputTokens", 0) for a in rec["attempts"])
        with self.lock, self.out.open("a") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return rec


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", required=True, help="dev230 | step1 | path to case-id list")
    ap.add_argument("--models", default="all")
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    run_dir = ROOT / "data/outputs/step2/runs" / args.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    cases = load_cases(args.cases)
    if args.limit:
        cases = cases[: args.limit]
    shorts = list(V["models"]) if args.models == "all" else args.models.split(",")
    meta = {"run_id": args.run_id, "cases": args.cases, "n_cases": len(cases), "models": shorts,
            "prompt_file": V["prompt_file"], "prompt_version": V["prompt_version"],
            "inference": V["inference"], "started_at": datetime.now(timezone.utc).isoformat()}
    (run_dir / "run_meta.json").write_text(json.dumps(meta, indent=2))

    def run_model(short: str) -> None:
        rn = Runner(short, run_dir)
        done = rn.done()   # read the run file once (calling it per case re-parses the whole file each time)
        todo = [c for c in cases if c["case_id"] not in done]
        print(f"[{short}] {len(todo)} to run", flush=True)
        n_ok = 0
        workers = V["models"][short].get("max_workers", V["max_workers_per_model"])
        with ThreadPoolExecutor(workers) as ex:
            for i, fut in enumerate(as_completed([ex.submit(rn.call, c) for c in todo]), 1):
                n_ok += fut.result()["ok"]
                if i % 25 == 0 or i == len(todo):
                    print(f"[{short}] {i}/{len(todo)} ok={n_ok}", flush=True)

    with ThreadPoolExecutor(len(shorts)) as ex:
        for f in [ex.submit(run_model, s) for s in shorts]:
            f.result()
    meta["finished_at"] = datetime.now(timezone.utc).isoformat()
    (run_dir / "run_meta.json").write_text(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
