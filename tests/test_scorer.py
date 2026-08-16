"""
test_scorer.py
~~~~~~~~~~~~~~
Unit tests for the scoring engine.

Run with:
    python -m pytest tests/ -v
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow importing src without installing the package
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.scorer import (
    MIN_NOTIFY_SCORE,
    score_competition,
    should_notify,
    _score_relevance,
    _score_portfolio,
    _score_prize,
    _score_feasibility,
    _score_time,
    _score_competition_size,
)



def _make_competition(**overrides) -> dict:
    """Return a minimal competition dict, optionally overriding fields."""
    base = {
        "id": "test-competition",
        "name": "Test Competition",
        "description": "",
        "category": "",
        "evaluation_metric": "",
        "modalities": [],
        "reward_usd": 0,
        "dataset_size_mb": 0.0,
        "days_remaining": 30,
        "teams": 200,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Relevance
# ---------------------------------------------------------------------------

class TestRelevance:
    def test_high_priority_many_keywords(self):
        comp = _make_competition(
            name="Deep Learning for Computer Vision NLP",
            description="A multimodal transformer challenge",
        )
        score = _score_relevance(comp)
        assert score >= 27, f"Expected >=27, got {score}"

    def test_medium_priority(self):
        comp = _make_competition(
            name="Tabular classification with gradient boosting",
        )
        score = _score_relevance(comp)
        assert 10 <= score <= 20, f"Expected 10–20, got {score}"

    def test_unrelated(self):
        comp = _make_competition(name="Historical Geography Quiz", description="Maps")
        score = _score_relevance(comp)
        assert score <= 10, f"Expected <=10, got {score}"


# ---------------------------------------------------------------------------
# Prize
# ---------------------------------------------------------------------------

class TestPrize:
    def test_100k(self):
        assert _score_prize(100_000) == 15

    def test_50k(self):
        assert _score_prize(50_000) == 13

    def test_zero(self):
        assert _score_prize(0) == 1

    def test_small_cash(self):
        score = _score_prize(3_000)
        assert score == 4


# ---------------------------------------------------------------------------
# Feasibility
# ---------------------------------------------------------------------------

class TestFeasibility:
    def test_tiny_dataset(self):
        assert _score_feasibility(100) == 15  # < 500 MB

    def test_medium_dataset(self):
        score = _score_feasibility(3_000)  # 3 GB
        assert score == 13

    def test_very_large(self):
        score = _score_feasibility(200_000)  # 200 GB
        assert score == 2

    def test_unknown(self):
        assert _score_feasibility(0) == 8  # neutral


# ---------------------------------------------------------------------------
# Time
# ---------------------------------------------------------------------------

class TestTime:
    def test_plenty_of_time(self):
        assert _score_time(90) == 10
        assert _score_time(30) == 9

    def test_tight(self):
        assert _score_time(5) == 1

    def test_moderate(self):
        score = _score_time(20)
        assert score == 6


# ---------------------------------------------------------------------------
# Competition size
# ---------------------------------------------------------------------------

class TestCompetitionSize:
    def test_sweet_spot(self):
        assert _score_competition_size(500) == 10

    def test_too_large(self):
        assert _score_competition_size(20_000) == 2

    def test_new_competition(self):
        assert _score_competition_size(0) == 6


# ---------------------------------------------------------------------------
# Full scoring pipeline
# ---------------------------------------------------------------------------

class TestScorePipeline:
    def test_excellent_competition(self):
        comp = _make_competition(
            name="Google DeepMind LLM NLP Challenge",
            description="A multimodal large language model competition with computer vision.",
            reward_usd=50_000,
            dataset_size_mb=2_000,  # 2 GB – feasible
            days_remaining=45,
            teams=400,
        )
        result = score_competition(comp)
        assert result["total_score"] >= 75
        assert "score_label" in result
        assert result["score_relevance"] > 0
        assert result["score_portfolio"] > 0
        assert result["score_prize"] > 0

    def test_low_score_competition(self):
        comp = _make_competition(
            name="Random Puzzle Game",
            description="Solve puzzles",
            reward_usd=0,
            dataset_size_mb=500_000,  # 500 GB
            days_remaining=3,
            teams=30,
        )
        result = score_competition(comp)
        assert result["total_score"] < 60

    def test_should_notify_threshold(self):
        high_comp = _make_competition(
            name="NVIDIA Deep Learning Segmentation Challenge",
            description="Computer vision semantic segmentation transformer.",
            reward_usd=25_000,
            dataset_size_mb=4_000,
            days_remaining=40,
            teams=300,
        )
        score_competition(high_comp)
        assert should_notify(high_comp)

    def test_should_not_notify_low_score(self):
        low_comp = _make_competition(
            name="Trivia Contest",
            reward_usd=0,
            dataset_size_mb=0,
            days_remaining=2,
            teams=10,
        )
        score_competition(low_comp)
        assert not should_notify(low_comp)

    def test_score_keys_present(self):
        comp = _make_competition()
        result = score_competition(comp)
        for key in [
            "score_relevance",
            "score_portfolio",
            "score_prize",
            "score_feasibility",
            "score_time",
            "score_teams",
            "total_score",
            "score_label",
        ]:
            assert key in result, f"Missing key: {key}"

    def test_total_within_bounds(self):
        """Total score must always be between 0 and 100."""
        for _ in range(10):
            comp = _make_competition(
                reward_usd=200_000,
                dataset_size_mb=1,
                days_remaining=365,
                teams=500,
            )
            result = score_competition(comp)
            assert 0 <= result["total_score"] <= 100


# ---------------------------------------------------------------------------
# Word Boundary False Positive Regressions
# ---------------------------------------------------------------------------

class TestWordBoundarySafety:
    def test_no_false_positive_for_short_keywords(self):
        # "world" contains "rl", "submit" contains "mit", "who" is a pronoun, "pineapple" contains "apple"
        comp = _make_competition(
            name="A world tour for people who submit answers about pineapple agriculture",
            description="No AI or data analysis involved here.",
        )
        score_rel = _score_relevance(comp)
        score_port = _score_portfolio(comp)
        # Should NOT trigger high score for "rl", "mit", or "who"
        assert score_rel <= 10, f"Expected <= 10 relevance, got {score_rel}"
        assert score_port <= 8, f"Expected <= 8 portfolio, got {score_port}"


    def test_genuine_rl_and_mit_matches(self):
        comp = _make_competition(
            name="Deep RL Challenge at MIT",
            description="Reinforcement learning benchmark with neural network models.",
        )
        score_rel = _score_relevance(comp)
        score_port = _score_portfolio(comp)
        assert score_rel >= 27
        assert score_port >= 8  # MIT recognized


# ---------------------------------------------------------------------------
# Prize Parsing Tests
# ---------------------------------------------------------------------------

class TestPrizeParsing:
    def test_dollar_formats(self):
        from src.kaggle_client import _parse_reward_usd
        assert _parse_reward_usd("$50,000") == 50000
        assert _parse_reward_usd("$100,000 USD") == 100000
        assert _parse_reward_usd("Top 3 get swag + $500") == 500
        assert _parse_reward_usd("5,000 TPU Hours") == 0
        assert _parse_reward_usd("Knowledge") == 0
        assert _parse_reward_usd("50000") == 50000


# ---------------------------------------------------------------------------
# Storage & Days Remaining Tests
# ---------------------------------------------------------------------------

class TestStorageAndDays:
    def test_atomic_storage(self, tmp_path):
        from src.storage import SeenCompetitionStorage
        storage_file = tmp_path / "seen.json"
        storage = SeenCompetitionStorage(path=storage_file)
        assert storage.count() == 0
        storage.mark_seen("comp-1")
        storage.mark_seen_batch(["comp-2", "comp-3"])
        assert storage.count() == 3
        assert storage.get_all() == ["comp-1", "comp-2", "comp-3"]
        assert not storage.is_new("comp-1")
        assert storage.is_new("comp-4")

        # Reload from disk
        storage2 = SeenCompetitionStorage(path=storage_file)
        assert storage2.get_all() == ["comp-1", "comp-2", "comp-3"]

    def test_days_remaining_sub_24h(self):
        from datetime import datetime, timezone, timedelta
        from src.kaggle_client import _days_remaining_from_dt
        # 12 hours in the future
        future = datetime.now(timezone.utc) + timedelta(hours=12)
        days = _days_remaining_from_dt(future)
        assert days >= 1, f"Expected at least 1 day for active competition in next 24h, got {days}"

