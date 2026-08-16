"""
subscribers.py
~~~~~~~~~~~~~~
Manages user subscriptions for the Telegram bot.
Persists subscriber chat IDs and metadata in data/subscribers.json.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_PATH = Path(__file__).parent.parent / "data" / "subscribers.json"


class SubscriberStorage:
    """Persistent storage for registered Telegram subscribers."""

    def __init__(self, path: Path = _DEFAULT_PATH) -> None:
        self._path = path
        self._subscribers: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            try:
                text = self._path.read_text(encoding="utf-8")
                data = json.loads(text)
                if isinstance(data, list):
                    # Migration from simple list of IDs
                    self._subscribers = {
                        str(cid): {"joined_at": datetime.now(timezone.utc).isoformat()}
                        for cid in data
                    }
                elif isinstance(data, dict):
                    self._subscribers = data.get("subscribers", {})
                logger.info("Loaded %d active subscribers from %s", len(self._subscribers), self._path)
            except Exception as exc:
                logger.warning("Could not load subscribers (%s) — starting fresh.", exc)
                self._subscribers = {}
        else:
            self._subscribers = {}

    def _save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "total": len(self._subscribers),
                "subscribers": self._subscribers,
            }
            content = json.dumps(payload, indent=2)
            temp_path = self._path.with_name(f"{self._path.name}.tmp")
            temp_path.write_text(content, encoding="utf-8")
            temp_path.replace(self._path)
            logger.debug("Saved %d subscribers to %s", len(self._subscribers), self._path)
        except OSError as exc:
            logger.error("Failed to save subscribers: %s", exc)

    def subscribe(
        self,
        chat_id: str | int,
        username: str = "",
        first_name: str = "",
    ) -> bool:
        """
        Register a chat_id as an active subscriber.
        Returns True if newly added, False if already subscribed.
        """
        cid = str(chat_id).strip()
        if not cid:
            return False

        is_new = cid not in self._subscribers
        self._subscribers[cid] = {
            "username": username,
            "first_name": first_name,
            "active": True,
            "last_active": datetime.now(timezone.utc).isoformat(),
            "joined_at": self._subscribers.get(cid, {}).get(
                "joined_at", datetime.now(timezone.utc).isoformat()
            ),
        }
        self._save()
        if is_new:
            logger.info("New subscriber registered: chat_id=%s username=%r", cid, username)
        return is_new

    def unsubscribe(self, chat_id: str | int) -> bool:
        """
        Unsubscribe a user from notifications.
        Returns True if removed, False if not found.
        """
        cid = str(chat_id).strip()
        if cid in self._subscribers:
            del self._subscribers[cid]
            self._save()
            logger.info("Subscriber removed: chat_id=%s", cid)
            return True
        return False

    def is_subscribed(self, chat_id: str | int) -> bool:
        """Check if chat_id is currently subscribed."""
        cid = str(chat_id).strip()
        return cid in self._subscribers and self._subscribers[cid].get("active", True)

    def get_all_chat_ids(self) -> list[str]:
        """
        Return all unique active chat IDs from storage plus any configured in TELEGRAM_CHAT_ID env var.
        """
        active_ids = {
            cid for cid, info in self._subscribers.items() if info.get("active", True)
        }

        # Also incorporate static IDs from environment if configured
        env_raw = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
        if env_raw:
            for item in env_raw.split(","):
                cleaned = item.strip()
                if cleaned:
                    active_ids.add(cleaned)

        return sorted(active_ids)

    def count(self) -> int:
        """Return the number of active subscribers."""
        return len([cid for cid, info in self._subscribers.items() if info.get("active", True)])
