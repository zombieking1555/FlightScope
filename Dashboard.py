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

flights = pd.read_sql_query(
    "SELECT id, filename FROM flights",
    conn
)


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
        df = pd.read_csv(uploaded_file)
        required = ["time","altitude","velocity"]
        if not all(c in df.columns for c in required):
            st.error("CSV must contain columns: time, altitude, velocity"); st.stop()
        df[required] = df[required].apply(pd.to_numeric, errors="coerce")
        if df[required].isnull().any().any():
            st.error("Required columns contain non-numeric values; fix CSV."); st.stop()

        # skip duplicate filename
        cursor.execute("SELECT id FROM flights WHERE filename = ?", (uploaded_file.name,))
        existing = cursor.fetchone()
        if existing:
            st.warning(f"File already uploaded as flight id {existing[0]}")
            selected_id = existing[0]
        else:
            # insert flight and telemetry (convert to native floats)
            cursor.execute(
                "INSERT INTO flights (filename, upload_date, max_altitude, max_velocity) VALUES (?, ?, ?, ?)",
                (uploaded_file.name, datetime.now().isoformat(), float(df["altitude"].max()), float(df["velocity"].max()))
            )
            flight_id = cursor.lastrowid
            for _, row in df.iterrows():
                assert flight_id is not None
                accel = float(row["acceleration"]) if "acceleration" in df.columns and pd.notna(row["acceleration"]) else None
                cursor.execute(
                    "INSERT INTO telemetry (flight_id, time, altitude, velocity, acceleration) VALUES (?, ?, ?, ?, ?)",
                    (int(flight_id), float(row["time"]), float(row["altitude"]), float(row["velocity"]), accel)
                )
            conn.commit()
            selected_id = flight_id
            flights = pd.read_sql_query("SELECT id, filename FROM flights", conn)

burnout = None
apogee = None
apogee_idx = None

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

        st.write(df.head())

        # Calculate burnout if acceleration data is available
        burnout = None
        if "acceleration" in df.columns:
            accel = np.asarray(df["acceleration"].values, dtype=float)
            # Burnout detected at maximum negative jerk (steepest drop in acceleration)
            # This is the transition from boost phase to coast phase
            jerk = np.diff(accel)
            burnout_idx = np.argmin(jerk)  # Index of maximum negative jerk
            if burnout_idx > 0 and jerk[burnout_idx] < -0.5:  # Ensure significant drop
                burnout = df["time"].iloc[burnout_idx]
        

        # Calculate apogee if altitude data is available
        if "altitude" in df.columns:
            # idxmax() returns the index label; keep it as-is for .loc
            apogee_idx = df["altitude"].idxmax()
            apogee = df["altitude"].max()
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df["time"], y=df["altitude"], mode="lines", name="Altitude"))
        fig.update_layout(title="Altitude vs Time", xaxis_title="Time", yaxis_title="Altitude")
        if burnout is not None:
            idx = (df["time"] - burnout).abs().idxmin()
            burnout_altitude = df.loc[idx, "altitude"]
            fig.add_trace(go.Scatter(x=[burnout], y=[burnout_altitude], mode="markers", name="Motor Burnout", marker=dict(size=12)))
        if apogee is not None:
            assert apogee_idx is not None
            apogee_time = df.loc[apogee_idx, "time"]
            fig.add_trace(go.Scatter(x=[apogee_time], y=[apogee], mode="markers", name="Apogee", marker=dict(size=12)))
        st.plotly_chart(fig)
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