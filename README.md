# Kaggle Competition Monitor

Automated system for discovering, evaluating, and alerting on high-quality Kaggle competitions.

---

## Features

- Fetches active Kaggle competitions via the official API
- Enriches competitions with dataset metadata (size, file types, modality)
- 100-point multi-dimensional scoring engine
- Deduplication storage to prevent duplicate notifications
- Structured Telegram notifications with metric breakdowns
- Automated execution via GitHub Actions (scheduled runs at 09:00 and 21:00 UTC)

---

## Project Structure

```
kaggle-competition-monitor/
├── src/
│   ├── kaggle_client.py      # Kaggle API wrapper and data normalization
│   ├── dataset_analyzer.py   # Dataset metadata inspection (size, modalities)
│   ├── scorer.py             # 100-point scoring engine
│   ├── storage.py            # Deduplication persistence layer (atomic JSON)
│   └── telegram_bot.py       # Message formatting and Telegram dispatch
├── data/
│   └── seen_competitions.json
├── tests/
│   └── test_scorer.py
├── main.py                   # CLI and orchestration entry point
├── start.py                  # Interactive CLI starter & setup wizard
├── start.bat                 # Windows one-click launcher
├── requirements.txt
├── .env.example
└── .github/workflows/monitor.yml
```

---

## Telegram Bot Interaction

Any user can start receiving alerts immediately by interacting with your bot on Telegram:

1. Open your bot in Telegram and send **`/start`**
2. The bot sends a welcome confirmation and automatically registers you for real-time broadcasts.

### Available Commands in Telegram

| Command   | Action                                                                  |
|:----------|:------------------------------------------------------------------------|
| `/start`  | Subscribe to automated competition alerts and view command guide        |
| `/scan`   | Trigger a real-time scan and receive immediate breakdown of top contests|
| `/top`    | View the top highest-scoring active Kaggle competitions                 |
| `/status` | Check your subscription state and active score threshold settings      |
| `/help`   | Display command reference and documentation                             |
| `/stop`   | Unsubscribe from automated alert broadcasts                             |

---

## Running the Bot Server

```bash
# Start interactive 2-way Telegram Bot daemon with live background scheduler
python bot.py

# Or launch via interactive starter menu
python start.py
```

---

## Quick Start

### Option 1: Interactive Starter (Recommended)

On Windows, double-click **`start.bat`**, or run:

```bash
python start.py
```

The interactive starter provides:
- Automated dependency validation
- Interactive configuration wizard for API credentials
- Preflight diagnostics to test Kaggle and Telegram connectivity
- Menu for live scans, dry-run previews, scheduled daemon mode, and test execution

---

### Option 2: CLI Usage

#### 1. Install dependencies
```bash
pip install -r requirements.txt
```

#### 2. Configure credentials
```bash
cp .env.example .env
# Configure .env with your credentials
```

- **Kaggle Token**: [kaggle.com/settings](https://www.kaggle.com/settings) -> API -> *Create New Token*
- **Telegram Bot**: Message [@BotFather](https://t.me/BotFather) on Telegram -> `/newbot`
- **Telegram Chat ID**: Message [@userinfobot](https://t.me/userinfobot) on Telegram

#### 3. Execution
```bash
# Dry-run: score active competitions and output terminal table
python main.py --dry-run

# Test Telegram connectivity
python main.py --test-telegram

# Full live scan and dispatch
python main.py

# Run test suite
python -m pytest tests/ -v
```

---

## Scoring Breakdown

| Dimension       | Points | Description                                    |
|:----------------|:-------|:-----------------------------------------------|
| Relevance       | 30     | Keyword relevance (CV, NLP, LLM, DL, etc.)     |
| Portfolio Value | 20     | Real-world application, organizer, research fit|
| Prize Pool      | 15     | Cash reward tier evaluation                    |
| Feasibility     | 15     | Dataset size relative to standard hardware     |
| Time Remaining  | 10     | Days remaining until deadline                  |
| Competition     | 10     | Team participation volume                      |
| **Total**       | **100**|                                                |

**Default notification threshold**: >= 75 points (Tier 1 & Tier 2)

---

## Notification Tiers

| Score Range | Tier Label                 | Action      |
|:------------|:---------------------------|:------------|
| 90–100      | Tier 1 (High Priority)     | Notified    |
| 75–89       | Tier 2 (Recommended)       | Notified    |
| 60–74       | Tier 3 (Moderate)          | Logged Only |
| < 60        | Tier 4 (Low Priority)      | Ignored     |

---

## GitHub Actions Setup

1. Push repository to GitHub
2. Navigate to **Settings -> Secrets and variables -> Actions**
3. Add repository secrets:
   - `KAGGLE_API_TOKEN` (or `KAGGLE_USERNAME` + `KAGGLE_KEY`)
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
4. The workflow executes automatically at 09:00 and 21:00 UTC daily.
5. Manual trigger: **Actions -> Kaggle Competition Monitor -> Run workflow**

---

## CLI Reference

```
python main.py --dry-run         Score competitions and print table without dispatching
python main.py --test-telegram   Send connectivity test message and exit
python main.py --list-seen       Print all previously notified competition IDs
```

---

## Environment Variables

| Variable            | Required | Default | Description                                |
|:--------------------|:---------|:--------|:-------------------------------------------|
| `KAGGLE_API_TOKEN`  | Yes*     | —       | Kaggle API token (new format)              |
| `KAGGLE_USERNAME`   | Yes*     | —       | Kaggle username (legacy format)            |
| `KAGGLE_KEY`        | Yes*     | —       | Kaggle API key (legacy format)             |
| `TELEGRAM_BOT_TOKEN`| Yes      | —       | Bot token from @BotFather                  |
| `TELEGRAM_CHAT_ID`  | Yes      | —       | Comma-separated recipient chat IDs         |
| `MAX_PAGES`         | No       | `3`     | Number of API pages to query (100/page)    |
| `MIN_SCORE`         | No       | `75`    | Minimum score threshold for notifications  |
| `MAX_DATASET_MB`    | No       | `5120`  | Max dataset size in MB to alert (5 GB)     |

*\*Either `KAGGLE_API_TOKEN` or both `KAGGLE_USERNAME` and `KAGGLE_KEY` are required.*

