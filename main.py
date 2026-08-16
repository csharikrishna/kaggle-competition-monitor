"""
main.py
~~~~~~~
Entry point for the Kaggle Competition Monitor.

Usage
-----
    python main.py                  # full run
    python main.py --dry-run        # score & print, no Telegram / no storage writes
    python main.py --test-telegram  # send a test message and exit
    python main.py --list-seen      # print all previously seen IDs

Environment variables (use .env locally or GitHub Secrets in CI)
-----------------------------------------------------------------
    KAGGLE_USERNAME
    KAGGLE_KEY
    TELEGRAM_BOT_TOKEN
    TELEGRAM_CHAT_ID         (comma-separated for multiple recipients)
    MAX_PAGES                (optional, default 3)
    MIN_SCORE                (optional, override notification threshold)
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

# Load .env before importing any src module
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv()
except ImportError:
    pass  # dotenv optional – fine in GitHub Actions where secrets are env vars

# ------------------------------------------------------------------
# Logging setup  (before local imports so sub-module loggers work)
# ------------------------------------------------------------------
# Ensure stdout is UTF-8 on all platforms (Windows CMD, GitHub Actions, etc.)
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("main")

# ------------------------------------------------------------------
# Local imports
# ------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).parent))

from src.kaggle_client import KaggleClient
from src.dataset_analyzer import enrich_with_dataset_info
from src.scorer import score_competition, should_notify, MIN_NOTIFY_SCORE
from src.storage import SeenCompetitionStorage
from src.telegram_bot import TelegramBot


# ------------------------------------------------------------------
# Filter helpers
# ------------------------------------------------------------------

def is_active(competition: dict) -> bool:
    """Return True if the competition has not yet ended."""
    return competition.get("days_remaining", 0) > 0


def passes_min_time(competition: dict, min_days: int = 7) -> bool:
    """Require at least *min_days* remaining to be worth notifying."""
    return competition.get("days_remaining", 0) >= min_days


# ------------------------------------------------------------------
# Main pipeline
# ------------------------------------------------------------------

def run(dry_run: bool = False) -> None:
    logger.info("=" * 60)
    logger.info("Kaggle Competition Monitor starting")
    logger.info("=" * 60)

    # ── 1. Fetch ──────────────────────────────────────────────────
    client = KaggleClient()
    max_pages = int(os.environ.get("MAX_PAGES", "3"))
    raw_competitions = client.fetch_all_active(max_pages=max_pages, group='general')
    logger.info("Total fetched: %d competitions", len(raw_competitions))

    # ── 2. Filter (active + enough time) ─────────────────────────
    min_days = int(os.environ.get("MIN_DAYS_REMAINING", "7"))
    active = [c for c in raw_competitions if is_active(c) and passes_min_time(c, min_days=min_days)]
    logger.info("Active with >=%d days remaining: %d", min_days, len(active))

    # ── 3. Enrich with dataset metadata ──────────────────────────
    logger.info("Enriching with dataset metadata...")

    for comp in active:
        enrich_with_dataset_info(comp, client._api)

    # ── 4. Score ──────────────────────────────────────────────────
    for comp in active:
        score_competition(comp)

    scored = sorted(active, key=lambda c: c["total_score"], reverse=True)

    # ── 5. Log all scores ─────────────────────────────────────────
    logger.info("\n%s\n  %-60s %s\n%s", "-" * 80, "Competition", "Score", "-" * 80)
    for c in scored:
        logger.info("  %-60s %3d  %s", c["name"][:60], c["total_score"], c["score_label"])
    logger.info("-" * 80)

    # ── 6. Deduplicate against seen storage ───────────────────────
    storage = SeenCompetitionStorage()
    min_score = int(os.environ.get("MIN_SCORE", str(MIN_NOTIFY_SCORE)))

    # Notify if dataset is <5 GB or unknown (0) — score still logged for info
    MAX_DATASET_MB = float(os.environ.get("MAX_DATASET_MB", "5120"))  # 5 GB default

    def _small_enough(c: dict) -> bool:
        size = c.get("dataset_size_mb", 0.0)
        return size <= 0 or size < MAX_DATASET_MB  # 0 = unknown, include it

    new_and_worthy = [
        c for c in scored
        if _small_enough(c) and storage.is_new(c["id"]) and c["total_score"] >= min_score
    ]

    logger.info(
        "New competitions above score threshold (%d) with dataset <%.0f MB: %d",
        min_score,
        MAX_DATASET_MB,
        len(new_and_worthy),
    )

    if not new_and_worthy:
        logger.info("Nothing new above score threshold to notify. Done.")
        return

    # ── 7. Send Telegram notifications ───────────────────────────
    if dry_run:
        logger.info("[DRY-RUN] Would notify about %d competition(s):", len(new_and_worthy))
        for c in new_and_worthy:
            logger.info("  -> %s  (%d/100) [%s]", c["name"], c["total_score"], c.get("score_label", ""))
        return

    try:
        bot = TelegramBot()
        delivered_ids = bot.send_competitions(new_and_worthy)
    except ValueError as exc:
        logger.error("Telegram configuration error: %s", exc)
        return


    # ── 8. Persist seen IDs ───────────────────────────────────────
    if delivered_ids:
        storage.mark_seen_batch(delivered_ids)
    logger.info("All done. Notified about %d/%d competition(s).", len(delivered_ids), len(new_and_worthy))


# ------------------------------------------------------------------
# CLI
# ------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Kaggle Competition Monitor")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run the full pipeline but do not send Telegram messages or write to storage.",
    )
    parser.add_argument(
        "--test-telegram",
        action="store_true",
        help="Send a test Telegram message and exit.",
    )
    parser.add_argument(
        "--list-seen",
        action="store_true",
        help="Print all previously seen competition IDs and exit.",
    )
    parser.add_argument(
        "--bot",
        action="store_true",
        help="Run the interactive 2-way Telegram Bot daemon with polling and background scheduler.",
    )
    return parser.parse_args()



if __name__ == "__main__":
    args = parse_args()

    if args.bot:
        from bot import run_interactive_bot
        run_interactive_bot()
        sys.exit(0)

    if args.list_seen:
        storage = SeenCompetitionStorage()
        ids = storage.get_all()
        print(f"Seen competitions ({len(ids)}):")
        for cid in ids:
            print(f"  {cid}")
        sys.exit(0)

    if args.test_telegram:
        bot = TelegramBot()
        ok = bot.send_test()
        sys.exit(0 if ok else 1)

    run(dry_run=args.dry_run)


