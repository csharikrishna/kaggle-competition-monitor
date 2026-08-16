"""
competition_cache.py
~~~~~~~~~~~~~~~~~~~~
Persistent disk cache for scored competition data.

The background refresh thread writes here after every fetch cycle.
All user-facing commands (/scan, /top) read exclusively from this cache
to avoid hammering the Kaggle API on every user request.

Cache file: data/competition_cache.json (~a few KB for 20 competitions)
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_PATH = Path(__file__).parent.parent / "data" / "competition_cache.json"


class CompetitionCache:
    """
    Read/write a JSON file that stores the last fetched-and-scored competition list.

    Thread-safety: writes are atomic (tmp file → rename), so concurrent reads
    from the Telegram command handler never see a partially-written file.
    """

    def __init__(self, path: Path = _DEFAULT_PATH) -> None:
        self._path = path

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def save(self, competitions: list[dict]) -> None:
        """Persist *competitions* with the current UTC timestamp."""
        payload = {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "competitions": competitions,
        }
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(".tmp")
            tmp.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
            tmp.replace(self._path)
            logger.info(
                "Competition cache saved: %d competitions to %s",
                len(competitions),
                self._path,
            )
        except OSError as exc:
            logger.error("Failed to write competition cache: %s", exc)

    def load(self) -> tuple[list[dict], datetime | None]:
        """
        Return (competitions, fetched_at) from disk.

        Returns ([], None) if the cache file does not exist or is corrupt.
        """
        if not self._path.exists():
            return [], None

        try:
            text = self._path.read_text(encoding="utf-8")
            data = json.loads(text)
            competitions: list[dict] = data.get("competitions", [])
            fetched_at_str: str = data.get("fetched_at", "")
            fetched_at: datetime | None = None
            if fetched_at_str:
                try:
                    fetched_at = datetime.fromisoformat(fetched_at_str)
                    if fetched_at.tzinfo is None:
                        fetched_at = fetched_at.replace(tzinfo=timezone.utc)
                except ValueError:
                    fetched_at = None
            return competitions, fetched_at
        except (json.JSONDecodeError, OSError, KeyError) as exc:
            logger.warning("Could not read competition cache (%s) — treating as empty.", exc)
            return [], None

    def age_seconds(self) -> float | None:
        """
        Return how many seconds have elapsed since the cache was last written.

        Returns None if the cache does not exist yet.
        """
        _, fetched_at = self.load()
        if fetched_at is None:
            return None
        return (datetime.now(timezone.utc) - fetched_at).total_seconds()

    def is_stale(self, ttl_seconds: float) -> bool:
        """Return True if cache is older than *ttl_seconds* or does not exist."""
        age = self.age_seconds()
        if age is None:
            return True
        return age >= ttl_seconds

    def age_label(self) -> str:
        """Human-readable age string for user-facing messages, e.g. '8 minutes ago'."""
        age = self.age_seconds()
        if age is None:
            return "unknown"
        if age < 60:
            return f"{int(age)}s ago"
        if age < 3600:
            return f"{int(age // 60)}m ago"
        return f"{int(age // 3600)}h ago"

    def exists(self) -> bool:
        """Return True if a non-empty cache file is on disk."""
        comps, _ = self.load()
        return len(comps) > 0
