import logging
from typing import Any, Dict, List, Set
import requests

from scraper.config import SHEET_WEBHOOK_URL, WEBHOOK_SECRET_KEY

logger = logging.getLogger(__name__)


class SheetSync:
    def __init__(self, webhook_url: str = "", secret_key: str = ""):
        self.webhook_url = webhook_url or SHEET_WEBHOOK_URL
        self.secret_key = secret_key or WEBHOOK_SECRET_KEY

    def get_existing_ids(self) -> Set[str]:
        """Fetches already logged unique activity IDs from Google Sheet via Apps Script webhook."""
        if not self.webhook_url:
            logger.warning("SHEET_WEBHOOK_URL not configured. Cannot check existing activity IDs.")
            return set()

        url = f"{self.webhook_url}?action=get_ids&secret={self.secret_key}"
        try:
            res = requests.get(url, timeout=15)
            if res.status_code == 200:
                data = res.json()
                ids = set(data.get("existingIds", []))
                logger.info(f"Retrieved {len(ids)} existing activity IDs from Google Sheet.")
                return ids
            else:
                logger.error(f"Failed to fetch existing IDs: HTTP {res.status_code} - {res.text}")
        except Exception as e:
            logger.error(f"Error connecting to Apps Script sheet webhook: {e}")

        return set()

    def append_activities(self, activities: List[Dict[str, Any]]) -> tuple[int, Set[str]]:
        """Sends newly scraped activities to Apps Script webhook to append to Data tab.
        Returns (added_count, set_of_added_ids).
        """
        if not self.webhook_url or not activities:
            return 0, set()

        # Map activity dicts to exact Google Sheet row format
        rows = [
            [
                act["unique_id"],
                act["first_name"],
                act["team"],
                act["date"],
                act["distance_km"],
                act["effective_distance_km"],
                act["duration_min"],
                act["pace"],
                act["elevation"],
                act["activity_type"]
            ]
            for act in activities
        ]

        payload = {
            "secret": self.secret_key,
            "action": "append_rows",
            "rows": rows
        }

        try:
            res = requests.post(self.webhook_url, json=payload, timeout=20)
            if res.status_code == 200:
                data = res.json()
                added_count = data.get("addedCount", 0)
                added_ids = set(data.get("addedIds", []))
                logger.info(f"Successfully appended {added_count} new rows to Google Sheet.")
                return added_count, added_ids
            else:
                logger.error(f"Apps Script webhook error appending rows: HTTP {res.status_code} - {res.text}")
        except Exception as e:
            logger.error(f"Error appending activities to Google Sheet: {e}")

        return 0, set()
