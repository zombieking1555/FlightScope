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
        params=(primary_id,),
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
    launch_idx_secondary = int(rel_candidates_secondary[0]) if rel_candidates_secondary else 
    
    launch_idx_list = [{launch_idx_primary, launch_idx_secondary}]

    
    land_time_list = []
    land_idx_list = []
    # progress ended here
    # make mask a Series (aligned with dataframe) to avoid type/alignment issues
    mask = pd.Series(df.index > launch_idx, index=df.index) & (
        df["velocity"].abs() < 0.5
    )
    sustained = mask.rolling(window=50).sum() >= 50

    land_candidates = sustained[sustained].index

    if len(land_candidates) == 0:
        land_time = float(df["time"].iloc[-1])
        land_idx = None
    else:
        land_idx = int(land_candidates[0]) - 49
        land_idx = max(0, land_idx)
        land_time = float(df.iloc[land_idx]["time"])

    df = df[df["time"] <= land_time].reset_index(drop=True)

    st.write(df.head())

    # ----------------------------
    # EVENT DETECTION
    # ----------------------------
    burnout = None
    parachute = None
    apogee_idx = df["altitude"].idxmax()
    apogee = df["altitude"].max()

    accel = np.asarray(df["acceleration"].values, dtype=float)
    jerk = np.diff(accel)

    burnout_idx = np.argmin(jerk)
    if burnout_idx > 0 and jerk[burnout_idx] < -0.5:
        burnout = df["time"].iloc[burnout_idx]

    parachute_idx = np.argmax(jerk)
    if parachute_idx > 0 and jerk[parachute_idx] > 0.5:
        parachute = df["time"].iloc[parachute_idx]

    has_zenith = "zenith" in df.columns and not df["zenith"].isna().all()
    # ----------------------------
    # PLOTTING
    # ----------------------------
    vel_fig = go.Figure()
    alt_fig = go.Figure()
    zenith_fig = go.Figure()

    vel_fig.add_trace(
        go.Scatter(x=df["time"], y=df["velocity"], mode="lines", name="Velocity")
    )

    alt_fig.add_trace(
        go.Scatter(x=df["time"], y=df["altitude"], mode="lines", name="Altitude")
    )

    if has_zenith:
        zenith_fig.add_trace(
            go.Scatter(x=df["time"], y=df["zenith"], mode="lines", name="zenith")
        )

    vel_fig.update_layout(title="Velocity vs Time")
    alt_fig.update_layout(title="Altitude vs Time")
    zenith_fig.update_layout(title="zenith vs Time")

    # Burnout marker
    if burnout is not None:
        idx = (df["time"] - burnout).abs().idxmin()

        vel_fig.add_trace(
            go.Scatter(
                x=[burnout],
                y=[df.loc[idx, "velocity"]],
                mode="markers",
                marker=dict(size=12),
                name="Burnout",
            )
        )

        alt_fig.add_trace(
            go.Scatter(
                x=[burnout],
                y=[df.loc[idx, "altitude"]],
                mode="markers",
                marker=dict(size=12),
                name="Burnout",
            )
        )

        if has_zenith:
            zenith_fig.add_trace(
                go.Scatter(
                    x=[burnout],
                    y=[df.loc[idx, "zenith"]],
                    mode="markers",
                    marker=dict(size=12),
                    name="Burnout",
                )
            )

    else:
        st.warning("Burnout time could not be determined from acceleration data.")

    # Apogee marker
    apogee_time = df.loc[apogee_idx, "time"]

    vel_fig.add_trace(
        go.Scatter(
            x=[apogee_time],
            y=[df.loc[apogee_idx, "velocity"]],
            mode="markers",
            marker=dict(size=12),
            name="Apogee",
        )
    )

    alt_fig.add_trace(
        go.Scatter(
            x=[apogee_time],
            y=[apogee],
            mode="markers",
            marker=dict(size=12),
            name="Apogee",
        )
    )

    if has_zenith:
        zenith_fig.add_trace(
            go.Scatter(
                x=[apogee_time],
                y=[df.loc[apogee_idx, "zenith"]],
                mode="markers",
                marker=dict(size=12),
                name="Apogee",
            )
        )

    # Parachute marker
    if parachute is not None:
        idx = (df["time"] - parachute).abs().idxmin()

        vel_fig.add_trace(
            go.Scatter(
                x=[parachute],
                y=[df.loc[idx, "velocity"]],
                mode="markers",
                marker=dict(size=12),
                name="Parachute",
            )
        )

        alt_fig.add_trace(
            go.Scatter(
                x=[parachute],
                y=[df.loc[idx, "altitude"]],
                mode="markers",
                marker=dict(size=12),
                name="Parachute",
            )
        )

        if has_zenith:
            zenith_fig.add_trace(
                go.Scatter(
                    x=[parachute],
                    y=[df.loc[idx, "zenith"]],
                    mode="markers",
                    marker=dict(size=12),
                    name="Parachute",
                )
            )
    else:
        st.warning(
            "Parachute deployment time could not be determined from acceleration data."
        )

    # Landing marker
    if land_idx is not None:
        land_time = df.iloc[land_idx]["time"]

        vel_fig.add_trace(
            go.Scatter(
                x=[land_time],
                y=[0],
                mode="markers",
                marker=dict(size=12),
                name="Landing",
            )
        )

        alt_fig.add_trace(
            go.Scatter(
                x=[land_time],
                y=[0],
                mode="markers",
                marker=dict(size=12),
                name="Landing",
            )
        )
    else:
        st.warning("Landing time could not be determined from velocity data.")

    st.plotly_chart(alt_fig)
    st.plotly_chart(vel_fig)
    if has_zenith:
        st.plotly_chart(zenith_fig)