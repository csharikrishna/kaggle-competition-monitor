"""
kaggle_client.py
~~~~~~~~~~~~~~~~
Wraps the Kaggle API and returns normalized competition dicts.

Every other module works with the Competition dict shape – never raw API objects.
"""

from __future__ import annotations

import json
import logging
import os
import pathlib
import re
from datetime import datetime, timezone
from typing import Any

from kaggle.api.kaggle_api_extended import KaggleApi  # type: ignore

logger = logging.getLogger(__name__)


def _setup_kaggle_auth() -> None:
    """
    Support both Kaggle token formats and ensure proper configuration:

    New format (KGAT_...):  Set KAGGLE_API_TOKEN env var (writes ~/.kaggle/access_token).
    Old format:             Set KAGGLE_USERNAME + KAGGLE_KEY env vars,
                            or place kaggle.json at ~/.kaggle/kaggle.json.
    """
    api_token = os.environ.get("KAGGLE_API_TOKEN", "").strip().strip("'\"")
    username = os.environ.get("KAGGLE_USERNAME", "").strip().strip("'\"")
    key = os.environ.get("KAGGLE_KEY", "").strip().strip("'\"")

    # If user pasted the whole kaggle.json content into KAGGLE_API_TOKEN
    if api_token.startswith("{") and "username" in api_token:
        try:
            data = json.loads(api_token)
            username = data.get("username", "").strip()
            key = data.get("key", "").strip()
            api_token = ""
            logger.info("Auto-extracted username and key from JSON payload.")
        except Exception:
            pass

    # If api_token was provided but does not start with KGAT_, it is likely a legacy API key
    if api_token and not api_token.startswith("KGAT_"):
        if not key:
            key = api_token
        api_token = ""

    kaggle_dir = pathlib.Path.home() / ".kaggle"
    try:
        kaggle_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

    if username and key:
        try:
            os.environ["KAGGLE_USERNAME"] = username
            os.environ["KAGGLE_KEY"] = key
            # Remove any stale access_token to prevent OAuth precedence conflicts
            os.environ.pop("KAGGLE_API_TOKEN", None)
            stale_token = kaggle_dir / "access_token"
            if stale_token.exists():
                try:
                    stale_token.unlink()
                except Exception:
                    pass

            config_json = kaggle_dir / "kaggle.json"
            config_json.write_text(
                f'{{"username":"{username}","key":"{key}"}}', encoding="utf-8"
            )
            logger.info("Using KAGGLE_USERNAME + KAGGLE_KEY for authentication.")
        except Exception as exc:
            logger.warning("Could not write ~/.kaggle/kaggle.json: %s", exc)

    elif api_token and api_token.startswith("KGAT_"):
        try:
            os.environ["KAGGLE_API_TOKEN"] = api_token
            access_token_path = kaggle_dir / "access_token"
            access_token_path.write_text(api_token, encoding="utf-8")
            logger.info("Configured Kaggle authentication using KAGGLE_API_TOKEN.")
        except Exception as exc:
            logger.warning("Could not write ~/.kaggle/access_token: %s", exc)

    else:
        if not ((kaggle_dir / "access_token").exists() or (kaggle_dir / "kaggle.json").exists()):
            logger.warning(
                "No valid Kaggle credentials configured. "
                "Provide KAGGLE_USERNAME + KAGGLE_KEY or a valid KAGGLE_API_TOKEN (KGAT_...)."
            )





# ---------------------------------------------------------------------------
# Competition dict shape (V1)
# ---------------------------------------------------------------------------
# {
#     "id":               str   – slugified competition ref, e.g. "titanic"
#     "name":             str   – human-readable title
#     "url":              str   – full Kaggle URL
#     "description":      str   – short description / subtitle
#     "deadline":         str   – ISO-8601 string  (UTC)
#     "days_remaining":   int   – calendar days until deadline (0 if past)
#     "reward":           str   – prize string, e.g. "$50,000" or "Knowledge"
#     "reward_usd":       int   – parsed USD amount (0 for non-cash)
#     "teams":            int   – number of participating teams
#     "category":         str   – Kaggle category tag
#     "evaluation_metric":str   – evaluation metric name
#     "dataset_size_mb":  float – total dataset size (populated later)
#     "file_count":       int   – number of dataset files   (populated later)
#     "file_types":       list  – unique file extensions    (populated later)
# }
# ---------------------------------------------------------------------------


def _parse_reward_usd(reward_str: str) -> int:
    """Extract integer USD value from Kaggle prize strings."""
    if not reward_str:
        return 0

    # Look for explicit dollar amounts like "$50,000" or "$100,000"
    dollar_match = re.search(r"\$\s*([\d,]+)", reward_str)
    if dollar_match:
        num_str = dollar_match.group(1).replace(",", "")
        try:
            return int(num_str)
        except ValueError:
            pass

    # Check if entire string is just a clean number (e.g. "50,000" or "50000")
    clean = reward_str.strip().replace(",", "")
    if clean.isdigit():
        return int(clean)

    return 0


def _days_remaining(deadline_str: str) -> int:
    """Return calendar days until *deadline_str* (ISO-8601, UTC). 0 if past."""
    if not deadline_str:
        return 0
    try:
        # Handle both naive ('2026-11-02T23:59:00') and aware ('...+00:00') strings
        dt = datetime.fromisoformat(deadline_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            # Kaggle returns naive datetimes - treat as UTC
            dt = dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        delta = dt - now
        total_sec = delta.total_seconds()
        if total_sec <= 0:
            return 0
        days = int(total_sec // 86400)
        return max(1, days)
    except (ValueError, TypeError):
        return 0


def _days_remaining_from_dt(deadline_dt: Any) -> int:
    """Compute days remaining directly from a datetime object (at least 1 if active in future)."""
    if deadline_dt is None:
        return 0
    try:
        if deadline_dt.tzinfo is None:
            deadline_dt = deadline_dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        delta = deadline_dt - now
        total_sec = delta.total_seconds()
        if total_sec <= 0:
            return 0
        days = int(total_sec // 86400)
        return max(1, days)
    except (AttributeError, TypeError):
        return 0


_KAGGLE_BASE = "https://www.kaggle.com/competitions/"


def _build_url(ref: str) -> str:
    """
    Build a clean Kaggle competition URL from *ref*.

    The Kaggle SDK returns either:
    - A slug:    "digit-recognizer"
    - A full URL: "https://www.kaggle.com/competitions/digit-recognizer"

    We always return the canonical full URL without duplication.
    """
    if not ref:
        return ""
    # Strip any leading/trailing whitespace
    ref = ref.strip()
    # If ref is already a full URL, return it as-is (strip trailing slashes)
    if ref.startswith("http"):
        return ref.rstrip("/")
    # Otherwise prepend the base URL
    return _KAGGLE_BASE + ref.lstrip("/")


def _normalize(raw: Any) -> dict:

    """Convert a raw Kaggle API competition object into our standard dict."""
    ref: str = getattr(raw, "ref", "") or ""
    title: str = getattr(raw, "title", "") or ""
    deadline_raw = getattr(raw, "deadline", None)
    if deadline_raw:
        if hasattr(deadline_raw, "tzinfo") and deadline_raw.tzinfo is not None:
            deadline_str = deadline_raw.isoformat()
        elif hasattr(deadline_raw, "isoformat"):
            deadline_str = deadline_raw.isoformat() + "+00:00"
        else:
            deadline_str = str(deadline_raw)
    else:
        deadline_str = ""

    reward: str = str(getattr(raw, "reward", "") or "")
    description: str = str(getattr(raw, "description", "") or "")

    # New SDK uses snake_case; old SDK uses camelCase — try both
    teams: int = int(
        getattr(raw, "team_count", None)        # new SDK (Linux)
        or getattr(raw, "teamCount", None)       # old SDK (Windows)
        or 0
    )
    category: str = str(getattr(raw, "category", "") or "")
    evaluation_metric: str = str(
        getattr(raw, "evaluation_metric", None)  # new SDK (Linux)
        or getattr(raw, "evaluationMetric", None) # old SDK (Windows)
        or ""
    )

    return {
        "id": ref,
        "name": title,
        "url": _build_url(ref),
        "description": description,
        "deadline": deadline_str,
        "days_remaining": _days_remaining_from_dt(deadline_raw),
        "reward": reward,
        "reward_usd": _parse_reward_usd(reward),
        "teams": teams,
        "category": category,
        "evaluation_metric": evaluation_metric,
        # Populated by dataset_analyzer.py
        "dataset_size_mb": 0.0,
        "file_count": 0,
        "file_types": [],
    }


class KaggleClient:
    """Thin wrapper around KaggleApi for competition listing."""

    def __init__(self) -> None:
        self.authenticated = False
        self._api = KaggleApi()
        self.try_authenticate()

    def try_authenticate(self) -> bool:
        """Attempt authentication without allowing SystemExit to terminate the server."""
        _setup_kaggle_auth()
        try:
            self._api.authenticate()
            self.authenticated = True
            logger.info("Kaggle API authenticated successfully.")
            return True
        except (SystemExit, Exception) as exc:
            self.authenticated = False
            logger.warning(
                "Kaggle API authentication pending or token invalid (%s). "
                "The bot will remain active and retry when valid credentials are provided.",
                exc,
            )
            return False

    def fetch_competitions(
        self,
        page: int = 1,
        page_size: int = 100,
        sort_by: str = "latestDeadline",
        category: str = "all",
        group: str = "general",
        search: str = "",
    ) -> list[dict]:
        """
        Fetch a page of active competitions.

        Parameters
        ----------
        page:      API page number (1-indexed).
        page_size: Results per page (max 100 per Kaggle API).
        sort_by:   One of 'latestDeadline', 'prize', 'numberOfTeams', etc.
        category:  Filter by Kaggle category; use 'all' for no filter.
        group:     'general' = active only, 'entered' = entered, 'inClass' = course.
        search:    Optional full-text search string.

        Returns
        -------
        List of normalized competition dicts.
        """
        if not self.authenticated:
            if not self.try_authenticate():
                return []

        logger.info(
            "Fetching competitions: page=%d sort_by=%s category=%s group=%s search=%r",
            page,
            sort_by,
            category,
            group,
            search,
        )

        try:
            raw_response = self._api.competitions_list(
                page=page,
                search=search,
                sort_by=sort_by,
                category=category,
                group=group,
            )
        except Exception as exc:
            logger.warning("competitions_list call failed: %s", exc)
            return []

        # Kaggle SDK v1.7+ may return ApiListCompetitionsResponse instead of list.
        # We try to iterate directly first; if that fails we extract .competitions.
        try:
            raw_list = list(raw_response)
        except TypeError:
            raw_list = list(getattr(raw_response, "competitions", None) or [])

        competitions = [_normalize(c) for c in raw_list]
        logger.info("Fetched %d competitions.", len(competitions))
        return competitions




    def fetch_all_active(self, max_pages: int = 5, group: str = "general") -> list[dict]:
        """
        Walk multiple pages and return all active competitions.

        Stops early when a page returns fewer results than expected
        (signals last page) or if a network error occurs.

        group='general' filters to active competitions only.
        """
        all_comps: list[dict] = []
        for page_num in range(1, max_pages + 1):
            try:
                page = self.fetch_competitions(page=page_num, group=group)
            except Exception as exc:
                logger.warning(
                    "Error fetching page %d: %s. Continuing with %d accumulated competitions.",
                    page_num,
                    exc,
                    len(all_comps),
                )
                break

            if not page:
                logger.info("Page %d empty - stopping pagination.", page_num)
                break
            all_comps.extend(page)
            logger.info("Accumulated %d competitions so far.", len(all_comps))
            if len(page) < 100:
                # Last page (Kaggle returns < 100 on the final page)
                break

        return all_comps

