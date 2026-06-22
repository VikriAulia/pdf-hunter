"""Webhook notifier for Discord, Slack, and Telegram."""
from __future__ import annotations

import logging
from typing import Iterable, Optional

import requests

from .config import WebhookConfig


def _post(url: str, json_body: dict, timeout: float = 10.0) -> bool:
    try:
        resp = requests.post(url, json=json_body, timeout=timeout)
        return 200 <= resp.status_code < 300
    except Exception as exc:
        logging.warning("Webhook POST %s failed: %s", url, exc)
        return False


def notify_discord(url: str, message: str) -> bool:
    return _post(url, {"content": message[:1900]})


def notify_slack(url: str, message: str) -> bool:
    return _post(url, {"text": message[:2900]})


def notify_telegram(token: str, chat_id: str, message: str) -> bool:
    if not token or not chat_id:
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    return _post(url, {"chat_id": chat_id, "text": message[:3900]})


def send(cfg: WebhookConfig, message: str) -> dict:
    """Send ``message`` to all enabled channels. Returns per-channel status."""
    results = {}
    if not cfg.enabled:
        return results
    if cfg.discord_url:
        results["discord"] = notify_discord(cfg.discord_url, message)
    if cfg.slack_url:
        results["slack"] = notify_slack(cfg.slack_url, message)
    if cfg.telegram_token and cfg.telegram_chat_id:
        results["telegram"] = notify_telegram(
            cfg.telegram_token, cfg.telegram_chat_id, message,
        )
    return results


def format_summary(*, status: str, pages: int, files: int,
                   duration: float, new_files: Iterable[str]) -> str:
    new_files = list(new_files)
    preview = "\n".join(f"• {f}" for f in new_files[:10])
    if len(new_files) > 10:
        preview += f"\n…and {len(new_files) - 10} more"
    return (
        f"PDF Hunter run **{status}**\n"
        f"Pages crawled: {pages}\n"
        f"Files downloaded: {files}\n"
        f"Duration: {duration:.1f}s\n"
        + (f"\nNew files:\n{preview}" if preview else "")
    )
