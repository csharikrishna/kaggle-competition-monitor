"""
storage.py
~~~~~~~~~~
Manages seen_competitions.json – a simple set of already-notified IDs.

V1: JSON file on disk.
V2: drop-in replacement could use SQLite.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_PATH = Path(__file__).parent.parent / "data" / "seen_competitions.json"


class SeenCompetitionStorage:
    """Persistent set of competition IDs that have already been notified."""

    def __init__(self, path: Path = _DEFAULT_PATH) -> None:
        self._path = path
        self._seen: set[str] = set()
        self._load()

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _load(self) -> None:
        if self._path.exists():
            try:
                # Try UTF-8 first; fall back to utf-8-sig (handles Windows BOM)
                try:
                    text = self._path.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    text = self._path.read_text(encoding="utf-8-sig")
                data = json.loads(text)
                # Support both plain list [] and {"competitions": [...]}
                if isinstance(data, list):
                    self._seen = set(data)
                else:
                    self._seen = set(data.get("competitions", []))
                logger.info(
                    "Loaded %d seen competition IDs from %s",
                    len(self._seen),
                    self._path,
                )
            except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
                logger.warning("Could not load seen competitions (%s) — starting fresh.", exc)
                self._seen = set()

        else:
            logger.info("No seen-competitions file found at %s – starting fresh.", self._path)
            self._seen = set()

    def _save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            payload = {"competitions": sorted(self._seen)}
            content = json.dumps(payload, indent=2)
            
            # Atomic write: write to temp file then replace target file
            temp_path = self._path.with_name(f"{self._path.name}.tmp")
            temp_path.write_text(content, encoding="utf-8")
            temp_path.replace(self._path)
            
            logger.debug("Saved %d seen IDs to %s", len(self._seen), self._path)
        except OSError as exc:
            logger.error("Failed to save seen competitions: %s", exc)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def is_new(self, competition_id: str) -> bool:
        """Return True if this competition has NOT been seen before."""
        return competition_id not in self._seen

    def mark_seen(self, competition_id: str) -> None:
        """Record that this competition has been notified and persist."""
        if competition_id not in self._seen:
            self._seen.add(competition_id)
            self._save()
            logger.info("Marked as seen: %s", competition_id)

    def mark_seen_batch(self, competition_ids: list[str]) -> None:
        """Mark multiple IDs at once and persist once."""
        added = [cid for cid in competition_ids if cid not in self._seen]
        if added:
            self._seen.update(added)
            self._save()
            logger.info("Marked %d competitions as seen.", len(added))

    def get_all(self) -> list[str]:
        """Return a sorted list of all seen competition IDs."""
        return sorted(self._seen)

    def clear(self) -> None:
        """Clear all seen competitions and persist empty storage."""
        self._seen.clear()
        self._save()
        logger.info("Cleared all seen competitions.")

    def count(self) -> int:
        return len(self._seen)

