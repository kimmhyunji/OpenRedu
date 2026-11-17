#!/usr/bin/env python3
"""Step 4c  (synonym-aware matching): fetch English UMLS synonyms (atoms) for every
topic-phrase CUI and for their direct narrower concepts, then build cleaned synonym phrase
lists per schedule entry.

Rationale: UMLS supplies synonyms that a hand-curated phrase list misses. Expanding topic phrases with UMLS strings and matching them lexically in the case
diagnosis/finding avoids depending on case-side CUIs (whose normalization is unreliable). Free UTS API, no LLM. Cached and resumable; errors never print the URL (key).

Cleaning rules (conservative, to avoid ambiguous strings):
  - English, non-suppressible atoms only; lowercase; "X, Y" inverted to "Y X"
  - drop strings with NOS / NEC / unspecified / "(disorder)"-style tags removed
  - drop strings shorter than 4 characters or all-uppercase abbreviations of <= 4 letters
  - drop strings with more than 6 words, digits-only, or containing [ ] { } < >
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

import requests
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).parent))
import safe_logging  # noqa: E402,F401  (masks UMLS apiKey/ticket in log records)
CFG = yaml.safe_load((ROOT / "config/pipeline.yaml").read_text())
S4 = CFG["step4_matching_compare"]
SNAP = ROOT / CFG["snapshot_dir"]
OUT = ROOT / "data/outputs/step4"
TAG = re.compile(r"\s*\((disorder|finding|morphologic abnormality|procedure|body structure|situation|"
                 r"diagnosis|qualifier value|observable entity|regime/therapy|substance|navigational concept)\)\s*$", re.I)


def atoms(cui: str, key: str) -> list[str] | None:
    names, page = [], 1
    while True:
        r = None
        for attempt in range(5):
            try:
                r = requests.get(f"https://uts-ws.nlm.nih.gov/rest/content/current/CUI/{cui}/atoms",
                                 params={"apiKey": key, "language": "ENG", "pageSize": 200, "pageNumber": page},
                                 timeout=60)
                if r.status_code < 500:
                    break
            except requests.RequestException:
                r = None
            time.sleep(2 ** attempt)
        if r is None or r.status_code >= 500:
            return None
        if r.status_code == 404:
            return names
        if r.status_code != 200:
            return None
        js = r.json()
        names += [a.get("name", "") for a in js.get("result", [])]
        if page >= js.get("pageCount", 1):
            return names
        page += 1


def clean(name: str) -> str | None:
    s = TAG.sub("", name).strip()
    if re.search(r"[\[\]{}<>;]|\bNOS\b|\bNEC\b|unspecified|\bnot otherwise\b", s, re.I):
        return None                                 # ';' = index-style permuted strings
    if "," in s:
        parts = [p.strip() for p in s.split(",")]
        if len(parts) == 2 and all(parts):
            s = f"{parts[1]} {parts[0]}"
        else:
            return None
    if re.search(r"\b(protein|proteins|gene|genes|agents?|antibod\w*|receptors?|drugs?|inhibitors?|"
                 r"vaccines?|measurement|assay|kit|product)\b", s, re.I):   # non-disease concepts
        return None
    if re.fullmatch(r"[A-Z0-9\-]{1,4}", s):          # short abbreviations are ambiguous
        return None
    s = re.sub(r"\s+", " ", s.lower()).strip()
    if len(s) < 4 or len(s.split()) > 6 or s.replace(" ", "").isdigit():
        return None
    return s


def _toks(x: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", x.lower()) if len(w) > 2}


def well_resolved(phrase: str, name: str) -> bool:
    """Expand only from topic phrases whose CUI clearly denotes the phrase (guards against
    resolver errors such as 'free fluid' -> CSF flow, 'umbilical cord' -> cord blood transplant)."""
    a, b = _toks(phrase), _toks(name)
    if not a or not b:
        return False
    # The concept must not be broader than the phrase: every phrase token must appear in the
    # concept name (e.g. 'lobar pneumonia' -> 'Pneumonia' is rejected as a generalization).
    return phrase.lower() in name.lower() or a <= b


def dedupe_permutations(candidates: list[str], curated: set[str]) -> set[str]:
    """Keep one word order per token multiset: drop orderings of a curated phrase, otherwise keep
    the most frequent ordering among the raw atoms (ties: alphabetical). Prevents inverted index
    strings ('aneurysm intracranial') that only match across concatenated field boundaries."""
    from collections import Counter, defaultdict
    cur_keys = {tuple(sorted(c.split())) for c in curated}
    freq = Counter(candidates)
    groups = defaultdict(list)
    for c in freq:
        groups[tuple(sorted(c.split()))].append(c)
    keep = set()
    for key, variants in groups.items():
        if key in cur_keys:
            continue
        keep.add(sorted(variants, key=lambda v: (-freq[v], v))[0])
    return keep


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--narrower", action="store_true", help="also fetch atoms of direct narrower concepts")
    args = ap.parse_args()
    from openredu.config import UMLS_API_KEY
    pc = json.loads((ROOT / S4["topic_cui_file"]).read_text())["phrases"]
    rels = json.loads((ROOT / S4["relations_file"]).read_text())
    topic_cuis = sorted({v["cui"] for v in pc.values() if v.get("cui")})
    narrow = {c: sorted({r["related_cui"] for r in rels.get(c, []) if r["label"] in S4["narrower_labels"]})
              for c in topic_cuis}
    cache_p = OUT / "cui_atoms_cache.json"
    cache = json.loads(cache_p.read_text()) if cache_p.exists() else {}
    good_cuis = {v["cui"] for p, v in pc.items() if v.get("cui") and well_resolved(p, v.get("name", ""))}
    want = list(topic_cuis) + (sorted({n for c, v in narrow.items() if c in good_cuis for n in v})
                               if args.narrower else [])
    todo = [c for c in want if c not in cache]
    print(f"{len(want)} CUIs, {len(todo)} to fetch", flush=True)
    for i, c in enumerate(todo, 1):
        a = atoms(c, UMLS_API_KEY)
        if a is not None:
            cache[c] = a
        if i % 100 == 0:
            cache_p.write_text(json.dumps(cache, ensure_ascii=False))
            print(f"  {i}/{len(todo)}", flush=True)
    cache_p.write_text(json.dumps(cache, ensure_ascii=False))

    entries = json.loads((SNAP / CFG["v1"]["topic_phrases"]).read_text())["entries"]
    syn_out = {}
    for e in entries:
        own = {p.lower().strip() for p in e["phrases"]}
        good = [p for p in e["phrases"] if pc.get(p.lower().strip(), {}).get("cui")
                and well_resolved(p, pc[p.lower().strip()].get("name", ""))]
        cuis = {pc[p.lower().strip()]["cui"] for p in good}
        raw = [x for c in cuis for x in map(clean, cache.get(c, [])) if x]
        syn = dedupe_permutations(raw, own)
        nar = set()
        if args.narrower:
            rawn = [x for c in cuis for n in narrow.get(c, []) for x in map(clean, cache.get(n, [])) if x]
            nar = dedupe_permutations(rawn, own | syn)
        syn_out[e["schedule_entry_id"]] = {"curated": sorted(own), "expanded_from": sorted(good),
                                          "umls_synonyms": sorted(syn - own),
                                          "umls_narrower": sorted(nar - own - syn)}
    (OUT / "topic_synonym_phrases.json").write_text(json.dumps(syn_out, indent=1, ensure_ascii=False))
    n_syn = sum(len(v["umls_synonyms"]) for v in syn_out.values())
    n_nar = sum(len(v["umls_narrower"]) for v in syn_out.values())
    print(json.dumps({"entries": len(syn_out), "added_synonym_phrases": n_syn, "added_narrower_phrases": n_nar,
                      "atoms_cached_cuis": len(cache)}, indent=2))


if __name__ == "__main__":
    main()
