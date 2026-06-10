import pandas as pd
import streamlit as st
import plotly.express as px
from pathlib import Path 
from datetime import datetime
import sqlite3

conn = sqlite3.connect("flights.db")
cursor = conn.cursor()

st.title("FlightScope Database Manager")

flights = pd.read_sql_query("SELECT id, filename FROM flights ORDER BY id", conn)

if flights.empty:
    st.info("No uploaded flights found.")
else:
    st.write("### Uploaded Flights")
    for row in flights.itertuples(index=False):
        col_id, col_name, col_delete = st.columns([1, 4, 1])
        col_id.write(row.id)
        col_name.write(row.filename)

        delete_key = f"delete_flight_{row.id}"
        if col_delete.button("Delete", key=delete_key):
            cursor.execute("DELETE FROM telemetry WHERE flight_id = ?", (row.id,))
            cursor.execute("DELETE FROM flights WHERE id = ?", (row.id,))
            conn.commit()
            st.success(f"Deleted flight id {row.id}")
            st.rerun()
