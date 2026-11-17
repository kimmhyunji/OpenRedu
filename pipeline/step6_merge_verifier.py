#!/usr/bin/env python3
"""Step 6: merge the verifier rerun on the figure-scoped corpus into the v2.1 verifier results .

From the NEW run (runs/full_v3_figscope): only parsed["finding"] (the finding verdict) and parsed["conditions"].
From the v2.1 run (runs/full_v3): everything else (classification, laterality, diagnosis_article, diagnosis_in_figure,
normalized_diagnosis, diagnosis_status), so the classification exclusion (418 cases) and the diagnosis-side labels do
not move.

Cases whose finding was not changed by pass 2 (finding == finding_article_level) keep the v2.1 record as is (--use-new-for-unchanged
takes the new run for them too). For these cases the script also counts how often the new run disagrees with v2.1 on the finding
verdict — a measure of run-to-run noise at temperature 0.

Output: runs/full_v3_figscope_merged/nova-pro.jsonl, one record per case of the input corpus (last ok record of each run;
salvaged records count). Each record has "merge": {field: source run} so the origin of every part is visible.
Also writes merge_summary.json. Missing cases are reported and make the script exit with code 1.

  python3 pipeline/step6_merge_verifier.py
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "data/outputs/step2/runs"
NEW_FIELDS = ("finding", "conditions")


def last_ok(path: Path) -> dict[str, dict]:
    out = {}
    for line in path.open():
        if line.strip():
            r = json.loads(line)
            if r.get("ok"):
                out[r["case_id"]] = r      # later records supersede earlier ones (as step5/step3 readers do)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default="data/outputs/step6_figure_scope/cases.jsonl")
    ap.add_argument("--base-run", default="full_v3")
    ap.add_argument("--new-run", default="full_v3_figscope")
    ap.add_argument("--out-run", default="full_v3_figscope_merged")
    ap.add_argument("--use-new-for-unchanged", action="store_true",
                    help="also take finding/conditions from the new run when pass 2 left the finding unchanged")
    a = ap.parse_args()

    corpus = [json.loads(l) for l in (ROOT / a.corpus).open() if l.strip()]
    ids = [c["case_id"] for c in corpus]
    changed = {c["case_id"]: c["finding"] != c["finding_article_level"] for c in corpus}
    base = last_ok(RUNS / a.base_run / "nova-pro.jsonl")
    new = last_ok(RUNS / a.new_run / "nova-pro.jsonl")

    out_dir = RUNS / a.out_run
    if (out_dir / "nova-pro.jsonl").exists():
        sys.exit(f"{out_dir}/nova-pro.jsonl already exists; not overwriting")
    out_dir.mkdir(parents=True, exist_ok=True)

    missing_base = [i for i in ids if i not in base]
    missing_new = [i for i in ids if changed[i] and i not in new]
    if a.use_new_for_unchanged:
        missing_new = [i for i in ids if i not in new]
    stats = Counter()
    flips = Counter()
    recs = []
    for cid in ids:
        if cid in missing_base or cid in missing_new:
            continue
        b = base[cid]
        take_new = cid in new and (changed[cid] or a.use_new_for_unchanged)
        p = json.loads(json.dumps(b["parsed"]))        # deep copy
        merge = {k: a.base_run for k in p}
        if take_new:
            for k in NEW_FIELDS:
                if k in new[cid]["parsed"]:
                    p[k] = new[cid]["parsed"][k]
                    merge[k] = a.new_run
                else:
                    p.pop(k, None)
                    merge[k] = f"{a.new_run} (absent)"
            stats["finding_conditions_from_new_run"] += 1
        else:
            stats["kept_v2_1_record_finding_unchanged"] += 1
            if cid in new:      # noise check on identical input
                o, n = b["parsed"]["finding"]["verdict"], new[cid]["parsed"]["finding"]["verdict"]
                stats["unchanged_with_new_result"] += 1
                if o != n:
                    flips[f"{o}->{n}"] += 1
        rec = {k: v for k, v in b.items() if k != "parsed"}
        rec["parsed"] = p
        rec["merge"] = merge
        rec["merge_info"] = {"base_run": a.base_run, "new_run": a.new_run if take_new else None,
                             "finding_changed_by_pass2": changed[cid],
                             "new_run_salvaged": bool(take_new and new[cid].get("salvaged"))}
        recs.append(rec)

    with (out_dir / "nova-pro.jsonl").open("w") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    def dist(get):
        return dict(Counter(get(r) for r in recs))

    # finding verdict: v2.1 vs merged, same cases
    v21_f = Counter(base[r["case_id"]]["parsed"]["finding"]["verdict"] for r in recs)
    new_f = Counter(r["parsed"]["finding"]["verdict"] for r in recs)
    trans = Counter(f'{base[r["case_id"]]["parsed"]["finding"]["verdict"]}->{r["parsed"]["finding"]["verdict"]}' for r in recs)
    # fields that must not move
    moved = Counter()
    for r in recs:
        for k in r["parsed"]:
            if k not in NEW_FIELDS and r["parsed"][k] != base[r["case_id"]]["parsed"][k]:
                moved[k] += 1
    n = len(recs)
    summary = {
        "date": datetime.now(timezone.utc).isoformat(),
        "corpus": a.corpus, "base_run": a.base_run, "new_run": a.new_run, "out_run": a.out_run,
        "use_new_for_unchanged": a.use_new_for_unchanged,
        "n_input": len(ids), "n_output": n, "n_missing_base": len(missing_base), "n_missing_new": len(missing_new),
        "missing_base_examples": missing_base[:10], "missing_new_examples": missing_new[:10],
        "sources": dict(stats), "unchanged_finding_verdict_flips_new_vs_v2_1": dict(flips),
        "n_new_run_salvaged_used": sum(r["merge_info"]["new_run_salvaged"] for r in recs),
        "finding_verdict_v2_1": dict(v21_f), "finding_verdict_merged": dict(new_f),
        "finding_not_supported_rate_v2_1": round(v21_f["not_supported"] / n, 4) if n else None,
        "finding_not_supported_rate_merged": round(new_f["not_supported"] / n, 4) if n else None,
        "finding_verdict_transitions": dict(trans),
        "fields_other_than_finding_conditions_that_differ_from_v2_1": dict(moved),
        "classification_not_supported": new_f and sum(r["parsed"]["classification"]["verdict"] == "not_supported" for r in recs),
    }
    (out_dir / "merge_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    if missing_base or missing_new or n != len(ids):
        sys.exit(1)


if __name__ == "__main__":
    main()
