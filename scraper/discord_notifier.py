import logging
import random
import time
from datetime import datetime, timezone
from typing import Any, Dict, List
import requests

from scraper.config import (
    DISCORD_COLOR,
    DISCORD_IDS,
    DISCORD_PHRASES,
    DISCORD_WEBHOOK_URL,
    format_duration,
    get_multiplier,
)

logger = logging.getLogger(__name__)


class DiscordNotifier:
    def __init__(self, webhook_url: str = ""):
        self.webhook_url = webhook_url or DISCORD_WEBHOOK_URL

    def send_activity_notifications(self, activities: List[Dict[str, Any]]) -> None:
        """Sends rich Discord embeds with randomized phrases and athlete mentions."""
        if not self.webhook_url:
            logger.info("DISCORD_WEBHOOK_URL not set. Skipping Discord notifications.")
            return

        # Filter out short walks (distance <= 1.0 km)
        qualifying = [
            act for act in activities
            if act["activity_type"] != "Walk" or act["distance_km"] > 1.0
        ]

        if not qualifying:
            logger.info("No qualifying activities for Discord notification.")
            return

        logger.info(f"Sending Discord notifications for {len(qualifying)} qualifying activities...")

        for i, act in enumerate(qualifying):
            if i > 0:
                time.sleep(2.0)  # Rate limiting delay between messages

            self._send_single_notification(act)

    def _send_single_notification(self, act: Dict[str, Any]) -> bool:
        first_name = act["first_name"]
        activity_type = act["activity_type"]
        dist = act["distance_km"]
        eff_dist = act["effective_distance_km"]
        duration = act["duration_min"]
        pace = act["pace"]
        elevation = act["elevation"]
        team = act["team"]
        multiplier = get_multiplier(activity_type, first_name, pace)

        discord_id = DISCORD_IDS.get(first_name, "")
        mention = f"<@{discord_id}>" if discord_id else first_name

        phrase_template = random.choice(DISCORD_PHRASES)
        message_content = phrase_template.replace("{name}", mention).replace("{type}", activity_type)

        # Discord requires valid ISO-8601 format for embed timestamp
        iso_timestamp = datetime.now(timezone.utc).isoformat()

        embed = {
            "color": DISCORD_COLOR,
            "fields": [
                {"name": "Distance", "value": f"{dist:.2f} km", "inline": True},
                {"name": "Multiplier", "value": f"{multiplier:.2f}x", "inline": True},
                {"name": "Effort", "value": f"{eff_dist:.2f}", "inline": True},
                {"name": "Duration", "value": f"{duration:.2f} min", "inline": True},
                {"name": "Pace", "value": f"{format_duration(pace)}/km", "inline": True},
                {"name": "Elevation", "value": f"{elevation:.0f} m", "inline": True},
                {"name": "Team", "value": team, "inline": True},
            ],
            "timestamp": iso_timestamp
        }

        payload = {
            "content": message_content,
            "embeds": [embed]
        }

        max_retries = 3
        for attempt in range(max_retries + 1):
            try:
                res = requests.post(self.webhook_url, json=payload, timeout=10)
                if 200 <= res.status_code < 300:
                    logger.info(f"Discord notification sent for {first_name} ({activity_type})")
                    return True
                elif res.status_code == 429:
                    retry_after = res.json().get("retry_after", 2.0)
                    wait_time = float(retry_after) + 0.5
                    logger.warning(f"Discord rate limited (429). Waiting {wait_time}s (Attempt {attempt+1}/{max_retries+1})")
                    time.sleep(wait_time)
                else:
                    logger.error(f"Discord webhook error: {res.status_code} - {res.text}")
                    break
            except Exception as e:
                logger.error(f"Error sending Discord webhook: {e}")
                time.sleep(2.0 * (attempt + 1))

        return False
