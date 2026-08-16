"""
setup_kaggle_auth.py
~~~~~~~~~~~~~~~~~~~~
One-time helper: reads KAGGLE_API_TOKEN from .env and writes it to
~/.kaggle/access_token so the kaggle library finds it automatically.

Run once:
    python setup_kaggle_auth.py
"""
import os
import pathlib
import sys

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

token = os.environ.get("KAGGLE_API_TOKEN", "").strip()

if not token:
    print("ERROR: KAGGLE_API_TOKEN is empty in your .env file.")
    print("Open .env and make sure you have:")
    print("  KAGGLE_API_TOKEN=KGAT_your_token_here")
    sys.exit(1)

if not token.startswith("KGAT_"):
    print(f"WARNING: Token doesn't start with KGAT_ — got: {token[:10]}...")
    print("This may not be a new-style Kaggle token.")

kaggle_dir = pathlib.Path.home() / ".kaggle"
kaggle_dir.mkdir(exist_ok=True)

access_token_path = kaggle_dir / "access_token"
access_token_path.write_text(token, encoding="utf-8")

print(f"Written token to: {access_token_path}")
print("Next steps:")
print("  python start.py   (Interactive Starter)")
print("  python bot.py     (Interactive Telegram Bot)")

