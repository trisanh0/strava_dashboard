"""
Data Manager - Handles data loading, transformation, and summarization.
"""

import pandas as pd
import streamlit as st

from config import SHEET_URL, REQUIRED_COLUMNS, STRING_COLUMNS, NUMERIC_COLUMNS


# --- Data Loading ---
@st.cache_data(ttl=60 * 30)
def load_data() -> pd.DataFrame:
    """Load and clean data from the Google Sheet."""
    try:
        df = pd.read_csv(SHEET_URL)
        df = df.dropna(subset=REQUIRED_COLUMNS)

        df["Date"] = pd.to_datetime(df["Date"])

        for col in STRING_COLUMNS:
            df[col] = df[col].astype(str)

        for col in NUMERIC_COLUMNS:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

        return df
    except Exception as e:
        st.error(f"Error loading data: {e}")
        return pd.DataFrame()


# --- Data Summarization ---
def get_data_summary(dataframe: pd.DataFrame) -> str:
    """Create a concise text summary of the dataframe for AI consumption."""
    if dataframe.empty:
        return "No activity data available."

    total_km = dataframe["Distance (km)"].sum()
    total_effort = dataframe["Effort"].sum()
    total_elevation = dataframe["Elevation (m)"].sum()
    total_time_min = dataframe["Time (min)"].sum()

    indiv_stats = dataframe.groupby("Name")["Effort"].sum().sort_values(ascending=False)
    top_performers = indiv_stats.head(5).to_dict()
    bottom_performers = indiv_stats.tail(5).to_dict()

    recent_activities = (
        dataframe.sort_values("Date", ascending=False)
        .head(10)[["Name", "Type", "Distance (km)", "Date"]]
        .to_dict(orient="records")
    )

    return f"""
Overall Stats:
- Total Distance: {total_km:.1f} km
- Total Effort: {total_effort:.1f}
- Total Elevation: {total_elevation:.0f} m
- Total Time: {total_time_min:.0f} mins

Leaderboard (Top 5): {top_performers}
Leaderboard (Bottom 5): {bottom_performers}

Recent Specific Activities:
{recent_activities}
"""

