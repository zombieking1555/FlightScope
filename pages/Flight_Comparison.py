import os

import pandas as pd
import numpy as np
import streamlit as st
import plotly.graph_objects as go
import sqlite3
import pyvista as pv

from mp4_tool import create_mp4
from rocket_render import render_frame_alt_only, render_rocket, render_frame
from db import get_connection

# ----------------------------
# DB SETUP
# ----------------------------
conn = get_connection()
cursor = conn.cursor()

# Ensure tables exist
cursor.execute("""
CREATE TABLE IF NOT EXISTS flights (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT,
    upload_date TEXT,
    max_altitude REAL,
    max_velocity REAL
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS telemetry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    flight_id INTEGER,
    time REAL,
    altitude REAL,
    velocity REAL,
    acceleration REAL,
    zenith REAL,
    azimuth REAL
)
""")

conn.commit()

# ----------------------------
# LOAD FLIGHT LIST
# ----------------------------
flights = pd.read_sql_query("SELECT id, filename FROM flights", conn)

st.title("Compare Flights")

primary_id = st.session_state.get("primary_id", None)
secondary_id = st.session_state.get("secondary_id", None)
id_list = [primary_id, secondary_id]

if len(flights) > 0:
    col1, col2 = st.columns(spec=2, gap="small")
    flight_name_map = dict(zip(flights["id"], flights["filename"]))

    with col1:
        primary_id = st.selectbox(
            "Choose Primary Flight",
            flights["id"],
            format_func=lambda flight_id: flight_name_map[flight_id],
            index=0 if primary_id is None else list(flights["id"]).index(primary_id),
        )
    with col2:
        secondary_id = st.selectbox(
            "Choose Secondary Flight",
            flights["id"],
            format_func=lambda flight_id: flight_name_map[flight_id],
            index=0 if secondary_id is None else list(flights["id"]).index(secondary_id),
        )
else:
    st.info("First, upload a flight CSV under the Upload Flight tab.")

# ----------------------------
# TELEMETRY LOADING
# ----------------------------
if primary_id is not None and secondary_id is not None:

    df_primary = pd.read_sql_query(
        """
        SELECT *
        FROM telemetry
        WHERE flight_id = ?
        ORDER BY time
        """,
        conn,
        params=(primary_id,),
    )

    df_secondary = pd.read_sql_query(
        """
        SELECT *
        FROM telemetry
        WHERE flight_id = ?
        ORDER BY time
        """,
        conn,
        params=(secondary_id,),
    )

    if df_primary.empty:
        st.info("Selected primary flight has no telemetry. Please select a different flight.")
        st.stop()
    
    if df_secondary.empty:
        st.info("Selected secondary flight has no telemetry. Please select a different flight.")

    df_primary = df_primary.astype(float, errors="ignore")
    df_secondary = df_secondary.astype(float, errors="ignore")
    df_list = [df_primary, df_secondary]
    # ----------------------------
    # FLIGHT FILTERING
    # ----------------------------

    # Try to find a clear launch acceleration spike. Prefer >15 m/s^2,
    # fall back to >5 m/s^2, otherwise use the first telemetry row.
    launch_idx_original_list = []
    threshold_list = []
    for df in df_list:
        launch_idx_candidates = df.index[df["acceleration"] > 15].tolist()
        threshold = 15
        if not launch_idx_candidates:
            launch_idx_candidates = df.index[df["acceleration"] > 5].tolist()
            threshold = 5
        threshold_list.append(threshold)

        if not launch_idx_candidates:
            st.warning(
                "Launch acceleration spike not found; using first telemetry time as launch."
            )
            launch_idx_original_list.append(0)
        else:
            launch_idx_original_list.append(int(launch_idx_candidates[0]))

    launch_idx_original_primary = launch_idx_original_list[0]
    launch_idx_original_secondary = launch_idx_original_list[1]
    threshold_primary = threshold_list[0]
    threshold_secondary = threshold_list[1]
    # use positional indexing since launch_idx_original is a row position
    launch_time_primary = float(df_primary.iloc[launch_idx_original_primary]["time"])
    launch_time_secondary = float(df_secondary.iloc[launch_idx_original_secondary]["time"])

    df_primary = df_primary[df_primary["time"] >= launch_time_primary].reset_index(drop=True)
    df_primary["time"] -= launch_time_primary
    df_secondary = df_secondary[df_secondary["time"] >= launch_time_secondary].reset_index(drop=True)
    df_secondary["time"] -= launch_time_secondary

    # Recompute launch index relative to the filtered/reset dataframe
    rel_candidates_primary = df_primary.index[df_primary["acceleration"] > threshold_primary].tolist()
    launch_idx_primary = int(rel_candidates_primary[0]) if rel_candidates_primary else 0
    rel_candidates_secondary = df_secondary.index[df_secondary["acceleration"] > threshold_secondary].tolist()
    launch_idx_secondary = int(rel_candidates_secondary[0]) if rel_candidates_secondary else 0

    #PRIMARY RUN
    # make mask a Series (aligned with dataframe) to avoid type/alignment issues
    mask = pd.Series(df_primary.index > launch_idx_primary, index=df_primary.index) & (
        df_primary["velocity"].abs() < 0.5
    )
    sustained = mask.rolling(window=50).sum() >= 50

    land_candidates_primary = sustained[sustained].index

    if len(land_candidates_primary) == 0:
        land_time_primary = float(df_primary["time"].iloc[-1])
        land_idx_primary = None
    else:
        land_idx_primary = int(land_candidates_primary[0]) - 49
        land_idx_primary = max(0, land_idx_primary)
        land_time_primary = float(df_primary.iloc[land_idx_primary]["time"])

    df_primary = df_primary[df_primary["time"] <= land_time_primary].reset_index(drop=True)

    

    #SECONDARY RUN
    mask = pd.Series(df_secondary.index > launch_idx_secondary, index=df_secondary.index) & (
        df_secondary["velocity"].abs() < 0.5
    )
    sustained = mask.rolling(window=50).sum() >= 50

    land_candidates_secondary = sustained[sustained].index

    if len(land_candidates_secondary) == 0:
        land_time_secondary = float(df_secondary["time"].iloc[-1])
        land_idx_secondary = None
    else:
        land_idx_secondary = int(land_candidates_secondary[0]) - 49
        land_idx_secondary = max(0, land_idx_secondary)
        land_time_secondary = float(df_secondary.iloc[land_idx_secondary]["time"])

    df_secondary = df_secondary[df_secondary["time"] <= land_time_secondary].reset_index(drop=True)

    
    col1, col2 = st.columns(2)
    with col1:
        st.write(df_primary.head())
    with col2:
        st.write(df_secondary.head())

    # ----------------------------
    # EVENT DETECTION
    # ----------------------------
    burnout_primary = None
    burnout_secondary = None
    parachute_primary = None
    parachute_secondary = None
    apogee_idx_primary = df_primary["altitude"].idxmax()
    apogee_idx_secondary = df_secondary["altitude"].idxmax()
    apogee_primary = df_primary["altitude"].max()
    apogee_secondary = df_secondary["altitude"].max()

    accel_primary = np.asarray(df_primary["acceleration"].values, dtype=float)
    accel_secondary = np.asarray(df_secondary["acceleration"].values, dtype=float)
    jerk_primary = np.diff(accel_primary)
    jerk_secondary = np.diff(accel_secondary)

    burnout_idx_primary = np.argmin(jerk_primary)
    if burnout_idx_primary > 0 and jerk_primary[burnout_idx_primary] < -0.5:
        burnout_primary = df_primary["time"].iloc[burnout_idx_primary]

    burnout_idx_secondary = np.argmin(jerk_secondary)
    if burnout_idx_secondary > 0 and jerk_secondary[burnout_idx_secondary] < -0.5:
        burnout_secondary = df_secondary["time"].iloc[burnout_idx_secondary]

    parachute_idx_primary = np.argmax(jerk_primary)
    if parachute_idx_primary > 0 and jerk_primary[parachute_idx_primary] > 0.5:
        parachute_primary = df_primary["time"].iloc[parachute_idx_primary]
    
    parachute_idx_secondary = np.argmax(jerk_secondary)
    if parachute_idx_secondary > 0 and jerk_secondary[parachute_idx_secondary] > 0.5:
        parachute_secondary = df_secondary["time"].iloc[parachute_idx_secondary]

    has_zenith_primary = "zenith" in df_primary.columns and not df_primary["zenith"].isna().all()
    has_zenith_secondary = "zenith" in df_secondary.columns and not df_secondary["zenith"].isna().all()
    # ----------------------------
    # PLOTTING
    # ----------------------------
    vel_fig = go.Figure()
    alt_fig = go.Figure()
    zenith_fig = go.Figure()
    event_list = []
    primary_times = []
    secondary_times = []
    df_list = [df_primary, df_secondary]
    has_zenith_list = [has_zenith_primary, has_zenith_secondary]

    for i in range(2):
        vel_fig.add_trace(
            go.Scatter(x=df_list[i]["time"], y=df_list[i]["velocity"], mode="lines", name="Velocity")
        )

        alt_fig.add_trace(
            go.Scatter(x=df_list[i]["time"], y=df_list[i]["altitude"], mode="lines", name="Altitude")
        )

        if has_zenith_list[i]:
            zenith_fig.add_trace(
                go.Scatter(x=df_list[i]["time"], y=df_list[i]["zenith"], mode="lines", name="zenith")
            )

    vel_fig.update_layout(title="Velocity vs Time")
    alt_fig.update_layout(title="Altitude vs Time")
    zenith_fig.update_layout(title="Zenith vs Time")

    # Burnout marker
    if burnout_primary is not None:
        primary_times.append(burnout_primary)
        idx = (df_primary["time"] - burnout_primary).abs().idxmin()

        vel_fig.add_trace(
            go.Scatter(
                x=[burnout_primary],
                y=[df_primary.loc[idx, "velocity"]],
                mode="markers",
                marker=dict(size=12),
                name="Burnout (primary)",
            )
        )

        alt_fig.add_trace(
            go.Scatter(
                x=[burnout_primary],
                y=[df_primary.loc[idx, "altitude"]],
                mode="markers",
                marker=dict(size=12),
                name="Burnout (primary)",
            )
        )

        if has_zenith_primary:
            zenith_fig.add_trace(
                go.Scatter(
                    x=[burnout_primary],
                    y=[df_primary.loc[idx, "zenith"]],
                    mode="markers",
                    marker=dict(size=12),
                    name="Burnout (primary)",
                )
            )

    else:
        st.warning("Primary burnout time could not be determined from acceleration data.")

    if burnout_secondary is not None:
        secondary_times.append(burnout_secondary)
        idx = (df_secondary["time"] - burnout_secondary).abs().idxmin()

        vel_fig.add_trace(
            go.Scatter(
                x=[burnout_secondary],
                y=[df_secondary.loc[idx, "velocity"]],
                mode="markers",
                marker=dict(size=12),
                name="Burnout (secondary)",
            )
        )

        alt_fig.add_trace(
            go.Scatter(
                x=[burnout_secondary],
                y=[df_secondary.loc[idx, "altitude"]],
                mode="markers",
                marker=dict(size=12),
                name="Burnout (secondary)",
            )
        )

        if has_zenith_secondary:
            zenith_fig.add_trace(
                go.Scatter(
                    x=[burnout_secondary],
                    y=[df_secondary.loc[idx, "zenith"]],
                    mode="markers",
                    marker=dict(size=12),
                    name="Burnout (secondary)",
                )
            )

    else:
        st.warning("Secondary burnout time could not be determined from acceleration data.")

    # Apogee marker
    apogee_time = df_primary.loc[apogee_idx_primary, "time"]
    primary_times.append(apogee_time)

    vel_fig.add_trace(
        go.Scatter(
            x=[apogee_time],
            y=[df_primary.loc[apogee_idx_primary, "velocity"]],
            mode="markers",
            marker=dict(size=12),
            name="Apogee (primary)",
        )
    )

    alt_fig.add_trace(
        go.Scatter(
            x=[apogee_time],
            y=[apogee_primary],
            mode="markers",
            marker=dict(size=12),
            name="Apogee (primary)",
        )
    )

    if has_zenith_primary:
        zenith_fig.add_trace(
            go.Scatter(
                x=[apogee_time],
                y=[df_primary.loc[apogee_idx_primary, "zenith"]],
                mode="markers",
                marker=dict(size=12),
                name="Apogee (primary)",
            )
        )
    
    apogee_time = df_secondary.loc[apogee_idx_secondary, "time"]
    secondary_times.append(apogee_time)

    vel_fig.add_trace(
        go.Scatter(
            x=[apogee_time],
            y=[df_secondary.loc[apogee_idx_secondary, "velocity"]],
            mode="markers",
            marker=dict(size=12),
            name="Apogee (secondary)",
        )
    )

    alt_fig.add_trace(
        go.Scatter(
            x=[apogee_time],
            y=[apogee_secondary],
            mode="markers",
            marker=dict(size=12),
            name="Apogee (secondary)",
        )
    )

    if has_zenith_secondary:
        zenith_fig.add_trace(
            go.Scatter(
                x=[apogee_time],
                y=[df_secondary.loc[apogee_idx_secondary, "zenith"]],
                mode="markers",
                marker=dict(size=12),
                name="Apogee (secondary)",
            )
        )

    # Parachute marker
    if parachute_primary is not None:
        primary_times.append(parachute_primary)
        idx = (df_primary["time"] - parachute_primary).abs().idxmin()

        vel_fig.add_trace(
            go.Scatter(
                x=[parachute_primary],
                y=[df_primary.loc[idx, "velocity"]],
                mode="markers",
                marker=dict(size=12),
                name="Parachute (primary)",
            )
        )

        alt_fig.add_trace(
            go.Scatter(
                x=[parachute_primary],
                y=[df_primary.loc[idx, "altitude"]],
                mode="markers",
                marker=dict(size=12),
                name="Parachute (primary)",
            )
        )

        if has_zenith_primary:
            zenith_fig.add_trace(
                go.Scatter(
                    x=[parachute_primary],
                    y=[df_primary.loc[idx, "zenith"]],
                    mode="markers",
                    marker=dict(size=12),
                    name="Parachute (primary)",
                )
            )
    else:
        st.warning(
            "Primary parachute deployment time could not be determined from acceleration data."
        )

    if parachute_secondary is not None:
        secondary_times.append(parachute_secondary)
        idx = (df_secondary["time"] - parachute_secondary).abs().idxmin()

        vel_fig.add_trace(
            go.Scatter(
                x=[parachute_secondary],
                y=[df_secondary.loc[idx, "velocity"]],
                mode="markers",
                marker=dict(size=12),
                name="Parachute (secondary)",
            )
        )

        alt_fig.add_trace(
            go.Scatter(
                x=[parachute_secondary],
                y=[df_secondary.loc[idx, "altitude"]],
                mode="markers",
                marker=dict(size=12),
                name="Parachute (secondary)",
            )
        )

        if has_zenith_secondary:
            zenith_fig.add_trace(
                go.Scatter(
                    x=[parachute_secondary],
                    y=[df_secondary.loc[idx, "zenith"]],
                    mode="markers",
                    marker=dict(size=12),
                    name="Parachute (secondary)",
                )
            )
    else:
        st.warning(
            "Secondary parachute deployment time could not be determined from acceleration data."
        )

    # Landing marker
    if land_idx_primary is not None:
        land_time = df_primary.iloc[land_idx_primary]["time"]
        primary_times.append(land_time)

        vel_fig.add_trace(
            go.Scatter(
                x=[land_time],
                y=[0],
                mode="markers",
                marker=dict(size=12),
                name="Landing (primary)",
            )
        )

        alt_fig.add_trace(
            go.Scatter(
                x=[land_time],
                y=[0],
                mode="markers",
                marker=dict(size=12),
                name="Landing (primary)",
            )
        )
    else:
        st.warning("Primary landing time could not be determined from velocity data.")
    
    if land_idx_secondary is not None:
        land_time = df_secondary.iloc[land_idx_secondary]["time"]
        secondary_times.append(land_time)

        vel_fig.add_trace(
            go.Scatter(
                x=[land_time],
                y=[0],
                mode="markers",
                marker=dict(size=12),
                name="Landing (secondary)",
            )
        )

        alt_fig.add_trace(
            go.Scatter(
                x=[land_time],
                y=[0],
                mode="markers",
                marker=dict(size=12),
                name="Landing (secondary)",
            )
        )
    else:
        st.warning("Secondary landing time could not be determined from velocity data.")

    st.plotly_chart(alt_fig)
    st.plotly_chart(vel_fig)
    while len(primary_times) < 4:
        primary_times.append("-")
    while len(secondary_times) < 4:
        secondary_times.append("-")

    events = ["Burnout", "Apogee", "Parachute", "Landing"]
    data = {
        "Event": events,
        "Primary Flight Timestamps (s)": primary_times,
        "Secondary Flight Timestamps (s)": secondary_times,
    }

    has_zenith = has_zenith_primary or has_zenith_secondary
    if has_zenith:
        st.plotly_chart(zenith_fig)

    st.subheader("Comparison Summary")
    st.table(pd.DataFrame(data))