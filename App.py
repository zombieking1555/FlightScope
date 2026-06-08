import pandas as pd
import streamlit as st
import pandas as pd
import plotly.express as px
from pathlib import Path 
from datetime import datetime
import sqlite3

conn = sqlite3.connect("flights.db")

files = list(Path("data").glob("*.csv"))


st.title("FlightScope")

selected = st.selectbox("Choose Flight", files, format_func=lambda x: x.stem)
uploaded_file = st.file_uploader("Choose a CSV file", type="csv")

if uploaded_file is not None:
    with open(Path("data") / uploaded_file.name, "wb") as f:
        f.write(uploaded_file.getbuffer())

df = pd.read_csv(selected)

st.write(df.head())

fig = px.line(
    df,
    x="time",
    y="altitude",
    title="Altitude vs Time"
)

st.metric(
    "Maximum Altitude",
    f"{df['altitude'].max():.1f} ft"
)

st.metric(
    "Maximum Velocity",
    f"{df['velocity'].max():.1f} ft/s"
)

st.plotly_chart(fig)