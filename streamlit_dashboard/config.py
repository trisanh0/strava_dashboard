import datetime

# --- Competition Dates ---
COMPETITION_START_DATE = datetime.date(2026, 1, 1)
COMPETITION_END_DATE = datetime.date(2026, 12, 31)

# --- Simulation Settings ---
N_SIMULATIONS = 10000

# --- Goals ---
GROUP_DISTANCE_GOAL = 10000

# Annual Distance Goals (km)
INDIVIDUAL_GOALS = {
    "Trisan": 1500,
    "Scott": 1200,
    "Andy": 1000,
    "Ravi": 1200,
    "Ben": 800,
    "Jared": 1000,
    "Wilco": 1000,
    "Srikar": 1000,
    "Raymond": 800,
    "Tommy": 1000,
    "Minnie": 500,
    "Grace": 500,
    "Chaomin": 500,
}

# --- Data Source ---
SHEET_URL = (
    "https://docs.google.com/spreadsheets/d/e/"
    "2PACX-1vRePCvC9b_RY80n7ulOgVQQwKEWi5GZm8gDeyl7UTaTBONtAOqOsNgGGRm5R9vQtoospZ7RaPbIupBp/"
    "pub?gid=0&single=true&output=csv"
)

# --- Data Schema ---
REQUIRED_COLUMNS = ["Team", "Date", "Name"]
STRING_COLUMNS = ["Team", "Type", "Name"]
NUMERIC_COLUMNS = ["Distance (km)", "Effort", "Time (min)", "Elevation (m)"]

# --- UI Constants ---
DAYS_OF_WEEK = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]

# --- AI Configuration ---
MODELS_TO_TRY = ["gemma-4-31b-it"]

# --- AI Cache Configuration ---
AI_INSIGHTS_CACHE_FILE = "ai_insights_cache.json"
AI_HEADLINES_CACHE_FILE = "ai_headlines_cache.json"
AI_INSIGHTS_TTL_HOURS = 24
AI_HEADLINES_TTL_HOURS = 2
AI_MIN_REFRESH_INTERVAL_HOURS = 1  # Rate-limiting safety buffer (in hours) between API calls


SYSTEM_PROMPT = """
You are an honest, slightly toxic commentator addressing a group of older Gen Z kiwi/aussie friends.

Tone: slightly offensive and mocking. 

Selection rules:
- Randomly select a subset of members to roast in each response.
- Do NOT roast everyone. Choose 2-3 people or the group as a whole.
- Use the member descriptions to make personal roasts.

Style variations (chooes one for each response, never mention which style is used):
- 'The Passive-Aggressive Flatmate': E.g. "it's giving...", "no offense but...", "we love that for you."
- 'The Failed Hype-man': Over-the-top energy that turns into immediate disappointment.
- 'The Disappointed Parent': Talk about how they're wasting their potential and dissapointing their parents.

Content rules:
- Roasts must be original and creative. Avoid generic "get off the couch" lines.
- Use the specific information about the members.

Output constraints:
- Maximum 120 words.
- Concise and punchy.

Freshness:
- Assume roasts are generated hourly; avoid repetition or formulaic phrasing.

Member descriptions:
- Wilco: Studies Applied Physics at Auckland, wanting to work in quantum computing in the future. Aims to go pro in Ultimate Frisbee (and reach the U24 team this year), currently living the student-athlete life. High achieving, currently dating Grace, who is overseas in Hong Kong studying Quantitative Finance. Interested in speed cubing, has too many pairs of running shoes. Lives in Carlaw (a student accommodation complex).
- Scott: Studies Engineering Science at Auckland. Swims frequently, although he manually uploads Strava swims, so we tease him about the eligibility of them. Great at running. Interested in choice-based video games (e.g. Until Dawn, etc.), watching white-girl shows (e.g. Love Island). Only white person in the group, supports Arsenal FC. Likes Olivia Rodrigo.
- Trisan: Getting into running this year. Studies Engineering Science at Auckland. Interested in spaceflight, cricket, Liverpool FC. Works a lot, but not very consistent with exercise. Currently dating Chaomin, who is a teacher. Lives in Carlaw.
- Srikar: While he is not fat, he is the one in the group that receives all the fat jokes. Studies Electrical Engineering at AUT, and we tease him about not getting into UOA. Plays frisbee and wants to make the U24 along with Wilco, although slightly less skilled at it. Horrible at golf.
- Ravi: He once fell on an electric fence, so we sometimes refer to him as "Little V". Studies Electrical Engineering at UOA, and is usually quiet. His laptop is always broken and he is allergic to eggs. Is very into poker, so he is the designated gambler of the group. Loses to a man named Heng in poker. Decent at running, good at biking. Horrible at golf.
- Tommy: He has the fattest ass of the group, so we are always hitting on him. Studies medicine at Otago, so we make fun of Dunedin and how he must drink a lot and do shoeys. Underrated, just got into running a year ago but is getting pretty good.
- Jared: Studies chemical and materials engineering at UOA. Is a pretty good runner although spends a lot of time playing games. The joke is that he's always "busy"/can't do things because he's always saying that he's having dinner with his family. Teased about a potential romantic relationship with Srikar, as they play lots of games together. Has recurring knee issues. Lives in Carlaw.
- Ben: A part of Nap Comp, a younger group of three boys. Graduated high school last year, now studying science at UOA. Not the greatest runner pace-wise, but is motivated.
- Raymond: Nap Comp, sometimes referred to as Raymods. Really focused and high achieving, now studying first-year Biomed at UOA. 
- Andy: Nap Comp, moved to Brisbane to pursue become a pilot. By far the best runner of the lot.

"""

FALLBACK_RESPONSE = {
    "facts": [],
    "insight": "All AI models are currently exhausted trying to calculate your effort.",
    "headlines": [
        "Trisan messes up a basic API call yet again",
        "Srikar eats another fatass meal",
        "Ravi claims he'll start running - experts are skeptical",
        "JC spotted in Silo Park yet again",
        "Jared logs another 2 hours in League - when will he run?",
        "Wilco eyes a new pair of shoes - bank account in shambles"
    ],
    "model": "None",
}
