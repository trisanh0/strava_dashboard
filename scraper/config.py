import os
from dotenv import load_dotenv

# Load environment variables from .env if present
load_dotenv()

# Strava Config
STRAVA_CLUB_ID = os.getenv("STRAVA_CLUB_ID", "1346373")
STRAVA_SESSION_COOKIE = os.getenv("STRAVA_SESSION_COOKIE", "")

# Webhook Configs
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")
SHEET_WEBHOOK_URL = os.getenv("SHEET_WEBHOOK_URL", "")
WEBHOOK_SECRET_KEY = os.getenv("WEBHOOK_SECRET_KEY", "sleep-comp-secret-key")

# Polling Interval (in minutes)
POLL_INTERVAL_MINUTES = int(os.getenv("POLL_INTERVAL_MINUTES", "60"))

# Teams
TEAMS = {
    "Srikar": ["Srikar", "Wilco", "Trisan", "Jared", "Raymond", "Minnie", "Jinchien"],
    "Ravi": ["Ravi", "Andy", "Scott", "Ben", "Tommy"]
}

# Multipliers
MULTIPLIERS = {
    "Hike": 0.5,
    "Ride": 0.3,
    "Rowing": 0.75,
    "Run": 1.0,
    "Swim": 4.0,
    "Walk": 0.2,
    "Workout": 0.3
}

# Special Multiplier Rules (e.g. Srikar pace threshold)
SPECIAL_MULTIPLIERS = {
    "Srikar": {
        "Run": {
            "threshold": 9.0,  # pace > 9.0 min/km
            "multiplier": 0.6
        }
    }
}

# Discord User IDs for @mentions
DISCORD_IDS = {
    "Srikar": "258466487012950018",
    "Wilco": "295065586797510658",
    "Trisan": "481967966657839107",
    "Jared": "273345887550439425",
    "Raymond": "581670531284074496",
    "Minnie": "608938431720194069",
    "Grace": "975644415852957736",
    "Chaomin": "608938431720194069",
    "Ravi": "328750094016970752",
    "Andy": "529931472233168908",
    "Scott": "635006091734024192",
    "Ben": "326226967160553472",
    "Tommy": "251433215481348096",
    "Jinchien": "423613231974842378"
}

DISCORD_COLOR = 15548997  # Strava Orange/Red

DISCORD_PHRASES = [
    "{name} completed a {type}!",
    "{name} just completed a {type}!",
    "{name} conquered a {type}!",
    "{name} powered through a {type}!",
    "{name} triumphantly completed a {type}!",
    "{name} mastered a {type}!",
    "{name} soared through a {type}!",
    "{name} crushed a {type}!",
    "{name} courageously conquered a {type}!",
    "{name} absolutely destroyed a {type}!",
    "{name} sailed through a {type}!",
    "{name} magnificently finished a {type}!",
    "{name} casually knocked out a {type}!",
    "{name} dominated a {type}!",
    "{name} supercharged their day with a {type}!",
    "{name} excelled in a {type}!",
    "{name} brought their A-game to a {type}!",
    "{name} impressed everyone during a {type}!",
    "{name} delivered a legendary {type}!",
    "{name} inspired the team with a {type}!",
    "{name} amazed everyone with a {type}!",
    "{name} smiled their way through a {type}!",
    "{name} stormed across the finish line of a {type}!",
    "{name} had a fantastic time on a {type}!",
    "{name} is feeling stronger than ever after that {type}!",
    "Legend has it {name} just set the standard with that {type}!",
    "Hats off to {name} for completing a {type}!",
    "Everyone give it up for the incredible {type} that {name} just did!",
    "Give a huge round of applause for {name}, who just completed a {type}!",
    "Successfully completed a {type} with flying colors: {name}!",
    "The prophecy has been fulfilled: {name} achieved greatness in a {type}!",
    "With pure determination, {name} finished a {type} today!"
]


def to_title_case(s: str) -> str:
    """Formats string to Title Case."""
    if not s:
        return ""
    return s.strip().capitalize()


def get_team(first_name: str) -> str:
    """Finds team for athlete by first name."""
    name = to_title_case(first_name)
    for team_name, members in TEAMS.items():
        if any(m.lower() == name.lower() for m in members):
            return team_name
    return "Other"


def get_multiplier(activity_type: str, first_name: str, pace: float) -> float:
    """Calculates effort multiplier based on activity type, athlete, and pace rules."""
    name = to_title_case(first_name)
    if name in SPECIAL_MULTIPLIERS and activity_type in SPECIAL_MULTIPLIERS[name]:
        rule = SPECIAL_MULTIPLIERS[name][activity_type]
        if pace > rule["threshold"]:
            return rule["multiplier"]
    return MULTIPLIERS.get(activity_type, 0.0)


def get_effective_distance(dist_km: float, activity_type: str, first_name: str, pace: float) -> float:
    """Calculates effective weighted distance."""
    mult = get_multiplier(activity_type, first_name, pace)
    return round(dist_km * mult, 2)


def format_duration(decimal_minutes: float) -> str:
    """Formats decimal minutes into mm:ss or hh:mm:ss string."""
    if not decimal_minutes or decimal_minutes <= 0:
        return "0:00"
    total_seconds = int(round(decimal_minutes * 60))
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60

    if hours > 0:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"
