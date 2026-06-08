import pandas as pd
import streamlit as st
import plotly.express as px
from pathlib import Path 
from datetime import datetime
import sqlite3

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
    velocity REAL
)
""")

conn.commit()

flights = pd.read_sql_query(
    "SELECT id, filename FROM flights",
    conn
)


st.title("FlightScope")
selected_id = None
if len(flights) > 0:
    selected_id = st.selectbox(
        "Choose Flight",
        flights["id"],
        format_func=lambda flight_id: flights.loc[flights["id"] == flight_id, "filename"].iloc[0],
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
                cursor.execute(
                    "INSERT INTO telemetry (flight_id, time, altitude, velocity) VALUES (?, ?, ?, ?)",
                    (int(flight_id), float(row["time"]), float(row["altitude"]), float(row["velocity"]))
                )
            conn.commit()
            selected_id = flight_id
            flights = pd.read_sql_query("SELECT id, filename FROM flights", conn)

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
        df[["time", "altitude", "velocity"]] = df[["time", "altitude", "velocity"]].astype(float)

        st.write(df.head())

        fig = px.line(df, x="time", y="altitude", title="Altitude vs Time")
        st.plotly_chart(fig)
else:
    st.info("No flight selected yet. Upload a CSV to see flight telemetry.")