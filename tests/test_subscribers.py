"""
test_subscribers.py
~~~~~~~~~~~~~~~~~~~
Unit tests for subscriber persistence and Telegram bot commands.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Allow importing src without installing the package
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.subscribers import SubscriberStorage


def test_subscriber_registration(tmp_path):
    sub_file = tmp_path / "subscribers.json"
    storage = SubscriberStorage(path=sub_file)

    assert storage.count() == 0
    assert not storage.is_subscribed("12345")

    # First subscription
    is_new = storage.subscribe("12345", username="johndoe", first_name="John")
    assert is_new is True
    assert storage.count() == 1
    assert storage.is_subscribed("12345")

    # Second subscription (same ID)
    is_new_again = storage.subscribe("12345", username="johndoe_updated", first_name="John")
    assert is_new_again is False
    assert storage.count() == 1

    # Reload from disk
    storage_reloaded = SubscriberStorage(path=sub_file)
    assert storage_reloaded.count() == 1
    assert storage_reloaded.is_subscribed("12345")


def test_subscriber_unsubscribe(tmp_path):
    sub_file = tmp_path / "subscribers.json"
    storage = SubscriberStorage(path=sub_file)

    storage.subscribe("111", username="user1")
    storage.subscribe("222", username="user2")
    assert storage.count() == 2

    removed = storage.unsubscribe("111")
    assert removed is True
    assert storage.count() == 1
    assert not storage.is_subscribed("111")
    assert storage.is_subscribed("222")

    # Removing non-existent
    assert storage.unsubscribe("999") is False


def test_get_all_chat_ids_merging(tmp_path, monkeypatch):
    sub_file = tmp_path / "subscribers.json"
    storage = SubscriberStorage(path=sub_file)
    storage.subscribe("100", username="alice")
    storage.subscribe("200", username="bob")

    monkeypatch.setenv("TELEGRAM_CHAT_ID", "300, 400, 100")
    all_ids = storage.get_all_chat_ids()

    assert all_ids == ["100", "200", "300", "400"]
