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

st.title("FlightScope Dashboard")

selected_id = st.session_state.get("selected_id", None)

if len(flights) > 0:
    flight_name_map = dict(zip(flights["id"], flights["filename"]))

    selected_id = st.selectbox(
        "Choose Flight",
        flights["id"],
        format_func=lambda flight_id: flight_name_map[flight_id],
        index=0 if selected_id is None else list(flights["id"]).index(selected_id),
    )
else:
    st.info("First, upload a flight CSV under the Upload Flight tab.")

# ----------------------------
# TELEMETRY LOADING
# ----------------------------
if selected_id is not None:

    df = pd.read_sql_query(
        """
        SELECT *
        FROM telemetry
        WHERE flight_id = ?
        ORDER BY time
        """,
        conn,
        params=(selected_id,),
    )

    if df.empty:
        st.info("Selected flight has no telemetry.")
        st.stop()

    df = df.astype(float, errors="ignore")

    # ----------------------------
    # FLIGHT FILTERING (robust)
    # ----------------------------
    # Try to find a clear launch acceleration spike. Prefer >15 m/s^2,
    # fall back to >5 m/s^2, otherwise use the first telemetry row.
    launch_idx_candidates = df.index[df["acceleration"] > 15].tolist()
    threshold = 15
    if not launch_idx_candidates:
        launch_idx_candidates = df.index[df["acceleration"] > 5].tolist()
        threshold = 5

    if not launch_idx_candidates:
        st.warning(
            "Launch acceleration spike not found; using first telemetry time as launch."
        )
        launch_idx_original = 0
    else:
        launch_idx_original = int(launch_idx_candidates[0])

    # use positional indexing since launch_idx_original is a row position
    launch_time = float(df.iloc[launch_idx_original]["time"])

    df = df[df["time"] >= launch_time].reset_index(drop=True)
    df["time"] -= launch_time

    # Recompute launch index relative to the filtered/reset dataframe
    rel_candidates = df.index[df["acceleration"] > threshold].tolist()
    launch_idx = int(rel_candidates[0]) if rel_candidates else 0

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

    # ----------------------------
    # ROCKET RENDER FRAME
    # ----------------------------
    # ----------------------------
    # ROCKET RENDER FRAME
    # ----------------------------

    TARGET_FRAMES = 500

    if "cached_flight" not in st.session_state:
        st.session_state.cached_flight = None

    if "frame_cache" not in st.session_state:
        st.session_state.frame_cache = []

    if "render_df" not in st.session_state:
        st.session_state.render_df = None

    def build_render_df(df, target_frames=TARGET_FRAMES):
        if len(df) <= target_frames:
            return df.reset_index(drop=True)

        indices = np.linspace(0, len(df) - 1, target_frames, dtype=int)

        return df.iloc[indices].reset_index(drop=True)

        # Rebuild cache when flight changes

    if st.session_state.cached_flight != selected_id:

        st.session_state.cached_flight = selected_id
        st.session_state.render_df = build_render_df(df)
        st.session_state.frame_cache = []

        render_df = st.session_state.render_df

        progress = st.progress(0, text="Rendering flight frames...")

        for i, (_, row) in enumerate(render_df.iterrows()):

            zenith = row.get("zenith", None)
            azimuth = row.get("azimuth", None)
            altitude = row.get("altitude", None)

            if pd.isna(zenith) or pd.isna(azimuth) or pd.isna(altitude):
                img = render_frame_alt_only(
                    altitude=altitude if not pd.isna(altitude) else 0
                )
            else:
                img = render_frame(
                    zenith=zenith,
                    azimuth=azimuth,
                    altitude=altitude,
                )

            st.session_state.frame_cache.append(img)

            progress.progress(
                (i + 1) / len(render_df),
                text=f"Rendering frame {i + 1}/{len(render_df)}",
            )

        progress.empty()

    st.session_state.video_path = create_mp4(
        st.session_state.frame_cache, f"cache/flight_{selected_id}.mp4", fps=30
    )

    render_df = st.session_state.render_df
    frame_cache = st.session_state.frame_cache

    tab1, tab2 = st.tabs(["Video", "Frame Viewer"])

    with tab1:
        video_path = st.session_state.video_path

        with open(video_path, "rb") as f:
            video_bytes = f.read()

        st.video(video_bytes)

    with tab2:

        frame = st.slider(
            "Frame",
            min_value=0,
            max_value=len(frame_cache) - 1,
            value=0,
        )
        assert render_df is not None
        row = render_df.iloc[frame]
        img = frame_cache[frame]
        st.image(img)

        st.metric("Time", f"{row['time']:.2f} s")

        if not pd.isna(row.get("altitude", None)):
            st.metric("Altitude", f"{row['altitude']:.1f} m")

        if not pd.isna(row.get("zenith", None)):
            st.metric("Zenith", f"{row['zenith']:.1f}°")

        if not pd.isna(row.get("azimuth", None)):
            st.metric("Azimuth", f"{row['azimuth']:.1f}°")


else:
    st.info("No flight selected yet. Upload a CSV to see telemetry.")


# ----------------------------
# SIDEBAR ADMIN
# ----------------------------
st.sidebar.subheader("Admin")

if "confirm_clear" not in st.session_state:
    st.session_state.confirm_clear = False

if st.sidebar.button("🗑️ Clear Database"):
    st.session_state.confirm_clear = True

if st.session_state.confirm_clear:

    st.sidebar.warning("Are you sure? This will delete ALL data.")

    col1, col2 = st.sidebar.columns(2)

    with col1:
        if st.button("✓ Confirm"):
            cursor.execute("DELETE FROM telemetry")
            cursor.execute("DELETE FROM flights")
            conn.commit()

            st.session_state.confirm_clear = False
            st.success("Database cleared!")
            st.rerun()

    with col2:
        if st.button("✗ Cancel"):
            st.session_state.confirm_clear = False
            st.rerun()
