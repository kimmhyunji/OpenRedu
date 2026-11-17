#!/usr/bin/env python3
"""Step 3: assertion/depiction-aware matching + technique gate.

1. Candidates: the unchanged v1 rule (Gate 1 division/modality, Gate 2 lexical phrase in
   diagnosis_normalized/diagnosis/finding, Gate 3 pediatric evidence), run on the Step 1
   corpus view with the original module.
2. For each candidate, every occurrence of a matched phrase gets a rule-based status from
   its sentence context (negation, differential, suspicion, history, complication).
3. If a Step 2 verifier run is configured, the phrase is aligned to the verifier's
   `conditions` list and its status/depiction is used (explicit negation found by rule
   still wins on conflict when configured).
4. Technique-specific topics additionally require a technique term in the figure evidence
   or the extraction (e.g. FES, PSMA, MAG3).
5. Keep = status allowed (confirmed; +suspected if configured) AND depiction allowed AND
   technique gate passed. Every candidate is written with its reason codes.
No LLM calls.
"""
from __future__ import annotations

import argparse
import contextlib
import csv
import io
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).parent))
import openredu.pipeline.report_apdr_schedule_coverage as cov  # noqa: E402
from step2_evidence import build_evidence  # noqa: E402

CFG = yaml.safe_load((ROOT / "config/pipeline.yaml").read_text())
S3 = CFG["step3_assertion"]
SNAP = ROOT / CFG["snapshot_dir"]
FIELDS = ("diagnosis_normalized", "diagnosis", "finding")

# ── rule-based context status (NegEx-style, clause-scoped) ────────────────────
PRE = {
    "ruled_out": [r"no", r"not", r"without", r"absence of", r"absent", r"negative for", r"no evidence of",
                  r"no sign(?:s)? of", r"no features of", r"free of", r"ruled out", r"rule out", r"excluded",
                  r"exclusion of", r"resolution of", r"resolved", r"disappearance of", r"unlikely",
                  r"no (?:definite|obvious|significant|apparent|residual|recurrent)"],
    "differential": [r"differential(?: diagnos[ie]s)?(?: of| includes?| including)?", r"versus", r"vs\.?",
                     r"mimick?(?:ing|s|ed)?", r"simulating", r"masquerading as", r"rather than", r"instead of",
                     r"distinguish(?:ed|ing)? from", r"differentiat(?:e|ed|ing) from", r"or"],
    "suspected": [r"suspected", r"suspicious (?:for|of)", r"concerning for", r"possible", r"possibly",
                  r"probable", r"probably", r"likely", r"presumed", r"presumptive", r"query", r"questionable",
                  r"cannot (?:be )?exclude[d]?", r"could not (?:be )?exclude[d]?", r"suggest(?:ive of|ing|s)?",
                  r"raising (?:the )?(?:possibility|suspicion) of", r"compatible with"],
    # Only strong history cues; "after"/"following" mark the cause, not the depicted condition.
    "historical": [r"history of", r"h/o", r"prior", r"previous(?:ly)?(?: treated| resected| diagnosed)?",
                   r"status post", r"s/p", r"background of", r"remote", r"known history of"],
}
POST = {
    "ruled_out": [r"(?:was|were|is|are|been)? ?(?:excluded|ruled out|not (?:seen|identified|detected|present|visualized|observed)|absent|resolved)",
                  r"(?:was|were) negative"],
    "differential": [r"(?:was|were)? ?(?:considered|included) in the differential", r"(?:was|were) (?:considered|suspected) but"],
    "historical": [r"carrier", r"history"],
}
TERMINATORS = re.compile(r"[.;:]|\bbut\b|\bhowever\b|\balthough\b|\bwhich\b|\bwith\b|\bshowing\b|\brevealed\b|"
                         r"\bdemonstrat\w*\b|\bconsistent with\b|\bconfirm\w*\b|\bdiagnos\w* (?:of|as|was)\b", re.I)
PRE_WINDOW = 7    # tokens before the phrase
POST_WINDOW = 5   # tokens after the phrase
STATUS_ORDER = ["confirmed", "suspected", "complication", "differential", "historical", "ruled_out"]


def phrase_regex(phrase: str) -> re.Pattern:
    toks = cov.normalize(phrase).split()
    return re.compile(r"(?<![a-z0-9])" + r"[^a-z0-9]+".join(map(re.escape, toks)) + r"(?![a-z0-9])", re.I)


def _clause_left(text: str, start: int) -> str:
    left = text[:start]
    cut = 0
    for m in TERMINATORS.finditer(left):
        cut = m.end()
    words = left[cut:].split()
    return " ".join(words[-PRE_WINDOW:]).lower()


def _clause_right(text: str, end: int) -> str:
    right = text[end:]
    m = TERMINATORS.search(right)
    right = right[: m.start()] if m else right
    return " ".join(right.split()[:POST_WINDOW]).lower()


def occurrence_status(text: str, start: int, end: int) -> tuple[str, str]:
    left, right = _clause_left(text, start), _clause_right(text, end)
    for status in ["ruled_out", "differential", "suspected", "historical"]:
        for trig in PRE[status]:
            if re.search(r"(?<![a-z])" + trig + r"(?![a-z])", left):
                if status == "differential" and trig == "or" and not re.search(r"\bor\b", left[-12:]):
                    continue
                return status, f"pre:{trig}"
        for trig in POST.get(status, []):
            if re.match(r"\s*" + trig, right):
                return status, f"post:{trig}"
    return "confirmed", "affirmative"


def rule_status(case: dict, phrases: list[str]) -> dict:
    occ = []
    for field in FIELDS:
        text = case.get(field) or ""
        for p in phrases:
            for m in phrase_regex(p).finditer(text):
                st, why = occurrence_status(text, m.start(), m.end())
                occ.append({"phrase": p, "field": field, "status": st, "trigger": why,
                            "context": text[max(0, m.start() - 60): m.end() + 40]})
    if S3.get("normalized_inherits_diagnosis_context", False):
        # The normalized term is a bare concept name ("Acute cholecystitis") with no sentence
        # context, so it always reads as affirmative. When the same phrase occurs in the raw
        # diagnosis with a non-affirmative context ("Cholelithiasis without acute cholecystitis",
        # "ICD mimicking breast cancer"), the normalized occurrence takes that context instead of
        # overriding it (found by the NO_NORMALIZATION downstream comparison).
        raw = {}
        for o in occ:
            if o["field"] == "diagnosis" and o["status"] != "confirmed":
                raw.setdefault(o["phrase"], o)
        for o in occ:
            if o["field"] == "diagnosis_normalized" and o["status"] == "confirmed" and o["phrase"] in raw:
                o["status"], o["trigger"] = raw[o["phrase"]]["status"], "inherited_from_diagnosis:" + raw[o["phrase"]]["trigger"]
    if not occ:
        # v1 joins diagnosis_normalized + diagnosis + finding before matching, so a phrase can be
        # formed across the field boundary ("...thyroid" + "cyst-solid mass" -> "thyroid cyst").
        return {"status": "cross_field_artifact", "occurrences": []}
    best = min(occ, key=lambda o: STATUS_ORDER.index(o["status"]))["status"]
    return {"status": best, "occurrences": occ,
            "all_negated": all(o["status"] == "ruled_out" for o in occ)}


# ── verifier alignment ─────────────────────────────────────────────────────────
def load_verifier(path: str | None) -> dict[str, dict]:
    if not path:
        return {}
    out = {}
    for line in (ROOT / "data/outputs/step2" / path).open():
        r = json.loads(line)
        if r.get("ok"):
            out[r["case_id"]] = r["parsed"]
    return out


# Off-vocabulary verifier values (rare; the prompt asks for the fixed vocabulary) mapped to the policy
# vocabulary. Ambiguous ones become "unclear" so the rule-based context decides (verifier_unclear_status).
STATUS_SYNONYMS = {"shown": "confirmed", "incidental": "confirmed", "persistent": "confirmed", "known": "confirmed",
                   "consistent": "confirmed", "suggestive": "suspected", "presumptive": "suspected",
                   "improved": "resolved", "misdiagnosed": "ruled_out", "alternative consideration": "differential",
                   "associated": "unclear", "not_supported": "unclear"}
DEPICTED_SYNONYMS = {"shown": "true", "not_shown": "false"}
KNOWN_STATUS = set(STATUS_ORDER) | {"unclear", "resolved", "mimicking"}


def norm_status(v) -> str:
    v = str(v or "unclear").strip().lower()
    v = STATUS_SYNONYMS.get(v, v)
    return v if v in KNOWN_STATUS else "unclear"


def norm_depicted(v) -> str:
    v = str(v or "unclear").strip().lower()
    v = DEPICTED_SYNONYMS.get(v, v)
    return v if v in ("true", "false", "unclear") else "unclear"


def align(parsed: dict, phrases: list[str]) -> dict | None:
    hits = []
    for cnd in parsed.get("conditions") or []:
        name = cov.normalize(str(cnd.get("name", "")))
        if not name:
            continue
        for p in phrases:
            np_ = cov.normalize(p)
            if cov.phrase_in_text(np_, name) or cov.phrase_in_text(name, np_):
                hits.append(cnd)
                break
    if not hits:
        return None
    def rank(c):
        st = norm_status(c.get("status"))
        return (STATUS_ORDER.index(st) if st in STATUS_ORDER else len(STATUS_ORDER),
                {"true": 0, "unclear": 1, "false": 2}[norm_depicted(c.get("depicted"))])
    best = min(hits, key=rank)
    return {"status": norm_status(best.get("status")), "depicted": norm_depicted(best.get("depicted")),
            "name": best.get("name"), "n_aligned": len(hits)}


# ── technique gate ─────────────────────────────────────────────────────────────
def technique_ok(case: dict, sid: str, terms_by_topic: dict | None = None) -> tuple[bool | None, str]:
    terms = (S3["technique_terms"] if terms_by_topic is None else terms_by_topic).get(sid)
    if not terms:
        return None, ""
    ev = build_evidence(case)
    text = " ".join([ev["caption"], *[s["text"] for s in ev["sentences"]],
                     case.get("finding") or "", case.get("diagnosis") or ""]).lower()
    for t in terms:
        if re.search(r"(?<![a-z0-9])" + re.escape(t.lower()), text):
            return True, t
    return False, ""


# ── main ──────────────────────────────────────────────────────────────────────
def v1_candidates(corpus_path: Path, out_dir: Path) -> dict:
    os.environ["OPENREDU_APDR_CORPUS"] = str(corpus_path.relative_to(ROOT))
    cov.DATA = out_dir / "v1_rule"
    cov.SCHEDULE_CSV = SNAP / CFG["v1"]["schedule_csv"]
    cov.TOPIC_KEYWORDS = cov._load_topic_keywords(SNAP / CFG["v1"]["topic_phrases"])
    for sid, adds in (S3.get("topic_phrase_additions") or {}).items():
        tc = cov.TOPIC_KEYWORDS[sid]
        tc["revision_added_phrases"] = [p for p in adds if p not in tc["phrases"]]
        tc["phrases"] = list(tc["phrases"]) + tc["revision_added_phrases"]
    if S3.get("concept_expansion") == "umls_synonyms":
        syn = json.loads((ROOT / "data/outputs/step4/topic_synonym_phrases.json").read_text())
        for sid, tc in cov.TOPIC_KEYWORDS.items():
            extra = (syn.get(sid) or {}).get("umls_synonyms", [])
            tc["curated_phrases"] = list(tc["phrases"])
            tc["phrases"] = list(tc["phrases"]) + [p for p in extra if p not in tc["phrases"]]
    with contextlib.redirect_stdout(io.StringIO()):
        cov.main()
    return json.loads((out_dir / "v1_rule/curriculum_mapping/apdr_schedule_coverage.json").read_text())


def match_strength(rs: dict) -> str:
    """strong = phrase in a diagnosis field; moderate = multi-word phrase only in finding;
    weak = only single-word phrase(s) only in finding (dev precision 67% vs 87-90% for
    diagnosis-field matches). Label only; not used to remove assignments."""
    occ = rs.get("occurrences") or []
    if not occ:
        return "none"
    if any(o["field"] != "finding" for o in occ):
        return "strong"
    if any(len(cov.normalize(o["phrase"]).split()) > 1 for o in occ):
        return "moderate"
    return "weak"


def decide(rs: dict, al: dict | None, tech: bool | None) -> tuple[bool, str, str, str]:
    include_susp = bool(S3.get("include_suspected"))
    # A complication that is present is an asserted condition; it is kept like "confirmed".
    allowed = {"confirmed", "complication"} | ({"suspected"} if include_susp else set())
    if al is not None and al["status"] in ("unclear", None, "") and S3.get("verifier_unclear_status") == "fallback_rule":
        # verifier could not tell the status: use the rule-based context status instead
        status, depicted, source = rs["status"], al["depicted"], "verifier_unclear->rule"
    elif al is not None:
        status, depicted, source = al["status"], al["depicted"], "verifier"
        if S3.get("explicit_negation_overrides_verifier") and rs.get("all_negated") and status != "ruled_out":
            status, source = "ruled_out", "rule_override"
    else:
        status, depicted, source = rs["status"], "unknown", "rule"
    reasons = []
    if status not in allowed:
        reasons.append(f"status:{status}")
    if depicted == "unknown":
        if not S3.get("keep_depicted_unknown", True):
            reasons.append("depicted:unknown")
    elif depicted not in set(S3["keep_depicted"]):
        # optional: a condition-level "false" removes only if the case-level check also says
        # the diagnosis is not shown in this figure
        if not (depicted == "false" and S3.get("depicted_false_requires_case_not_shown")
                and (al or {}).get("case_dx_in_figure") != "not_shown"):
            reasons.append(f"depicted:{depicted}")
    if tech is False:
        reasons.append("technique:missing")
    return (not reasons), status, depicted, source + ("|" + ";".join(reasons) if reasons else "")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default="data/outputs/step1/corpus_casereport_only/cases.jsonl")
    ap.add_argument("--verifier", default=S3.get("verifier_run"))
    ap.add_argument("--out", default="data/outputs/step3/rule_only")
    ap.add_argument("--include-suspected", choices=["true", "false"], default=None)
    ap.add_argument("--keep-depicted", default=None, help="comma list, e.g. true,unclear")
    ap.add_argument("--depicted-false-requires-case-not-shown", action="store_true")
    ap.add_argument("--concept-expansion", choices=["none", "umls_synonyms"], default=None)
    args = ap.parse_args()
    if args.concept_expansion:
        S3["concept_expansion"] = args.concept_expansion
    if args.depicted_false_requires_case_not_shown:
        S3["depicted_false_requires_case_not_shown"] = True
    if args.include_suspected is not None:
        S3["include_suspected"] = args.include_suspected == "true"
    if args.keep_depicted:
        S3["keep_depicted"] = args.keep_depicted.split(",")
    out_dir = ROOT / args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    corpus_path = ROOT / args.corpus
    cases = {json.loads(l)["case_id"]: json.loads(l) for l in corpus_path.open()}
    ver = load_verifier(args.verifier)
    covres = v1_candidates(corpus_path, out_dir)
    topics = [t for t in covres["topics"] if t["status"] != "excluded"]

    rows = []
    for t in topics:
        sid, phrases = t["schedule_entry_id"], t["match_phrases"]
        curated = cov.TOPIC_KEYWORDS[sid].get("curated_phrases", phrases)
        added = set(cov.TOPIC_KEYWORDS[sid].get("revision_added_phrases", []))
        for cid in t.get("matched_case_ids", []):
            c = cases[cid]
            rs = rule_status(c, phrases)
            al = align(ver[cid], phrases) if cid in ver else None
            if al is not None:
                al["case_dx_in_figure"] = (ver[cid].get("diagnosis_in_figure") or {}).get("verdict")
            tech, tech_term = technique_ok(c, sid)
            keep, status, depicted, why = decide(rs, al, tech)
            rows.append({
                "case_id": cid, "schedule_entry_id": sid, "canonical_topic_id": t["canonical_topic_id"],
                "division": t["division"], "keyword": t["keyword"], "modality": c.get("modality"),
                "matched_phrases": sorted({o["phrase"] for o in rs["occurrences"]}),
                "matched_fields": sorted({o["field"] for o in rs["occurrences"]}),
                "rule_status": rs["status"], "rule_triggers": sorted({o["trigger"] for o in rs["occurrences"]}),
                "verifier_aligned": al is not None, "verifier_status": (al or {}).get("status"),
                "verifier_depicted": (al or {}).get("depicted"), "verifier_condition": (al or {}).get("name"),
                "technique_gate": tech, "technique_term": tech_term,
                "match_strength": match_strength(rs),
                "final_status": status, "final_depicted": depicted, "keep": keep, "decision": why,
                "match_method": ("L" if any(o["phrase"] in curated and o["phrase"] not in added for o in rs["occurrences"])
                                 or not rs["occurrences"]
                                 else "L_revision_added" if any(o["phrase"] in added for o in rs["occurrences"])
                                 else "S_umls_synonym"),
            })
    with (out_dir / "assignments.jsonl").open("w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # ── before/after per topic ──
    before, after = Counter(), Counter()
    for r in rows:
        before[r["schedule_entry_id"]] += 1
        after[r["schedule_entry_id"]] += r["keep"]
    per_topic = []
    for t in topics:
        sid = t["schedule_entry_id"]
        per_topic.append({"schedule_entry_id": sid, "division": t["division"], "keyword": t["keyword"],
                          "n_before": before[sid], "n_after": after[sid]})
    with (out_dir / "topic_before_after.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(per_topic[0]))
        w.writeheader()
        w.writerows(per_topic)
    ns = sorted(p["n_after"] for p in per_topic)
    summary = {
        "verifier": args.verifier, "include_suspected": S3.get("include_suspected"),
        "keep_depicted": S3.get("keep_depicted"),
        "concept_expansion": S3.get("concept_expansion", "none"),
        "kept_by_match_method": Counter(r["match_method"] for r in rows if r["keep"]),
        "depicted_false_requires_case_not_shown": bool(S3.get("depicted_false_requires_case_not_shown")),
        "candidates": len(rows), "kept": sum(r["keep"] for r in rows),
        "removed_by_reason": Counter(r["decision"].split("|", 1)[1] for r in rows if not r["keep"]),
        "decision_source": Counter(r["decision"].split("|")[0] for r in rows),
        "rule_status": Counter(r["rule_status"] for r in rows),
        "kept_by_match_strength": Counter(r["match_strength"] for r in rows if r["keep"]),
        "topics_covered_before": sum(p["n_before"] > 0 for p in per_topic),
        "topics_covered_after": sum(p["n_after"] > 0 for p in per_topic),
        "topics_zero_after": [f"{p['division']}: {p['keyword']}" for p in per_topic if p["n_after"] == 0],
        "median_after": (ns[len(ns) // 2] + ns[(len(ns) - 1) // 2]) / 2,
    }

    # ── regression on dev labels (263 mapping assignments) ──
    mech = {r["case_id"]: r for r in csv.DictReader(
        open(ROOT / "data/dev_labels/mapping_unsupported_42_mechanism.csv", encoding="utf-8-sig"))}
    keep_idx = defaultdict(bool)
    present = set()
    for r in rows:
        present.add((r["case_id"], r["schedule_entry_id"]))
        keep_idx[(r["case_id"], r["schedule_entry_id"])] |= r["keep"]
    reg = Counter()
    detail = []
    for lab in csv.DictReader(open(ROOT / "data/dev_labels/mapping_labels_263.csv")):
        sids = json.loads(lab["schedule_entry_ids"])
        cid = lab["case_id"]
        if not any((cid, s) in present for s in sids):
            state = "not_in_step1_candidates"
        else:
            state = "kept" if any(keep_idx[(cid, s)] for s in sids) else "removed"
        sup = lab["label_supported"] == "1"
        m = mech.get(cid, {}).get("mechanism", "") if not sup else ""
        reg[("supported" if sup else f"unsupported:{m}", state)] += 1
        detail.append({"case_id": cid, "group_keyword": lab["group_keyword"], "label_supported": int(sup),
                       "mechanism": m, "state": state})
    with (out_dir / "regression_263.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(detail[0]))
        w.writeheader()
        w.writerows(detail)
    c_cases = [d for d in detail if d["mechanism"] == "differential_background"]
    summary["regression"] = {f"{k[0]} → {k[1]}": v for k, v in sorted(reg.items())}
    summary["regression_differential_background_6"] = {d["case_id"]: d["state"] for d in c_cases}
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=dict))
    print(json.dumps(summary, indent=2, ensure_ascii=False, default=dict))


if __name__ == "__main__":
    main()
