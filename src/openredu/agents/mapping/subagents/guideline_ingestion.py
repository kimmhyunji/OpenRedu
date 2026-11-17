"""
GuidelineIngestionSubagent: converts guideline source files to standard 4-column CSV.

Supported formats: .pdf, .docx, .doc, .xlsx, .xls, .csv

Standard output CSV columns:
  canonical_name  — clinical condition or topic name
  category        — priority level or clinical category (e.g. "Cat1", "Level_I", "Chest")
  specialty       — radiology subspecialty (e.g. "Breast Radiology", "Neuroradiology")
  source_type     — item type ("must_see_diagnosis" | "condition" | "objective")

For CSV/Excel: direct column mapping (no LLM needed).
For PDF/Word:  chunked text → LLM structuring → deduplicated output.

is_llm = True because PDF/Word path uses LLM.
"""
import csv
import json
import logging
import re
from pathlib import Path
from typing import Optional

from openredu.core.base import Subagent
from openredu.config import PATHS, MODELS

log = logging.getLogger(__name__)

SUPPORTED_FORMATS = {".pdf", ".docx", ".doc", ".xlsx", ".xls", ".csv"}

# Standard output columns
OUTPUT_COLUMNS = ["canonical_name", "category", "specialty", "source_type"]

_STRUCTURING_SYSTEM = """You are a medical education curriculum analyst.
Extract all distinct clinical conditions, diagnoses, or topics from the provided radiology training guideline text.
For each item, identify:
1. canonical_name: The standard clinical name as written in the source
2. category: The clinical category or body system (e.g. "Neoplastic", "Vascular", "Infectious", "Cat1", "Level_I")
3. specialty: The radiology subspecialty (e.g. "Breast Radiology", "Neuroradiology", "Chest Radiology")
4. source_type: One of "must_see_diagnosis" | "condition" | "objective"

Return a JSON array. Each element:
{"canonical_name": str, "category": str, "specialty": str, "source_type": str}

Extract ONLY clinically specific items. Do NOT extract administrative text, scheduling info, or structural headers."""

_STRUCTURING_USER = (
    "Extract all clinical conditions and diagnoses from this radiology curriculum text.\n"
    "Source: {source_filename}\n\n"
    "Text:\n{chunk_text}\n\n"
    "Return JSON array only."
)


# ── Column mappings for known guideline CSVs ──────────────────────────────────

_APDR_MAPPING = {
    "canonical_name": "canonical_keyword",
    "specialty":      "division",
    "source_type":    "source_type",
    "category":       None,  # not available in APDR; derive from division
}

class GuidelineIngestionSubagent(Subagent):
    """Converts raw guideline files to standard 4-column CSV."""
    name = "GuidelineIngestionSubagent"
    is_llm = True

    def run(
        self,
        source_path: Path,
        source_label: str,
        force: bool = False,
    ) -> Path:
        """
        Convert source_path to standard CSV.

        Returns path to output CSV.
        Idempotent: skips if output already exists and force=False.
        """
        source_path = Path(source_path)
        suffix = source_path.suffix.lower()

        if suffix not in SUPPORTED_FORMATS:
            raise ValueError(
                f"Unsupported format: {suffix}. "
                f"Supported: {', '.join(sorted(SUPPORTED_FORMATS))}"
            )

        out_path = PATHS["guidelines"] / f"structured_{source_label}.csv"

        if out_path.exists() and not force:
            log.info(f"Output already exists (use --force to overwrite): {out_path}")
            return out_path

        log.info(f"Ingesting {source_path} as {source_label} → {out_path}")

        if suffix == ".csv":
            rows = self._ingest_csv(source_path, source_label)
        elif suffix in (".xlsx", ".xls"):
            rows = self._ingest_excel(source_path, source_label)
        elif suffix in (".docx", ".doc"):
            rows = self._ingest_word(source_path)
        elif suffix == ".pdf":
            rows = self._ingest_pdf(source_path)
        else:
            raise ValueError(f"Unhandled format: {suffix}")

        # Deduplicate by canonical_name (case-insensitive)
        seen = set()
        unique_rows = []
        for row in rows:
            key = (row.get("canonical_name", "") or "").strip().lower()
            if key and key not in seen:
                seen.add(key)
                unique_rows.append(row)

        with open(out_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(unique_rows)

        log.info(f"Wrote {len(unique_rows)} rows → {out_path}")
        return out_path

    # ── CSV ingestion ─────────────────────────────────────────────────────────

    def _ingest_csv(self, path: Path, label: str) -> list:
        """Map existing CSV columns to standard schema."""
        rows = []
        with open(path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames or []

            # Detect known guideline types
            if "canonical_keyword" in headers and "division" in headers:
                mapping = _APDR_MAPPING
                fixed_source_type = None
                for row in reader:
                    if row.get("source_type") != "must_see_diagnosis":
                        continue
                    rows.append({
                        "canonical_name": (row.get("canonical_keyword") or "").strip(),
                        "category":       (row.get("division") or "").strip(),
                        "specialty":      (row.get("division") or "").strip(),
                        "source_type":    "must_see_diagnosis",
                    })

            else:
                # Generic CSV: try to map any column named "canonical_name" etc.
                for row in reader:
                    rows.append({
                        "canonical_name": (row.get("canonical_name") or row.get("name", "")).strip(),
                        "category":       (row.get("category") or "").strip(),
                        "specialty":      (row.get("specialty") or "").strip(),
                        "source_type":    (row.get("source_type") or "condition").strip(),
                    })

        return [r for r in rows if r.get("canonical_name")]

    # ── Excel ingestion ───────────────────────────────────────────────────────

    def _ingest_excel(self, path: Path, label: str) -> list:
        """Read Excel file and map columns to standard schema."""
        try:
            import openpyxl
        except ImportError:
            raise ImportError("openpyxl required for Excel ingestion: pip install openpyxl")

        wb = openpyxl.load_workbook(path)
        ws = wb.active
        headers = [cell.value for cell in ws[1]]

        raw_rows = []
        for row in ws.iter_rows(min_row=2, values_only=True):
            d = {str(h).strip(): str(v).strip() if v is not None else ""
                 for h, v in zip(headers, row) if h}
            if any(d.values()):
                raw_rows.append(d)

        # Create a temp CSV-like structure and reuse _ingest_csv logic
        import tempfile, os
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False,
                                         newline='', encoding='utf-8') as tmp:
            writer = csv.DictWriter(tmp, fieldnames=headers)
            writer.writeheader()
            writer.writerows(raw_rows)
            tmp_path = tmp.name

        try:
            return self._ingest_csv(Path(tmp_path), label)
        finally:
            os.unlink(tmp_path)

    # ── Word ingestion ────────────────────────────────────────────────────────

    def _ingest_word(self, path: Path) -> list:
        """Extract text from Word document and structure via LLM."""
        try:
            import docx
        except ImportError:
            raise ImportError("python-docx required: pip install python-docx")

        doc = docx.Document(path)
        text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        return self._structure_with_llm(text, path.name)

    # ── PDF ingestion ─────────────────────────────────────────────────────────

    def _ingest_pdf(self, path: Path) -> list:
        """Extract text from PDF and structure via LLM."""
        try:
            import pdfplumber
        except ImportError:
            raise ImportError("pdfplumber required: pip install pdfplumber")

        pages = []
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    pages.append(t)
        text = "\n".join(pages)
        return self._structure_with_llm(text, path.name)

    # ── LLM structuring ───────────────────────────────────────────────────────

    def _structure_with_llm(self, text: str, source_filename: str) -> list:
        """
        Split text into 2000-char chunks with 200-char overlap,
        call LLM on each chunk, deduplicate results.
        """
        from openredu.core.llm import _call_bedrock_anthropic

        chunk_size = 2000
        overlap    = 200
        chunks = []
        i = 0
        while i < len(text):
            chunks.append(text[i:i + chunk_size])
            i += chunk_size - overlap

        log.info(f"LLM structuring: {len(chunks)} chunks from {source_filename}")
        all_rows = []

        for j, chunk in enumerate(chunks, 1):
            user_msg = _STRUCTURING_USER.format(
                source_filename=source_filename,
                chunk_text=chunk,
            )
            try:
                import time; time.sleep(1)
                raw = _call_bedrock_anthropic(
                    model=MODELS["guideline_structuring"],
                    user_msg=user_msg,
                    system_prompt=_STRUCTURING_SYSTEM,
                    max_tokens=1000,
                )
                # raw might be a list or dict; normalize to list
                if isinstance(raw, dict):
                    items = [raw]
                elif isinstance(raw, list):
                    items = raw
                else:
                    items = []

                for item in items:
                    if isinstance(item, dict) and item.get("canonical_name"):
                        all_rows.append({
                            "canonical_name": str(item.get("canonical_name", "")).strip(),
                            "category":       str(item.get("category", "")).strip(),
                            "specialty":      str(item.get("specialty", "")).strip(),
                            "source_type":    str(item.get("source_type", "condition")).strip(),
                        })
                log.debug(f"Chunk {j}/{len(chunks)}: {len(items)} items")
            except Exception as e:
                log.warning(f"LLM structuring error on chunk {j}: {e}")

        return [r for r in all_rows if r.get("canonical_name")]
