#!/bin/bash
# Step 6: after the running verifier pass ends, retry rate-limit failures until none are left (max 8 rounds),
# recover format failures with step2_salvage.py, then merge. Resumable; safe to run twice (merge refuses to overwrite).
cd "$(dirname "$0")/.." || exit 1
RUN=data/outputs/step2/runs/full_v3_figscope
CASES=corpus:data/outputs/step6_figure_scope/cases.jsonl
LOG=data/outputs/step2/runs/full_v3_figscope_chain.log
notok() { python3 - <<'PY'
import json
ok=set(); allc=set()
for l in open("data/outputs/step2/runs/full_v3_figscope/nova-pro.jsonl"):
    r=json.loads(l); allc.add(r["case_id"])
    if r["ok"]: ok.add(r["case_id"])
print(len(allc-ok))
PY
}
{
echo "chain start $(date -u)"
while pgrep -f "^python3 pipeline/step2_verifier.py" >/dev/null; do sleep 30; done
for round in 1 2 3 4 5 6 7 8; do
  n=$(notok); echo "round $round: not ok = $n ($(date -u))"
  [ "$n" -eq 0 ] && break
  python3 pipeline/step2_verifier.py --cases $CASES --models nova-pro --run-id full_v3_figscope
done
n=$(notok); echo "after retries: not ok = $n"
if [ "$n" -gt 0 ]; then
  python3 pipeline/step2_salvage.py --run runs/full_v3_figscope/nova-pro.jsonl
  echo "after salvage: not ok = $(notok)"
fi
python3 pipeline/step6_merge_verifier.py && echo "merge done $(date -u)" || echo "MERGE FAILED OR INCOMPLETE $(date -u)"
echo "chain end $(date -u)"
} >> $LOG 2>&1
