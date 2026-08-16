"""
start.py
~~~~~~~~
1-Click Interactive Starter and Setup Wizard for Kaggle Competition Monitor.

Run with:
    python start.py
or double-click start.bat
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

# Fix terminal encoding on Windows
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

ROOT_DIR = Path(__file__).parent
ENV_PATH = ROOT_DIR / ".env"
ENV_EXAMPLE_PATH = ROOT_DIR / ".env.example"

# ANSI Colors for terminal UI
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


def print_banner() -> None:
    banner = f"""{CYAN}{BOLD}
==============================================================================
  KAGGLE COMPETITION MONITOR
  Automated ML Competition Discovery, Scoring & Alert Engine
=============================================================================={RESET}"""
    print(banner)
    print(f"{DIM}Version: 2.0.0 | OS: {sys.platform} | Python: {sys.version.split()[0]}{RESET}\n")


def check_dependencies() -> bool:
    """Verify that all required packages are installed."""
    required = ["kaggle", "requests", "dotenv", "pytest"]
    missing = []
    for pkg in required:
        try:
            if pkg == "dotenv":
                import dotenv  # noqa: F401
            elif pkg == "kaggle":
                import kaggle  # noqa: F401
            elif pkg == "requests":
                import requests  # noqa: F401
            elif pkg == "pytest":
                import pytest  # noqa: F401
        except ImportError:
            missing.append(pkg)

    if missing:
        print(f"{YELLOW}[WARN] Missing required dependencies: {', '.join(missing)}{RESET}")
        print(f"Installing missing dependencies automatically...\n")
        import subprocess
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", str(ROOT_DIR / "requirements.txt")])
            print(f"{GREEN}[OK] Dependencies installed successfully.{RESET}\n")
            return True
        except subprocess.CalledProcessError:
            print(f"{RED}[ERROR] Failed to install dependencies. Please run: pip install -r requirements.txt{RESET}\n")
            return False
    return True


def check_credentials_status() -> dict[str, bool]:
    """Check which credentials are configured."""
    has_token = bool(os.environ.get("KAGGLE_API_TOKEN", "").strip())
    has_user_key = bool(
        os.environ.get("KAGGLE_USERNAME", "").strip() and os.environ.get("KAGGLE_KEY", "").strip()
    )
    kaggle_dir = Path.home() / ".kaggle"
    has_kaggle_dir = (kaggle_dir / "access_token").exists() or (kaggle_dir / "kaggle.json").exists()

    kaggle_ready = has_token or has_user_key or has_kaggle_dir

    tg_token = bool(os.environ.get("TELEGRAM_BOT_TOKEN", "").strip())
    tg_chat = bool(os.environ.get("TELEGRAM_CHAT_ID", "").strip())
    tg_ready = tg_token and tg_chat

    return {
        "kaggle": kaggle_ready,
        "telegram": tg_ready,
        "env_exists": ENV_PATH.exists(),
    }


def run_setup_wizard() -> None:
    """Interactive wizard to guide user through creating or updating .env."""
    print(f"\n{BOLD}Configuration Wizard{RESET}")
    print(f"{'-' * 60}")
    print(f"Configure Kaggle and Telegram API credentials:\n")


    current_token = os.environ.get("KAGGLE_API_TOKEN", "")
    current_tg_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    current_tg_chat = os.environ.get("TELEGRAM_CHAT_ID", "")
    current_min_score = os.environ.get("MIN_SCORE", "75")

    # 1. Kaggle Token
    print(f"{BOLD}1. Kaggle API Token:{RESET}")
    print(f"   URL: {CYAN}https://www.kaggle.com/settings{RESET} -> API -> 'Create New Token'")
    display_token = f"{current_token[:8]}..." if current_token else "none"
    kaggle_input = input(f"   KAGGLE_API_TOKEN [{display_token}]: ").strip()
    if kaggle_input:
        current_token = kaggle_input

    # 2. Telegram Bot Token
    print(f"\n{BOLD}2. Telegram Bot Token:{RESET}")
    print(f"   Message @BotFather on Telegram -> /newbot -> Copy token")
    display_tg = f"{current_tg_token[:8]}..." if current_tg_token else "none"
    tg_token_input = input(f"   TELEGRAM_BOT_TOKEN [{display_tg}]: ").strip()
    if tg_token_input:
        current_tg_token = tg_token_input

    # 3. Telegram Chat ID
    print(f"\n{BOLD}3. Telegram Chat ID:{RESET}")
    print(f"   Message @userinfobot on Telegram to obtain your numeric chat ID")
    display_chat = current_tg_chat if current_tg_chat else "none"
    tg_chat_input = input(f"   TELEGRAM_CHAT_ID [{display_chat}]: ").strip()
    if tg_chat_input:
        current_tg_chat = tg_chat_input

    # 4. Min Score
    print(f"\n{BOLD}4. Minimum Notification Score Threshold (0-100):{RESET}")
    score_input = input(f"   MIN_SCORE [{current_min_score}]: ").strip()
    if score_input.isdigit():
        current_min_score = score_input

    # Write .env
    env_content = f"""# Kaggle Competition Monitor Configuration
KAGGLE_API_TOKEN={current_token}
TELEGRAM_BOT_TOKEN={current_tg_token}
TELEGRAM_CHAT_ID={current_tg_chat}
MIN_SCORE={current_min_score}
MAX_PAGES=3
MAX_DATASET_MB=5120
"""
    ENV_PATH.write_text(env_content, encoding="utf-8")
    
    # Reload environment
    try:
        from dotenv import load_dotenv
        load_dotenv(override=True)
    except Exception:
        pass
    
    os.environ["KAGGLE_API_TOKEN"] = current_token
    os.environ["TELEGRAM_BOT_TOKEN"] = current_tg_token
    os.environ["TELEGRAM_CHAT_ID"] = current_tg_chat
    os.environ["MIN_SCORE"] = current_min_score

    print(f"\n{GREEN}[OK] Configuration saved to .env successfully.{RESET}\n")


def run_diagnostics() -> bool:
    """Test Kaggle and Telegram connections."""
    print(f"{BOLD}Preflight System Diagnostics{RESET}")
    print(f"{'-' * 60}")

    # 1. Kaggle Check
    print("  * Kaggle API Authentication:     ", end="", flush=True)
    try:
        from src.kaggle_client import KaggleClient
        client = KaggleClient()
        test_fetch = client.fetch_competitions(page=1, page_size=1)
        print(f"{GREEN}[PASS] (Response verified, {len(test_fetch)} sample){RESET}")
        kaggle_ok = True
    except Exception as exc:
        print(f"{RED}[FAIL] ({exc}){RESET}")
        kaggle_ok = False

    # 2. Telegram Check
    print("  * Telegram Bot Connectivity:     ", end="", flush=True)
    try:
        from src.telegram_bot import TelegramBot
        bot = TelegramBot()
        if bot.send_test():
            print(f"{GREEN}[PASS] (Test message delivered){RESET}")
            tg_ok = True
        else:
            print(f"{RED}[FAIL] (Message rejected by Telegram API){RESET}")
            tg_ok = False
    except Exception as exc:
        print(f"{RED}[FAIL] ({exc}){RESET}")
        tg_ok = False

    print()
    return kaggle_ok and tg_ok



def continuous_monitor_loop() -> None:
    """Run continuous monitoring loop."""
    print(f"\n{BOLD}Continuous Scheduled Daemon Active{RESET}")
    print("Interval: 6 hours (Press Ctrl+C to interrupt)\n")
    try:
        from main import run as run_pipeline
        while True:
            print(f"{CYAN}[INFO] Executing scan cycle at {time.strftime('%Y-%m-%d %H:%M:%S')}...{RESET}")
            run_pipeline(dry_run=False)
            next_time = time.strftime('%H:%M:%S', time.localtime(time.time() + 21600))
            print(f"\n{DIM}[IDLE] Next scheduled execution at {next_time}.{RESET}\n")
            time.sleep(21600)
    except KeyboardInterrupt:
        print(f"\n{YELLOW}[INFO] Continuous scheduler stopped by user.{RESET}\n")


def show_menu() -> None:
    """Display the interactive main menu."""
    while True:
        status = check_credentials_status()
        k_icon = f"{GREEN}[READY]{RESET}" if status["kaggle"] else f"{RED}[NOT SET]{RESET}"
        t_icon = f"{GREEN}[READY]{RESET}" if status["telegram"] else f"{RED}[NOT SET]{RESET}"

        print(f"{BOLD}Select an operation:{RESET}")
        print(f"  [1] Start Interactive Telegram Bot  Run 2-way bot service (handles /start, /scan, /top)")
        print(f"  [2] Run One-Shot Monitor Scan       Execute immediate scan & broadcast to subscribers")
        print(f"  [3] Run Dry-Run Preview             Evaluate active competitions in terminal table")
        print(f"  [4] Run Test Suite                  Execute automated verification tests (pytest)")
        print(f"  [5] View Subscribers & History      List active subscribers and notified competition IDs")
        print(f"  [6] Run Preflight Diagnostics       Verify API credentials and connectivity")
        print(f"  [7] Configuration Wizard            Review or update environment settings [Kaggle: {k_icon} | Telegram: {t_icon}]")
        print(f"  [8] Exit")

        choice = input(f"\n{CYAN}Choice [1-8]: {RESET}").strip()

        if choice == "1":
            from bot import run_interactive_bot
            run_interactive_bot()

        elif choice == "2":
            from main import run as run_pipeline
            print(f"\n{CYAN}[INFO] Starting one-shot scan execution...{RESET}")
            try:
                run_pipeline(dry_run=False)
            except Exception as e:
                print(f"{RED}[ERROR] {e}{RESET}")
            print()

        elif choice == "3":
            from main import run as run_pipeline
            print(f"\n{CYAN}[INFO] Starting dry-run preview...{RESET}")
            try:
                run_pipeline(dry_run=True)
            except Exception as e:
                print(f"{RED}[ERROR] {e}{RESET}")
            print()

        elif choice == "4":
            import subprocess
            print(f"\n{CYAN}[INFO] Executing test suite...{RESET}\n")
            subprocess.run([sys.executable, "-m", "pytest", "tests/", "-v"])
            print()

        elif choice == "5":
            from src.subscribers import SubscriberStorage
            from src.storage import SeenCompetitionStorage
            subs = SubscriberStorage()
            storage = SeenCompetitionStorage()
            sub_ids = subs.get_all_chat_ids()
            comp_ids = storage.get_all()
            print(f"\n{BOLD}Active Subscribers ({len(sub_ids)}):{RESET}")
            for sid in sub_ids:
                print(f"  * Chat ID: {sid}")
            print(f"\n{BOLD}Notified History ({len(comp_ids)} total):{RESET}")
            if not comp_ids:
                print(f"  {DIM}(No historical records found){RESET}")
            for cid in comp_ids:
                print(f"  * {cid}")
            print()


        elif choice == "6":
            run_diagnostics()

        elif choice == "7":
            run_setup_wizard()

        elif choice == "8" or choice.lower() in ("q", "exit"):
            print(f"\n{GREEN}Shutdown complete.{RESET}\n")
            break
        else:
            print(f"{YELLOW}[WARN] Invalid selection. Choose an option between 1 and 8.{RESET}\n")



def main() -> None:
    print_banner()

    if not check_dependencies():
        input("\nPress Enter to exit...")
        sys.exit(1)

    status = check_credentials_status()

    # If first time or missing credentials, offer setup wizard automatically
    if not status["kaggle"] or not status["telegram"]:
        print(f"{YELLOW}[NOTICE] API credentials are not fully configured.{RESET}")
        wizard_choice = input(f"Launch Configuration Wizard now? (Y/n): ").strip().lower()
        if wizard_choice in ("", "y", "yes"):
            run_setup_wizard()

    show_menu()


if __name__ == "__main__":
    main()

