"""
Sleep Comp Fitness Comp Dashboard
Main entry point for the Streamlit application.
"""

import datetime

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

from utils.ai_manager import (
    get_ai_insights_non_blocking,
    get_ai_headlines_non_blocking,
    clear_ai_cache,
    get_client,
)
from utils.data_manager import get_data_summary, load_data

from config import (
    COMPETITION_END_DATE,
    COMPETITION_START_DATE,
    DAYS_OF_WEEK,
    GROUP_DISTANCE_GOAL,
    INDIVIDUAL_GOALS,
    N_SIMULATIONS,
    SYSTEM_PROMPT,
    MODELS_TO_TRY,
)

st.set_page_config(page_title="Sleep Comp Fitness Comp", page_icon="🏃", layout="wide")


# --- Helper Functions ---
def display_metrics(data: pd.DataFrame) -> None:
    """Display key summary metrics in a row of columns."""
    total_km = data["Distance (km)"].sum()
    total_elevation = data["Elevation (m)"].sum()
    total_time_min = data["Time (min)"].sum()

    hours, minutes = divmod(int(total_time_min), 60)
    days, hours = divmod(hours, 24)
    time_str = f"{days}d {hours}h" if days > 0 else f"{hours}h {minutes}m"

    num_activities = len(data)

    cols = st.columns(4)
    for col, (label, value) in zip(
        cols,
        [
            ("Total Distance", f"{total_km:,.0f} km"),
            ("Total Time", time_str),
            ("Total Elevation", f"{int(total_elevation)} m"),
            ("Activities", f"{num_activities:,}"),
        ],
    ):
        with col:
            with st.container(border=True):
                st.metric(label, value)


def render_goal_progress(data: pd.DataFrame, today: datetime.date) -> None:
    """Render a progress bar for the group distance goal with predictions."""
    total_distance = data["Distance (km)"].sum()
    progress = min(1.0, total_distance / GROUP_DISTANCE_GOAL)

    # Calculate prediction based on daily average
    days_elapsed = (today - COMPETITION_START_DATE).days + 1
    if days_elapsed > 0:
        predicted_total = (total_distance / days_elapsed) * 365
    else:
        predicted_total = 0

    st.subheader("Goal Progress")
    st.progress(progress)

    with st.container(border=True):
        st.metric("Goal", f"{total_distance:,.1f} / {GROUP_DISTANCE_GOAL:,.0f} km")
    with st.container(border=True):
        st.metric(
            "Projected Total",
            f"{predicted_total:,.1f} km",
            delta=f"{predicted_total - GROUP_DISTANCE_GOAL:,.1f} km",
            help="Prediction based on current daily average extrapolated to 365 days.",
        )


def get_winner_history(
    source_df: pd.DataFrame, group_cols: list, value_col: str = "Effort"
) -> pd.DataFrame:
    """Calculate the winner for each month based on the provided grouping."""
    if source_df.empty:
        return pd.DataFrame()

    monthly_sums = (
        source_df.groupby(["Month"] + group_cols)[value_col].sum().reset_index()
    )
    results = []
    for month in sorted(monthly_sums["Month"].unique(), reverse=True):
        month_data = monthly_sums[monthly_sums["Month"] == month]
        if month_data.empty:
            continue
        winner = month_data.loc[month_data[value_col].idxmax()]
        entry = {
            "Month": month,
            "Winner": winner[group_cols[0]],
            "Effort": winner[value_col],
        }
        if "Name" in group_cols:
            entry["Team"] = winner["Team"]
        results.append(entry)
    return pd.DataFrame(results)


def run_monte_carlo_simulation(
    daily_effort_df: pd.DataFrame,
    current_totals: pd.Series,
    days_remaining: int,
    today: datetime.date,
) -> pd.DataFrame:
    """Run Monte Carlo simulation to estimate win probabilities."""
    all_dates = pd.date_range(start=COMPETITION_START_DATE, end=today)
    teams = current_totals.index.tolist()
    n_days = len(all_dates)

    # Calculate daily stats per team
    team_stats = {}
    for team in daily_effort_df["Team"].unique():
        team_data = (
            daily_effort_df[daily_effort_df["Team"] == team]
            .set_index("Date")["Effort"]
            .reindex(all_dates, fill_value=0)
        )
        team_stats[team] = {
            "mean": team_data.mean(),
            "std": team_data.std(),
        }

    # Simulate future efforts
    future_efforts = {}
    for team in teams:
        mu, sigma = team_stats[team]["mean"], team_stats[team]["std"]
        sim_mu = mu * days_remaining
        sim_sigma = np.sqrt(
            days_remaining * (sigma**2) + (days_remaining**2) * ((sigma**2) / n_days)
        )
        future_efforts[team] = np.random.normal(sim_mu, sim_sigma, N_SIMULATIONS)

    final_scores = pd.DataFrame(
        {team: current_totals[team] + future_efforts[team] for team in teams}
    )
    win_probs = (
        final_scores.idxmax(axis=1).value_counts() / N_SIMULATIONS
    ).reset_index()
    win_probs.columns = ["Team", "Probability"]
    return win_probs


# --- Render Functions ---
def render_activity_heatmap(data: pd.DataFrame) -> None:
    """Render the effort heatmap showing daily effort."""
    st.subheader("Effort Heatmap")

    daily_summary = (
        data.groupby("Date")
        .agg(
            {
                "Effort": "sum",
                "Distance (km)": "sum",
                "Name": lambda x: ", ".join(sorted(x.unique())),
                "Type": lambda x: ", ".join(sorted(x.unique())),
            }
        )
        .reset_index()
    )
    daily_summary["Week"] = daily_summary["Date"].dt.isocalendar().week
    daily_summary["Day"] = daily_summary["Date"].dt.day_name()

    heatmap = (
        alt.Chart(daily_summary)
        .mark_rect()
        .encode(
            x=alt.X("Week:O", title="Week of Year"),
            y=alt.Y("Day:N", sort=DAYS_OF_WEEK, title="Day of Week"),
            color=alt.Color(
                "Effort:Q", title="Daily Effort", scale=alt.Scale(scheme="greens")
            ),
            tooltip=[
                alt.Tooltip("Date:T", format="%Y-%m-%d"),
                alt.Tooltip("Effort:Q", format=".1f", title="Total Effort"),
                alt.Tooltip("Distance (km):Q", format=".1f", title="Total Km"),
                alt.Tooltip("Name:N", title="People"),
                alt.Tooltip("Type:N", title="Activities"),
            ],
        )
        .properties(height=250)
        .configure_axis(labelFontSize=10, titleFontSize=12)
    )

    st.altair_chart(heatmap, width="stretch")


def render_group_effort_chart(data: pd.DataFrame) -> None:
    """Render the cumulative distance line chart."""
    st.subheader(
        "Distance Progress",
        help="The orange line is the required pace to hit the 10,000 km goal.",
    )

    group_daily = data.groupby("Date")["Distance (km)"].sum().reset_index()
    group_daily = group_daily.sort_values("Date")
    group_daily["Cumulative Distance"] = group_daily["Distance (km)"].cumsum()

    line_chart = (
        alt.Chart(group_daily)
        .mark_line(point=True, strokeWidth=3)
        .encode(
            x=alt.X("Date:T", title=None),
            y=alt.Y("Cumulative Distance:Q", title="Distance (km)"),
            tooltip=["Date:T", alt.Tooltip("Cumulative Distance:Q", format=".1f")],
        )
        .properties(height=230)
    )

    if group_daily.empty:
        max_date = pd.to_datetime(datetime.date.today())
    else:
        max_date = group_daily["Date"].max()

    min_date = pd.to_datetime(COMPETITION_START_DATE)

    total_days = (pd.to_datetime(COMPETITION_END_DATE) - min_date).days
    days_to_max = (max_date - min_date).days
    target_distance_at_max = (days_to_max / total_days) * GROUP_DISTANCE_GOAL

    ideal_df = pd.DataFrame(
        {
            "Date": [min_date, max_date],
            "Cumulative Distance": [0, target_distance_at_max],
            "Label": ["Goal Pace", "Goal Pace"],
        }
    )

    target_line = (
        alt.Chart(ideal_df)
        .mark_line(strokeDash=[5, 5], color="#ff7f0e", strokeWidth=2)
        .encode(
            x="Date:T",
            y="Cumulative Distance:Q",
            tooltip=[
                alt.Tooltip("Label:N", title="Goal"),
                alt.Tooltip("Cumulative Distance:Q", format=".1f"),
            ],
        )
    )

    st.altair_chart((line_chart + target_line), width="stretch")


def _render_team_bar_chart(stats: pd.DataFrame) -> None:
    """Render a horizontal bar chart for team standings."""
    bar_chart = (
        alt.Chart(stats)
        .mark_bar(cornerRadiusEnd=4, height=40)
        .encode(
            x=alt.X("Effort:Q", title="Total Effort", axis=None),
            y=alt.Y(
                "Team:N",
                sort="-x",
                title=None,
                axis=alt.Axis(labelFontSize=13, tickSize=0, domain=False),
            ),
            color=alt.Color("Team:N", legend=None),
            tooltip=[
                alt.Tooltip("Team:N"),
                alt.Tooltip("Effort:Q", format=".1f"),
                alt.Tooltip("Distance (km):Q", format=".1f"),
            ],
        )
    )
    text = bar_chart.mark_text(
        align="left", baseline="middle", dx=5, fontWeight="bold"
    ).encode(text=alt.Text("Effort:Q", format=".1f"))
    st.altair_chart((bar_chart + text).properties(height=180), width="stretch")


def render_team_standings(
    filtered_df: pd.DataFrame,
    history_df: pd.DataFrame,
    today: datetime.date,
    current_month: str,
) -> None:
    """Render the team standings tabs (Month, Year, History)."""
    st.subheader("Standings")
    tab_month, tab_year, tab_history = st.tabs(["Month", "Year", "History"])

    with tab_month:
        st.caption(f"Standings for {today.strftime('%B %Y')}")
        month_data = filtered_df[filtered_df["Month"] == current_month]
        if not month_data.empty:
            stats = (
                month_data.groupby("Team")[["Effort", "Distance (km)"]]
                .sum()
                .sort_values("Effort", ascending=False)
                .reset_index()
            )
            _render_team_bar_chart(stats)
        else:
            st.info("No activities for the current month.")

    with tab_year:
        stats = (
            filtered_df.groupby("Team")[["Effort", "Distance (km)"]]
            .sum()
            .sort_values("Effort", ascending=False)
            .reset_index()
        )
        _render_team_bar_chart(stats)

    with tab_history:
        st.caption("Winners of each month")
        history_table = get_winner_history(history_df, ["Team"])
        if not history_table.empty:
            st.dataframe(history_table, width="stretch", hide_index=True)
        else:
            st.info("No data available for history.")


def render_win_probability(df: pd.DataFrame, today: datetime.date) -> None:
    """Render the win probability donut chart."""
    days_remaining = (COMPETITION_END_DATE - today).days
    st.subheader(
        "Win Probability", help=f"10k simulations over {days_remaining} remaining days."
    )

    if days_remaining > 0:
        daily_effort = df.groupby(["Team", "Date"])["Effort"].sum().reset_index()
        current_totals = df.groupby("Team")["Effort"].sum()
        win_probs = run_monte_carlo_simulation(
            daily_effort, current_totals, days_remaining, today
        )

        prob_chart = (
            alt.Chart(win_probs)
            .mark_arc(innerRadius=60)
            .encode(
                theta=alt.Theta(field="Probability", type="quantitative"),
                color=alt.Color(field="Team"),
                tooltip=["Team", alt.Tooltip("Probability", format=".1%")],
                order=alt.Order("Probability", sort="descending"),
            )
            .properties(height=230)
        )

        st.altair_chart(prob_chart, width="stretch")
    else:
        st.info("Competition has ended.")


def render_team_effort_chart(data: pd.DataFrame) -> None:
    """Render the cumulative team effort line chart."""
    st.subheader("Effort")

    team_daily = data.groupby(["Team", "Date"])["Effort"].sum().reset_index()
    team_daily = team_daily.sort_values("Date")
    team_daily["Cumulative Effort"] = team_daily.groupby("Team")["Effort"].cumsum()

    teams = sorted(team_daily["Team"].unique())
    if len(teams) == 2:
        team1, team2 = teams[0], teams[1]

        min_date = data["Date"].min()
        max_date = data["Date"].max()
        all_dates = pd.date_range(min_date, max_date)

        pivot_df = team_daily.pivot(
            index="Date", columns="Team", values="Cumulative Effort"
        )
        pivot_df = pivot_df.reindex(all_dates).ffill().fillna(0)
        pivot_df = pivot_df.reset_index().rename(columns={"index": "Date"})
        pivot_df["Gap"] = (pivot_df[team1] - pivot_df[team2]).abs()

        team_daily = pd.merge(team_daily, pivot_df, on="Date", how="left")

        shared_tooltip = [
            alt.Tooltip("Date:T", format="%Y-%m-%d"),
            alt.Tooltip(f"{team1}:Q", format=".1f", title=f"{team1} Effort"),
            alt.Tooltip(f"{team2}:Q", format=".1f", title=f"{team2} Effort"),
            alt.Tooltip("Gap:Q", format=".1f", title="Gap"),
        ]

        area_chart = (
            alt.Chart(pivot_df)
            .mark_area(opacity=0.2)
            .encode(
                x=alt.X("Date:T", title=None),
                y=alt.Y(f"{team1}:Q", title="Effort"),
                y2=alt.Y2(f"{team2}:Q"),
                color=alt.condition(
                    f"datum['{team1}'] > datum['{team2}']",
                    alt.value("#1f77b4"),
                    alt.value("#ff7f0e"),
                ),
                tooltip=shared_tooltip,
            )
        )

        team_line_chart = (
            alt.Chart(team_daily)
            .mark_line(point=True)
            .encode(
                x=alt.X("Date:T", title=None),
                y=alt.Y("Cumulative Effort:Q", title="Effort"),
                color=alt.Color("Team:N"),
                tooltip=shared_tooltip,
            )
        )
        final_chart = (area_chart + team_line_chart).properties(height=230)
    else:
        team_line_chart = (
            alt.Chart(team_daily)
            .mark_line(point=True)
            .encode(
                x=alt.X("Date:T", title=None),
                y=alt.Y("Cumulative Effort:Q", title="Effort"),
                color=alt.Color("Team:N"),
                tooltip=["Date", "Team", "Cumulative Effort"],
            )
        )
        final_chart = team_line_chart.properties(height=230)

    st.altair_chart(final_chart, width="stretch")


def _render_standings_chart(stats: pd.DataFrame) -> None:
    if stats.empty:
        return

    bar_chart = (
        alt.Chart(stats)
        .mark_bar(cornerRadiusEnd=4, height=30)
        .encode(
            x=alt.X("Effort:Q", title="Total Effort", axis=None),
            y=alt.Y(
                "Name:N",
                sort="-x",
                title=None,
                axis=alt.Axis(labelFontSize=12, tickSize=0, domain=False),
            ),
            color=alt.Color("Team:N"),
            tooltip=[
                alt.Tooltip("Name:N"),
                alt.Tooltip("Team:N"),
                alt.Tooltip("Effort:Q", format=".1f"),
                alt.Tooltip("Distance (km):Q", format=".1f"),
                alt.Tooltip("Time (min):Q", format=".0f"),
            ],
        )
    )
    text = bar_chart.mark_text(
        align="left", baseline="middle", dx=5, fontWeight="bold"
    ).encode(text=alt.Text("Effort:Q", format=".1f"))
    # Use alt.Step instead of fixed height for dynamic list sizes
    st.altair_chart((bar_chart + text).properties(height=alt.Step(40)), width="stretch")


def render_individual_standings(
    filtered_df: pd.DataFrame,
    history_df: pd.DataFrame,
    today: datetime.date,
    current_month: str,
) -> None:
    """Render the individual standings tabs (Month, Year, History)."""
    st.subheader("Standings")
    indiv_tab_month, indiv_tab_year, indiv_tab_history = st.tabs(
        ["Month", "Year", "History"]
    )

    with indiv_tab_month:
        st.caption(f"Standings for {today.strftime('%B %Y')}")
        month_data_indiv = filtered_df[filtered_df["Month"] == current_month]
        if not month_data_indiv.empty:
            stats = (
                month_data_indiv.groupby(["Name", "Team"])[
                    ["Effort", "Distance (km)", "Time (min)"]
                ]
                .sum()
                .reset_index()
                .sort_values("Effort", ascending=False)
                .reset_index(drop=True)
            )
            stats.index += 1
            _render_standings_chart(stats)
        else:
            st.info("No activities for the current month.")

    with indiv_tab_year:
        stats = (
            filtered_df.groupby(["Name", "Team"])[
                ["Effort", "Distance (km)", "Time (min)"]
            ]
            .sum()
            .reset_index()
            .sort_values("Effort", ascending=False)
            .reset_index(drop=True)
        )
        stats.index += 1
        _render_standings_chart(stats)

    with indiv_tab_history:
        st.caption("Winners of each month")
        history_table_indiv = get_winner_history(history_df, ["Name", "Team"])
        if not history_table_indiv.empty:
            st.dataframe(history_table_indiv, width="stretch", hide_index=True)
        else:
            st.info("No data available for history.")


def render_individual_records(data: pd.DataFrame) -> None:
    """Render the top single-activity records."""
    if data.empty:
        return

    st.subheader("Single Activity Records")

    # Longest Distance
    max_dist_idx = data["Distance (km)"].idxmax()
    max_dist_row = data.loc[max_dist_idx] if pd.notna(max_dist_idx) else None

    # Highest Elevation
    max_elev_idx = (
        data["Elevation (m)"].idxmax() if "Elevation (m)" in data.columns else None
    )
    max_elev_row = data.loc[max_elev_idx] if pd.notna(max_elev_idx) else None

    # Longest Duration
    max_time_idx = data["Time (min)"].idxmax()
    max_time_row = data.loc[max_time_idx] if pd.notna(max_time_idx) else None

    # Highest Effort
    max_effort_idx = data["Effort"].idxmax()
    max_effort_row = data.loc[max_effort_idx] if pd.notna(max_effort_idx) else None

    records = [
        (
            "Longest Distance",
            max_dist_row,
            (
                f"{max_dist_row['Distance (km)']:.1f} km"
                if max_dist_row is not None
                else None
            ),
            True,
        ),
        (
            "Most Elevation Gain",
            max_elev_row,
            (
                f"{int(max_elev_row['Elevation (m)'])} m"
                if max_elev_row is not None
                and pd.notna(max_elev_row.get("Elevation (m)"))
                else None
            ),
            max_elev_row is not None and pd.notna(max_elev_row.get("Elevation (m)")),
        ),
        (
            "Longest Duration",
            max_time_row,
            (
                f"{int(max_time_row['Time (min)'])} min"
                if max_time_row is not None
                else None
            ),
            True,
        ),
        (
            "Highest Effort",
            max_effort_row,
            f"{max_effort_row['Effort']:.1f}" if max_effort_row is not None else None,
            True,
        ),
    ]

    cols = st.columns(4)
    for col, (title, row, value, show) in zip(cols, records):
        with col:
            with st.container(border=True):
                if row is not None and show and value is not None:
                    st.metric(
                        title,
                        value,
                        f"{row['Name']} ({row['Date'].strftime('%d %b')})",
                        delta_color="off",
                    )
                else:
                    st.metric(title, "—")


def render_head_to_head_comparison(data: pd.DataFrame) -> None:
    """Render a head-to-head comparison of two selected athletes."""
    st.subheader("Head-to-Head Comparison")

    if data.empty:
        st.info("No data available.")
        return

    athletes = sorted(data["Name"].unique())
    if len(athletes) < 2:
        st.info("Need at least two athletes for comparison.")
        return

    sel_col1, sel_col2 = st.columns(2)
    with sel_col1:
        athlete1 = st.selectbox("Athlete 1", athletes, index=0)
    with sel_col2:
        athlete2 = st.selectbox("Athlete 2", athletes, index=min(1, len(athletes) - 1))

    if athlete1 == athlete2:
        st.warning("Please select two different athletes.")
        return

    a1_data = data[data["Name"] == athlete1]
    a2_data = data[data["Name"] == athlete2]

    stat_defs = [
        ("Distance (km)", "Distance (km)"),
        ("Effort", "Effort"),
        ("Time (min)", "Time (min)"),
        ("Activities", None),
    ]
    if "Elevation (m)" in data.columns:
        stat_defs.append(("Elevation (m)", "Elevation (m)"))

    rows = []
    for label, col in stat_defs:
        if col is not None:
            a1_val = float(a1_data[col].sum()) if not a1_data.empty else 0.0
            a2_val = float(a2_data[col].sum()) if not a2_data.empty else 0.0
        else:
            a1_val = float(len(a1_data))
            a2_val = float(len(a2_data))

        max_val = max(a1_val, a2_val, 1.0)
        rows.append(
            {
                "Stat": label,
                "Athlete": athlete1,
                "Value": a1_val,
                "Pct": a1_val / max_val,
            }
        )
        rows.append(
            {
                "Stat": label,
                "Athlete": athlete2,
                "Value": a2_val,
                "Pct": a2_val / max_val,
            }
        )

    chart_df = pd.DataFrame(rows)
    stat_order = [s[0] for s in stat_defs]

    bar = (
        alt.Chart(chart_df)
        .mark_bar(cornerRadiusEnd=4)
        .encode(
            x=alt.X("Pct:Q", axis=None, scale=alt.Scale(domain=[0, 1.25])),
            y=alt.Y(
                "Stat:N",
                sort=stat_order,
                title=None,
                axis=alt.Axis(
                    labelFontSize=12, labelFontWeight="bold", tickSize=0, domain=False
                ),
            ),
            yOffset=alt.YOffset("Athlete:N"),
            color=alt.Color("Athlete:N", legend=alt.Legend(orient="top")),
            tooltip=[
                alt.Tooltip("Athlete:N"),
                alt.Tooltip("Stat:N"),
                alt.Tooltip("Value:Q", format=",.1f"),
            ],
        )
    )

    text = bar.mark_text(
        align="left", baseline="middle", dx=5, fontWeight="bold", fontSize=11
    ).encode(text=alt.Text("Value:Q", format=",.1f"))

    st.altair_chart(
        (bar + text).properties(height=alt.Step(25)),
        width="stretch",
    )


def render_individual_goals(filtered_df: pd.DataFrame) -> None:
    """Render progress bars for individual distance goals."""
    st.subheader("Goal Progress")

    # Get annual distance per person
    person_stats = filtered_df.groupby("Name")["Distance (km)"].sum().to_dict()

    # Create a grid of columns
    cols = st.columns(4)

    # Sort goals by person name for consistency (or by progress if preferred)
    for i, (name, goal) in enumerate(sorted(INDIVIDUAL_GOALS.items())):
        current = person_stats.get(name, 0)
        progress = min(1.0, current / goal)

        with cols[i % 4]:
            with st.container(border=True):
                st.write(f"**{name}**")
                st.metric(
                    label="Progress",
                    value=f"{current:,.1f} / {goal:,.0f} km",
                    delta=f"{(current / goal) * 100:.1f}%",
                )
                st.progress(progress)


def render_individual_effort_chart(data: pd.DataFrame) -> None:
    """Render the cumulative individual effort line chart with padded zero-days."""
    st.subheader("Effort Tracking")

    if data.empty:
        st.info("No data available.")
        return

    # Create a continuous daily timeline for all athletes
    min_date = data["Date"].min()
    max_date = data["Date"].max()
    all_dates = pd.date_range(min_date, max_date)
    names = data["Name"].unique()

    # Reindex to ensure every person has a 0 effort entry for days they didn't train
    multi_idx = pd.MultiIndex.from_product([all_dates, names], names=["Date", "Name"])

    # Sum total effort per day per person
    daily_effort = data.groupby(["Date", "Name"])["Effort"].sum().reset_index()
    daily_effort = daily_effort.set_index(["Date", "Name"])

    # Pad out the missing days with zeros
    full_daily_effort = daily_effort.reindex(multi_idx, fill_value=0).reset_index()

    # Compute statistically accurate cumulative sum per person
    full_daily_effort = full_daily_effort.sort_values(["Name", "Date"])
    full_daily_effort["Cumulative Effort"] = full_daily_effort.groupby("Name")[
        "Effort"
    ].cumsum()

    # Plot the accurate cumulative tracking chart
    line_chart = (
        alt.Chart(full_daily_effort)
        .mark_line(interpolate="step-after")
        .encode(
            x=alt.X("Date:T", title=None),
            y=alt.Y("Cumulative Effort:Q", title="Total Effort"),
            color=alt.Color("Name:N"),
            tooltip=[
                alt.Tooltip("Date:T", format="%Y-%m-%d"),
                alt.Tooltip("Name:N"),
                alt.Tooltip("Cumulative Effort:Q", format=".1f", title="Total Effort"),
            ],
        )
    )

    st.altair_chart(line_chart, width="stretch")


def render_activity_feed(data: pd.DataFrame) -> None:
    """Render the activity feed table."""
    st.header("Activities")
    st.caption(f"{len(data):,} activities")

    display_cols = [
        "Date",
        "Name",
        "Team",
        "Type",
        "Distance (km)",
        "Time (min)",
        "Pace (min/km)",
        "Effort",
    ]

    st.dataframe(
        data.sort_values("Date", ascending=False)[display_cols],
        width="stretch",
        hide_index=True,
        column_config={
            "Date": st.column_config.DateColumn("Date", format="MMM DD, YYYY"),
            "Name": st.column_config.TextColumn("Athlete"),
            "Team": st.column_config.TextColumn("Team"),
            "Type": st.column_config.TextColumn("Type"),
            "Distance (km)": st.column_config.NumberColumn(
                "Distance", format="%.2f km"
            ),
            "Time (min)": st.column_config.NumberColumn("Duration", format="%.0f min"),
            "Pace (min/km)": st.column_config.NumberColumn(
                "Pace", format="%.2f min/km"
            ),
            "Effort": st.column_config.NumberColumn("Effort", format="%.2f"),
        },
    )


def render_ai_section(data: pd.DataFrame, ai_insights: dict) -> None:
    """Render the AI-powered insights and fun facts section."""
    if get_client():
        st.subheader("Summary")

        # Display background status message if currently fetching
        if ai_insights.get("status") == "fetching":
            current_insight = ai_insights.get("insight", "")
            if current_insight != "Generating AI insights...":
                st.info("Refreshing AI insights in the background. Please refresh or interact to update.")
        
        st.info(
            ai_insights.get("insight", "Generating AI insights...")
        )

        ai_facts = ai_insights.get("facts", [])
        if ai_facts and not any(
            "Error" in f or "AI is being shy" in f or "analyzing" in f.lower() for f in ai_facts
        ):
            st.subheader("Key Insights")
            for fact in ai_facts:
                st.write(f"• {fact}")

        # Construct visual metadata caption
        meta = []
        if "model" in ai_insights and ai_insights["model"] != "None (Pending)":
            meta.append(f"Model: {ai_insights['model']}")
        if "generated_at" in ai_insights:
            try:
                from zoneinfo import ZoneInfo
                gen_time = datetime.datetime.fromisoformat(ai_insights["generated_at"])
                if gen_time.tzinfo is None:
                    gen_time = gen_time.replace(tzinfo=datetime.timezone.utc)
                local_time = gen_time.astimezone(ZoneInfo("Pacific/Auckland"))
                meta.append(f"Updated: {local_time.strftime('%I:%M %p, %b %d')}")
            except:
                try:
                    gen_time = datetime.datetime.fromisoformat(ai_insights["generated_at"])
                    meta.append(f"Updated: {gen_time.strftime('%I:%M %p, %b %d')}")
                except:
                    pass
        
        if ai_insights.get("status") == "fetching":
            meta.append("Syncing...")
            
        if meta:
            st.caption(" | ".join(meta))
    else:
        st.subheader("Insights")
        st.info("Gemini API Error")


def render_sidebar(df: pd.DataFrame) -> tuple:
    """Render sidebar filters and return filter values."""
    st.sidebar.header("Filters")

    # --- Data Refresh & Reset Controls ---
    col_update, col_reset = st.sidebar.columns(2)
    with col_update:
        if st.button("Refresh", width="stretch", help="Fetch latest data"):
            load_data.clear()
            st.rerun()
    with col_reset:
        if st.button("Reset", width="stretch", help="Reset all filters"):
            for key in list(st.session_state.keys()):
                if key.startswith("filter_"):
                    del st.session_state[key]
            st.rerun()

    if st.sidebar.button(
        "Refresh AI",
        width="stretch",
        help="Trigger background generation of fresh AI roasts and headlines.",
    ):
        clear_ai_cache()
        st.session_state["force_refresh_ai"] = True
        st.rerun()

    st.sidebar.divider()

    # --- Date Range Filter ---
    min_date, max_date = df["Date"].min(), df["Date"].max()
    today = datetime.date.today()

    # Initialize date filter state
    if "filter_date_preset" not in st.session_state:
        st.session_state["filter_date_preset"] = "All Time"

    with st.sidebar.expander("Date Range", expanded=True):
        # Quick date presets
        date_presets = {
            "Last 7 Days": (today - datetime.timedelta(days=7), today),
            "Last 30 Days": (today - datetime.timedelta(days=30), today),
            "This Month": (today.replace(day=1), today),
            "Last Month": (
                (today.replace(day=1) - datetime.timedelta(days=1)).replace(day=1),
                today.replace(day=1) - datetime.timedelta(days=1),
            ),
            "Year to Date": (datetime.date(today.year, 1, 1), today),
            "All Time": (min_date.date(), max_date.date()),
        }

        selected_preset = st.radio(
            "Quick Select",
            options=list(date_presets.keys()),
            horizontal=True,
            key="filter_date_preset",
            label_visibility="collapsed",
        )

        # Get preset dates, clamped to available data range
        preset_start, preset_end = date_presets[selected_preset]
        preset_start = max(preset_start, min_date.date())
        preset_end = min(preset_end, max_date.date())

        # Custom date input (updates based on preset)
        date_range = st.date_input(
            "Custom Range",
            value=(preset_start, preset_end),
            min_value=min_date,
            max_value=max_date,
            label_visibility="collapsed",
        )

    # --- Team Filter ---
    all_teams = sorted(df["Team"].unique())

    if "filter_teams" not in st.session_state:
        st.session_state["filter_teams"] = all_teams

    with st.sidebar.expander("Teams", expanded=True):
        col_all, col_clear = st.columns(2)
        with col_all:
            if st.button("Select All", key="teams_all", width="stretch"):
                st.session_state["filter_teams"] = all_teams
                st.rerun()
        with col_clear:
            if st.button("Clear", key="teams_clear", width="stretch"):
                st.session_state["filter_teams"] = []
                st.rerun()

        selected_teams = st.pills(
            "Teams",
            all_teams,
            selection_mode="multi",
            key="filter_teams",
            label_visibility="collapsed",
        )

    # --- Activity Type Filter ---
    all_types = sorted(df["Type"].unique())

    if "filter_types" not in st.session_state:
        st.session_state["filter_types"] = all_types

    with st.sidebar.expander("Activity Type", expanded=True):
        col_all, col_clear = st.columns(2)
        with col_all:
            if st.button("Select All", key="types_all", width="stretch"):
                st.session_state["filter_types"] = all_types
                st.rerun()
        with col_clear:
            if st.button("Clear", key="types_clear", width="stretch"):
                st.session_state["filter_types"] = []
                st.rerun()

        selected_types = st.pills(
            "Types",
            all_types,
            selection_mode="multi",
            key="filter_types",
            label_visibility="collapsed",
        )

    # --- Competitors Filter ---
    all_names = sorted(df["Name"].unique())

    if "filter_names" not in st.session_state:
        st.session_state["filter_names"] = all_names

    with st.sidebar.expander("Competitors", expanded=True):
        col_all, col_clear = st.columns(2)
        with col_all:
            if st.button("Select All", key="names_all", width="stretch"):
                st.session_state["filter_names"] = all_names
                st.rerun()
        with col_clear:
            if st.button("Clear", key="names_clear", width="stretch"):
                st.session_state["filter_names"] = []
                st.rerun()

        selected_names = st.pills(
            "Competitors",
            all_names,
            selection_mode="multi",
            key="filter_names",
            label_visibility="collapsed",
        )

    return date_range, selected_teams, selected_types, selected_names


def apply_filters(
    df: pd.DataFrame,
    date_range: tuple,
    selected_teams: list,
    selected_types: list,
    selected_names: list,
) -> tuple:
    """Apply filters to the dataframe and return filtered + history dataframes."""
    categorical_mask = (
        df["Team"].isin(selected_teams)
        & df["Type"].isin(selected_types)
        & df["Name"].isin(selected_names)
    )

    if len(date_range) == 2:
        start_date, end_date = date_range
        date_mask = (df["Date"].dt.date >= start_date) & (
            df["Date"].dt.date <= end_date
        )
        filtered_df = df[date_mask & categorical_mask]
    else:
        filtered_df = df[categorical_mask]

    # History uses categorical filters only (ignores date range)
    history_df = df[categorical_mask].copy()

    return filtered_df, history_df


# --- Main Application ---
def main():
    """Main application entry point."""
    # Data Loading
    df = load_data()
    if df.empty:
        st.stop()

    df["Month"] = df["Date"].dt.strftime("%Y-%m")
    today = datetime.date.today()
    current_month = today.strftime("%Y-%m")

    # Sidebar Filters
    date_range, selected_teams, selected_types, selected_names = render_sidebar(df)
    filtered_df, history_df = apply_filters(
        df, date_range, selected_teams, selected_types, selected_names
    )

    # Fetch AI Content (Non-Blocking)
    data_summary = get_data_summary(df)
    force_refresh_ai = st.session_state.get("force_refresh_ai", False)
    
    ai_insights = get_ai_insights_non_blocking(
        data_summary, SYSTEM_PROMPT, MODELS_TO_TRY, force_refresh=force_refresh_ai
    )
    ai_headlines = get_ai_headlines_non_blocking(
        data_summary, SYSTEM_PROMPT, MODELS_TO_TRY, force_refresh=force_refresh_ai
    )
    
    if force_refresh_ai:
        st.session_state["force_refresh_ai"] = False

    # Reserve space for breaking news ticker
    ticker_placeholder = st.empty()

    # Main Dashboard Header
    st.title("Sleep Comp Fitness Comp")

    if len(date_range) == 2:
        st.markdown(
            f"*Tracking activities from **{date_range[0]}** to **{date_range[1]}***"
        )

    display_metrics(filtered_df)
    st.divider()

    # Reserve space for AI section (rendered last to avoid blocking)
    ai_placeholder = st.empty()
    st.divider()

    # Group Section
    st.header("Group")
    render_activity_heatmap(filtered_df)

    col_group_effort, col_goal_progress = st.columns(2)
    with col_group_effort:
        render_group_effort_chart(filtered_df)
    with col_goal_progress:
        render_goal_progress(filtered_df, today)

    st.divider()

    # Team Section
    st.header("Team")
    col_team_stats, col_win_prob = st.columns(2)

    with col_team_stats:
        render_team_standings(filtered_df, history_df, today, current_month)

    with col_win_prob:
        render_win_probability(df, today)

    render_team_effort_chart(filtered_df)
    st.divider()

    # Individual Section
    st.header("Individual")
    render_individual_standings(filtered_df, history_df, today, current_month)
    render_individual_effort_chart(filtered_df)
    render_individual_records(filtered_df)
    render_head_to_head_comparison(filtered_df)
    st.divider()

    # Activity Feed
    render_activity_feed(filtered_df)

    # Inject Ticker into top placeholder
    if ai_headlines and "headlines" in ai_headlines:
        headlines = ai_headlines["headlines"]
        if isinstance(headlines, list):
            base_str = " &nbsp;&nbsp;&nbsp;&bull;&nbsp;&nbsp;&nbsp; ".join(headlines)
        else:
            base_str = headlines

        unit_str = f"BREAKING NEWS &nbsp;&nbsp;&nbsp;&bull;&nbsp;&nbsp;&nbsp; {base_str} &nbsp;&nbsp;&nbsp;&bull;&nbsp;&nbsp;&nbsp; "
        headlines_str = unit_str * 5

        ticker_placeholder.markdown(
            f"""
            <div style="background-color: #d32f2f; padding: 10px; margin-bottom: 20px; border-radius: 4px; box-shadow: 0 2px 4px rgba(0,0,0,0.2);">
                <marquee scrollamount="8" style="color: #ffffff; font-weight: bold; font-family: inherit; font-size: 1.15rem; vertical-align: middle; text-transform: uppercase;">
                    {headlines_str}
                </marquee>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with ai_placeholder.container():
        render_ai_section(df, ai_insights)


if __name__ == "__main__":
    main()
