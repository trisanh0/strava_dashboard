import argparse
import logging
import sys
import time
from datetime import datetime

from scraper.config import POLL_INTERVAL_MINUTES
from scraper.discord_notifier import DiscordNotifier
from scraper.sheet_sync import SheetSync
from scraper.strava import StravaClubScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("strava_scraper")


class DuplicateChecker:
    def __init__(self, existing_id_list):
        self.exact_set = set(str(eid).strip() for eid in existing_id_list if eid)
        self.parsed_list = []
        for eid in existing_id_list:
            parts = str(eid).strip().split("_")
            if len(parts) >= 5:
                try:
                    first = parts[0].strip().lower()
                    dist = float(parts[2])
                    time_sec = float(parts[3])
                    title = "_".join(parts[4:]).strip().lower()
                    self.parsed_list.append({
                        "first": first,
                        "dist": dist,
                        "time": time_sec,
                        "title": title
                    })
                except ValueError:
                    pass

    def is_duplicate(self, act: dict) -> bool:
        uid = act["unique_id"]
        if uid in self.exact_set:
            return True

        first = act["first_name"].strip().lower()
        title = act["title"].replace(" ", "_").strip().lower()
        dist_m = act["distance_km"] * 1000.0
        time_s = act["duration_min"] * 60.0

        for existing in self.parsed_list:
            if existing["first"] == first and existing["title"] == title:
                dist_diff = abs(existing["dist"] - dist_m)
                time_diff = abs(existing["time"] - time_s)
                if (time_diff <= 120 or time_diff / max(existing["time"], 1) <= 0.05) or \
                   (dist_diff <= 150 or dist_diff / max(existing["dist"], 1) <= 0.08):
                    return True

        return False


def run_scrape_cycle() -> int:
    """Executes a single scrape, deduplication, sheet update, and Discord notification cycle."""
    logger.info("Starting Strava scraping cycle...")

    scraper = StravaClubScraper()
    sheet_sync = SheetSync()
    discord_notifier = DiscordNotifier()

    # 1. Fetch existing activity IDs from Google Sheet
    existing_ids = sheet_sync.get_existing_ids()
    dup_checker = DuplicateChecker(existing_ids)

    # 2. Scrape recent club activities from Strava
    scraped_activities = scraper.fetch_recent_activities()
    if not scraped_activities:
        logger.info("No activities returned from Strava club feed.")
        return 0

    # 3. Deduplicate
    new_activities = []
    seen_ids = set()

    for act in scraped_activities:
        uid = act["unique_id"]
        if dup_checker.is_duplicate(act):
            logger.info(f"Duplicate (already logged): {uid}")
        elif uid in seen_ids:
            logger.info(f"Duplicate in current batch: {uid}")
        else:
            logger.info(f"NEW activity detected: {uid}")
            new_activities.append(act)
            seen_ids.add(uid)

    logger.info(f"Found {len(new_activities)} new activities (out of {len(scraped_activities)} scraped).")

    if not new_activities:
        logger.info("No new activities to process.")
        return 0

    # 4. Append new activities to Google Sheet
    added_count = sheet_sync.append_activities(new_activities)

    # 5. Dispatch Discord notifications
    discord_notifier.send_activity_notifications(new_activities)

    logger.info(f"Scrape cycle complete. Added {added_count} items to Google Sheet.")
    return len(new_activities)


def main():
    parser = argparse.ArgumentParser(description="Strava Club Activity Scraper Service")
    parser.add_argument("--once", action="store_true", help="Run a single scrape cycle and exit")
    args = parser.parse_args()

    logger.info("=== Strava Club Scraper Service Initialized ===")

    if args.once:
        run_scrape_cycle()
        logger.info("Single run complete. Exiting.")
        return

    interval_sec = max(POLL_INTERVAL_MINUTES, 5) * 60
    logger.info(f"Starting continuous polling loop (interval: {POLL_INTERVAL_MINUTES} minutes)...")

    while True:
        try:
            run_scrape_cycle()
        except Exception as e:
            logger.error(f"Unexpected error during scrape cycle: {e}", exc_info=True)

        logger.info(f"Sleeping for {POLL_INTERVAL_MINUTES} minutes until next check...")
        time.sleep(interval_sec)


if __name__ == "__main__":
    main()
