"""
telegram_bot.py
~~~~~~~~~~~~~~~
Sends Kaggle competition notifications and provides an interactive
2-way Telegram Bot interface (/start, /scan, /top, /status, /help).
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from typing import Callable

import requests

from src.subscribers import SubscriberStorage

logger = logging.getLogger(__name__)

_TELEGRAM_API_BASE = "https://api.telegram.org/bot{token}"
_MAX_MESSAGE_LENGTH = 4096  # Telegram hard limit


# ---------------------------------------------------------------------------
# Message formatting
# ---------------------------------------------------------------------------


def _fmt_size(size_mb: float) -> str:
    if size_mb <= 0:
        return "Unknown"
    if size_mb >= 1024:
        return f"{size_mb / 1024:.1f} GB"
    return f"{size_mb:.0f} MB"


def _fmt_deadline(competition: dict) -> str:
    days = competition.get("days_remaining", 0)
    deadline_str = competition.get("deadline", "")

    if not deadline_str:
        return "Unknown"

    try:
        dt = datetime.fromisoformat(deadline_str.replace("Z", "+00:00"))
        date_part = dt.strftime("%d %b %Y")
    except (ValueError, TypeError):
        date_part = deadline_str[:10]

    if days == 0:
        return f"ENDED ({date_part})"
    return f"{days} days remaining ({date_part})"


def _fmt_prize(competition: dict) -> str:
    reward = competition.get("reward", "")
    usd = competition.get("reward_usd", 0)
    if usd > 0:
        return f"{reward} (${usd:,})"
    return reward or "No monetary prize"


def _why_score(competition: dict) -> str:
    """Generate a short human-readable rationale."""
    reasons: list[str] = []

    if competition.get("score_relevance", 0) >= 25:
        reasons.append("highly relevant ML/DL topic")
    if competition.get("score_portfolio", 0) >= 15:
        reasons.append("strong portfolio / research value")
    if competition.get("score_prize", 0) >= 11:
        reasons.append("significant prize")
    if competition.get("score_feasibility", 0) >= 13:
        reasons.append("manageable dataset size")
    if competition.get("score_time", 0) >= 9:
        reasons.append("plenty of time to participate")
    if competition.get("score_teams", 0) == 10:
        reasons.append("healthy competition size")

    if not reasons:
        reasons = ["balanced scores across all dimensions"]

    return ", ".join(reasons).capitalize() + "."


def format_competition_message(competition: dict) -> str:
    """Render the competition dict as a Telegram-ready text message."""
    label = competition.get("score_label", "Qualified")
    total = competition.get("total_score", 0)
    name = competition.get("name", "Unknown")
    modalities = competition.get("modalities", [])
    category_str = (
        "/".join(m.title() for m in modalities)
        if modalities
        else competition.get("category", "General ML")
    )

    # Dataset line
    size_mb = competition.get("dataset_size_mb", 0)
    size_str = _fmt_size(size_mb)
    file_count = competition.get("file_count", 0)
    file_types = competition.get("file_types", [])
    types_str = (", ".join(f".{t.lstrip('.')}" for t in file_types)) if file_types else "unknown"
    dataset_line = f"{size_str} | {file_count:,} files | {types_str}"

    # Score breakdown — fixed-width columns
    s_rel  = competition.get("score_relevance",   0)
    s_port = competition.get("score_portfolio",   0)
    s_prize= competition.get("score_prize",       0)
    s_feas = competition.get("score_feasibility", 0)
    s_time = competition.get("score_time",        0)
    s_comp = competition.get("score_teams",       0)

    lines = [
        f"[{label.upper()}] NEW COMPETITION",
        "=" * 40,
        f"  {name}",
        f"  Score: {total}/100",
        "-" * 40,
        f"  Category:  {category_str}",
        f"  Prize:     {_fmt_prize(competition)}",
        f"  Dataset:   {dataset_line}",
        f"  Teams:     {competition.get('teams', 0):,}",
        f"  Deadline:  {_fmt_deadline(competition)}",
        "-" * 40,
        "  Score Breakdown:",
        f"    Relevance    {s_rel:2d}/30",
        f"    Portfolio    {s_port:2d}/20",
        f"    Prize        {s_prize:2d}/15",
        f"    Feasibility  {s_feas:2d}/15",
        f"    Time         {s_time:2d}/10",
        f"    Competition  {s_comp:2d}/10",
        "-" * 40,
        f"  {_why_score(competition)}",
        f"  {competition.get('url', '')}",
        "=" * 40,
    ]

    message = "\n".join(lines)
    if len(message) > _MAX_MESSAGE_LENGTH:
        message = message[: _MAX_MESSAGE_LENGTH - 3] + "..."
    return message


def format_summary_message(competitions: list[dict]) -> str:
    """Render a brief digest message when there are multiple new competitions."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    header = [
        f"[Kaggle Competition Monitor Digest — {now}]",
        f"Discovered {len(competitions)} qualified competition(s) above threshold:\n",
    ]
    entries = []
    for i, c in enumerate(competitions, 1):
        entries.append(
            f"{i}. [{c.get('score_label','')}] {c.get('name', 'Unknown')} "
            f"({c.get('total_score', 0)}/100) -> {c.get('url', '')}"
        )
    return "\n".join(header + entries)


# ---------------------------------------------------------------------------
# Interactive Bot Engine
# ---------------------------------------------------------------------------


class TelegramBot:
    """Interactive Telegram Bot and notification dispatcher."""

    def __init__(
        self,
        token: str | None = None,
        chat_ids: list[str] | None = None,
        subscribers: SubscriberStorage | None = None,
    ) -> None:
        self._token: str = token or os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
        self._explicit_chat_ids = chat_ids
        self._subscribers = subscribers or SubscriberStorage()

        if not self._token:
            raise ValueError(
                "TELEGRAM_BOT_TOKEN is not set. "
                "Set it in your .env file or as an environment variable."
            )

    @property
    def recipients(self) -> list[str]:
        """Return list of active recipient chat IDs."""
        if self._explicit_chat_ids is not None:
            return self._explicit_chat_ids
        return self._subscribers.get_all_chat_ids()

    def send_to_chat(self, chat_id: str | int, text: str) -> bool:
        """Send *text* to a single *chat_id*. Returns True on success."""
        url = f"{_TELEGRAM_API_BASE.format(token=self._token)}/sendMessage"
        payload = {
            "chat_id": str(chat_id),
            "text": text,
            "disable_web_page_preview": True,
        }
        try:
            response = requests.post(url, json=payload, timeout=15)
            if response.ok:
                logger.debug("Telegram message sent to chat_id=%s", chat_id)
                return True
            else:
                logger.error(
                    "Telegram API error for chat_id=%s: %s %s",
                    chat_id,
                    response.status_code,
                    response.text,
                )
                return False
        except requests.RequestException as exc:
            logger.error("Network error sending to chat_id=%s: %s", chat_id, exc)
            return False

    def send_text(self, text: str, chat_ids: list[str] | None = None) -> int:
        """Broadcast *text* to target chat IDs. Returns success count."""
        targets = chat_ids or self.recipients
        if not targets:
            logger.warning("No Telegram recipients available to receive broadcast.")
            return 0
        successes = sum(self.send_to_chat(cid, text) for cid in targets)
        logger.info("Sent message to %d/%d recipients.", successes, len(targets))
        return successes

    def send_competition(self, competition: dict, chat_ids: list[str] | None = None) -> int:
        """Format and broadcast a single competition notification."""
        msg = format_competition_message(competition)
        return self.send_text(msg, chat_ids=chat_ids)

    def send_competitions(
        self,
        competitions: list[dict],
        chat_ids: list[str] | None = None,
        delay_seconds: float = 1.0,
    ) -> list[str]:
        """
        Send a brief digest summary first, then one message per competition with rate limiting.
        Returns a list of competition IDs that were successfully delivered.
        """
        if not competitions:
            return []

        targets = chat_ids or self.recipients
        if not targets:
            logger.warning("No recipients configured for competition notifications.")
            return []

        delivered_ids: list[str] = []

        if len(competitions) > 1:
            summary = format_summary_message(competitions)
            self.send_text(summary, chat_ids=targets)
            time.sleep(delay_seconds)

        for comp in competitions:
            successes = self.send_competition(comp, chat_ids=targets)
            if successes > 0:
                delivered_ids.append(comp["id"])
            time.sleep(delay_seconds)

        logger.info(
            "Delivered %d/%d competitions successfully to subscribers.",
            len(delivered_ids),
            len(competitions),
        )
        return delivered_ids

    def send_test(self, chat_ids: list[str] | None = None) -> bool:
        """Send a simple connectivity test message."""
        targets = chat_ids or self.recipients
        if not targets:
            return False
        return (
            self.send_text(
                "[OK] Kaggle Competition Monitor: Connectivity verification successful.",
                chat_ids=targets,
            )
            > 0
        )

    # -----------------------------------------------------------------------
    # Interactive 2-Way Message Polling & Command Handling
    # -----------------------------------------------------------------------

    def get_updates(self, offset: int = 0, timeout: int = 25) -> list[dict]:
        """Fetch incoming Telegram messages via long-polling."""
        url = f"{_TELEGRAM_API_BASE.format(token=self._token)}/getUpdates"
        params = {"offset": offset, "timeout": timeout}
        try:
            resp = requests.get(url, params=params, timeout=timeout + 10)
            if resp.ok:
                data = resp.json()
                return data.get("result", [])
            else:
                logger.error("getUpdates failed with status %d: %s", resp.status_code, resp.text)
                return []
        except Exception as exc:
            logger.debug("Error during getUpdates polling: %s", exc)
            return []

    def handle_update(
        self,
        update: dict,
        on_scan_requested: Callable[[], list[dict]] | None = None,
        get_cache_age_label: Callable[[], str] | None = None,
    ) -> None:
        """Route incoming user commands."""
        message = update.get("message") or update.get("edited_message")
        if not message:
            return

        chat = message.get("chat", {})
        chat_id = chat.get("id")
        if not chat_id:
            return

        from_user = message.get("from", {})
        username = from_user.get("username", "")
        first_name = from_user.get("first_name", "User")
        text = (message.get("text") or "").strip()

        logger.info("Received Telegram command from %s (%s): %r", first_name, chat_id, text)

        command = text.split()[0].lower() if text else ""

        if command in ("/start", "start"):
            self._subscribers.subscribe(chat_id, username=username, first_name=first_name)
            welcome_msg = (
                f"[KAGGLE COMPETITION MONITOR]\n"
                f"----------------------------------------\n"
                f"Welcome, {first_name}!\n\n"
                f"You are now subscribed to automated alerts for top-tier Kaggle competitions.\n\n"
                f"Available Commands:\n"
                f"  /scan    - Run real-time scan and view top recommendations\n"
                f"  /top     - View highest scoring competitions active right now\n"
                f"  /status  - View subscription status and monitor settings\n"
                f"  /help    - Display command reference\n"
                f"  /stop    - Unsubscribe from automated broadcasts"
            )
            self.send_to_chat(chat_id, welcome_msg)

        elif command in ("/help", "help"):
            help_msg = (
                f"[KAGGLE COMPETITION MONITOR — COMMANDS]\n"
                f"----------------------------------------\n"
                f"/start   - Subscribe and receive automated competition alerts\n"
                f"/scan    - Fetch and score current active competitions in real-time\n"
                f"/top     - Show highest scoring active competitions\n"
                f"/status  - View active subscription and threshold parameters\n"
                f"/stop    - Pause / unsubscribe from automated alerts"
            )
            self.send_to_chat(chat_id, help_msg)

        elif command in ("/status", "status"):
            is_sub = self._subscribers.is_subscribed(chat_id)
            sub_status = "ACTIVE" if is_sub else "INACTIVE"
            min_score = os.environ.get("MIN_SCORE", "75")
            max_mb = os.environ.get("MAX_DATASET_MB", "5120")
            total_subs = self._subscribers.count()

            status_msg = (
                f"[MONITOR STATUS]\n"
                f"----------------------------------------\n"
                f"Your Subscription: {sub_status}\n"
                f"Total Subscribers: {total_subs}\n"
                f"Score Threshold:   >= {min_score} pts\n"
                f"Max Dataset Size:  < {float(max_mb)/1024:.1f} GB\n"
                f"Server Time:       {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
            )
            self.send_to_chat(chat_id, status_msg)

        elif command in ("/stop", "stop"):
            self._subscribers.unsubscribe(chat_id)
            self.send_to_chat(
                chat_id,
                "[OK] You have unsubscribed from automated alerts. Send /start at any time to resume.",
            )

        elif command in ("/scan", "/latest", "/top", "scan", "top"):
            if on_scan_requested:
                try:
                    results = on_scan_requested()
                    if not results:
                        self.send_to_chat(
                            chat_id,
                            "[NOTICE] No data in cache yet. The background scanner is running its"
                            " first cycle. Please try again in about 1 minute.",
                        )
                    else:
                        age_label = get_cache_age_label() if get_cache_age_label else "unknown"
                        count = len(results)
                        is_top = command in ("/top", "top")
                        items = results[:5] if is_top else results
                        label_str = "Top 5" if is_top else f"All {count}"
                        header = (
                            f"[RESULTS] {label_str} competition(s)"
                            f" (data from {age_label}):"
                        )
                        self.send_to_chat(chat_id, header)
                        time.sleep(0.3)
                        for comp in items:
                            self.send_to_chat(chat_id, format_competition_message(comp))
                            time.sleep(0.5)
                        if not is_top and count > 5:
                            self.send_to_chat(
                                chat_id,
                                f"[DONE] Sent all {count} competitions above threshold."
                                f" Use /top for just the 5 highest-scored.",
                            )
                except Exception as exc:
                    logger.error("Scan error: %s", exc)
                    self.send_to_chat(chat_id, f"[ERROR] Failed to retrieve results: {exc}")
            else:
                self.send_to_chat(
                    chat_id,
                    "[NOTICE] Scanner is initializing. Please try again in a moment.",
                )

        else:
            self.send_to_chat(
                chat_id,
                "Command not recognized. Send /help to view available commands.",
            )

    def listen_forever(
        self,
        poll_timeout: int = 25,
        on_scan_requested: Callable[[], list[dict]] | None = None,
        get_cache_age_label: Callable[[], str] | None = None,
    ) -> None:
        """Start long-polling loop for incoming messages."""
        logger.info("Starting Telegram Bot long-polling service...")
        offset = 0
        while True:
            try:
                updates = self.get_updates(offset=offset, timeout=poll_timeout)
                for update in updates:
                    offset = max(offset, update.get("update_id", 0) + 1)
                    self.handle_update(
                        update,
                        on_scan_requested=on_scan_requested,
                        get_cache_age_label=get_cache_age_label,
                    )
            except Exception as exc:
                logger.error("Polling loop encountered error: %s", exc)
                time.sleep(3)
