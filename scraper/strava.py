import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import requests
from bs4 import BeautifulSoup

from scraper.config import (
    STRAVA_CLUB_ID,
    STRAVA_SESSION_COOKIE,
    get_effective_distance,
    get_team,
    to_title_case,
)

logger = logging.getLogger(__name__)


def clean_number(val_str: str) -> float:
    """Extracts floating point number from string (e.g. '10.5 km' -> 10.5)."""
    if not val_str:
        return 0.0
    match = re.search(r"[-+]?\d*\.\d+|\d+", val_str.replace(",", ""))
    return float(match.group()) if match else 0.0


def parse_duration_string(time_str: str) -> float:
    """Parses duration string like '1h 23m', '45m 12s', '1:23:45' into decimal minutes."""
    if not time_str:
        return 0.0

    time_str = time_str.strip().lower()

    # Format: 1:23:45 or 45:12
    if ":" in time_str:
        parts = time_str.split(":")
        try:
            if len(parts) == 3:
                return float(parts[0]) * 60 + float(parts[1]) + float(parts[2]) / 60
            elif len(parts) == 2:
                return float(parts[0]) + float(parts[1]) / 60
        except ValueError:
            pass

    # Format: 1h 23m or 45m 10s
    total_minutes = 0.0
    hours_match = re.search(r"(\d+)\s*h", time_str)
    if hours_match:
        total_minutes += float(hours_match.group(1)) * 60

    min_match = re.search(r"(\d+)\s*m", time_str)
    if min_match:
        total_minutes += float(min_match.group(1))

    sec_match = re.search(r"(\d+)\s*s", time_str)
    if sec_match:
        total_minutes += float(sec_match.group(1)) / 60

    if total_minutes == 0.0:
        total_minutes = clean_number(time_str)

    return round(total_minutes, 2)


class StravaClubScraper:
    def __init__(self, club_id: Optional[str] = None, session_cookie: Optional[str] = None):
        self.club_id = club_id or STRAVA_CLUB_ID
        self.session_cookie = (session_cookie or STRAVA_SESSION_COOKIE).strip()
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/128.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        })

        if self.session_cookie:
            # Handle cookie if passed as full string or just value
            if "=" in self.session_cookie:
                for part in self.session_cookie.split(";"):
                    if "=" in part:
                        k, v = part.strip().split("=", 1)
                        self.session.cookies.set(k, v, domain=".strava.com")
            else:
                self.session.cookies.set("_strava4_session", self.session_cookie, domain=".strava.com")

    def fetch_recent_activities(self) -> List[Dict[str, Any]]:
        """
        Fetches recent activities from the Strava club page.
        Attempts both JSON recent_activity endpoint and HTML feed parsing.
        """
        if not self.session_cookie:
            logger.warning("STRAVA_SESSION_COOKIE is empty. Fetching public club page...")

        url_json = f"https://www.strava.com/clubs/{self.club_id}/recent_activity"
        headers_xhr = {
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"https://www.strava.com/clubs/{self.club_id}",
        }

        # Attempt 1: Recent Activity JSON/XHR endpoint
        try:
            res = self.session.get(url_json, headers=headers_xhr, timeout=15)
            if res.status_code == 200:
                try:
                    data = res.json()
                    activities = self._parse_json_feed(data)
                    if activities:
                        logger.info(f"Successfully scraped {len(activities)} activities from JSON endpoint.")
                        return activities
                except ValueError:
                    # Returned HTML instead of JSON
                    activities = self._parse_html_feed(res.text)
                    if activities:
                        logger.info(f"Successfully scraped {len(activities)} activities from XHR HTML response.")
                        return activities
            else:
                logger.debug(f"XHR endpoint returned status {res.status_code}. Falling back to main club page.")
        except Exception as e:
            logger.warning(f"Error requesting XHR endpoint: {e}")

        # Attempt 2: Main Club Page HTML
        url_main = f"https://www.strava.com/clubs/{self.club_id}"
        try:
            res = self.session.get(url_main, timeout=15)
            if res.status_code == 200:
                activities = self._parse_html_feed(res.text)
                logger.info(f"Successfully scraped {len(activities)} activities from main club page.")
                return activities
            else:
                logger.error(f"Failed to load club page. HTTP status {res.status_code}")
        except Exception as e:
            logger.error(f"Error scraping club main page: {e}")

        return []

    def _parse_json_feed(self, data: Any) -> List[Dict[str, Any]]:
        """Parses Strava internal JSON feed models if returned."""
        activities = []
        entries = []

        if isinstance(data, dict):
            entries = data.get("models") or data.get("activities") or []
        elif isinstance(data, list):
            entries = data

        for item in entries:
            try:
                athlete = item.get("athlete") or {}
                first_name = to_title_case(athlete.get("firstname") or item.get("athlete_name", "").split()[0])
                last_name = athlete.get("lastname") or ""
                activity_type = item.get("type") or item.get("activity_type") or "Workout"
                title = item.get("name") or item.get("title") or activity_type

                dist_km = round(clean_number(str(item.get("distance", 0))) / (1000 if item.get("distance_in_meters") else 1), 2)
                duration_min = round(clean_number(str(item.get("moving_time", 0))) / (60 if item.get("time_in_seconds") else 1), 2)
                elevation = clean_number(str(item.get("elevation_gain", 0)))

                pace = round(duration_min / dist_km, 2) if dist_km > 0 else 0.0
                team = get_team(first_name)
                eff_dist = get_effective_distance(dist_km, activity_type, first_name, pace)

                date_str = item.get("start_date_local") or item.get("start_date") or datetime.now(timezone.utc).isoformat()
                athlete_key = f"{first_name}_{last_name}".replace(" ", "_")
                unique_id = f"{athlete_key}_{dist_km * 1000:.0f}_{duration_min * 60:.0f}_{title}".replace(" ", "_")

                activities.append({
                    "unique_id": unique_id,
                    "first_name": first_name,
                    "team": team,
                    "date": date_str,
                    "distance_km": dist_km,
                    "effective_distance_km": eff_dist,
                    "duration_min": duration_min,
                    "pace": pace,
                    "elevation": elevation,
                    "activity_type": activity_type,
                    "title": title
                })
            except Exception as e:
                logger.debug(f"Error parsing JSON activity model: {e}")

        return activities

    def _parse_html_feed(self, html_content: str) -> List[Dict[str, Any]]:
        """Parses Strava Club HTML markup for recent activity cards."""
        soup = BeautifulSoup(html_content, "html.parser")
        activities = []

        # Look for activity container elements in feed
        activity_cards = soup.select(
            "div.activity, div[data-testid='web-feed-entry'], div.entry-container, div.feed-entry"
        )
        if not activity_cards:
            activity_cards = soup.select("ul.feed li, div.recent-activities-list > div")

        for card in activity_cards:
            try:
                # Athlete Name
                name_elem = card.select_one("a.entry-athlete, a.athlete-name, a[data-testid='owners-name'], .entry-header a")
                full_name = name_elem.get_text(strip=True) if name_elem else ""
                if not full_name:
                    continue

                first_name = to_title_case(full_name.split()[0])
                last_name = " ".join(full_name.split()[1:]) if len(full_name.split()) > 1 else ""

                # Title & Type
                title_elem = card.select_one("a.entry-title, .activity-title, [data-testid='activity_name'], h3 a")
                title = title_elem.get_text(strip=True) if title_elem else "Activity"

                # Detect type from icon or text if available
                type_elem = card.select_one(".app-icon, .icon-sport, [data-testid='type_and_datetime']")
                type_text = type_elem.get_text(strip=True) if type_elem else ""
                activity_type = "Workout"
                for known_type in ["Run", "Ride", "Swim", "Hike", "Walk", "Rowing", "Workout"]:
                    if known_type.lower() in (title.lower() + " " + type_text.lower()):
                        activity_type = known_type
                        break

                # Stat entries (Distance, Duration, Elevation, Pace)
                dist_km = 0.0
                duration_min = 0.0
                elevation = 0.0

                stat_items = card.select("ul.inline-stats li, .activity-stats .stat, .entry-stats .stat")
                for stat in stat_items:
                    label = stat.select_one(".stat-subheading, .title, .label")
                    value = stat.select_one(".stat-value, .value, b, strong")
                    if not value:
                        continue
                    lbl_text = (label.get_text(strip=True) if label else "").lower()
                    val_text = value.get_text(strip=True).lower()

                    if "dist" in lbl_text or "km" in val_text or "mi" in val_text:
                        dist_km = clean_number(val_text)
                    elif "time" in lbl_text or "m" in val_text or "h" in val_text or ":" in val_text:
                        duration_min = parse_duration_string(val_text)
                    elif "elev" in lbl_text or "m" in val_text or "ft" in val_text:
                        elevation = clean_number(val_text)

                pace = round(duration_min / dist_km, 2) if dist_km > 0 else 0.0
                team = get_team(first_name)
                eff_dist = get_effective_distance(dist_km, activity_type, first_name, pace)

                # Date / Time
                time_elem = card.select_one("time, .timestamp, [data-testid='date_and_group']")
                date_str = datetime.now(timezone.utc).isoformat()
                if time_elem and time_elem.has_attr("datetime"):
                    date_str = time_elem["datetime"]

                athlete_key = f"{first_name}_{last_name}".replace(" ", "_")
                unique_id = f"{athlete_key}_{dist_km * 1000:.0f}_{duration_min * 60:.0f}_{title}".replace(" ", "_")

                activities.append({
                    "unique_id": unique_id,
                    "first_name": first_name,
                    "team": team,
                    "date": date_str,
                    "distance_km": dist_km,
                    "effective_distance_km": eff_dist,
                    "duration_min": duration_min,
                    "pace": pace,
                    "elevation": elevation,
                    "activity_type": activity_type,
                    "title": title
                })
            except Exception as e:
                logger.debug(f"Error parsing HTML card: {e}")

        return activities
