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


def parse_relative_date(date_text: str) -> str:
    """Parses relative and standard date text from Strava feed into ISO 8601 string."""
    now = datetime.now(timezone.utc)
    if not date_text:
        return now.isoformat()

    text = date_text.strip().lower()

    # Extract time like "11:34" or "7:15 am"
    time_match = re.search(r"(\d{1,2}):(\d{2})(?:\s*(am|pm))?", text)
    hour = 12
    minute = 0
    if time_match:
        hour = int(time_match.group(1))
        minute = int(time_match.group(2))
        ampm = time_match.group(3)
        if ampm == "pm" and hour < 12:
            hour += 12
        elif ampm == "am" and hour == 12:
            hour = 0

    if "today" in text:
        dt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        return dt.isoformat()
    elif "yesterday" in text:
        dt = (now - timedelta(days=1)).replace(hour=hour, minute=minute, second=0, microsecond=0)
        return dt.isoformat()

    # Format like "August 30, 2026 at 11:34" or "Aug 30 at 11:34"
    try:
        cleaned = re.sub(r"\s+at\s+", " ", date_text.strip())
        dt = datetime.strptime(cleaned, "%B %d, %Y %H:%M")
        return dt.replace(tzinfo=timezone.utc).isoformat()
    except Exception:
        pass

    return now.isoformat()


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
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        })

        if self.session_cookie:
            cookie_header = self.session_cookie
            if not any(k in cookie_header for k in ["_strava4_session", "="]):
                cookie_header = f"_strava4_session={self.session_cookie}"
            self.session.headers["Cookie"] = cookie_header

    def fetch_recent_activities(self) -> List[Dict[str, Any]]:
        """
        Fetches recent activities from the Strava club page.
        Attempts JSON recent_activity endpoint, feed endpoints, and HTML feed parsing.
        """
        if not self.session_cookie:
            logger.warning("STRAVA_SESSION_COOKIE is empty. Session cookie needed for private club data.")

        # Attempt 1: Recent Activity JSON/XHR endpoint
        url_json = f"https://www.strava.com/clubs/{self.club_id}/recent_activity"
        headers_xhr = {
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"https://www.strava.com/clubs/{self.club_id}",
        }

        try:
            res = self.session.get(url_json, headers=headers_xhr, timeout=15)
            logger.info(f"XHR endpoint {url_json} -> HTTP {res.status_code}")
            if res.status_code == 200:
                try:
                    data = res.json()
                    activities = self._parse_json_feed(data)
                    if activities:
                        logger.info(f"Successfully parsed {len(activities)} activities from JSON endpoint.")
                        return activities
                except Exception:
                    activities = self._parse_html_feed(res.text)
                    if activities:
                        logger.info(f"Successfully parsed {len(activities)} activities from XHR HTML.")
                        return activities
        except Exception as e:
            logger.warning(f"Error requesting XHR endpoint: {e}")

        # Attempt 2: Main Club Page HTML
        url_main = f"https://www.strava.com/clubs/{self.club_id}"
        try:
            res = self.session.get(url_main, timeout=15)
            logger.info(f"Main club page {url_main} -> HTTP {res.status_code} (Final URL: {res.url})")

            if "login" in res.url.lower():
                logger.error("Strava redirected to login page! Your STRAVA_SESSION_COOKIE is invalid, expired, or missing.")
                return []

            if res.status_code == 200:
                activities = self._parse_html_feed(res.text)
                if activities:
                    logger.info(f"Successfully parsed {len(activities)} activities from main club page.")
                    return activities
                else:
                    logger.warning(f"Club page loaded ({len(res.text)} bytes) but 0 activities matched feed selectors.")
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
                dist_meters = int(round(dist_km * 1000))
                duration_sec = int(round(duration_min * 60))
                unique_id = f"{athlete_key}_{dist_meters}_{duration_sec}_{title}".replace(" ", "_")

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

        # Check for embedded Preact / React data-props
        for preact_div in soup.select("div[data-props], div[data-react-props]"):
            props_str = preact_div.get("data-props") or preact_div.get("data-react-props")
            if props_str and ("activity" in props_str.lower() or "athlete" in props_str.lower()):
                try:
                    import json
                    parsed_props = json.loads(props_str)
                    extracted = self._parse_json_feed(parsed_props)
                    if extracted:
                        activities.extend(extracted)
                except Exception:
                    pass

        if activities:
            return activities

        # Look for modern and classic activity card containers
        activity_cards = soup.select(
            "[data-testid='web-feed-entry'], [id^='feed-entry-'], div.activity, div.entry-container, div.feed-entry"
        )
        if not activity_cards:
            activity_cards = soup.select("ul.feed li, div.recent-activities-list > div, table.activities-table tr")

        for card in activity_cards:
            try:
                # 1. Athlete Name
                name_elem = card.select_one("[data-testid='owners-name'], a.entry-athlete, a.athlete-name, .entry-header a")
                full_name = name_elem.get_text(strip=True) if name_elem else ""
                if not full_name:
                    continue

                first_name = to_title_case(full_name.split()[0])
                last_name = " ".join(full_name.split()[1:]) if len(full_name.split()) > 1 else ""

                # 2. Activity Title
                title_elem = card.select_one("[data-testid='activity_name'], a.entry-title, .activity-title, h3 a")
                title = title_elem.get_text(strip=True) if title_elem else "Workout"

                # 3. Activity Type from icon title
                activity_type = "Workout"
                icon_elem = card.select_one("[data-testid='activity-icon'] title, .app-icon, .icon-sport")
                if icon_elem:
                    activity_type = icon_elem.get_text(strip=True)
                else:
                    for known in ["Run", "Ride", "Swim", "Hike", "Walk", "Rowing", "Workout"]:
                        if known.lower() in title.lower():
                            activity_type = known
                            break

                # 4. Stats extraction (Distance, Pace, Time, Elevation)
                dist_km = 0.0
                duration_min = 0.0
                pace = 0.0
                elevation = 0.0

                stat_lis = card.select("ul li, .activity-stats .stat, .entry-stats .stat")
                for li in stat_lis:
                    text = li.get_text(" ", strip=True)
                    divs = li.find_all("div")
                    spans = li.find_all("span")

                    lbl = spans[0].get_text(strip=True).lower() if spans else ""
                    val = divs[-1].get_text(" ", strip=True).lower() if len(divs) >= 2 else (divs[0].get_text(" ", strip=True).lower() if divs else text.lower())

                    if "dist" in lbl or "distance" in text.lower():
                        dist_km = clean_number(val if "dist" in lbl else text)
                    elif "pace" in lbl or "pace" in text.lower():
                        p_val = val if "pace" in lbl else text
                        pace_match = re.search(r"(\d+):(\d{2})", p_val)
                        if pace_match:
                            pace = round(float(pace_match.group(1)) + float(pace_match.group(2)) / 60, 2)
                        else:
                            pace = clean_number(p_val)
                    elif "time" in lbl or "time" in text.lower():
                        duration_min = parse_duration_string(val if "time" in lbl else text)
                    elif "elev" in lbl or "elev" in text.lower():
                        elevation = clean_number(val if "elev" in lbl else text)

                if pace == 0.0 and dist_km > 0 and duration_min > 0:
                    pace = round(duration_min / dist_km, 2)
                elif duration_min == 0.0 and dist_km > 0 and pace > 0:
                    duration_min = round(dist_km * pace, 2)

                team = get_team(first_name)
                eff_dist = get_effective_distance(dist_km, activity_type, first_name, pace)

                # 5. Date / Time
                time_elem = card.select_one("[data-testid='date_at_time'], time, .timestamp")
                date_str = parse_relative_date(time_elem.get_text(strip=True) if time_elem else "")

                athlete_key = f"{first_name}_{last_name}".replace(" ", "_")
                dist_meters = int(round(dist_km * 1000))
                duration_sec = int(round(duration_min * 60))
                unique_id = f"{athlete_key}_{dist_meters}_{duration_sec}_{title}".replace(" ", "_")

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

