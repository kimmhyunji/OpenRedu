"""
Image download tools: CDN URL discovery and image file download.

Adapted from the earlier prototype extraction script.
"""
import logging
import re
import requests
import tempfile
from pathlib import Path
from typing import Optional
from urllib.parse import urlsplit

from PIL import Image

log = logging.getLogger(__name__)

CDN_PATTERN = re.compile(
    r'(?:https?:)?//cdn\.ncbi\.nlm\.nih\.gov/pmc/blobs/[^\s"\'<>?]+\.(?:jpg|jpeg|png|gif|webp)(?:\?[^\s"\'<>]*)?',
    re.IGNORECASE,
)


def get_cdn_map(pmcid: str) -> dict:
    """
    Scrape the PMC article HTML page to discover CDN image URLs.
    Returns {stem: full_cdn_url} mapping.
    Called lazily — only after a modality-confirmed figure is found.
    """
    try:
        resp = requests.get(
            f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmcid}/",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=20,
        )
        resp.raise_for_status()
        cdn_map = {}
        for u in CDN_PATTERN.findall(resp.text):
            # Normalise protocol-relative URLs to https
            if u.startswith("//"):
                u = "https:" + u
            cdn_map[Path(urlsplit(u).path).stem] = u
        return cdn_map
    except Exception as e:
        log.warning(f"CDN map fetch failed for {pmcid}: {e}")
        return {}


def is_valid_image(path: Path) -> bool:
    """Require a decodable image, including its pixel data, not just a header."""
    try:
        with Image.open(path) as img:
            img.verify()
        with Image.open(path) as img:
            img.load()
        return True
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError):
        return False


def case_has_valid_images(case: dict, root: Path = Path(".")) -> bool:
    paths = case.get("image_paths") or ([case["image_path"]] if case.get("image_path") else [])
    return (isinstance(paths, list) and bool(paths)
            and all(isinstance(p, str) and bool(p) and is_valid_image(root / p) for p in paths))


def download_image(
    pmcid: str,
    img_href: str,
    cdn_map: dict,
    out_dir: Path,
) -> Optional[str]:
    """
    Download a figure image to out_dir.

    Reuses only a valid existing image; publishes downloads atomically.
    Returns absolute path string or None on failure.
    """
    stem = Path(img_href).stem

    # Reuse if already on disk
    if out_dir.exists():
        for existing in out_dir.glob(f"{pmcid}_{stem}.*"):
            if is_valid_image(existing):
                return str(existing)

    cdn_url = cdn_map.get(stem)
    if not cdn_url:
        return None

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{pmcid}_{Path(urlsplit(cdn_url).path).name}"
    temp_path = None
    resp = None
    try:
        resp = requests.get(cdn_url, timeout=20, stream=True)
        resp.raise_for_status()
        with tempfile.NamedTemporaryFile(dir=out_dir, prefix=".download-", suffix=".part", delete=False) as f:
            temp_path = Path(f.name)
            for chunk in resp.iter_content(8192):
                f.write(chunk)
        if not is_valid_image(temp_path):
            raise ValueError("download is not a complete decodable image")
        temp_path.replace(out_path)
        return str(out_path)
    except Exception as e:
        log.warning(f"Image download failed {cdn_url}: {e}")
        return None
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        if resp is not None:
            resp.close()
