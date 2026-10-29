"""Opt-in notifications; never send without explicit configuration."""

import logging
import os
from typing import Mapping

import httpx

logger = logging.getLogger(__name__)


def notify_failure(
    run_id: str, job_name: str, *, env: Mapping[str, str] | None = None, client=None
) -> bool:
    settings = os.environ if env is None else env
    if settings.get("TELEGRAM_ENABLED", "false").lower() != "true":
        logger.info("Telegram notification disabled")
        return False
    token, chat_id = settings.get("TELEGRAM_BOT_TOKEN"), settings.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        logger.warning("Telegram notification skipped: token or chat ID is missing")
        return False
    # httpx logs full URLs at INFO, and this URL contains the bot token.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    # Never log the response, request, or exception text.
    message = f"Marketplace pipeline failed: job={job_name}, run_id={run_id}. Check Dagster logs."
    try:
        if client is None:
            with httpx.Client(timeout=5.0) as owned_client:
                response = owned_client.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={"chat_id": chat_id, "text": message},
                )
        else:
            response = client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": message},
            )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or payload.get("ok") is not True:
            logger.warning("Telegram API rejected notification")
            return False
        return True
    except (httpx.HTTPError, ValueError):
        logger.warning("Telegram notification failed; see network and configuration")
        return False
