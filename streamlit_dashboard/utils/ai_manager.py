"""
AI Manager - Handles all AI/LLM interactions for the dashboard with persistent caching.
"""

import json
import os
import hashlib
import datetime
import threading
import streamlit as st
from dotenv import load_dotenv
from google import genai

from config import (
    FALLBACK_RESPONSE,
    MODELS_TO_TRY,
    SYSTEM_PROMPT,
    AI_INSIGHTS_CACHE_FILE,
    AI_HEADLINES_CACHE_FILE,
    AI_INSIGHTS_TTL_HOURS,
    AI_HEADLINES_TTL_HOURS,
    AI_MIN_REFRESH_INTERVAL_HOURS,
)

load_dotenv()

# --- Absolute Cache File Paths ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INSIGHTS_CACHE_PATH = os.path.join(BASE_DIR, AI_INSIGHTS_CACHE_FILE)
HEADLINES_CACHE_PATH = os.path.join(BASE_DIR, AI_HEADLINES_CACHE_FILE)

# --- Global State for Background Thread Safety ---
_insights_fetching_lock = threading.Lock()
_headlines_fetching_lock = threading.Lock()
_file_lock = threading.Lock()

_is_insights_fetching = False
_is_headlines_fetching = False

_last_insights_attempt = datetime.datetime.min
_last_headlines_attempt = datetime.datetime.min


# --- Helper Functions ---
def get_api_key() -> str | None:
    """Retrieve the Gemini API key from Streamlit secrets or environment variables."""
    try:
        return st.secrets.get("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY")
    except FileNotFoundError:
        return os.getenv("GEMINI_API_KEY")


def get_client() -> genai.Client | None:
    """Create and return a GenAI client, or None if no API key is available."""
    api_key = get_api_key()
    if not api_key:
        return None
    return genai.Client(api_key=api_key)


def _load_cache(file_path: str) -> dict | None:
    """Safely load cache from a JSON file, using a global lock."""
    with _file_lock:
        if not os.path.exists(file_path):
            return None
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error reading cache {file_path}: {e}")
            return None


def _save_cache(file_path: str, data: dict) -> bool:
    """Safely save data to a JSON cache file, using a global lock."""
    with _file_lock:
        try:
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"Error writing cache to {file_path}: {e}")
            return False


def _extract_json(text: str) -> dict | None:
    """Extract and parse JSON from a raw text response as a fallback."""
    try:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start != -1 and end > start:
            return json.loads(text[start:end])
    except (json.JSONDecodeError, ValueError):
        pass
    return None


def clear_ai_cache():
    """Clear persistent AI cache files to force refresh."""
    global _last_insights_attempt, _last_headlines_attempt
    with _file_lock:
        for p in [INSIGHTS_CACHE_PATH, HEADLINES_CACHE_PATH]:
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception as e:
                    print(f"Error deleting cache {p}: {e}")
    # Reset attempt tracking
    _last_insights_attempt = datetime.datetime.min
    _last_headlines_attempt = datetime.datetime.min


def _build_insights_prompt(summary: str, system_prompt: str) -> str:
    """Build the insights prompt (roast + facts)."""
    return (
        f"{system_prompt}\n\n"
        f"Data Summary:\n{summary}\n\n"
        "Tasks:\n"
        "1. For 'insight': One brutal roast of the group (use your coach persona)\n"
        "2. For 'facts': 3 genuine, data-driven insights about trends, comparisons, or patterns (be entirely analytical, no snark)\n\n"
        "Return a valid JSON object with exactly these two keys: 'insight' and 'facts'."
    )


def _build_headlines_prompt(summary: str, system_prompt: str) -> str:
    """Build the headlines prompt (funny ticker snippets)."""
    return (
        f"{system_prompt}\n\n"
        f"Data Summary:\n{summary}\n\n"
        "Tasks:\n"
        "For 'headlines': A list of six funny, sensationalised snippets **in the style of news headlines** that poke fun at specific recent activities, as well as individual/team/group progress. Do not include 'Breaking:' or similar. Do not include periods. Do not use the personality used for the other generated content."
        "Avoid using the same person for more than two headlines. Use the 'Recent Specific Activities' data to report on exact events.\n\n"
        "Return a valid JSON object with exactly one key: 'headlines' containing a list of these six strings."
    )


# --- Background Worker Thread Targets ---
def _fetch_insights_worker(
    summary: str, system_prompt: str, models: list, summary_hash: str
):
    """Background worker to fetch AI insights."""
    global _is_insights_fetching, _last_insights_attempt
    client = get_client()
    if not client:
        with _insights_fetching_lock:
            _is_insights_fetching = False
        return

    prompt = _build_insights_prompt(summary, system_prompt)
    success = False

    for model_name in models:
        try:
            print(f"[BG] Attempting insights with model: {model_name}")
            try:
                # Try 1: Call with structured JSON config (preferred for Gemini)
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config={"response_mime_type": "application/json"},
                )
                text = response.text
                parsed = json.loads(text)
            except Exception as e:
                # Try 2: Fallback without response_mime_type (essential for Gemma models)
                print(f"[BG] JSON mode failed for model {model_name}: {e}. Retrying without JSON config...")
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                )
                text = response.text
                parsed = _extract_json(text)

            print(f"[BG] Insights response received. Parsed: {parsed is not None}")

            if isinstance(parsed, dict) and "insight" in parsed and "facts" in parsed:
                cache_data = {
                    "timestamp": datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None).isoformat(),
                    "summary_hash": summary_hash,
                    "content": {
                        "insight": parsed["insight"],
                        "facts": parsed["facts"],
                        "model": model_name,
                    },
                }
                _save_cache(INSIGHTS_CACHE_PATH, cache_data)
                success = True
                break
        except Exception as e:
            print(f"[BG] Error with insights model {model_name}: {e}")
            continue

    with _insights_fetching_lock:
        _is_insights_fetching = False
        if not success:
            _last_insights_attempt = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
            # Save fallback to cache to prevent indefinite loading/fetching states
            fallback_cache = {
                "timestamp": datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None).isoformat(),
                "summary_hash": summary_hash,
                "content": {
                    "insight": FALLBACK_RESPONSE["insight"],
                    "facts": FALLBACK_RESPONSE["facts"],
                    "model": "None (System Fallback)",
                },
            }
            _save_cache(INSIGHTS_CACHE_PATH, fallback_cache)


def _fetch_headlines_worker(
    summary: str, system_prompt: str, models: list, summary_hash: str
):
    """Background worker to fetch AI headlines."""
    global _is_headlines_fetching, _last_headlines_attempt
    client = get_client()
    if not client:
        with _headlines_fetching_lock:
            _is_headlines_fetching = False
        return

    prompt = _build_headlines_prompt(summary, system_prompt)
    success = False

    for model_name in models:
        try:
            print(f"[BG] Attempting headlines with model: {model_name}")
            try:
                # Try 1: Call with structured JSON config
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config={"response_mime_type": "application/json"},
                )
                text = response.text
                parsed = json.loads(text)
            except Exception as e:
                # Try 2: Fallback without response_mime_type (essential for Gemma models)
                print(f"[BG] JSON mode failed for model {model_name}: {e}. Retrying without JSON config...")
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                )
                text = response.text
                parsed = _extract_json(text)

            print(f"[BG] Headlines response received. Parsed: {parsed is not None}")

            if isinstance(parsed, dict) and "headlines" in parsed:
                cache_data = {
                    "timestamp": datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None).isoformat(),
                    "summary_hash": summary_hash,
                    "content": {
                        "headlines": parsed["headlines"],
                        "model": model_name,
                    },
                }
                _save_cache(HEADLINES_CACHE_PATH, cache_data)
                success = True
                break
        except Exception as e:
            print(f"[BG] Error with headlines model {model_name}: {e}")
            continue

    with _headlines_fetching_lock:
        _is_headlines_fetching = False
        if not success:
            _last_headlines_attempt = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
            # Save fallback to cache to prevent indefinite loading/fetching states
            fallback_cache = {
                "timestamp": datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None).isoformat(),
                "summary_hash": summary_hash,
                "content": {
                    "headlines": FALLBACK_RESPONSE["headlines"],
                    "model": "None (System Fallback)",
                },
            }
            _save_cache(HEADLINES_CACHE_PATH, fallback_cache)


def _is_cache_expired(cache: dict | None, ttl_hours: float, current_hash: str) -> bool:
    """Check if cache is missing, summary hash changed, or TTL has elapsed."""
    if not cache or "content" not in cache or "timestamp" not in cache:
        return True
    if cache.get("summary_hash") != current_hash:
        return True
    try:
        cached_time = datetime.datetime.fromisoformat(cache["timestamp"])
        now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
        return (now - cached_time).total_seconds() > ttl_hours * 3600
    except Exception:
        return True


# --- Public Entrypoints ---
def get_ai_insights_non_blocking(
    summary: str,
    system_prompt: str = SYSTEM_PROMPT,
    models: list = MODELS_TO_TRY,
    force_refresh: bool = False,
) -> dict:
    """
    Get AI insights (roast + facts) instantly from persistent cache.
    Auto-triggers background thread if cache is missing, expired, or force_refresh is True.
    """
    global _is_insights_fetching, _last_insights_attempt

    summary_hash = hashlib.sha256(summary.encode("utf-8")).hexdigest()
    cache = _load_cache(INSIGHTS_CACHE_PATH)
    expired = _is_cache_expired(cache, AI_INSIGHTS_TTL_HOURS, summary_hash)

    now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    recent_attempt = (now - _last_insights_attempt).total_seconds() < (
        AI_MIN_REFRESH_INTERVAL_HOURS * 3600
    )

    if (force_refresh or expired) and not recent_attempt:
        with _insights_fetching_lock:
            if not _is_insights_fetching:
                _is_insights_fetching = True
                _last_insights_attempt = now
                thread = threading.Thread(
                    target=_fetch_insights_worker,
                    args=(summary, system_prompt, models, summary_hash),
                    daemon=True,
                )
                thread.start()

    if cache and "content" in cache:
        res = dict(cache["content"])
        res["status"] = "fetching" if _is_insights_fetching else "success"
        res["generated_at"] = cache.get("timestamp")
        return res

    return {
        "insight": "Generating AI insights...",
        "facts": [],
        "model": "None (Pending)",
        "status": "fetching",
    }


def get_ai_headlines_non_blocking(
    summary: str,
    system_prompt: str = SYSTEM_PROMPT,
    models: list = MODELS_TO_TRY,
    force_refresh: bool = False,
) -> dict:
    """
    Get AI headlines instantly from persistent cache.
    Auto-triggers background thread if cache is missing, expired, or force_refresh is True.
    """
    global _is_headlines_fetching, _last_headlines_attempt

    summary_hash = hashlib.sha256(summary.encode("utf-8")).hexdigest()
    cache = _load_cache(HEADLINES_CACHE_PATH)
    expired = _is_cache_expired(cache, AI_HEADLINES_TTL_HOURS, summary_hash)

    now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    recent_attempt = (now - _last_headlines_attempt).total_seconds() < (
        AI_MIN_REFRESH_INTERVAL_HOURS * 3600
    )

    if (force_refresh or expired) and not recent_attempt:
        with _headlines_fetching_lock:
            if not _is_headlines_fetching:
                _is_headlines_fetching = True
                _last_headlines_attempt = now
                thread = threading.Thread(
                    target=_fetch_headlines_worker,
                    args=(summary, system_prompt, models, summary_hash),
                    daemon=True,
                )
                thread.start()

    if cache and "content" in cache:
        res = dict(cache["content"])
        res["status"] = "fetching" if _is_headlines_fetching else "success"
        res["generated_at"] = cache.get("timestamp")
        return res

    return {
        "headlines": FALLBACK_RESPONSE["headlines"],
        "model": "None (Pending)",
        "status": "fetching",
    }

