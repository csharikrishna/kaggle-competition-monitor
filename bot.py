"""
bot.py
~~~~~~
Interactive Telegram Bot Daemon with Live Command Polling and Background Scheduler.

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


def is_active(competition: dict) -> bool:
    return competition.get("days_remaining", 0) > 0


def passes_min_time(competition: dict, min_days: int = 7) -> bool:
    return competition.get("days_remaining", 0) >= min_days


def fetch_and_score_active(client: KaggleClient) -> list[dict]:
    """Fetch active Kaggle competitions, enrich with metadata, and score them."""
    max_pages = int(os.environ.get("MAX_PAGES", "3"))
    raw = client.fetch_all_active(max_pages=max_pages, group="general")
    active = [c for c in raw if is_active(c)]

    for c in active:
        enrich_with_dataset_info(c, client._api)
        score_competition(c)

    return sorted(active, key=lambda c: c["total_score"], reverse=True)


def background_scheduler_worker(
    client: KaggleClient,
    storage: SeenCompetitionStorage,
    bot: TelegramBot,
    interval_hours: float = 6.0,
) -> None:
    """Periodically scan Kaggle and dispatch new competition alerts to all subscribers."""
    logger.info("Background scheduler thread started. Scan interval: %.1f hours.", interval_hours)
    interval_seconds = max(300.0, interval_hours * 3600.0)

    while True:
        try:
            logger.info("Scheduler: Starting periodic competition scan...")
            scored = fetch_and_score_active(client)

            min_score = int(os.environ.get("MIN_SCORE", str(MIN_NOTIFY_SCORE)))
            max_mb = float(os.environ.get("MAX_DATASET_MB", "5120"))
            min_days = int(os.environ.get("MIN_DAYS_REMAINING", "7"))

            def _small_enough(c: dict) -> bool:
                size = c.get("dataset_size_mb", 0.0)
                return size <= 0 or size < max_mb

            new_and_worthy = [
                c for c in scored
                if _small_enough(c)
                and passes_min_time(c, min_days=min_days)
                and storage.is_new(c["id"])
                and c["total_score"] >= min_score
            ]

            logger.info(
                "Scheduler: Found %d new competitions above threshold (%d pts).",
                len(new_and_worthy),
                min_score,
            )

            if new_and_worthy:
                delivered_ids = bot.send_competitions(new_and_worthy)
                if delivered_ids:
                    storage.mark_seen_batch(delivered_ids)
                logger.info("Scheduler: Broadcasted %d competitions to subscribers.", len(delivered_ids))

        except Exception as exc:
            logger.error("Scheduler encountered an error: %s", exc)

        logger.info("Scheduler: Sleeping for %.1f hours until next cycle.", interval_hours)
        time.sleep(interval_seconds)


def start_health_server(port: int = 10000) -> None:
    """Lightweight HTTP health check server for Render and Cloud web services."""
    class HealthHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            payload = json.dumps({"status": "ok", "service": "kaggle-competition-monitor"})
            self.wfile.write(payload.encode("utf-8"))

        def log_message(self, format, *args):
            pass  # Suppress health check ping noise in stdout

    try:
        server = http.server.HTTPServer(("0.0.0.0", port), HealthHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        logger.info("HTTP health probe server listening on port %d", port)
    except Exception as exc:
        logger.warning("Could not start HTTP health server on port %d: %s", port, exc)



def run_interactive_bot() -> None:
    """Initialize and run the interactive 2-way Telegram Bot."""
    print("=" * 70)
    print("  Kaggle Competition Monitor — Interactive Telegram Bot")
    print("=" * 70)

    # Start health server for Render / Cloud web services
    port = int(os.environ.get("PORT", "10000"))
    start_health_server(port=port)

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN is missing in .env file. Please run: python start.py")
        sys.exit(1)

    subscribers = SubscriberStorage()
    storage = SeenCompetitionStorage()
    bot = TelegramBot(token=token, subscribers=subscribers)

    logger.info("Authenticating Kaggle client...")
    client = KaggleClient()

    # Cached results for instant response to user commands
    cached_competitions: list[dict] = []
    last_cache_time = 0.0

    def get_competitions_on_demand() -> list[dict]:
        nonlocal cached_competitions, last_cache_time
        now = time.time()
        # Use cached results if under 15 minutes old to prevent API hammering
        if cached_competitions and (now - last_cache_time < 900):
            return cached_competitions

        results = fetch_and_score_active(client)
        min_score = int(os.environ.get("MIN_SCORE", str(MIN_NOTIFY_SCORE)))
        qualified = [c for c in results if c["total_score"] >= min_score]
        cached_competitions = qualified if qualified else results
        last_cache_time = now
        return cached_competitions

    # Start background scheduler
    interval_hours = float(os.environ.get("POLL_INTERVAL_HOURS", "6.0"))
    scheduler_thread = threading.Thread(
        target=background_scheduler_worker,
        args=(client, storage, bot, interval_hours),
        daemon=True,
    )
    scheduler_thread.start()

    print(f"\n[READY] Telegram Bot is listening for incoming messages.")
    print(f"Active Subscribers: {subscribers.count()}")
    print("Commands supported: /start, /scan, /top, /status, /help, /stop\n")


    try:
        bot.listen_forever(
            poll_timeout=25,
            on_scan_requested=get_competitions_on_demand,
        )
    except KeyboardInterrupt:
        print("\n[INFO] Bot stopped by user. Exiting cleanly.")
        sys.exit(0)


if __name__ == "__main__":
    run_interactive_bot()
