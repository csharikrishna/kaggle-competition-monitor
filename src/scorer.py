"""
scorer.py
~~~~~~~~~
100-point scoring engine + category labels for competitions.

Scoring breakdown
-----------------
Relevance       30  – how well the topic matches ML/DL interest areas
Portfolio       20  – real-world value, org prestige, research potential
Prize           15  – cash reward tier
Feasibility     15  – dataset size vs typical hardware
Time            10  – days remaining until deadline
Competition     10  – team count sweet-spot (not too tiny, not too crowded)
---------       ---
Total          100
"""

from __future__ import annotations

import re


# ---------------------------------------------------------------------------
# Keyword pools
# ---------------------------------------------------------------------------

HIGH_PRIORITY_KEYWORDS: list[str] = [
    "computer vision",
    "object detection",
    "image classification",
    "image segmentation",
    "optical character recognition",
    "ocr",
    "deep learning",
    "neural network",
    "convolutional",
    "transformer",
    "nlp",
    "natural language processing",
    "large language model",
    "llm",
    "language model",
    "generative ai",
    "gen ai",
    "multimodal",
    "diffusion",
    "stable diffusion",
    "time series",
    "forecasting",
    "anomaly detection",
    "recommendation",
    "reinforcement learning",
    "rl",
    "self-supervised",
    "contrastive learning",
    "foundation model",
    "pretrained",
    "fine-tuning",
    "speech recognition",
    "audio",
    "3d",
    "point cloud",
    "medical imaging",
    "satellite",
    "remote sensing",
]

MEDIUM_PRIORITY_KEYWORDS: list[str] = [
    "machine learning",
    "classification",
    "regression",
    "clustering",
    "feature engineering",
    "gradient boosting",
    "xgboost",
    "lightgbm",
    "tabular",
    "structured data",
    "neural",
    "prediction",
    "fraud detection",
    "sentiment analysis",
    "text classification",
    "named entity",
]

PRESTIGIOUS_ORGS: list[str] = [
    "google",
    "meta",
    "microsoft",
    "amazon",
    "apple",
    "nvidia",
    "openai",
    "deepmind",
    "anthropic",
    "hugging face",
    "nasa",
    "world health organization",
    "world health",
    "mit",
    "stanford",
    "cern",
    "ieee",
    "neurips",
    "cvpr",
    "iclr",
    "icml",
]

RESEARCH_KEYWORDS: list[str] = [
    "research",
    "novel",
    "benchmark",
    "challenge",
    "workshop",
    "competition",
    "dataset",
    "survey",
]


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------


def _contains_keyword(kw: str, text: str) -> bool:
    """Return True if kw matches text using non-word boundary checks."""
    if not kw or not text:
        return False
    # Use word boundary / non-word character lookarounds
    escaped = re.escape(kw.lower())
    pattern = rf"(?<!\w){escaped}(?!\w)"
    return bool(re.search(pattern, text, re.IGNORECASE))


def _text(competition: dict) -> str:
    """Combine searchable fields into one lowercase string."""
    parts = [
        competition.get("name", ""),
        competition.get("description", ""),
        competition.get("category", ""),
        competition.get("evaluation_metric", ""),
        " ".join(competition.get("modalities", [])),
    ]
    return " ".join(parts).lower()


def _score_relevance(competition: dict) -> int:
    """30 points – keyword relevance to ML/DL topics."""
    text = _text(competition)

    # Count weighted keyword hits with word boundaries
    high_hits = sum(1 for kw in HIGH_PRIORITY_KEYWORDS if _contains_keyword(kw, text))
    med_hits = sum(1 for kw in MEDIUM_PRIORITY_KEYWORDS if _contains_keyword(kw, text))

    # Map to 0–30
    if high_hits >= 3:
        return 30
    if high_hits == 2:
        return 27
    if high_hits == 1:
        return 22 if med_hits >= 1 else 20
    if med_hits >= 3:
        return 17
    if med_hits >= 1:
        return 13
    return 5


def _score_portfolio(competition: dict) -> int:
    """20 points – portfolio / research value."""
    text = _text(competition)
    score = 0

    # Prestigious organizer with word boundaries
    if any(_contains_keyword(org, text) for org in PRESTIGIOUS_ORGS):
        score += 8

    # Research / benchmark potential
    research_hits = sum(1 for kw in RESEARCH_KEYWORDS if _contains_keyword(kw, text))
    score += min(research_hits * 2, 6)

    # Real-world problem signals
    real_world_signals = [
        "health",
        "medical",
        "climate",
        "environment",
        "safety",
        "autonomous",
        "robot",
        "robotics",
        "drug",
        "cancer",
        "covid",
        "pandemic",
        "disaster",
        "wildfire",
        "agriculture",
        "finance",
        "fraud",
    ]
    if any(_contains_keyword(s, text) for s in real_world_signals):
        score += 4

    # Technical challenge richness
    modalities: list[str] = competition.get("modalities", [])
    if len(modalities) >= 2:  # multimodal → more interesting
        score += 2

    return min(score, 20)


def _score_prize(reward_usd: int) -> int:
    """15 points – cash prize tier."""
    if reward_usd >= 100_000:
        return 15
    if reward_usd >= 50_000:
        return 13
    if reward_usd >= 25_000:
        return 11
    if reward_usd >= 10_000:
        return 9
    if reward_usd >= 5_000:
        return 7
    if reward_usd > 0:
        return 4
    return 1  # "Knowledge" / merchandise competitions still have value


def _score_feasibility(dataset_size_mb: float) -> int:
    """
    15 points – dataset size vs consumer hardware.

    <500 MB   -> 15  (fits in RAM, fast iteration)
    <5 GB     -> 13  (comfortable on a laptop)
    <20 GB    -> 10  (needs SSD + patience)
    <50 GB    -> 7   (dedicated GPU workstation or colab pro)
    <100 GB   -> 4   (cloud GPU required)
    >=100 GB  -> 2   (serious infra needed)
    unknown   -> 8   (neutral)
    """

    if dataset_size_mb <= 0:
        return 8  # unknown – neutral score
    if dataset_size_mb < 500:
        return 15
    if dataset_size_mb < 5_120:     # 5 GB
        return 13
    if dataset_size_mb < 20_480:    # 20 GB
        return 10
    if dataset_size_mb < 51_200:    # 50 GB
        return 7
    if dataset_size_mb < 102_400:   # 100 GB
        return 4
    return 2


def _score_time(days_remaining: int) -> int:
    """10 points – time remaining until deadline."""
    if days_remaining >= 60:
        return 10
    if days_remaining >= 30:
        return 9
    if days_remaining >= 14:
        return 6
    if days_remaining >= 7:
        return 3
    return 1


def _score_competition_size(teams: int) -> int:
    """
    10 points – sweet-spot between too small and too crowded.

    < 50       → 4   (possibly niche / low-quality)
    50–200     → 7   (small, good to get noticed)
    200–1000   → 10  (healthy, meaningful ranking)
    1000–5000  → 8   (popular, competitive)
    5000–15000 → 5   (very competitive)
    >15000     → 2   (titan competition, hard to rank)
    0          → 6   (new / data not yet available)
    """
    if teams == 0:
        return 6
    if teams < 50:
        return 4
    if teams < 200:
        return 7
    if teams < 1_000:
        return 10
    if teams < 5_000:
        return 8
    if teams < 15_000:
        return 5
    return 2


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

CATEGORY_THRESHOLDS = [
    (90, "Tier 1 (High Priority)"),
    (75, "Tier 2 (Recommended)"),
    (60, "Tier 3 (Moderate)"),
    (0,  "Tier 4 (Low Priority)"),
]

MIN_NOTIFY_SCORE = 75  # only competitions at or above this score get notified



def score_competition(competition: dict) -> dict:
    """
    Compute the 100-point score for *competition* and add scoring data.

    Adds to the dict in-place (and returns it):
        score_relevance  int
        score_portfolio  int
        score_prize      int
        score_feasibility int
        score_time       int
        score_teams      int
        total_score      int
        score_label      str   e.g. "Tier 1 (High Priority)"
    """
    s_rel  = _score_relevance(competition)
    s_port = _score_portfolio(competition)
    s_pri  = _score_prize(competition.get("reward_usd", 0))
    s_feas = _score_feasibility(competition.get("dataset_size_mb", 0.0))
    s_time = _score_time(competition.get("days_remaining", 0))
    s_team = _score_competition_size(competition.get("teams", 0))

    total = s_rel + s_port + s_pri + s_feas + s_time + s_team

    label = next(
        label for threshold, label in CATEGORY_THRESHOLDS if total >= threshold
    )

    competition.update(
        {
            "score_relevance":   s_rel,
            "score_portfolio":   s_port,
            "score_prize":       s_pri,
            "score_feasibility": s_feas,
            "score_time":        s_time,
            "score_teams":       s_team,
            "total_score":       total,
            "score_label":       label,
        }
    )
    return competition


def should_notify(competition: dict, min_score: int = MIN_NOTIFY_SCORE) -> bool:
    """Return True if total_score meets the notification threshold."""
    return competition.get("total_score", 0) >= min_score
