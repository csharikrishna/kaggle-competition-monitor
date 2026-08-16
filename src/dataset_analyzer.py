"""
dataset_analyzer.py
~~~~~~~~~~~~~~~~~~~
Enriches a competition dict with dataset metadata.

Design goal: **never download files**.
We use the Kaggle API's competition_list_files endpoint which returns
file-level metadata (name, size) without transferring any data.
"""

from __future__ import annotations

import logging
import time
from pathlib import PurePosixPath
from typing import Any

from kaggle.api.kaggle_api_extended import KaggleApi  # type: ignore

logger = logging.getLogger(__name__)

# File extensions that hint at modality
_MODALITY_MAP: dict[str, str] = {
    ".jpg": "image",
    ".jpeg": "image",
    ".png": "image",
    ".bmp": "image",
    ".gif": "image",
    ".tif": "image",
    ".tiff": "image",
    ".webp": "image",
    ".mp4": "video",
    ".avi": "video",
    ".mov": "video",
    ".wav": "audio",
    ".mp3": "audio",
    ".flac": "audio",
    ".csv": "tabular",
    ".tsv": "tabular",
    ".parquet": "tabular",
    ".feather": "tabular",
    ".xlsx": "tabular",
    ".xls": "tabular",
    ".txt": "text",
    ".json": "text/structured",
    ".jsonl": "text/structured",
    ".xml": "text/structured",
    ".html": "text",
    ".pdf": "text",
    ".zip": "archive",
    ".gz": "archive",
    ".tar": "archive",
    ".7z": "archive",
    ".npy": "array",
    ".npz": "array",
    ".h5": "array",
    ".hdf5": "array",
    ".pt": "model",
    ".pth": "model",
    ".pkl": "model",
    ".dicom": "medical",
    ".dcm": "medical",
}


def _ext(filename: str) -> str:
    """Return lowercase extension including dot, e.g. '.csv'."""
    return PurePosixPath(filename).suffix.lower()


def _bytes_to_mb(size_bytes: int) -> float:
    return round(size_bytes / (1024 * 1024), 2)


def enrich_with_dataset_info(competition: dict, api: KaggleApi, delay_seconds: float = 0.0) -> dict:
    """
    Fetch dataset file metadata for *competition* and add to the dict.

    Modifies competition in-place and also returns it.

    Parameters
    ----------
    competition   : The competition dict to enrich in-place.
    api           : Authenticated KaggleApi instance.
    delay_seconds : Seconds to sleep before issuing the API call.
                    Set > 0 during batch processing to avoid rate-limiting.

    Fields added / updated
    ----------------------
    dataset_size_mb : float  - total size of all files in MB
    file_count      : int    - number of files
    file_types      : list   - unique lowercase extensions
    modalities      : list   - inferred data modalities (image/text/tabular/...)
    dataset_summary : str    - human-readable one-liner
    """
    comp_id: str = competition.get("id", "")
    if not comp_id:
        return competition

    # Throttle before calling the Kaggle API to respect rate limits
    if delay_seconds > 0:
        time.sleep(delay_seconds)

    # The API expects just the slug (e.g. "titanic"), not a full URL
    slug = comp_id.split("/")[-1] if "/" in comp_id else comp_id
    logger.info("Fetching dataset info for: %s", slug)

    try:
        response = api.competition_list_files(slug)
        # New kaggle SDK returns ApiListDataFilesResponse with a .files attribute
        if hasattr(response, "files"):
            files: list[Any] = response.files or []
        else:
            files = list(response) if response else []

    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not fetch files for %s: %s", comp_id, exc)
        competition.update(
            {
                "dataset_size_mb": 0.0,
                "file_count": 0,
                "file_types": [],
                "modalities": [],
                "dataset_summary": "Dataset info unavailable",
            }
        )
        return competition

    total_bytes = 0
    extensions: set[str] = set()

    for f in files:
        # New SDK: total_bytes  |  Old SDK: totalBytes  |  fallback: size
        size = (
            getattr(f, "total_bytes", None)
            or getattr(f, "totalBytes", None)
            or getattr(f, "size", 0)
            or 0
        )
        name = getattr(f, "name", "") or ""
        try:
            total_bytes += int(size)
        except (ValueError, TypeError):
            pass
        if name:
            extensions.add(_ext(name))

    extensions.discard("")  # remove empty string if any

    # Derive modalities
    modalities: list[str] = sorted(
        {_MODALITY_MAP.get(ext, "other") for ext in extensions}
    )

    size_mb = _bytes_to_mb(total_bytes)

    # Human-readable summary
    if size_mb >= 1024:
        size_str = f"{size_mb / 1024:.1f} GB"
    elif size_mb > 0:
        size_str = f"{size_mb:.0f} MB"
    else:
        size_str = "Unknown"

    summary = (
        f"{size_str}, {len(files)} file{'s' if len(files) != 1 else ''}, "
        f"{'/'.join(modalities) if modalities else 'unknown'}"
    )

    competition.update(
        {
            "dataset_size_mb": size_mb,
            "file_count": len(files),
            "file_types": sorted(extensions),
            "modalities": modalities,
            "dataset_summary": summary,
        }
    )

    logger.info(
        "%s -> %s (%d files, types: %s)",
        comp_id,
        size_str,
        len(files),
        ", ".join(sorted(extensions)) or "none",
    )

    return competition
