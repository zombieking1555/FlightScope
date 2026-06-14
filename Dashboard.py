import pandas as pd
import numpy as np
import streamlit as st
import plotly.graph_objects as go
from pathlib import Path
from datetime import datetime
import sqlite3
from create_db import ensure_db

# Ensure the database file and tables exist before connecting
ensure_db()

conn = sqlite3.connect("flights.db")
cursor = conn.cursor()

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
    acceleration REAL
)
""")

conn.commit()

flights = pd.read_sql_query("SELECT id, filename FROM flights", conn)


st.title("FlightScope Dashboard")


selected_id = None
if len(flights) > 0:
    # Create a mapping once
    flight_name_map = dict(zip(flights["id"], flights["filename"]))

    selected_id = None
    if len(flights) > 0:
        selected_id = st.selectbox(
            "Choose Flight",
            flights["id"],
            format_func=lambda flight_id: flight_name_map[flight_id],
        )
else:
    st.info("First, upload a flight CSV.")

uploaded_file = st.file_uploader("Choose a CSV file", type="csv")
if uploaded_file is not None:
    st.info(f"Ready to import {uploaded_file.name}. Click Import to add.")
    if st.button("Import CSV"):
        lines = uploaded_file.getvalue().decode("utf-8").splitlines()

        # Keep the header line that starts with "# Time"
        cleaned = []
        for line in lines:
            if line.startswith("#") and not line.startswith("# Time"):
                continue
            cleaned.append(line)

        import io
        df = pd.read_csv(io.StringIO("\n".join(cleaned)))

        df.columns = df.columns.str.replace("#", "").str.strip()
        
        df = df.rename(
            columns={
                "Time (s)": "time",
                "Altitude (m)": "altitude",
                "Vertical velocity (m/s)": "velocity",
                "Vertical acceleration (m/s²)": "acceleration",
            }
        )

        required = ["time", "altitude", "velocity"]
        if not all(c in df.columns for c in required):
            st.error("CSV must contain columns: time, altitude, velocity")
            st.stop()
        df[required] = df[required].apply(pd.to_numeric, errors="coerce")
        if df[required].isnull().any().any():
            st.error("Required columns contain non-numeric values; fix CSV.")
            st.stop()

        # skip duplicate filename
        cursor.execute(
            "SELECT id FROM flights WHERE filename = ?", (uploaded_file.name,)
        )
        existing = cursor.fetchone()
        if existing:
            st.warning(f"File already uploaded as flight id {existing[0]}")
            selected_id = existing[0]
        else:
            # insert flight and telemetry (convert to native floats)
            cursor.execute(
                "INSERT INTO flights (filename, upload_date, max_altitude, max_velocity) VALUES (?, ?, ?, ?)",
                (
                    uploaded_file.name,
                    datetime.now().isoformat(),
                    float(df["altitude"].max()),
                    float(df["velocity"].max()),
                ),
            )
            flight_id = cursor.lastrowid
            for _, row in df.iterrows():
                assert flight_id is not None
                accel = (
                    float(row["acceleration"])
                    if "acceleration" in df.columns and pd.notna(row["acceleration"])
                    else None
                )
                cursor.execute(
                    "INSERT INTO telemetry (flight_id, time, altitude, velocity, acceleration) VALUES (?, ?, ?, ?, ?)",
                    (
                        int(flight_id),
                        float(row["time"]),
                        float(row["altitude"]),
                        float(row["velocity"]),
                        accel,
                    ),
                )
            conn.commit()
            selected_id = flight_id
            flights = pd.read_sql_query("SELECT id, filename FROM flights", conn)

burnout = None
apogee = None
apogee_idx = None
parachute = None
parachute_idx = None

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
    else:
        # ensure numeric native types for plotting/serialization
        cols_to_convert = ["time", "altitude", "velocity"]
        if "acceleration" in df.columns:
            cols_to_convert.append("acceleration")
        df[cols_to_convert] = df[cols_to_convert].astype(float)

        launch_time = float(df.loc[df["acceleration"] > 15, "time"].iloc[0])

        df = df[df["time"] >= launch_time].reset_index(drop=True)
        df["time"] = df["time"].astype(float)
        df["time"] -= launch_time
        launch_idx = df[df["acceleration"] > 15].index[0]

        mask = (df.index > launch_idx) & (df["velocity"].abs() < 0.5)

        sustained = mask.rolling(window=50).sum() >= 50

        land_idx = None
        land_candidates = sustained[sustained].index
        if len(land_candidates) == 0:
            land_time = float(df["time"].iloc[-1])
        else:
            land_idx = int(land_candidates[0]) - 49
            if land_idx < 0:
                land_idx = 0
            land_time = float(df.iloc[land_idx]["time"])
            

        df = df[df["time"] <= land_time]
        df["time"] = df["time"].astype(float)

        st.write(df.head())

        # Calculate burnout and parachute deployment if acceleration data is available
        if "acceleration" in df.columns:
            accel = np.asarray(df["acceleration"].values, dtype=float)
            # Burnout detected at maximum negative jerk (steepest drop in acceleration)
            # This is the transition from boost phase to coast phase
            jerk = np.diff(accel)
            burnout_idx = np.argmin(jerk)  # Index of maximum negative jerk
            if burnout_idx > 0 and jerk[burnout_idx] < -0.5:  # Ensure significant drop
                burnout = df["time"].iloc[burnout_idx]

            # Parachute deployment detected at maximum positive jerk (steepest rise in acceleration)
            # This is the transition from coast phase to descent phase
            parachute_idx = np.argmax(jerk)  # Index of maximum positive jerk
            if (
                parachute_idx > 0 and jerk[parachute_idx] > 0.5
            ):  # Ensure significant rise
                parachute = df["time"].iloc[parachute_idx]

            # idxmax() returns the index label; keep it as-is for .loc
        apogee_idx = df["altitude"].idxmax()
        apogee = df["altitude"].max()

        vel_time_graph = go.Figure()
        vel_time_graph.add_trace(
            go.Scatter(x=df["time"], y=df["velocity"], mode="lines", name="Velocity")
        )
        vel_time_graph.update_layout(
            title="Velocity vs Time", xaxis_title="Time", yaxis_title="Velocity"
        )

        alt_time_graph = go.Figure()
        alt_time_graph.add_trace(
            go.Scatter(x=df["time"], y=df["altitude"], mode="lines", name="Altitude")
        )
        alt_time_graph.update_layout(
            title="Altitude vs Time", xaxis_title="Time", yaxis_title="Altitude"
        )
        if burnout is not None:
            idx = (df["time"] - burnout).abs().idxmin()
            burnout_altitude = df.loc[idx, "altitude"]
            burnout_velocity = df.loc[idx, "velocity"]
            alt_time_graph.add_trace(
                go.Scatter(
                    x=[burnout],
                    y=[burnout_altitude],
                    mode="markers",
                    name="Motor Burnout",
                    marker=dict(size=12),
                )
            )
            vel_time_graph.add_trace(
                go.Scatter(
                    x=[burnout],
                    y=[burnout_velocity],
                    mode="markers",
                    name="Motor Burnout",
                    marker=dict(size=12),
                )
            )
        else:
            st.warning("Could not detect motor burnout from acceleration data.")
        if apogee is not None:
            assert apogee_idx is not None
            apogee_time = df.loc[apogee_idx, "time"]
            apogee_velocity = df.loc[apogee_idx, "velocity"]
            alt_time_graph.add_trace(
                go.Scatter(
                    x=[apogee_time],
                    y=[apogee],
                    mode="markers",
                    name="Apogee",
                    marker=dict(size=12),
                )
            )
            vel_time_graph.add_trace(
                go.Scatter(
                    x=[apogee_time],
                    y=[apogee_velocity],
                    mode="markers",
                    name="Apogee",
                    marker=dict(size=12),
                )
            )
        else:
            st.warning("Could not detect apogee from altitude data.")
        if parachute is not None:
            idx = (df["time"] - parachute).abs().idxmin()
            parachute_altitude = df.loc[idx, "altitude"]
            parachute_velocity = df.loc[idx, "velocity"]
            alt_time_graph.add_trace(
                go.Scatter(
                    x=[parachute],
                    y=[parachute_altitude],
                    mode="markers",
                    name="Parachute Deploy",
                    marker=dict(size=12),
                )
            )
            vel_time_graph.add_trace(
                go.Scatter(
                    x=[parachute],
                    y=[parachute_velocity],
                    mode="markers",
                    name="Parachute Deploy",
                    marker=dict(size=12),
                )
            )
        else:
            st.warning("Could not detect parachute deployment from acceleration data.")

        if land_idx is not None:
            alt_time_graph.add_trace(
                go.Scatter(
                    x=[land_time],
                    y=[0],
                    mode="markers",
                    name="Landing",
                    marker=dict(size=12),
                )
            )
            vel_time_graph.add_trace(
                go.Scatter(
                    x=[land_time],
                    y=[0],
                    mode="markers",
                    name="Landing",
                    marker=dict(size=12),
                )
            )
        else:
            st.warning("Could not detect landing from velocity data.")

        st.plotly_chart(alt_time_graph)
        st.plotly_chart(vel_time_graph)
else:
    st.info("No flight selected yet. Upload a CSV to see flight telemetry.")


st.sidebar.subheader("Admin")

# initialize state
if "confirm_clear" not in st.session_state:
    st.session_state.confirm_clear = False

# Step 1: click clear
if st.sidebar.button("🗑️ Clear Database"):
    st.session_state.confirm_clear = True

# Step 2: confirmation UI
if st.session_state.confirm_clear:

    st.sidebar.warning("Are you sure? This will delete ALL data.")

    col1, col2 = st.sidebar.columns(2)

    with col1:
        if st.button("✓ Confirm"):
            try:
                cursor.execute("DELETE FROM telemetry")
                cursor.execute("DELETE FROM flights")
                conn.commit()

                st.sidebar.success("Database cleared!")
                st.session_state.confirm_clear = False
                st.rerun()

            except Exception as e:
                st.sidebar.error(f"Error: {e}")

    with col2:
        if st.button("✗ Cancel"):
            st.session_state.confirm_clear = False
            st.rerun()
