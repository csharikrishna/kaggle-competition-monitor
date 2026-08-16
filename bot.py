"""
bot.py
~~~~~~
Interactive Telegram Bot Daemon with Live Command Polling and Background Scheduler.

Architecture
------------
- One background thread owns all Kaggle API calls (rate-limited, every N minutes).
- All user commands (/scan, /top) read only from the on-disk competition cache.
- The health server keeps Render's web service alive 24/7.

Run with:
    python bot.py
"""

from __future__ import annotations

import http.server
import json
import logging
import os
import sys
import threading
import time
from pathlib import Path

# UTF-8 stdout
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("bot")

sys.path.insert(0, str(Path(__file__).parent))

from src.kaggle_client import KaggleClient
from src.dataset_analyzer import enrich_with_dataset_info
from src.scorer import score_competition, MIN_NOTIFY_SCORE
from src.storage import SeenCompetitionStorage
from src.subscribers import SubscriberStorage
from src.telegram_bot import TelegramBot
from src.competition_cache import CompetitionCache


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def is_active(competition: dict) -> bool:
    return competition.get("days_remaining", 0) > 0


def passes_min_time(competition: dict, min_days: int = 7) -> bool:
    return competition.get("days_remaining", 0) >= min_days


def fetch_and_score_active(client: KaggleClient, fetch_delay: float = 0.5) -> list[dict]:
    """
    Fetch active Kaggle competitions, enrich with metadata, and score them.

    Parameters
    ----------
    client      : Authenticated KaggleClient.
    fetch_delay : Seconds to wait between each per-competition metadata call.
                  Prevents Kaggle API rate limiting during batch enrichment.
    """
    max_pages = int(os.environ.get("MAX_PAGES", "3"))
    raw = client.fetch_all_active(max_pages=max_pages, group="general")
    active = [c for c in raw if is_active(c)]

    for c in active:
        enrich_with_dataset_info(c, client._api, delay_seconds=fetch_delay)
        score_competition(c)

    return sorted(active, key=lambda c: c["total_score"], reverse=True)


# ---------------------------------------------------------------------------
# Background refresh thread (the only component that calls Kaggle API)
# ---------------------------------------------------------------------------

def background_refresh_worker(
    client: KaggleClient,
    cache: CompetitionCache,
    storage: SeenCompetitionStorage,
    bot: TelegramBot,
    refresh_minutes: float = 15.0,
    fetch_delay: float = 0.5,
) -> None:
    """
    Periodically fetch, score, and cache competition data.

    This is the sole component that makes live Kaggle API calls.
    Each cycle:
      1. Fetch all active competitions (with per-call delays)
      2. Save scored results to disk cache
      3. Check for newly seen competitions and notify subscribers
    """
    logger.info(
        "Background refresh thread started. Refresh interval: %.0f min | "
        "Per-competition API delay: %.1fs",
        refresh_minutes,
        fetch_delay,
    )
    refresh_seconds = max(300.0, refresh_minutes * 60.0)

    while True:
        try:
            logger.info("Refresh: Starting competition fetch cycle...")
            scored = fetch_and_score_active(client, fetch_delay=fetch_delay)

            # Persist to disk so user commands can read instantly
            cache.save(scored)

            # Dispatch notifications for new competitions to subscribers
            min_score = int(os.environ.get("MIN_SCORE", str(MIN_NOTIFY_SCORE)))
            max_mb = float(os.environ.get("MAX_DATASET_MB", "5120"))
            min_days = int(os.environ.get("MIN_DAYS_REMAINING", "7"))

            def _qualifies(c: dict) -> bool:
                size = c.get("dataset_size_mb", 0.0)
                size_ok = size <= 0 or size < max_mb
                return (
                    size_ok
                    and passes_min_time(c, min_days=min_days)
                    and storage.is_new(c["id"])
                    and c["total_score"] >= min_score
                )

            new_and_worthy = [c for c in scored if _qualifies(c)]

            logger.info(
                "Refresh: %d competitions cached | %d new above threshold (%d pts).",
                len(scored),
                len(new_and_worthy),
                min_score,
            )

            if new_and_worthy:
                delivered_ids = bot.send_competitions(new_and_worthy)
                if delivered_ids:
                    storage.mark_seen_batch(delivered_ids)
                    logger.info(
                        "Refresh: Broadcasted %d competitions to subscribers.",
                        len(delivered_ids),
                    )

        except Exception as exc:
            logger.error("Refresh cycle error: %s", exc)

        logger.info("Refresh: Sleeping %.0f minutes until next cycle.", refresh_minutes)
        time.sleep(refresh_seconds)


# ---------------------------------------------------------------------------
# HTTP health server (keeps Render web service alive)
# ---------------------------------------------------------------------------

def start_health_server(port: int = 10000) -> None:
    """Lightweight HTTP health check server for Render web service health probes."""
    class HealthHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            payload = json.dumps({"status": "ok", "service": "kaggle-competition-monitor"})
            self.wfile.write(payload.encode("utf-8"))

        def log_message(self, format, *args):
            pass  # Suppress health check noise in stdout

    try:
        server = http.server.HTTPServer(("0.0.0.0", port), HealthHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        logger.info("HTTP health probe server listening on port %d", port)
    except Exception as exc:
        logger.warning("Could not start HTTP health server on port %d: %s", port, exc)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_interactive_bot() -> None:
    """Initialize and run the interactive 2-way Telegram Bot."""
    print("=" * 70)
    print("  Kaggle Competition Monitor — Interactive Telegram Bot")
    print("=" * 70)

    # Start health server for Render
    port = int(os.environ.get("PORT", "10000"))
    start_health_server(port=port)

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN is not set. Configure it in your environment.")
        sys.exit(1)

    subscribers = SubscriberStorage()
    storage = SeenCompetitionStorage()
    cache = CompetitionCache()
    bot = TelegramBot(token=token, subscribers=subscribers)

    logger.info("Authenticating Kaggle client...")
    client = KaggleClient()

    # Read config
    refresh_minutes = float(os.environ.get("CACHE_REFRESH_MINUTES", "15.0"))
    fetch_delay = float(os.environ.get("DATASET_FETCH_DELAY_SECONDS", "0.5"))

    # Start background refresh thread
    refresh_thread = threading.Thread(
        target=background_refresh_worker,
        args=(client, cache, storage, bot, refresh_minutes, fetch_delay),
        daemon=True,
    )
    refresh_thread.start()

    # ----------------------------------------------------------------
    # On-demand handler for /scan and /top — reads ONLY from cache
    # ----------------------------------------------------------------
    def get_competitions_on_demand() -> list[dict]:
        competitions, _ = cache.load()

        if not competitions:
            # Cache not yet populated — background thread is on its first run
            return []

        min_score = int(os.environ.get("MIN_SCORE", str(MIN_NOTIFY_SCORE)))
        qualified = [c for c in competitions if c.get("total_score", 0) >= min_score]
        return qualified if qualified else competitions

    def get_cache_age_label() -> str:
        return cache.age_label()

    print(f"\n[READY] Telegram Bot is listening for incoming messages.")
    print(f"Active Subscribers: {subscribers.count()}")
    print(f"Cache exists: {cache.exists()} | Age: {cache.age_label()}")
    print("Commands supported: /start, /scan, /top, /status, /help, /stop\n")

    try:
        bot.listen_forever(
            poll_timeout=25,
            on_scan_requested=get_competitions_on_demand,
            get_cache_age_label=get_cache_age_label,
        )
    except KeyboardInterrupt:
        print("\n[INFO] Bot stopped by user. Exiting cleanly.")
        sys.exit(0)


if __name__ == "__main__":
    run_interactive_bot()
