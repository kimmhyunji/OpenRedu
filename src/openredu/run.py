"""
OpenRedu CLI entry point.

Usage examples:
  # Paper-reproducible run (scratch + date range)
  python -m openredu.run pipeline --scratch --year-start 2020 --year-end 2026 \\
    --modality CT_CHEST MRI_BRAIN

  # Dev shortcut (skip PMC re-download)
  python -m openredu.run pipeline --from-cache --modality CXR --limit 10

  # Status check
  python -m openredu.run status

  # Ingest a guideline file
  python -m openredu.run ingest --source data/guidelines/<guideline_file> --label <name>

NOTE on --from-cache:
  Dev shortcut that reads earlier extraction records (phase2_cases_*.jsonl) from OPENREDU_PHASE2_CACHE_DIR.
  Classification, extraction, and mapping all run fresh.
  NOT suitable for final paper numbers — use --scratch with date range for those.
"""
import argparse
import json
import logging
import sys
from pathlib import Path

# Ensure openredu package is importable when run as script
sys.path.insert(0, str(Path(__file__).parent.parent))

from openredu.config import PATHS, MODELS, TARGET_MODALITIES, GAP_FILL_MODALITIES

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)


# ── Subcommand handlers ───────────────────────────────────────────────────────

def cmd_pipeline(args):
    from openredu.coordinator import run_pipeline

    modalities = args.modality or TARGET_MODALITIES
    for mod in modalities:
        if mod not in TARGET_MODALITIES:
            log.error(f"Unknown modality: {mod}. Available: {TARGET_MODALITIES}")
            sys.exit(1)

    from_cache = not args.scratch

    for mod in modalities:
        log.info(f"=== Running pipeline for {mod} ===")
        stats = run_pipeline(
            modality=mod,
            limit=args.limit,
            from_cache=from_cache,
            dry_run=args.dry_run,
            year_start=args.year_start,
            year_end=args.year_end,
        )
        log.info(f"[{mod}] {stats}")


def cmd_remap(args):
    """
    Re-run MappingMasterAgent only, reading from extracted checkpoint.
    Use this after build-index to activate Path 2 (synonym) + Path 3 (CUI) matching.
    Does NOT re-run Curation.
    """
    from openredu.coordinator import remap_from_checkpoint
    modalities = args.modality or TARGET_MODALITIES
    for mod in modalities:
        if mod not in TARGET_MODALITIES:
            log.error(f"Unknown modality: {mod}")
            sys.exit(1)
        log.info(f"=== Re-mapping [{mod}] ===")
        stats = remap_from_checkpoint(mod, dry_run=args.dry_run)
        log.info(f"[{mod}] {stats}")


def cmd_map(args):
    """Run only the mapping phase on already-curated cases."""
    from openredu.coordinator import _get_mapping_agent, _load_already_done
    from openredu.core.state import CaseState

    modalities = args.modality or TARGET_MODALITIES
    mapping_agent = _get_mapping_agent()

    for mod in modalities:
        path = PATHS["processed"] / f"cases_{mod.lower()}.jsonl"
        if not path.exists():
            log.warning(f"No processed cases for {mod}: {path}")
            continue

        lines = [l for l in path.read_text().splitlines() if l.strip()]
        log.info(f"[{mod}] Re-mapping {len(lines)} cases...")
        for line in lines:
            state = CaseState.from_dict(json.loads(line))
            if state.status in ("extracted",):
                state = mapping_agent.run(state)
        log.info(f"[{mod}] Done")


def cmd_ingest(args):
    from openredu.agents.mapping.subagents.guideline_ingestion import GuidelineIngestionSubagent
    sub = GuidelineIngestionSubagent()
    out = sub.run(
        source_path=Path(args.source),
        source_label=args.label,
        force=args.force,
    )
    log.info(f"Ingestion complete: {out}")


def cmd_build_index(args):
    """
    Build final_synonym_index.json from any guideline CSV.

    Input:  --guideline PATH  (optional)
              Standard 4-column CSV from GuidelineIngestionSubagent, or raw APDR CSV.
              If omitted, auto-detects structured_apdr.csv or falls back to raw APDR CSV.

    Pipeline: guideline keywords → Layer1(MeSH) → Layer2(SNOMED) → Layer3(LLM+UMLS) → merge
    Output:  data/guidelines/final_synonym_index.json
    Idempotent: resumes from per-layer checkpoints if interrupted.

    Example:
      # Build from raw APDR (default)
      python -m openredu.run build-index

      # Build from any other guideline after ingestion
      python -m openredu.run ingest --source <guideline_file> --label <name>
      python -m openredu.run build-index --guideline data/guidelines/structured_<name>.csv
    """
    from pathlib import Path as _Path
    from openredu.tools.index_builder import build_index
    guideline_csv = _Path(args.guideline) if getattr(args, 'guideline', None) else None
    final = build_index(guideline_csv)
    log.info(f"build-index complete: {len(final)} keywords in final_synonym_index.json")


def cmd_status(args):
    """Show counts from all queue files."""
    print(f"{'Modality':<15} {'processed':>10} {'failed':>8} {'rejected':>9} {'unmapped':>9}")
    print("-" * 55)

    for mod in TARGET_MODALITIES:
        processed = _count_jsonl(PATHS["processed"] / f"cases_{mod.lower()}.jsonl")
        failed    = _count_jsonl(PATHS["failed"]    / f"failed_{mod.lower()}.jsonl")
        rejected  = _count_jsonl(PATHS["failed"]    / f"rejected_{mod.lower()}.jsonl")
        unmapped  = _count_jsonl(PATHS["unmapped"]  / f"unmapped_{mod.lower()}.jsonl")
        print(f"{mod:<15} {processed:>10} {failed:>8} {rejected:>9} {unmapped:>9}")


def cmd_manifest(args):
    """Show most recent manifest for each modality."""
    for mod in TARGET_MODALITIES:
        manifests = sorted(PATHS["manifests"].glob(f"manifest_{mod.lower()}_*.json"))
        if manifests:
            m = json.loads(manifests[-1].read_text())
            print(f"[{mod}] {m['run_id']} @ {m['timestamp'][:19]} — {m['counts']}")
        else:
            print(f"[{mod}] no manifest")


def cmd_version(args):
    print("OpenRedu — Model configuration:")
    for key, model_id in MODELS.items():
        print(f"  {key:<30} {model_id}")


def cmd_coverage_gaps(args):
    """
    Report APDR curriculum coverage gaps in the current final corpus.
    mapping_coverage_revision: shows which of the 397 APDR must_see_diagnosis
    topics have zero mapped cases, grouped by APDR division.
    """
    from openredu.coordinator import compute_coverage_gaps
    from collections import defaultdict

    corpus_dirs = ["final", "processed"]
    if args.include_bypass:
        corpus_dirs.append("gap_fill_bypass")
    result = compute_coverage_gaps(corpus_dirs=corpus_dirs)
    covered   = len(result["covered_topics"])
    total_col = result["collectible"]
    pct       = result["coverage_pct"]

    print(f"\n=== APDR Coverage (collectible topics only) ===")
    print(f"Corpus  : {' + '.join(result['corpus_stats']['corpus_dirs'])}")
    print(f"Cases   : {result['corpus_stats']['active_cases']:,} active "
          f"({result['corpus_stats']['unique_cases']:,} unique before exclusions)")
    print(f"Covered : {covered}/{total_col} ({pct:.1%})")
    print(f"Gaps    : {len(result['uncovered_topics'])}")
    print(f"Normal-study exclusions: {len(result['excluded_normal'])}")

    by_div = defaultdict(list)
    for t in result["uncovered_topics"]:
        by_div[t["specialty"]].append(t["raw_keyword"])

    print("\nUncovered by division:")
    for div in sorted(by_div):
        print(f"  [{div}] ({len(by_div[div])})")
        for kw in sorted(by_div[div]):
            print(f"    - {kw}")

    print(f"\nNormal-study exclusions (not counted in denominator):")
    for t in result["excluded_normal"]:
        print(f"  - {t['raw_keyword']}")


def cmd_gap_fill(args):
    """
    Phase 2: curriculum-driven supplemental retrieval.
    Runs the identical pipeline for gap-fill modalities.
    Use --dry-run to preview coverage gaps without hitting PMC.
    """
    from openredu.coordinator import run_gap_fill_pipeline, compute_coverage_gaps
    from openredu.config import GAP_FILL_MODALITIES

    modalities = args.modality or None  # None → all gap-fill modalities

    if args.dry_run:
        print("\n=== GAP-FILL DRY RUN ===")
        result = compute_coverage_gaps()
        print(f"Current coverage: {result['coverage_pct']:.1%} "
              f"({len(result['covered_topics'])}/{result['collectible']} topics)")
        print(f"Uncovered topics: {len(result['uncovered_topics'])}")
        print(f"\nWould run modalities: {modalities or GAP_FILL_MODALITIES}")
        print("\nUncovered topics to target:")
        for t in result["uncovered_topics"]:
            print(f"  [{t['specialty']}] {t['raw_keyword']}")
        return

    stats = run_gap_fill_pipeline(
        modalities=modalities,
        year_start=args.year_start,
        year_end=args.year_end,
        limit=args.limit,
        dry_run=False,
    )

    print("\n=== GAP-FILL RESULTS ===")
    for mod, s in stats.items():
        if not mod.startswith("_"):
            print(f"  {mod}: {s}")
    before = stats.get("_coverage_before", 0)
    after  = stats.get("_coverage_after", 0)
    print(f"\nCoverage: {before:.1%} → {after:.1%}")
    print(f"Uncovered: {stats.get('_uncovered_before','?')} → {stats.get('_uncovered_after','?')}")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _count_jsonl(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for l in path.read_text().splitlines() if l.strip())


# ── Argument parser ───────────────────────────────────────────────────────────

def build_parser():
    parser = argparse.ArgumentParser(
        prog="run.py",
        description="OpenRedu: agentic radiology case curation and curriculum mapping",
    )
    sub = parser.add_subparsers(dest="command")

    # pipeline
    p = sub.add_parser("pipeline", help="Run full curation + mapping pipeline")
    p.add_argument("--modality", nargs="+", default=None,
                   metavar="MOD", help=f"Modalities ({', '.join(TARGET_MODALITIES)})")
    p.add_argument("--from-cache", action="store_true",
                   help="Dev shortcut: skip PMC API, use existing phase2 JSONL")
    p.add_argument("--scratch",    action="store_true",
                   help="Full scratch run from PMC (required for paper numbers)")
    p.add_argument("--year-start", type=int, default=None)
    p.add_argument("--year-end",   type=int, default=None)
    p.add_argument("--limit",      type=int, default=None, help="Max cases per modality")
    p.add_argument("--dry-run",    action="store_true")

    # remap
    p = sub.add_parser("remap",
                       help="Re-run mapping from extracted checkpoint (after build-index)")
    p.add_argument("--modality", nargs="+", default=None,
                   metavar="MOD", help="Modalities to re-map (default: all 10)")
    p.add_argument("--dry-run", action="store_true")

    # map
    p = sub.add_parser("map", help="Run mapping only on existing processed cases")
    p.add_argument("--modality", nargs="+", default=None)

    # ingest
    p = sub.add_parser("ingest", help="Ingest guideline file to standard CSV")
    p.add_argument("--source", required=True, help="Path to guideline file")
    p.add_argument("--label",  required=True, help="Short output label (e.g. 'apdr')")
    p.add_argument("--force",  action="store_true", help="Overwrite existing output")

    # build-index
    p = sub.add_parser("build-index",
                       help="Build final_synonym_index.json from any guideline CSV")
    p.add_argument("--guideline", default=None,
                   help="Path to standard 4-column CSV (from `ingest`) or raw APDR CSV. "
                        "Default: auto-detect structured_apdr.csv or raw APDR CSV")

    # status
    sub.add_parser("status", help="Show queue counts per modality")

    # manifest
    sub.add_parser("manifest", help="Show latest run manifests")

    # coverage-gaps
    p = sub.add_parser("coverage-gaps",
                       help="Show APDR curriculum coverage gaps in current corpus")
    p.add_argument(
        "--include-bypass",
        action="store_true",
        help="Include provisional gap_fill_bypass cases in addition to final + processed",
    )

    # gap-fill
    p = sub.add_parser(
        "gap-fill",
        help=(
            "Phase 2: curriculum-driven supplemental retrieval. "
            "Runs the identical curation+mapping pipeline for uncovered APDR topics, "
            "using targeted PMC queries per gap-fill modality."
        ),
    )
    p.add_argument("--modality", nargs="+", default=None,
                   metavar="MOD",
                   help=f"Gap-fill modalities to run (default: all). "
                        f"Available: {', '.join(GAP_FILL_MODALITIES)}")
    p.add_argument("--year-start", type=int, default=2020)
    p.add_argument("--year-end",   type=int, default=2026)
    p.add_argument("--limit",      type=int, default=None,
                   help="Max articles per modality (smoke-test)")
    p.add_argument("--dry-run",    action="store_true",
                   help="Show coverage gaps and planned queries; skip PMC API calls")

    # version
    sub.add_parser("version", help="Show model IDs")
    parser.add_argument("--version", action="store_true")

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if getattr(args, 'version', False) or args.command == "version":
        cmd_version(args)
        return

    if not args.command:
        parser.print_help()
        sys.exit(1)

    handlers = {
        "pipeline":    cmd_pipeline,
        "remap":       cmd_remap,
        "map":         cmd_map,
        "ingest":      cmd_ingest,
        "build-index":   cmd_build_index,
        "status":        cmd_status,
        "manifest":      cmd_manifest,
        "coverage-gaps": cmd_coverage_gaps,
        "gap-fill":      cmd_gap_fill,
    }
    handlers[args.command](args)


if __name__ == "__main__":
    main()
