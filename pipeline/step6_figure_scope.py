#!/usr/bin/env python3
"""Step 6: apply extraction pass 2 (figure-scope finding) to an existing corpus — resume from checkpoint.

 Pass 1 is NOT called again: each case is loaded with CaseState.from_dict and only
ExtractionSubagent.scope_finding_to_figure runs (checkpoint-resume principle). Diagnosis, laterality and every
other field stay as stored.

Input  : data/outputs/gapfill_v21/step1_view/cases.jsonl (the corpus v2.1 was built from, before the
         classification exclusion; 16,445 cases).
Output : <out>/cases.jsonl   same records, finding rewritten, + finding_article_level, finding_scope, one agent_log entry
         <out>/calls.jsonl   one line per case: case_id, model, prompt version, tokens, latency, finding_scope, calls
         <out>/summary.json  counts, finding_scope counts, cost, word-support distribution
Checkpoint: case_id. Cases already in <out>/cases.jsonl are skipped; a case is written once (both files, under one lock).
Cost: Haiku 4.5 list price (input $1/M, output $5/M); the Bedrock bill still has to be checked.

  python3 pipeline/step6_figure_scope.py --sample <sample_items.csv> \
      --out data/outputs/step6_figure_scope/sample120          # step 3: 120-case pilot reproduction
  nohup python3 pipeline/step6_figure_scope.py > data/outputs/step6_figure_scope/run.log 2>&1 &   # step 4
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import statistics
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from openredu.agents.curation.subagents.extraction import (  # noqa: E402
    FIGURE_SCOPE_PROMPT_VERSION,
    ExtractionSubagent,
)
from openredu.config import MODELS  # noqa: E402
from openredu.core.figure_evidence import build_evidence, evidence_text, support_ratio  # noqa: E402
from openredu.core.state import CaseState  # noqa: E402

PRICE = {"in": 1.0 / 1e6, "out": 5.0 / 1e6}  # Haiku 4.5 list price, USD per token
COPY_BACK = ("finding", "finding_article_level", "finding_scope", "agent_log", "models_used")
log = logging.getLogger("step6")


def read_jsonl(path: Path):
    with path.open() as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def done_ids(path: Path) -> set[str]:
    return {d["case_id"] for d in read_jsonl(path)} if path.exists() else set()


def process(sub: ExtractionSubagent, case: dict) -> tuple[dict, dict]:
    st = CaseState.from_dict(case)
    if st.finding_scope or st.finding_article_level:
        raise ValueError(f"{st.case_id}: input already has pass-2 fields")
    t0 = time.time()
    sub.scope_finding_to_figure(st)
    out = dict(case)
    for k in COPY_BACK:
        out[k] = getattr(st, k)
    entry = next((e for e in reversed(st.agent_log) if e.get("step") == "figure_scope_finding"), {})
    call = {"case_id": st.case_id, "model": entry.get("model"), "prompt_version": entry.get("prompt_version"),
            "finding_scope": st.finding_scope, "input_tokens": entry.get("input_tokens", 0),
            "output_tokens": entry.get("output_tokens", 0), "latency_s": round(time.time() - t0, 3),
            "support_article_level": entry.get("support_article_level"), "support_new": entry.get("support_new"),
            "n_calls": len(entry.get("calls", [])), "calls": entry.get("calls", []),
            "ts": datetime.now(timezone.utc).isoformat()}
    return out, call


def dist(vals: list) -> dict:
    v = [x for x in vals if x is not None]
    if not v:
        return {"n": 0}
    q = statistics.quantiles(v, n=4) if len(v) > 1 else [v[0]] * 3
    return {"n": len(v), "n_none": len(vals) - len(v), "mean": round(statistics.mean(v), 4),
            "median": round(statistics.median(v), 4), "q1": round(q[0], 4), "q3": round(q[2], 4),
            "below_0.7": sum(x < 0.7 for x in v), "below_0.5": sum(x < 0.5 for x in v)}


def summarize(out_dir: Path, input_ids: list[str], input_path: str) -> dict:
    cases = list(read_jsonl(out_dir / "cases.jsonl"))
    calls = list(read_jsonl(out_dir / "calls.jsonl"))
    ids = [c["case_id"] for c in cases]
    scopes: dict[str, int] = {}
    for c in cases:
        scopes[c["finding_scope"]] = scopes.get(c["finding_scope"], 0) + 1
    sup_before, sup_after = [], []
    for c in cases:
        evid = evidence_text(build_evidence(c))
        sup_before.append(support_ratio(c["finding_article_level"], evid))
        sup_after.append(support_ratio(c["finding"], evid))
    ti = sum(c["input_tokens"] for c in calls)
    to = sum(c["output_tokens"] for c in calls)
    n_fallback = sum(v for k, v in scopes.items() if k.startswith("article_fallback"))
    return {
        "date": datetime.now(timezone.utc).isoformat(),
        "input": input_path, "model": MODELS["extraction_primary"], "prompt_version": FIGURE_SCOPE_PROMPT_VERSION,
        "temperature": 0, "pass1_called": False,
        "n_input": len(input_ids), "n_output": len(cases), "n_unique_output": len(set(ids)),
        "n_missing": len(set(input_ids) - set(ids)), "n_extra": len(set(ids) - set(input_ids)),
        "n_calls_lines": len(calls), "finding_scope_counts": dict(sorted(scopes.items())),
        "fallback_rate": round(n_fallback / len(cases), 4) if cases else None,
        "finding_changed": sum(c["finding"] != c["finding_article_level"] for c in cases),
        "support_article_level": dist(sup_before), "support_final": dist(sup_after),
        "input_tokens": ti, "output_tokens": to,
        "cost_usd_list_price": round(ti * PRICE["in"] + to * PRICE["out"], 4),
        "cost_note": "Haiku 4.5 list price (input $1/M, output $5/M); check the Bedrock bill.",
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", default="data/outputs/gapfill_v21/step1_view/cases.jsonl")
    ap.add_argument("--sample", default="", help="sample_items.csv: only these case_ids")
    ap.add_argument("--out", default="data/outputs/step6_figure_scope")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("openredu").setLevel(logging.WARNING)

    out = ROOT / a.out
    out.mkdir(parents=True, exist_ok=True)
    for protected in ("data/freeze", "data/outputs/v2_1"):
        if str(out.resolve()).startswith(str((ROOT / protected).resolve())):
            raise SystemExit(f"refusing to write under {protected}")

    want = None
    if a.sample:
        want = {r["case_id"] for r in csv.DictReader(open(ROOT / a.sample, encoding="utf-8-sig"))}
    cases = [c for c in read_jsonl(ROOT / a.cases) if want is None or c["case_id"] in want]
    if want is not None and len(cases) != len(want):
        raise SystemExit(f"sample case_ids missing from input: {sorted(want - {c['case_id'] for c in cases})[:5]}")
    if a.limit:
        cases = cases[: a.limit]
    input_ids = [c["case_id"] for c in cases]
    if len(set(input_ids)) != len(input_ids):
        raise SystemExit("duplicate case_id in input")

    done = done_ids(out / "cases.jsonl")
    todo = [c for c in cases if c["case_id"] not in done]
    log.info("input %d, already done %d, to do %d, workers %d", len(cases), len(done), len(todo), a.workers)

    sub = ExtractionSubagent()
    lock = threading.Lock()
    n_ok = n_err = 0
    t_start = time.time()
    with (out / "cases.jsonl").open("a") as fc, (out / "calls.jsonl").open("a") as fl, \
            ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = {ex.submit(process, sub, c): c["case_id"] for c in todo}
        for fut in as_completed(futs):
            cid = futs[fut]
            try:
                rec, call = fut.result()
            except Exception as e:  # not written -> retried on the next run
                n_err += 1
                log.error("%s failed: %s", cid, e)
                continue
            with lock:
                if cid in done:
                    continue
                fc.write(json.dumps(rec, ensure_ascii=False) + "\n")
                fl.write(json.dumps(call, ensure_ascii=False) + "\n")
                fc.flush()
                fl.flush()
                done.add(cid)
                n_ok += 1
            if n_ok % 100 == 0:
                rate = n_ok / (time.time() - t_start)
                log.info("done %d/%d this run (%.2f/s, ~%.0f min left)", n_ok, len(todo), rate,
                         (len(todo) - n_ok) / rate / 60 if rate else -1)

    s = summarize(out, input_ids, a.cases)
    s["this_run"] = {"processed": n_ok, "errors_not_written": n_err, "elapsed_s": round(time.time() - t_start, 1)}
    (out / "summary.json").write_text(json.dumps(s, indent=2, ensure_ascii=False))
    print(json.dumps({k: v for k, v in s.items()}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
