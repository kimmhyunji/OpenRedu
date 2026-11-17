#!/usr/bin/env python3
"""Step 1: fetch article-type metadata for every source article of the v1 corpus.

For each PMCID: JATS <article article-type>, article-categories subjects
(heading and others), and PubMed publication types (via PMID). NCBI E-utilities
only; no LLM. Results are cached per PMCID so the run is resumable.

Output: data/outputs/step1/article_meta.jsonl (one row per PMCID)
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

import requests
import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
CFG = yaml.safe_load((ROOT / "config/pipeline.yaml").read_text())
SNAP = ROOT / CFG["snapshot_dir"]
OUT = ROOT / "data/outputs/step1/article_meta.jsonl"
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
IDCONV = "https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/"

load_dotenv(ROOT / ".env")
KEY = os.environ.get("ENTREZ_API_KEY", "")
EMAIL = os.environ.get("ENTREZ_EMAIL", "")
DELAY = 0.12 if KEY else 0.4


def get(url: str, params: dict, tries: int = 5) -> requests.Response:
    params = {**params, "api_key": KEY, "email": EMAIL, "tool": "openredu"}
    for attempt in range(tries):
        try:
            time.sleep(DELAY)
            r = requests.post(url, data=params, timeout=120) if "eutils" in url else \
                requests.get(url, params=params, timeout=120)
            if r.status_code == 200:
                return r
        except requests.RequestException:
            pass
        time.sleep(2 ** attempt)
    raise RuntimeError(f"request failed: {url}")


def text(el) -> str:
    return " ".join("".join(el.itertext()).split()) if el is not None else ""


def parse_pmc(xml: str) -> dict[str, dict]:
    root = ET.fromstring(xml)
    out = {}
    for art in root.iter("article"):
        front = art.find("front")
        meta = front.find("article-meta") if front is not None else None
        if meta is None:
            continue
        pmcid = ""
        for aid in meta.findall("article-id"):
            t, v = aid.get("pub-id-type"), (aid.text or "").strip()
            if t in ("pmcid",) and v:
                pmcid = v if v.startswith("PMC") else f"PMC{v}"
            elif t in ("pmc", "pmcaid") and v and not pmcid:
                pmcid = v if v.startswith("PMC") else f"PMC{v}"
        headings, subjects = [], []
        cats = meta.find("article-categories")
        if cats is not None:
            for sg in cats.iter("subj-group"):
                for s in sg.findall("subject"):
                    (headings if sg.get("subj-group-type") == "heading" else subjects).append(text(s))
        out[pmcid] = {
            "pmcid": pmcid,
            "jats_article_type": art.get("article-type", ""),
            "subject_headings": headings,
            "subjects_other": subjects,
            "jats_title": text(meta.find("title-group/article-title")),
            "journal": text(front.find("journal-meta/journal-title-group/journal-title")),
        }
    return out


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default=None, help="other corpus jsonl (default: v1 snapshot corpus); results append to the same cache")
    ap.add_argument("--out", default=None, help="isolated metadata cache path (default: Step 1 shared cache)")
    args = ap.parse_args()
    out = ROOT / args.out if args.out else OUT
    out.parent.mkdir(parents=True, exist_ok=True)
    src = ROOT / args.corpus if args.corpus else SNAP / CFG["v1"]["corpus"]
    pmcids = sorted({json.loads(l)["pmcid"] for l in src.open()})
    done = {}
    if out.exists():
        for l in out.open():
            d = json.loads(l)
            done[d["pmcid"]] = d
    todo = [p for p in pmcids if p not in done]
    print(f"{len(pmcids)} PMCIDs, {len(done)} cached, {len(todo)} to fetch", flush=True)

    fetched_at = datetime.now(timezone.utc).isoformat()
    with out.open("a") as f:
        for i in range(0, len(todo), 100):
            batch = todo[i:i + 100]
            pmc = parse_pmc(get(f"{EUTILS}/efetch.fcgi", {
                "db": "pmc", "id": ",".join(p[3:] for p in batch), "retmode": "xml"}).text)
            conv = get(IDCONV, {"ids": ",".join(batch), "format": "json"}).json()["records"]
            pmid_of = {r["pmcid"]: str(r["pmid"]) for r in conv if r.get("pmid")}
            pubtypes = {}
            pmids = [pmid_of[p] for p in batch if p in pmid_of]
            if pmids:
                res = get(f"{EUTILS}/esummary.fcgi", {"db": "pubmed", "id": ",".join(pmids),
                                                      "retmode": "json"}).json()["result"]
                pubtypes = {u: res[u].get("pubtype", []) for u in res.get("uids", [])}
            for p in batch:
                row = pmc.get(p, {"pmcid": p, "jats_article_type": "", "subject_headings": [],
                                  "subjects_other": [], "jats_title": "", "journal": "",
                                  "fetch_error": "not_in_efetch_response"})
                row["pmid"] = pmid_of.get(p, "")
                row["pubmed_pubtypes"] = pubtypes.get(pmid_of.get(p, ""), [])
                row["fetched_at"] = fetched_at
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
            print(f"  {min(i + 100, len(todo))}/{len(todo)}", flush=True)


if __name__ == "__main__":
    sys.exit(main())
